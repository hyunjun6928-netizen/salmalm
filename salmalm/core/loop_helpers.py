"""Extracted helpers from IntelligenceEngine._execute_loop.

Breaks the god object into composable functions.
"""

import asyncio
import hashlib
import json
import logging
from collections import Counter

log = logging.getLogger("salmalm")


def check_abort(session_id: str) -> str | None:
    """Check if generation was aborted. Returns partial response or None."""
    from salmalm.features.edge_cases import abort_controller

    if abort_controller.is_aborted(session_id):
        partial = abort_controller.get_partial(session_id) or ""
        abort_controller.clear(session_id)
        return (partial + "\n\n⏹ [생성 중단됨 / Generation aborted]").strip()
    return None


def select_model(model_override, user_message, tier, iteration, router):
    """Select model based on override, tier, or router."""
    if model_override:
        return model_override
    model = router.route(user_message, has_tools=True, iteration=iteration)
    if tier == 3 and iteration == 0:
        model = router._pick_available(3)
    elif tier == 2 and iteration == 0:
        model = router._pick_available(2)
    return model


def trim_history(session, classification) -> None:
    """Aggressive history trim for simple intents."""
    _INTENT_HISTORY_LIMIT = {"chat": 10, "memory": 10, "creative": 20}
    _hist_limit = _INTENT_HISTORY_LIMIT.get(classification["intent"])
    if _hist_limit and len(session.messages) > _hist_limit:
        _sys = [m for m in session.messages if m.get("role") == "system"]
        _recent = [m for m in session.messages if m.get("role") != "system"][-_hist_limit:]
        session.messages = _sys + _recent


def prune_session_context(session, model: str):
    """Prune context if cache TTL expired."""
    from salmalm.core.engine import _should_prune_for_cache, estimate_context_window, prune_context

    if _should_prune_for_cache():
        _ctx_win = estimate_context_window(model)
        pruned, stats = prune_context(session.messages, context_window_tokens=_ctx_win)
        if stats["soft_trimmed"] or stats["hard_cleared"]:
            log.info(f"[PRUNE] soft={stats['soft_trimmed']} hard={stats['hard_cleared']}")
        return pruned
    return session.messages


def record_usage(session_id: str, model: str, result, classification, iteration) -> None:
    """Record API usage and audit log."""
    from salmalm.core.engine import record_response_usage, estimate_cost, audit_log

    usage = result.get("usage", {})
    record_response_usage(session_id, result.get("model", model), usage)

    api_detail = {
        "model": result.get("model", model),
        "input_tokens": usage.get("input", 0),
        "output_tokens": usage.get("output", 0),
        "iteration": iteration,
    }
    if usage.get("input", 0) or usage.get("output", 0):
        audit_log(
            "api_call",
            f"{model} in={usage.get('input', 0)} out={usage.get('output', 0)}",
            detail_dict=api_detail,
        )
        try:
            from salmalm.features.edge_cases import usage_tracker

            _inp, _out = usage.get("input", 0), usage.get("output", 0)
            _cost = estimate_cost(model, usage)
            usage_tracker.record(session_id, model, _inp, _out, _cost, classification.get("intent", ""))
        except Exception as _exc:
            log.debug(f"Suppressed: {_exc}")


def validate_tool_calls(tool_calls: list) -> tuple[list, dict]:
    """Validate and parse tool call arguments. Returns (valid_tools, error_outputs)."""
    valid_tools = []
    error_outputs = {}
    for tc in tool_calls:
        if not isinstance(tc.get("arguments"), dict):
            try:
                tc["arguments"] = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else {}
            except (json.JSONDecodeError, TypeError):
                error_outputs[tc["id"]] = f"❌ Invalid tool arguments for {tc['name']} / 잘못된 도구 인자"
                continue
        valid_tools.append(tc)
    return valid_tools, error_outputs


def check_circuit_breaker(tool_outputs: dict, consecutive_errors: int, max_errors: int) -> tuple[int, str | None]:
    """Check for consecutive tool errors. Returns (new_error_count, error_message_or_None)."""
    errors = sum(1 for v in tool_outputs.values() if str(v).startswith("❌"))
    if errors > 0:
        consecutive_errors += errors
        if consecutive_errors >= max_errors:
            log.warning(f"[BREAK] {consecutive_errors} consecutive tool errors — stopping loop")
            err_summary = "\n".join(f"• {v}" for v in tool_outputs.values() if str(v).startswith("❌"))
            return consecutive_errors, f"⚠️ Tool errors detected, stopping:\n{err_summary}"
        return consecutive_errors, None
    return 0, None


def check_loop_detection(tool_calls: list, recent_calls: list) -> str | None:
    """Detect infinite loops from repeated tool calls. Returns error message or None."""
    for tc in tool_calls:
        sig = (
            tc.get("name", ""),
            hashlib.md5(json.dumps(tc.get("arguments", {}), sort_keys=True).encode()).hexdigest()[:8],
        )
        recent_calls.append(sig)

    if len(recent_calls) >= 6:
        freq = Counter(recent_calls[-6:])
        top = freq.most_common(1)[0]
        if top[1] >= 3:
            log.warning(f"[BREAK] Loop detected: {top[0][0]} called {top[1]}x with same args in last 6 iterations")
            return f"⚠️ Infinite loop detected — tool `{top[0][0]}` repeating with same arguments. Stopping."
    return None


async def handle_empty_response(call_fn, pruned_messages, model: str, tools: list) -> str:
    """Retry empty responses up to 2 times with backoff."""
    for _retry in range(2):
        log.warning(f"[LLM] Empty response, retry #{_retry + 1}")
        await asyncio.sleep(0.5 * (_retry + 1))
        retry_result, _ = await call_fn(pruned_messages, model=model, tools=tools, max_tokens=4096, thinking=False)
        response = retry_result.get("content", "")
        if response and response.strip():
            return response
    return "⚠️ 응답을 생성할 수 없습니다. / Could not generate a response."


def finalize_response(result: dict, response: str) -> str:
    """Handle truncation and content filter edge cases."""
    stop_reason = result.get("stop_reason", "")
    if stop_reason == "max_tokens" or result.get("usage", {}).get("output", 0) >= 4090:
        response += "\n\n⚠️ [응답이 잘렸습니다 / Response was truncated]"
    if stop_reason in ("content_filter", "safety"):
        response = "⚠️ 안전 필터에 의해 응답이 차단되었습니다. / Response blocked by content filter."
    return response


def auto_log_conversation(user_message: str, response: str, classification: dict) -> None:
    """Auto-log significant conversations to daily memory."""
    try:
        # Skip trivial exchanges
        if not user_message or len(user_message) < 20:
            return
        intent = classification.get("intent", "")
        if intent in ("chat",) and len(response) < 100:
            return  # Skip short casual chat

        # Log code/search/action results and substantial conversations
        from salmalm.core import write_daily_log

        q_snippet = user_message[:150].replace("\n", " ")
        a_snippet = response[:200].replace("\n", " ")
        tag = f"[{intent}]" if intent else "[conv]"
        entry = f"{tag} Q: {q_snippet}\n  A: {a_snippet}"
        write_daily_log(entry)
    except Exception as e:  # noqa: broad-except
        pass  # Memory logging should never break the main flow
