"""Chat API endpoints — send, abort, regenerate, compare, edit, delete messages."""
import asyncio



from salmalm.security.crypto import vault, log
import json
from salmalm.core import router


class WebChatMixin:
    """Mixin providing chat route handlers."""
    def _post_api_chat(self):
        """Handle /api/chat and /api/chat/stream — main conversation endpoint."""
        from salmalm.core.engine import process_message

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
        use_stream = self.path.endswith("/stream")

        if use_stream:
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            def send_sse(event, data) -> None:
                try:
                    payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    self.wfile.write(payload.encode())
                    self.wfile.flush()
                except Exception as e:
                    log.debug(f"Suppressed: {e}")

            send_sse("status", {"text": "🤔 Thinking..."})
            tool_count = [0]

            def on_tool_sse(name, args) -> None:
                tool_count[0] += 1
                send_sse("tool", {"name": name, "args": str(args)[:200], "count": tool_count[0]})
                send_sse("status", {"text": f"🔧 Running {name}..."})

            streamed_text = [""]

            def on_token_sse(event) -> None:
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
                except Exception as e:
                    log.debug(f"Suppressed: {e}")

            try:
                loop = asyncio.new_event_loop()
                # Pass session-level model override to engine
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
                loop.close()
            except Exception as e:
                log.error(f"SSE process_message error: {e}")
                response = f"❌ Internal error: {type(e).__name__}"
            from salmalm.core import get_session as _gs2

            _sess2 = _gs2(session_id)
            try:
                from salmalm.tools.tools_ui import pop_pending_commands

                for cmd in pop_pending_commands():
                    send_sse("ui_cmd", cmd)
            except Exception as e:
                log.debug(f"Suppressed: {e}")
            send_sse(
                "done",
                {
                    "response": response,
                    "model": getattr(_sess2, "last_model", router.force_model or "auto"),
                    "complexity": getattr(_sess2, "last_complexity", "auto"),
                },
            )
            try:
                self.wfile.write(b"event: close\ndata: {}\n\n")
                self.wfile.flush()
            except Exception as e:
                log.debug(f"Suppressed: {e}")
        else:
            try:
                loop = asyncio.new_event_loop()
                # Pass session-level model override to engine
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
                loop.close()
            except Exception as e:
                log.error(f"Chat process_message error: {e}")
                response = f"❌ Internal error: {type(e).__name__}"
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

        try:
            loop = asyncio.new_event_loop()
            response = loop.run_until_complete(conversation_fork.regenerate(session_id, int(message_index)))
            loop.close()
            if response:
                self._json({"ok": True, "response": response})
            else:
                self._json({"ok": False, "error": "Could not regenerate"}, 400)
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:200]}, 500)
        return

    def _post_api_chat_compare(self):
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

        try:
            loop = asyncio.new_event_loop()
            results = loop.run_until_complete(compare_models(session_id, message, models or None))
            loop.close()
            self._json({"ok": True, "results": results})
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:200]}, 500)
        return

    def _post_api_alternatives_switch(self):
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

