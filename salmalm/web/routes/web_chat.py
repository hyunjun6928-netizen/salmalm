"""Chat API endpoints — send, abort, regenerate, compare, edit, delete messages."""

import asyncio
import threading
import time as _time

from salmalm.security.crypto import vault, log
import json
from salmalm.core import router

# ── SSE response idempotency cache ───────────────────────────────────────────
# Prevents duplicate processing when SSE stream fails and client falls back to
# HTTP POST with the same req_id.
# Format: { "req_id:session_id": {"response": str, "model": str, "complexity": str, "ts": float} }
_RESP_CACHE: dict = {}
_RESP_CACHE_TTL = 300  # 5 minutes — enough to cover any SSE→HTTP fallback window


def _get_cached_response(req_id: str, session_id: str, wait_if_processing: bool = False) -> dict | None:
    """Return cached response dict for req_id+session or None if not found / expired.

    If wait_if_processing=True and entry has status='processing', polls up to 12s
    for the SSE path to finish before returning. Prevents HTTP fallback double-processing
    when SSE stall fires but server hasn't aborted yet.
    """
    if not req_id:
        return None
    key = f"{req_id}:{session_id}"

    # If processing: optionally wait for completion
    if wait_if_processing:
        for _ in range(24):  # 24 × 0.5s = 12s max wait
            entry = _RESP_CACHE.get(key)
            if not entry:
                break
            if entry.get("status") == "done":
                log.info(f"[IDEMPOTENCY] Cache hit (waited) for req_id={req_id[:12]}…")
                return entry
            if _time.time() - entry["ts"] > _RESP_CACHE_TTL:
                break
            _time.sleep(0.5)

    entry = _RESP_CACHE.get(key)
    if not entry:
        return None
    if _time.time() - entry["ts"] >= _RESP_CACHE_TTL:
        del _RESP_CACHE[key]
        return None
    if entry.get("status") == "processing":
        return None  # Still running — fall through to HTTP POST path
    log.info(f"[IDEMPOTENCY] Cache hit for req_id={req_id[:12]}… — skipping re-process")
    return entry


def _mark_processing(req_id: str, session_id: str) -> None:
    """Mark a request as in-progress at SSE start.
    Prevents HTTP fallback from reprocessing while SSE engine is still running.
    """
    if not req_id:
        return
    _RESP_CACHE[f"{req_id}:{session_id}"] = {"status": "processing", "ts": _time.time()}


def _cache_response(req_id: str, session_id: str, response: str, model: str, complexity: str) -> None:
    """Cache completed SSE response for idempotency. Prunes expired entries."""
    if not req_id:
        return
    key = f"{req_id}:{session_id}"
    _RESP_CACHE[key] = {
        "status": "done",
        "response": response, "model": model, "complexity": complexity,
        "ts": _time.time(),
    }
    now = _time.time()
    expired = [k for k, v in list(_RESP_CACHE.items()) if now - v["ts"] > _RESP_CACHE_TTL]
    for k in expired:
        _RESP_CACHE.pop(k, None)


class WebChatMixin:
    """Mixin providing chat route handlers."""

    def _post_api_chat(self):
        """Handle /api/chat and /api/chat/stream — main conversation endpoint."""
        from salmalm.core.engine_pipeline import process_message

        body = self._body
        self._auto_unlock_localhost()
        if not vault.is_unlocked:
            self._json({"error": "Vault locked"}, 403)
            return
        message = body.get("message", "")
        session_id = body.get("session", "web")
        image_b64 = body.get("image_base64")
        image_mime = body.get("image_mime", "image/png")
        ui_lang = body.get("lang", "")
        req_id = body.get("req_id", "")  # idempotency key (generated per-send by client)
        use_stream = self.path.endswith("/stream")

        # Input message length cap: prevents context explosion from very large pastes
        # OpenClaw pattern: bootstrapMaxChars per-file cap; we apply same idea to user messages
        _MAX_MSG_CHARS = 50_000  # ~12,500 tokens — a reasonable ceiling
        if len(message) > _MAX_MSG_CHARS:
            log.warning(f"[INPUT] Message too large ({len(message):,} chars) — truncating to {_MAX_MSG_CHARS:,}")
            message = (
                message[:_MAX_MSG_CHARS]
                + f"\n\n⚠️ **[Message truncated at {_MAX_MSG_CHARS:,} chars]** "
                f"Original was {len(message):,} chars. "
                f"For large content, use file upload instead."
            )

        if use_stream:
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            # Mark request as processing immediately — HTTP fallback will wait/skip
            _mark_processing(req_id, session_id)

            # Fix #2: track client disconnect state
            _client_disconnected = [False]
            # Fix #3: keepalive thread control
            _keepalive_stop = [False]

            def send_sse(event, data: dict) -> bool:
                """Send SSE event. Returns False if client disconnected."""
                if _client_disconnected[0]:
                    return False
                try:
                    payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    self.wfile.write(payload.encode())
                    self.wfile.flush()
                    return True
                except (BrokenPipeError, ConnectionResetError, OSError) as e:
                    # Fix #2: client disconnected — signal abort so engine stops
                    log.info(f"[SSE] Client disconnected: {type(e).__name__}")
                    _client_disconnected[0] = True
                    try:
                        from salmalm.features.edge_cases import abort_controller
                        abort_controller.set_abort(session_id)
                    except Exception as e:
                        log.debug(f"[SSE] abort_controller unavailable: {e}")
                    return False
                except Exception as e:
                    log.debug(f"[SSE] send error: {e}")
                    _client_disconnected[0] = True
                    return False

            # Fix #3: keepalive ping thread — prevents proxy/nginx 60s idle timeout
            def _keepalive_worker():
                import time
                while not _keepalive_stop[0]:
                    time.sleep(15)
                    if _keepalive_stop[0]:
                        break
                    try:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                    except Exception:
                        break

            _ka_thread = threading.Thread(target=_keepalive_worker, daemon=True)
            _ka_thread.start()

            send_sse("status", {"text": "🤔 Thinking..."})
            tool_count = [0]

            def on_tool_sse(name: str, args) -> None:
                """On tool sse."""
                if _client_disconnected[0]:
                    return
                tool_count[0] += 1
                # Fix #5: use "input" key (client checks edata.input, not edata.args)
                send_sse("tool", {"name": name, "input": str(args)[:200], "count": tool_count[0]})
                send_sse("status", {"text": f"🔧 Running {name}..."})

            streamed_text = [""]

            def on_token_sse(event) -> None:
                """On token sse."""
                # Fix #2: stop generating if client is gone
                if _client_disconnected[0]:
                    raise RuntimeError("[SSE] Client disconnected — aborting generation")
                try:
                    etype = event.get("type", "")
                    if etype == "text_delta":
                        text = event.get("text", "")
                        if text:
                            streamed_text[0] += text
                            send_sse("chunk", {"text": text, "streaming": True})
                    elif etype == "thinking_delta":
                        send_sse("thinking", {"text": event.get("text", "")})
                    elif etype == "tool_use_start":
                        tool_count[0] += 1
                        send_sse("status", {"text": f"🔧 Running {event.get('name', 'tool')}..."})
                        send_sse("tool", {"name": event.get("name", ""), "count": tool_count[0]})
                    elif etype == "error":
                        send_sse("error", {"text": event.get("error", "")})
                except RuntimeError:
                    raise  # propagate disconnect signal
                except Exception as e:
                    log.debug(f"[SSE] on_token error: {e}")

            # Fix #1: always close loop via try/finally
            loop = asyncio.new_event_loop()
            try:
                from salmalm.core import get_session as _gs_pre

                _sess_pre = _gs_pre(session_id)
                _model_ov = getattr(_sess_pre, "model_override", None)
                if _model_ov == "auto":
                    _model_ov = None
                response = loop.run_until_complete(
                    process_message(
                        session_id,
                        message,
                        model_override=_model_ov,
                        image_data=(image_b64, image_mime) if image_b64 else None,
                        on_tool=on_tool_sse,
                        on_token=on_token_sse,
                        lang=ui_lang,
                    )
                )
            except Exception as e:
                log.error(f"[SSE] process_message error: {e}")
                response = f"❌ Internal error: {type(e).__name__}"
            finally:
                loop.close()  # Fix #1: always close loop
                _keepalive_stop[0] = True  # Fix #3: stop keepalive thread

            # If client disconnected mid-stream, nothing to send
            if _client_disconnected[0]:
                log.info(f"[SSE] Skipping done event — client already disconnected")
                return

            from salmalm.core import get_session as _gs2

            _sess2 = _gs2(session_id)
            try:
                from salmalm.tools.tools_ui import pop_pending_commands

                for cmd in pop_pending_commands():
                    send_sse("ui_cmd", cmd)
            except Exception as e:
                log.debug(f"Suppressed: {e}")
            _done_model = getattr(_sess2, "last_model", router.force_model or "auto")
            _done_complexity = getattr(_sess2, "last_complexity", "auto")
            # Cache response for idempotency (SSE fallback → HTTP POST dedup)
            _cache_response(req_id, session_id, response, _done_model, _done_complexity)
            try:
                send_sse(
                    "done",
                    {
                        "response": response,
                        "model": _done_model,
                        "complexity": _done_complexity,
                    },
                )
                log.info(f"[SSE] Done event sent ({len(response)} chars)")
            except Exception as done_err:
                log.error(f"[SSE] Failed to send done event: {done_err}")
        else:
            # Idempotency check: if SSE already processed this req_id, return cached response.
            # wait_if_processing=True: if SSE marked "processing", poll up to 12s for completion.
            # This handles the race where stall timer fires before server finishes generating.
            _cached = _get_cached_response(req_id, session_id, wait_if_processing=True)
            if _cached:
                self._json({
                    "response": _cached["response"],
                    "model": _cached["model"],
                    "complexity": _cached["complexity"],
                    "from_cache": True,
                })
                return

            # Fix #1: always close loop via try/finally (non-stream path)
            loop = asyncio.new_event_loop()
            try:
                from salmalm.core import get_session as _gs_pre2

                _sess_pre2 = _gs_pre2(session_id)
                _model_ov2 = getattr(_sess_pre2, "model_override", None)
                if _model_ov2 == "auto":
                    _model_ov2 = None
                response = loop.run_until_complete(
                    process_message(
                        session_id,
                        message,
                        model_override=_model_ov2,
                        image_data=(image_b64, image_mime) if image_b64 else None,
                        lang=ui_lang,
                    )
                )
            except Exception as e:
                log.error(f"[Chat] process_message error: {e}")
                response = f"❌ Internal error: {type(e).__name__}"
            finally:
                loop.close()
            from salmalm.core import get_session as _gs

            _sess = _gs(session_id)
            self._json(
                {
                    "response": response,
                    "model": getattr(_sess, "last_model", router.force_model or "auto"),
                    "complexity": getattr(_sess, "last_complexity", "auto"),
                }
            )

    def _post_api_chat_abort(self):
        """Post api chat abort."""
        body = self._body
        # Abort generation — LibreChat style (생성 중지)
        if not self._require_auth("user"):
            return
        session_id = body.get("session", body.get("session_id", "web"))
        from salmalm.features.edge_cases import abort_controller

        abort_controller.set_abort(session_id)
        self._json({"ok": True, "message": "Abort signal sent / 중단 신호 전송됨"})
        return

    def _post_api_chat_regenerate(self):
        """Post api chat regenerate."""
        body = self._body
        # Regenerate response — LibreChat style (응답 재생성)
        if not self._require_auth("user"):
            return
        session_id = body.get("session_id", "web")
        message_index = body.get("message_index")
        if message_index is None:
            self._json({"error": "Missing message_index"}, 400)
            return
        from salmalm.features.edge_cases import conversation_fork

        loop = asyncio.new_event_loop()
        try:
            response = loop.run_until_complete(conversation_fork.regenerate(session_id, int(message_index)))
            if response:
                self._json({"ok": True, "response": response})
            else:
                self._json({"ok": False, "error": "Could not regenerate"}, 400)
        except Exception as e:
            self._json({"ok": False, "error": "Internal server error"}, 500)
        finally:
            loop.close()
        return

    def _post_api_chat_compare(self):
        """Post api chat compare."""
        body = self._body
        # Compare models — BIG-AGI style (응답 비교)
        if not self._require_auth("user"):
            return
        message = body.get("message", "")
        models = body.get("models", [])
        session_id = body.get("session_id", "web")
        if not message:
            self._json({"error": "Missing message"}, 400)
            return
        from salmalm.features.edge_cases import compare_models

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(compare_models(session_id, message, models or None))
            self._json({"ok": True, "results": results})
        except Exception as e:
            self._json({"ok": False, "error": "Internal server error"}, 500)
        finally:
            loop.close()
        return

    def _post_api_alternatives_switch(self):
        """Post api alternatives switch."""
        body = self._body
        # Switch alternative — LibreChat style (대안 전환)
        if not self._require_auth("user"):
            return
        session_id = body.get("session_id", "")
        message_index = body.get("message_index")
        alt_id = body.get("alt_id")
        if not all([session_id, message_index is not None, alt_id]):
            self._json({"error": "Missing parameters"}, 400)
            return
        from salmalm.features.edge_cases import conversation_fork

        content = conversation_fork.switch_alternative(session_id, int(message_index), int(alt_id))
        if content:
            # Update session messages
            from salmalm.core import get_session

            session = get_session(session_id)
            ua = [(i, m) for i, m in enumerate(session.messages) if m.get("role") in ("user", "assistant")]
            if int(message_index) < len(ua):
                real_idx = ua[int(message_index)][0]
                session.messages[real_idx] = {
                    "role": "assistant",
                    "content": content,
                }
                session._persist()
            self._json({"ok": True, "content": content})
        else:
            self._json({"ok": False, "error": "Alternative not found"}, 404)
        return

    def _post_api_messages_edit(self):
        """Post api messages edit."""
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        idx = body.get("message_index")
        content = body.get("content", "")
        if not sid or idx is None or not content:
            self._json(
                {
                    "ok": False,
                    "error": "Missing session_id, message_index, or content",
                },
                400,
            )
            return
        from salmalm.core import edit_message

        result = edit_message(sid, int(idx), content)
        self._json(result)

    def _post_api_messages_delete(self):
        """Post api messages delete."""
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        idx = body.get("message_index")
        if not sid or idx is None:
            self._json({"ok": False, "error": "Missing session_id or message_index"}, 400)
            return
        from salmalm.core import delete_message

        result = delete_message(sid, int(idx))
        self._json(result)
