"""Engine message processing pipeline."""

import logging
import time
from typing import Optional, Tuple, Any, Callable

import threading as _threading

log = logging.getLogger(__name__)

_shutting_down = False
_active_requests = 0
_active_requests_lock = _threading.Lock()
_active_requests_event = _threading.Event()

# Per-session concurrency guard — prevents overlapping requests on same session
_session_locks: dict = {}  # session_id → threading.Lock
_session_locks_lock = _threading.Lock()

import re as _re


def _get_thinking_budget_map():
    """Lazy import to avoid circular dependency."""
    from salmalm.core.engine import _THINKING_BUDGET_MAP

    return _THINKING_BUDGET_MAP


_MAX_MESSAGE_LENGTH = 100_000
_SESSION_ID_RE = _re.compile(r"^[a-zA-Z0-9_\-\.]+$")


# Lazy imports to break circular deps — resolved at call time
def _get_engine_deps():
    """Import engine dependencies lazily."""

    return locals()


def _sanitize_input(text: str) -> str:
    """Strip null bytes and control characters. Keeps newlines/tabs and Unicode (ord > 127) for i18n support."""
    # Keep printable ASCII (32+) and all Unicode; strip control chars except \n \t \r
    return "".join(c for c in text if c == "\n" or c == "\t" or c == "\r" or ord(c) >= 32)


async def process_message(
    session_id: str,
    user_message: str,
    model_override: Optional[str] = None,
    image_data: Optional[Tuple[str, str]] = None,
    on_tool: Optional[Callable[[str, Any], None]] = None,
    on_token: Optional[Callable] = None,
    on_status: Optional[Callable] = None,
    lang: Optional[str] = None,
) -> str:
    """Process a user message through the Intelligence Engine pipeline.

    Edge cases:
    - Shutdown rejection
    - Unhandled exceptions → graceful error message
    """
    # Event loop reference is now obtained dynamically via _get_event_loop()
    # Reject new requests during shutdown
    if _shutting_down:
        return "⚠️ Server is shutting down. Please try again later. / 서버가 종료 중입니다."

    # Per-session lock: if previous request still running, abort it and wait
    with _session_locks_lock:
        if session_id not in _session_locks:
            _session_locks[session_id] = _threading.Lock()
        sess_lock = _session_locks[session_id]

    if not sess_lock.acquire(blocking=False):
        # Previous request still running — send abort signal and wait
        from salmalm.features.abort import abort_controller
        abort_controller.set_abort(session_id)
        log.info(f"[ENGINE] Session {session_id} busy — aborting previous and waiting")
        acquired = sess_lock.acquire(timeout=15.0)
        if not acquired:
            log.warning(f"[ENGINE] Session {session_id} lock timeout — proceeding anyway")

    with _active_requests_lock:
        global _active_requests
        _active_requests += 1
        _active_requests_event.clear()

    try:
        return await _process_message_inner(
            session_id,
            user_message,
            model_override=model_override,
            image_data=image_data,
            on_tool=on_tool,
            on_token=on_token,
            on_status=on_status,
            lang=lang,
        )
    except Exception as e:
        log.error(f"[ENGINE] Unhandled error: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return f"❌ Internal error / 내부 오류: {type(e).__name__}. Please try again."
    finally:
        with _active_requests_lock:
            _active_requests -= 1
            if _active_requests == 0:
                _active_requests_event.set()
        try:
            sess_lock.release()
        except RuntimeError:
            pass  # Already released


def _classify_task(session, user_message: str) -> dict:
    """Classify task and apply thinking settings."""
    from salmalm.core.classifier import TaskClassifier

    classification = TaskClassifier.classify(user_message, len(session.messages))
    thinking_on = getattr(session, "thinking_enabled", False)
    classification["thinking"] = thinking_on
    level = getattr(session, "thinking_level", "medium") if thinking_on else None
    classification["thinking_level"] = level
    classification["thinking_budget"] = _get_thinking_budget_map().get(level or "medium", 10000) if thinking_on else 0

    if not thinking_on and classification["tier"] >= 3 and classification["score"] >= 4:
        if not getattr(session, "_thinking_suggested", False):
            session._thinking_suggested = True
            session._thinking_hint = (
                "\n\n💡 *이 작업은 복잡해 보입니다. 🧠 Extended Thinking을 켜면 더 정확한 결과를 얻을 수 있습니다.* "
                "`/thinking on` 또는 🧠 버튼을 눌러주세요."
                "\n💡 *This looks complex. Enable 🧠 Extended Thinking for better results.* "
                "Use `/thinking on` or the 🧠 button."
            )
    return classification


def _route_model(model_override, user_message: str, session) -> tuple:
    """Select model via routing or override. Returns (model, complexity).

    .. deprecated:: Thin wrapper — all routing logic lives in
       :mod:`salmalm.core.model_selection`.  Prefer calling
       ``model_selection.select_model`` directly for new code.
    """
    from salmalm.core.model_selection import select_model as _select_model, fix_model_name as _fix_model_name
    from salmalm.constants import MODEL_ALIASES as _ALIASES

    if model_override:
        # Resolve short aliases (sonnet → anthropic/claude-sonnet-4-6, etc.)
        resolved = _ALIASES.get(model_override, model_override)
        return _fix_model_name(resolved), "auto"
    selected, complexity = _select_model(user_message, session)
    log.info(f"[ROUTE] Multi-model: {complexity} → {selected}")
    return _fix_model_name(selected), complexity


def _prepare_context(session, user_message: str, lang, on_status) -> None:
    """Prepare session context: language, compaction, RAG, mood, self-evolve."""
    from salmalm.core.compaction import compact_messages
    from salmalm.core.prompt import build_system_prompt

    if lang and lang in ("en", "ko"):
        lang_directive = "Respond in English." if lang == "en" else "한국어로 응답하세요."
        session.messages.append({"role": "system", "content": f"[Language: {lang_directive}]"})

    session.messages = compact_messages(session.messages, session=session, on_status=on_status)
    if len(session.messages) % 20 == 0:
        session.add_system(build_system_prompt(full=False))

    try:
        from salmalm.features.rag import inject_rag_context

        for i, m in enumerate(session.messages):
            if m.get("role") == "system":
                session.messages[i] = dict(m)
                session.messages[i]["content"] = inject_rag_context(session.messages, m["content"], max_chars=2500)
                break
    except Exception as e:
        log.warning(f"RAG injection skipped: {e}")

    # Auto-recall: inject relevant memory context (OpenClaw-style)
    try:
        from salmalm.core.memory import memory_manager

        recall = memory_manager.auto_recall(user_message)
        if recall:
            session.messages.append({"role": "system", "content": recall})
    except Exception as _recall_err:
        log.debug(f"[PIPELINE] auto_recall skipped: {_recall_err}")

    try:
        from salmalm.features.mood import mood_detector

        if mood_detector.enabled:
            _detected_mood, _mood_conf = mood_detector.detect(user_message)
            if _detected_mood != "neutral" and _mood_conf > 0.3:
                _tone_hint = mood_detector.get_tone_injection(_detected_mood)
                if _tone_hint:
                    for i, m in enumerate(session.messages):
                        if m.get("role") == "system":
                            session.messages[i] = dict(m)
                            session.messages[i]["content"] = (
                                m["content"] + f"\n\n[감정 감지: {_detected_mood}] {_tone_hint}"
                            )
                            break
                mood_detector.record_mood(_detected_mood, _mood_conf)
    except Exception as _mood_err:
        log.debug(f"Mood detection skipped: {_mood_err}")

    try:
        from salmalm.features.self_evolve import prompt_evolver

        if len(session.messages) > 4 and len(session.messages) % 10 == 0:
            prompt_evolver.record_conversation(session.messages)
    except Exception as _exc:
        log.debug(f"Suppressed: {_exc}")


def _record_sla(sla_start: float, first_token_time: float, model: str, session_id: str) -> None:
    """Record SLA latency metrics."""
    try:
        from salmalm.features.sla import latency_tracker, sla_config as _sla_cfg

        sla_end = time.time()
        ttft_ms = (first_token_time - sla_start) * 1000 if first_token_time > 0 else (sla_end - sla_start) * 1000
        total_ms = (sla_end - sla_start) * 1000
        timed_out = total_ms > _sla_cfg.get("response_target_ms", 30000)
        latency_tracker.record(
            ttft_ms=ttft_ms, total_ms=total_ms, model=model or "auto", timed_out=timed_out, session_id=session_id
        )
        if latency_tracker.should_failover():
            log.warning("[SLA] Consecutive timeout threshold reached — failover recommended")
            latency_tracker.reset_timeout_counter()
    except Exception as e:
        log.debug(f"[SLA] Latency tracking error: {e}")


def _post_process(session, session_id: str, user_message: str, response: str, classification: dict) -> str:
    """Post-process: auto-title, notification, hooks, thinking hint."""
    try:
        user_msgs = [m for m in session.messages if m.get("role") == "user" and isinstance(m.get("content"), str)]
        assistant_msgs = [m for m in session.messages if m.get("role") == "assistant"]
        if len(assistant_msgs) == 1 and user_msgs:
            from salmalm.core import auto_title_session

            auto_title_session(session_id, user_msgs[0]["content"])
    except Exception as e:
        log.warning(f"Auto-title hook error: {e}")

    try:
        _notify_completion(session_id, user_message, response, classification)
    except Exception as e:
        log.error(f"Notification hook error: {e}")

    try:
        from salmalm.features.hooks import hook_manager

        hook_manager.fire("on_response", {"session_id": session_id, "message": response})
    except Exception as _exc:
        log.debug(f"Suppressed: {_exc}")

    _hint = getattr(session, "_thinking_hint", None)
    if _hint:
        response = response + _hint
        del session._thinking_hint
    return response


async def _process_message_inner(
    session_id: str,
    user_message: str,
    model_override: Optional[str] = None,
    image_data: Optional[Tuple[str, str]] = None,
    on_tool: Optional[Callable[[str, Any], None]] = None,
    on_token: Optional[Callable] = None,
    on_status: Optional[Callable] = None,
    lang: Optional[str] = None,
) -> str:
    """Inner implementation of process_message."""
    from salmalm.core.engine import _engine  # singleton

    # Input sanitization
    if not _SESSION_ID_RE.match(session_id):
        return "❌ Invalid session ID format (alphanumeric and hyphens only)."
    if len(user_message) > _MAX_MESSAGE_LENGTH:
        return f"❌ Message too long ({len(user_message)} chars). Maximum is {_MAX_MESSAGE_LENGTH}."
    user_message = _sanitize_input(user_message)

    from salmalm.core.session_store import get_session

    session = get_session(session_id)

    # Set user context for cost tracking (multi-tenant)
    from salmalm.core import set_current_user_id

    set_current_user_id(session.user_id)

    # Multi-tenant quota check
    if session.user_id:
        try:
            from salmalm.features.users import user_manager, QuotaExceeded

            user_manager.check_quota(session.user_id)
        except QuotaExceeded as e:
            return f"⚠️ {e.message}"

    # Fire on_message hook (메시지 수신 훅)
    try:
        from salmalm.features.hooks import hook_manager

        hook_manager.fire("on_message", {"session_id": session_id, "message": user_message})
    except Exception as _exc:
        log.debug(f"Suppressed: {_exc}")

    # --- Slash commands (fast path, no LLM) ---
    cmd = user_message.strip()
    from salmalm.core.slash_commands import _dispatch_slash_command

    slash_result = await _dispatch_slash_command(cmd, session, session_id, model_override, on_tool)
    if slash_result is not None:
        return slash_result

    # --- Normal message processing ---
    if not user_message.strip() and not image_data:
        return "Please enter a message."

    if image_data:
        b64, mime = image_data
        log.info(f"[IMG] Image attached: {mime}, {len(b64) // 1024}KB base64")
        # Auto-resize for token savings
        from salmalm.core.image_resize import resize_image_b64

        b64, mime = resize_image_b64(b64, mime)
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
            {"type": "text", "text": user_message or "Analyze this image."},
        ]
        session.messages.append({"role": "user", "content": content})
    else:
        # Deduplication guard: if the last message is already this user message
        # (e.g., SSE path added it before aborting, HTTP fallback is now retrying),
        # don't add it again to prevent duplicate messages in session history.
        _last = session.messages[-1] if session.messages else {}
        _already_added = (
            _last.get("role") == "user"
            and isinstance(_last.get("content"), str)
            and _last.get("content") == user_message
        )
        if not _already_added:
            session.add_user(user_message)
        else:
            log.info("[ENGINE] Dedup: user message already in session — skipping add_user (SSE fallback)")

    _prepare_context(session, user_message, lang, on_status)

    classification = _classify_task(session, user_message)
    selected_model, complexity = _route_model(model_override, user_message, session)

    # ── SLA: Measure latency (레이턴시 측정) + abort token accumulation ──
    _sla_start = time.time()
    _sla_first_token_time = [0.0]  # mutable for closure
    _orig_on_token = on_token

    # Start streaming accumulator for abort recovery
    from salmalm.features.abort import abort_controller as _abort_ctl

    _abort_ctl.start_streaming(session_id)

    def _sla_on_token(event) -> None:
        """Sla on token."""
        if _sla_first_token_time[0] == 0.0:
            _sla_first_token_time[0] = time.time()
        # Accumulate tokens for abort recovery
        if isinstance(event, dict):
            delta = event.get("delta", {})
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                _abort_ctl.accumulate_token(session_id, delta.get("text", ""))
            elif event.get("type") == "text" and event.get("text"):
                _abort_ctl.accumulate_token(session_id, event["text"])
        if _orig_on_token:
            _orig_on_token(event)

    response = await _engine.run(
        session,
        user_message,
        model_override=selected_model,
        on_tool=on_tool,
        classification=classification,
        on_token=_sla_on_token,
        on_status=on_status,
    )

    _record_sla(_sla_start, _sla_first_token_time[0], selected_model, session_id)
    session.last_model = selected_model or "auto"
    session.last_complexity = complexity
    response = _post_process(session, session_id, user_message, response, classification)
    return response


def _notify_completion(session_id: str, user_message: str, response: str, classification: dict) -> None:
    """Send completion notifications to Telegram + Web chat."""
    from salmalm.core import _tg_bot
    from salmalm.security.crypto import vault

    # Only notify for complex tasks (tier 3 or high-score tool-using)
    tier = classification.get("tier", 1)
    intent = classification.get("intent", "chat")
    score = classification.get("score", 0)
    if tier < 3 and score < 3:
        return  # Skip simple/medium tasks — avoid notification spam

    # Build summary
    task_preview = user_message[:80] + ("..." if len(user_message) > 80 else "")
    resp_preview = response[:150] + ("..." if len(response) > 150 else "")
    notify_text = f"✅ Task completed [{intent}]\n📝 Request: {task_preview}\n💬 Result: {resp_preview}"

    # Telegram notification (if task came from web)
    if session_id != "telegram" and _tg_bot and _tg_bot.token:
        owner_id = vault.get("telegram_owner_id") if vault.is_unlocked else None
        if owner_id:
            try:
                _tg_bot.send_message(owner_id, f"🔔 SalmAlm webchat Task completed\n{notify_text}")
            except Exception as e:
                log.error(f"TG notify error: {e}")

    # Web notification (if task came from telegram)
    if session_id == "telegram":
        # Store notification for web polling
        from salmalm.core import _sessions  # noqa: F811

        web_session = _sessions.get("web")
        if web_session:
            if not hasattr(web_session, "_notifications"):
                web_session._notifications = []  # type: ignore[attr-defined]
            web_session._notifications.append(
                {  # type: ignore[attr-defined]
                    "time": __import__("time").time(),
                    "text": f"🔔 SalmAlm telegram Task completed\n{notify_text}",
                }
            )
            # Keep max 20 notifications
            web_session._notifications = web_session._notifications[-20:]  # type: ignore[attr-defined]


def begin_shutdown() -> None:
    """Signal the engine to stop accepting new requests."""
    global _shutting_down
    _shutting_down = True
    log.info("[SHUTDOWN] Engine: rejecting new requests")


def wait_for_active_requests(timeout: float = 30.0) -> bool:
    """Wait for active requests to complete. Returns True if all done, False if timed out."""
    with _active_requests_lock:
        if _active_requests == 0:
            return True
    log.info(f"[SHUTDOWN] Waiting for {_active_requests} active request(s) (timeout={timeout}s)")
    return _active_requests_event.wait(timeout=timeout)
