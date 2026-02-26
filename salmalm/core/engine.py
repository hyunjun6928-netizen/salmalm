"""SalmAlm Intelligence Engine — TaskClassifier + IntelligenceEngine + process_message.

Re-exports from submodules for backward compatibility. Consumers may import
directly from the original modules (e.g. salmalm.core.model_selection) instead.
"""

from __future__ import annotations

import asyncio
import json as _json
import os as _os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from salmalm.constants import (  # noqa: F401
    VERSION,
    INTENT_SHORT_MSG,
    INTENT_COMPLEX_MSG,  # noqa: F401
    INTENT_CONTEXT_DEPTH,
    REFLECT_SNIPPET_LEN,
    MODEL_ALIASES as _CONST_ALIASES,
    COMMAND_MODEL,
    THINKING_BUDGET_MAP as _THINKING_BUDGET_MAP_CONST,
)  # noqa: F401
import re as _re
import time as _time
from salmalm.security.crypto import log
from salmalm.core.engine_pipeline import (  # noqa: F401
    process_message,
    _process_message_inner,
    _notify_completion,
    begin_shutdown,
    wait_for_active_requests,
)
from salmalm.core.cost import (  # noqa: F401
    estimate_tokens,
    estimate_cost,
    MODEL_PRICING,
    get_pricing as _get_pricing,
)

# Graceful shutdown state
from salmalm.core import (  # noqa: F401
    router,
    compact_messages,
    get_session,
    _sessions,
    _metrics,
    compact_session,
    auto_compact_if_needed,
    audit_log,
)  # noqa: F401
from salmalm.tools.tool_handlers import execute_tool

# ── Imports from extracted modules ──
from salmalm.core.session_manager import (  # noqa: F401
    _should_prune_for_cache,
    _record_api_call_time,
    prune_context,
    _has_image_block,
    _soft_trim,
    estimate_context_window,
    _PRUNE_KEEP_LAST_ASSISTANTS,
    _PRUNE_SOFT_LIMIT,
    _PRUNE_HARD_LIMIT,
    _PRUNE_HEAD,
)
from salmalm.core.llm_loop import (  # noqa: F401
    _call_llm_async,
    _call_llm_streaming,
    _load_failover_config,
    _load_cooldowns,
    _save_cooldowns,
    _is_model_cooled_down,
    _record_model_failure,
    _clear_model_cooldown,
    get_failover_config,
    save_failover_config,
    call_with_failover as _call_with_failover_fn,
    try_llm_call as _try_llm_call_fn,
    STATUS_TYPING,
    STATUS_THINKING,
    STATUS_TOOL_RUNNING,
)

# Keep _PRUNE_TAIL for backward compat
_PRUNE_TAIL = 500

# ============================================================
# Model aliases — sourced from constants.py (single source of truth)
MODEL_ALIASES = {"auto": None, **_CONST_ALIASES}

# Multi-model routing: cost-optimized model selection
# ── Model selection (extracted to core/model_selection.py) ──
from salmalm.core.model_selection import (  # noqa: F401
    select_model as _select_model_impl,
    fix_model_name as _fix_model_name,
    load_routing_config as _load_routing_config,
    save_routing_config as _save_routing_config,
    _SIMPLE_PATTERNS,
    _MODERATE_KEYWORDS,
    _COMPLEX_KEYWORDS,
    _MODEL_NAME_FIXES,
)

# Backward-compat re-exports
get_routing_config = _load_routing_config


# _select_model delegates to core/model_selection.py (backward compat)
_select_model = _select_model_impl


# ── User-friendly error messages (extracted to core/error_messages.py) ──
from salmalm.core.error_messages import friendly_error as _friendly_error


def _get_event_loop() -> asyncio.AbstractEventLoop:
    """Get the running event loop safely (no stale global reference)."""
    try:
        loop = asyncio.get_running_loop()
        return loop if loop.is_running() else None
    except RuntimeError:
        return None


def _safe_callback(cb, *args) -> None:
    """Call a callback that may be sync or async. Fire-and-forget for async.

    Works from both async context and sync threads (e.g. ThreadPoolExecutor).
    Uses run_coroutine_threadsafe when no running loop in current thread.
    """
    if cb is None:
        return
    result = cb(*args)
    if asyncio.iscoroutine(result):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(result)
        except RuntimeError:
            # We're in a sync thread — schedule on the main loop
            _loop = _get_event_loop()
            if _loop:
                asyncio.run_coroutine_threadsafe(result, _loop)
            else:
                log.warning("[ENGINE] Dropping coroutine callback — no event loop available (data loss possible)")
                result.close()


from salmalm.core.classifier import (  # noqa: F401
    TaskClassifier,
    INTENT_TOOLS,
    _KEYWORD_TOOLS,
    INTENT_MAX_TOKENS,
    _DETAIL_KEYWORDS,
    _get_dynamic_max_tokens,
)


class IntelligenceEngine:
    """Core AI reasoning engine.

    Architecture:
    1. CLASSIFY — Determine task type, complexity, required resources
    2. PLAN — For complex tasks, generate execution plan before acting (opt-in)
    3. EXECUTE — Tool loop with parallel execution and circuit-breaker
    4. REFLECT — Self-evaluate response quality, retry if insufficient (opt-in)
    """

    # Planning prompt — injected before complex tasks
    # Engine-internal prompts (opt-in via SALMALM_PLANNING=1 / SALMALM_REFLECT=1)
    PLAN_PROMPT = """Before answering, briefly plan your approach:
1. What is the user asking? (one sentence)
2. What tools/steps are needed? (bullet list)
3. What could go wrong? (potential issues)
4. Expected output format?
Then execute the plan."""

    # Reflection prompt — used to evaluate response quality
    REFLECT_PROMPT = """Evaluate your response:
- Did it fully answer the question?
- Are there errors or hallucinations?
- Is the code correct (if any)?
- Could the answer be improved?
If the answer is insufficient, improve it now. If satisfactory, return it as-is."""

    def __init__(self) -> None:
        """Init  ."""
        self._tool_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool")

    def _get_tools_for_provider(self, provider: str, intent: str = None, user_message: str = "") -> list:
        """Get tools for provider."""
        from salmalm.core.tool_selector import get_tools_for_provider

        return get_tools_for_provider(provider, intent, user_message)

    # Max chars per tool result sent to LLM context (default + per-type overrides)
    MAX_TOOL_RESULT_CHARS = 20_000
    # Aggressive truncation — every char costs tokens
    _TOOL_TRUNCATE_LIMITS = {
        "exec": 8_000,
        "exec_session": 4_000,
        "sandbox_exec": 8_000,
        "python_eval": 6_000,
        "browser": 5_000,
        "http_request": 6_000,
        "web_fetch": 6_000,
        "read": 10_000,
        "rag_search": 4_000,
        "system_info": 2_000,
        "canvas": 2_000,
        "web_search": 4_000,
        "weather": 2_000,
        "google_calendar": 3_000,
        "gmail": 4_000,
    }
    # Per-tool hard timeout (seconds) — total wall-clock including subprocess/IO
    _TOOL_TIMEOUTS = {
        "exec": 120,
        "exec_session": 10,  # Just submits, doesn't wait
        "sandbox_exec": 60,
        "python_eval": 30,
        "browser": 90,
        "http_request": 30,
        "web_fetch": 30,
        "mesh": 60,
        "image_generate": 120,
    }
    _DEFAULT_TOOL_TIMEOUT = 60

    # Patterns that look like leaked secrets in tool output
    _SECRET_OUTPUT_RE = _re.compile(
        r"(?i)(?:"
        r"(?:sk|pk|api|key|token|secret|bearer|ghp|gho|pypi)-[A-Za-z0-9_\-]{20,}"
        r"|AKIA[0-9A-Z]{16}"  # AWS access key
        r"|AIza[0-9A-Za-z_\-]{35}"  # Google API key
        r"|(?:ghp|gho|ghu|ghs|ghr)_\w{36,}"  # GitHub tokens
        r"|pypi-[A-Za-z0-9_\-]{50,}"  # PyPI tokens
        r"|sk-(?:ant-)?[A-Za-z0-9_\-]{20,}"  # OpenAI/Anthropic keys
        r"|xai-[A-Za-z0-9_\-]{20,}"  # xAI keys
        r")"
    )

    def _redact_secrets(self, text: str) -> str:
        """Scrub anything that looks like a leaked API key/token from output."""
        return self._SECRET_OUTPUT_RE.sub("[REDACTED]", text) if text else text

    def _truncate_tool_result(self, result: str, tool_name: str = "") -> str:
        """Truncate tool result based on tool type to prevent context explosion."""

        result = self._redact_secrets(result)
        # File pre-summarization: summarize large file reads with a fast model.
        # NOTE: call_llm is synchronous — this blocks the ThreadPoolExecutor worker
        # while waiting for the API response.  With max_workers=4 and multiple
        # concurrent tools, all workers can be blocked simultaneously.  This path
        # is only active when SALMALM_FILE_PRESUMMARY=1 (default OFF), so the
        # real-world impact is minimal.  A proper fix would use asyncio.to_thread()
        # at the caller and pass an async call; deferred to a future refactor.
        if (
            _os.environ.get("SALMALM_FILE_PRESUMMARY", "0") == "1"
            and tool_name in ("read_file", "web_fetch")
            and len(result) > 5000
        ):
            try:
                from salmalm.core.llm import call_llm

                summary = call_llm(
                    model=COMMAND_MODEL,   # fast, low-cost — was hardcoded haiku
                    messages=[
                        {
                            "role": "user",
                            "content": f"Summarize this content concisely, preserving key facts, code structure, and important details:\n\n{result[:15000]}",
                        }
                    ],
                    max_tokens=1024,
                    tools=None,
                )
                if summary.get("content"):
                    return f"[Pre-summarized — original {len(result)} chars]\n\n{summary['content']}"
            except Exception as _exc:
                log.debug(f"Suppressed: {_exc}")
                pass  # Fall through to normal truncation
        limit = self._TOOL_TRUNCATE_LIMITS.get(tool_name, self.MAX_TOOL_RESULT_CHARS)
        if len(result) > limit:
            return (
                result[:limit]
                + f"\n\n... [truncated: {len(result)} chars total, limit {limit} for {tool_name or 'default'}]"
            )
        return result

    def _get_tool_timeout(self, tool_name: str) -> int:
        """Get hard timeout for a tool (total wall-clock)."""
        return self._TOOL_TIMEOUTS.get(tool_name, self._DEFAULT_TOOL_TIMEOUT)

    def _execute_tools_parallel(self, tool_calls: list, on_tool=None, session=None) -> dict:
        """Execute multiple tools in parallel, return {id: result}."""
        for tc in tool_calls:
            if on_tool:
                _safe_callback(on_tool, tc["name"], tc["arguments"])

        # Fire on_tool_call hook for each tool (도구 호출 훅)
        try:
            from salmalm.features.hooks import hook_manager

            for tc in tool_calls:
                hook_manager.fire(
                    "on_tool_call", {"session_id": "", "message": f"{tc['name']}: {str(tc.get('arguments', ''))[:200]}"}
                )
        except Exception as _exc:
            log.debug(f"Suppressed: {_exc}")

        if len(tool_calls) == 1:
            tc = tool_calls[0]
            _metrics["tool_calls"] += 1
            t0 = _time.time()
            # Copy args: never mutate tc["arguments"] — it is referenced later by
            # _append_tool_results and serialised into LLM context (tool_use input).
            # _session_id / _authenticated must NOT appear in the LLM's view of args.
            exec_args = {**tc["arguments"],
                         "_session_id": getattr(session, "id", ""),
                         "_authenticated": getattr(session, "authenticated", False)}
            try:
                result = self._truncate_tool_result(execute_tool(tc["name"], exec_args), tool_name=tc["name"])
                elapsed = _time.time() - t0
                audit_log(
                    "tool_call",
                    f"{tc['name']}: ok ({elapsed:.2f}s)",
                    detail_dict={
                        "tool": tc["name"],
                        "args_summary": str(tc["arguments"])[:200],
                        "elapsed_s": round(elapsed, 3),
                        "success": True,
                    },
                )
            except Exception as e:
                elapsed = _time.time() - t0
                _metrics["tool_errors"] += 1
                result = f"❌ Tool execution error: {e}"
                audit_log(
                    "tool_call",
                    f"{tc['name']}: error ({e})",
                    detail_dict={
                        "tool": tc["name"],
                        "args_summary": str(tc["arguments"])[:200],
                        "elapsed_s": round(elapsed, 3),
                        "success": False,
                        "error": str(e)[:200],
                    },
                )
            return {tc["id"]: result}

        futures = {}
        start_times = {}
        for tc in tool_calls:
            _metrics["tool_calls"] += 1
            start_times[tc["id"]] = _time.time()
            exec_args = {**tc["arguments"],
                         "_session_id": getattr(session, "id", ""),
                         "_authenticated": getattr(session, "authenticated", False)}
            f = self._tool_executor.submit(execute_tool, tc["name"], exec_args)
            futures[tc["id"]] = (f, tc)
        outputs = {}
        for tc_id, (f, tc) in futures.items():
            try:
                _tool_timeout = self._get_tool_timeout(tc["name"])
                outputs[tc_id] = self._truncate_tool_result(f.result(timeout=_tool_timeout), tool_name=tc["name"])
                elapsed = _time.time() - start_times[tc_id]
                audit_log(
                    "tool_call",
                    f"{tc['name']}: ok ({elapsed:.2f}s)",
                    detail_dict={
                        "tool": tc["name"],
                        "args_summary": str(tc["arguments"])[:200],
                        "elapsed_s": round(elapsed, 3),
                        "success": True,
                    },
                )
            except Exception as e:
                elapsed = _time.time() - start_times[tc_id]
                _metrics["tool_errors"] += 1
                outputs[tc_id] = f"❌ Tool execution error: {e}"
                audit_log(
                    "tool_call",
                    f"{tc['name']}: error",
                    detail_dict={
                        "tool": tc["name"],
                        "args_summary": str(tc["arguments"])[:200],
                        "elapsed_s": round(elapsed, 3),
                        "success": False,
                        "error": str(e)[:200],
                    },
                )
        log.info(f"[FAST] Parallel: {len(tool_calls)} tools completed")
        return outputs

    def _append_tool_results(self, session, provider: str, result, tool_calls, tool_outputs) -> None:
        """Append tool call + results to session messages."""
        if provider == "anthropic":
            content_blocks = []
            if result.get("content"):
                content_blocks.append({"type": "text", "text": result["content"]})
            for tc in tool_calls:
                content_blocks.append(
                    {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["arguments"]}
                )
            session.messages.append({"role": "assistant", "content": content_blocks})
            session.add_tool_results(
                [{"tool_use_id": tc["id"], "content": tool_outputs[tc["id"]]} for tc in tool_calls]
            )
        else:
            # Store assistant message WITH tool_calls in OpenAI format
            # so _sanitize_messages_for_provider can convert to tool_use for Anthropic fallback
            asst_tool_calls = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": _json.dumps(tc["arguments"]) if isinstance(tc["arguments"], dict) else str(tc["arguments"]),
                    },
                }
                for tc in tool_calls
            ]
            session.messages.append({
                "role": "assistant",
                "content": result.get("content", "") or "",
                "tool_calls": asst_tool_calls,
            })
            session.last_active = _time.time()
            for tc in tool_calls:
                session.messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "name": tc["name"], "content": tool_outputs[tc["id"]]}
                )

    def _should_reflect(self, classification: dict, response: str, iteration: int) -> bool:
        """Determine if response needs self-reflection pass.
        Disabled by default for token optimization — reflection doubles LLM cost.
        Enable with SALMALM_REFLECT=1 env var."""

        if _os.environ.get("SALMALM_REFLECT", "0") != "1":
            return False
        if classification["intent"] not in ("code", "analysis"):
            return False
        if iteration >= self.MAX_TOOL_ITERATIONS - 5:
            return False
        if len(response) < 100:
            return False
        if classification.get("score", 0) >= 3:
            return True
        return False

    async def _call_with_failover(
        self, messages, model, tools=None, max_tokens=4096, thinking=False, on_token=None, on_status=None
    ):
        """LLM call with automatic failover on failure. Delegates to llm_loop."""
        return await _call_with_failover_fn(
            messages,
            model,
            tools=tools,
            max_tokens=max_tokens,
            thinking=thinking,
            on_token=on_token,
            on_status=on_status,
        )

    async def _try_llm_call(self, messages: list, model: str, tools: list, max_tokens: int, thinking, on_token):
        """Single LLM call attempt. Delegates to llm_loop."""
        model = _fix_model_name(model)
        return await _try_llm_call_fn(messages, model, tools, max_tokens, thinking, on_token)

    async def run(
        self,
        session: object,
        user_message: str,
        model_override: Optional[str] = None,
        on_tool: Optional[object] = None,
        classification: Optional[Dict[str, Any]] = None,
        on_token: Optional[object] = None,
        on_status: Optional[object] = None,
    ) -> str:
        """Main execution loop — Plan → Execute → Reflect."""

        if not classification:
            classification = TaskClassifier.classify(user_message, len(session.messages))

        tier = classification["tier"]
        use_thinking = classification["thinking"]
        thinking_budget = classification["thinking_budget"]
        log.info(
            f"[AI] Intent: {classification['intent']} (tier={tier}, "
            f"think={use_thinking}, budget={thinking_budget}, "
            f"score={classification.get('score', 0)})"
        )

        # PHASE 1: PLANNING — opt-in via SALMALM_PLANNING=1 or settings toggle

        if _os.environ.get("SALMALM_PLANNING", "0") == "1":
            if classification["intent"] in ("code", "analysis") and classification.get("score", 0) >= 2:
                plan_msg = {"role": "system", "content": self.PLAN_PROMPT, "_plan_injected": True}
                last_user_idx = None
                for i in range(len(session.messages) - 1, -1, -1):
                    if session.messages[i].get("role") == "user":
                        last_user_idx = i
                        break
                if last_user_idx is not None:
                    session.messages.insert(last_user_idx, plan_msg)

        # PHASE 2: EXECUTE — tool loop
        try:
            return await self._execute_loop(
                session,
                user_message,
                model_override,  # type: ignore[no-any-return]
                on_tool,
                classification,
                tier,
                on_token=on_token,
                on_status=on_status,
            )
        except Exception as e:
            log.error(f"Engine.run error: {e}")
            import traceback

            traceback.print_exc()
            # User-friendly message (기술 세부사항은 로그에만)
            friendly = _friendly_error(e)
            session.add_assistant(friendly)
            error_msg = friendly
            # Fire on_error hook (에러 발생 훅)
            try:
                from salmalm.features.hooks import hook_manager

                hook_manager.fire("on_error", {"session_id": getattr(session, "id", ""), "message": error_msg})
            except Exception as _exc:
                log.debug(f"Suppressed: {_exc}")
            return error_msg
        finally:
            # Guarantee plan message cleanup regardless of exit path.
            # _finalize_loop_response also does this on normal exit — filtering twice is harmless.
            session.messages = [m for m in session.messages if not m.get("_plan_injected")]

    # ── OpenClaw-style limits ──
    MAX_TOOL_ITERATIONS = 25
    MAX_CONSECUTIVE_ERRORS = 3

    async def _handle_token_overflow(
        self, session, model: str, tools: list, max_tokens: int, thinking, on_status
    ) -> tuple:
        """Handle token overflow with 3-stage recovery. Returns (result, error_msg_or_None)."""
        log.warning(f"[CUT] Token overflow with {len(session.messages)} messages — running compaction")

        # Stage A: Compaction
        session.messages = compact_messages(session.messages, session=session, on_status=on_status)
        result, _ = await self._call_with_failover(
            session.messages, model=model, tools=tools, max_tokens=max_tokens, thinking=thinking
        )

        # Stage B: Force truncation — keep system + last 10
        if result.get("error") == "token_overflow" and len(session.messages) > 12:
            system_msgs = [m for m in session.messages if m["role"] == "system"][:1]
            session.messages = system_msgs + session.messages[-10:]
            log.warning(f"[CUT] Post-compaction truncation: -> {len(session.messages)} msgs")
            result, _ = await self._call_with_failover(
                session.messages, model=model, tools=tools, max_tokens=max_tokens, thinking=False
            )

        # Stage C: Nuclear — keep only last 4
        if result.get("error") == "token_overflow" and len(session.messages) > 4:
            system_msgs = [m for m in session.messages if m["role"] == "system"][:1]
            session.messages = (system_msgs or []) + session.messages[-4:]
            log.warning(f"[CUT][CUT] Nuclear truncation: -> {len(session.messages)} msgs")
            result, _ = await self._call_with_failover(
                session.messages, model=model, tools=tools, max_tokens=max_tokens
            )

        if result.get("error"):
            session.add_assistant("⚠️ Context too large. Use /clear to reset.")
            return result, "⚠️ Context too large. Use /clear to reset."
        return result, None

    async def _handle_tool_calls(
        self, result, session, provider, on_tool, on_status, consecutive_errors: int, recent_tool_calls: list
    ) -> "tuple[Optional[str], int]":
        """Execute tool calls, check circuit breaker and loop detection.

        Returns:
            (break_message, updated_consecutive_errors)
            break_message is non-None when the loop should stop.
        """
        from salmalm.core.loop_helpers import validate_tool_calls, check_circuit_breaker, check_loop_detection

        if on_status:
            tool_names = ", ".join(tc["name"] for tc in result["tool_calls"][:3])
            _safe_callback(on_status, STATUS_TOOL_RUNNING, f"🔧 Running {tool_names}...")

        valid_tools, tool_outputs = validate_tool_calls(result["tool_calls"])
        if valid_tools:
            exec_outputs = await asyncio.to_thread(self._execute_tools_parallel, valid_tools, on_tool, session)
            tool_outputs.update(exec_outputs)

        # consecutive_errors is an int (value type) — must be returned to caller
        # so the circuit breaker accumulates across iterations, not just within one.
        consecutive_errors, break_msg = check_circuit_breaker(
            tool_outputs, consecutive_errors, self.MAX_CONSECUTIVE_ERRORS
        )
        if break_msg:
            session.add_assistant(break_msg)
            return break_msg, consecutive_errors

        loop_msg = check_loop_detection(result.get("tool_calls", []), recent_tool_calls)
        if loop_msg:
            session.add_assistant(loop_msg)
            return loop_msg, consecutive_errors

        self._append_tool_results(session, provider, result, result["tool_calls"], tool_outputs)
        return None, consecutive_errors

    async def _finalize_loop_response(
        self,
        result,
        session,
        pruned_messages,
        model: str,
        tools,
        user_message: str,
        classification: dict,
        iteration: int,
        failover_warn,
    ) -> str:
        """Finalize LLM response: empty retry, reflection, logging."""
        from salmalm.core.loop_helpers import handle_empty_response, finalize_response, is_truncated, auto_log_conversation

        response = result.get("content", "")
        if not response or not response.strip():
            response = await handle_empty_response(self._call_with_failover, pruned_messages, model, tools)

        # Auto-continuation: if response was truncated, ask LLM to continue (up to 2 times)
        _continuation_count = 0
        while is_truncated(result) and _continuation_count < 2:
            _continuation_count += 1
            log.info(f"[AI] Response truncated, auto-continuing ({_continuation_count}/2)...")
            _cont_msgs = list(pruned_messages) + [
                {"role": "assistant", "content": response},
                {"role": "user", "content": "Continue from where you left off. Do not repeat what you already said."},
            ]
            result, _ = await self._call_with_failover(
                _cont_msgs, model=model, tools=None, max_tokens=4096, thinking=False,
            )
            _cont = result.get("content", "")
            if _cont and _cont.strip():
                response += _cont
            else:
                break

        response = finalize_response(result, response)

        if self._should_reflect(classification, response, iteration):
            response = await self._run_reflection(user_message, response)

        if failover_warn:
            response = f"{failover_warn}\n\n{response}"

        session.add_assistant(response)
        log.info(
            f"[CHAT] Response ({result.get('model', '?')}): {len(response)} chars, iteration {iteration + 1}, intent={classification['intent']}"
        )
        auto_log_conversation(user_message, response, classification)
        session.messages = [m for m in session.messages if not m.get("_plan_injected")]
        return response

    async def _run_reflection(self, user_message: str, response: str) -> str:
        """Run reflection pass to improve response quality."""
        log.info(f"[SEARCH] Reflection pass")
        reflect_msgs = [
            {"role": "system", "content": self.REFLECT_PROMPT},
            {"role": "user", "content": f"Original question: {user_message[:REFLECT_SNIPPET_LEN]}"},
            {"role": "assistant", "content": response},
            {"role": "user", "content": "Evaluate and improve if needed."},
        ]
        reflect_result = await _call_llm_async(reflect_msgs, model=router._pick_available(2), max_tokens=4000)
        improved = reflect_result.get("content", "")
        if improved and len(improved) > len(response) * 0.5 and len(improved) > 50:
            skip_phrases = ["satisfactory", "sufficient", "correct"]
            if not any(p in improved[:100].lower() for p in skip_phrases):
                response = improved
            log.info(f"[SEARCH] Reflection improved: {len(response)} chars")
        return response

    async def _execute_loop(
        self, session, user_message, model_override, on_tool, classification, tier, on_token=None, on_status=None
    ):
        """Execute loop."""
        from salmalm.core.loop_helpers import (
            check_abort,
            select_model,
            trim_history,
            prune_session_context,
            record_usage,
        )

        use_thinking = getattr(session, "thinking_enabled", False)
        iteration = 0
        consecutive_errors = 0
        _recent_tool_calls = []
        _session_id = getattr(session, "id", "")
        result: dict = {}   # guard against NameError if _max_iter=0 or loop exits early

        _max_iter = int(_os.environ.get("SALMALM_MAX_TOOL_ITER", str(self.MAX_TOOL_ITERATIONS)))
        while iteration < _max_iter:
            # Abort check
            abort_msg = check_abort(_session_id)
            if abort_msg:
                session.add_assistant(abort_msg)
                log.info(f"[ABORT] Generation aborted: session={_session_id}")
                return abort_msg

            # Model & provider selection
            model = select_model(model_override, user_message, tier, iteration, router)
            provider = model.split("/")[0] if "/" in model else "anthropic"

            # Tools
            tools = self._get_tools_for_provider(
                provider, intent=classification["intent"], user_message=user_message or ""
            )

            # Thinking mode — pass level string instead of bool
            _think_level = getattr(session, "thinking_level", "medium") if use_thinking else None
            think_this_call = (
                _think_level
                if (
                    use_thinking
                    and iteration == 0
                    and ("opus" in model or "sonnet" in model or "o3" in model or "o4" in model)
                )
                else False
            )

            # History & context management
            trim_history(session, classification)
            pruned_messages = prune_session_context(session, model)

            # Status callback
            if on_status:
                if think_this_call:
                    _safe_callback(on_status, STATUS_THINKING, "🧠 Thinking...")
                else:
                    _safe_callback(on_status, STATUS_TYPING, "typing")

            # LLM call
            _dynamic_max_tokens = _get_dynamic_max_tokens(classification["intent"], user_message or "", model)
            # Inject token budget hint so LLM structures its response to fit
            _budget_hint = {
                "role": "system",
                "content": f"[Response budget: ~{_dynamic_max_tokens} tokens. "
                "Structure your response to be complete within this limit. "
                "If the topic is too large, prioritize the most important points and summarize the rest. "
                "Never stop mid-sentence.]",
            }
            _msgs_with_budget = list(pruned_messages) + [_budget_hint]
            result, _failover_warn = await self._call_with_failover(
                _msgs_with_budget,
                model=model,
                tools=tools,
                max_tokens=_dynamic_max_tokens,
                thinking=think_this_call,
                on_token=on_token,
                on_status=on_status,
            )
            result.pop("_failed", None)
            _record_api_call_time()

            # Token overflow recovery
            if result.get("error") == "token_overflow":
                result, overflow_msg = await self._handle_token_overflow(
                    session, model, tools, _dynamic_max_tokens, think_this_call, on_status
                )
                if overflow_msg:
                    return overflow_msg

            # Usage tracking
            record_usage(_session_id, model, result, classification, iteration)

            if result.get("thinking"):
                log.info(f"[AI] Thinking: {len(result['thinking'])} chars")

            # ── Tool execution branch ──
            if result.get("tool_calls"):
                break_msg, consecutive_errors = await self._handle_tool_calls(
                    result,
                    session,
                    provider,
                    on_tool,
                    on_status,
                    consecutive_errors,
                    _recent_tool_calls,
                )
                if break_msg:
                    return break_msg
                # Mid-loop compaction
                if len(session.messages) > 40:
                    session.messages = compact_messages(session.messages, session=session, on_status=on_status)
                    log.info(f"[CUT] Mid-loop compaction: -> {len(session.messages)} msgs")
                iteration += 1
                continue

            # ── Final response branch ──
            return await self._finalize_loop_response(
                result,
                session,
                pruned_messages,
                model,
                tools,
                user_message,
                classification,
                iteration,
                _failover_warn,
            )

        # Loop exhausted (result is initialized to {} above so this is always safe)
        log.warning(f"[BREAK] Max iterations ({_max_iter}) reached")
        response = result.get("content", "Reached maximum tool iterations. Please try a simpler request.")
        if not response:
            response = "Reached maximum tool iterations. Please try a simpler request."
        session.add_assistant(response)
        session.messages = [m for m in session.messages if not m.get("_plan_injected")]
        return response


# Singleton
_engine = IntelligenceEngine()


_MAX_MESSAGE_LENGTH = 100_000
_SESSION_ID_RE = _re.compile(r"^[a-zA-Z0-9_\-\.]+$")


# ── Slash commands + usage tracking — extracted to slash_commands.py ──
from salmalm.core.slash_commands import (  # noqa: F401, E402
    _session_usage,
    _get_session_usage,
    record_response_usage,
    _SLASH_COMMANDS,
    _SLASH_PREFIX_COMMANDS,
    _dispatch_slash_command,
    # Re-export for backward compatibility (tests import from engine)
    _cmd_context,
    _cmd_usage,
    _cmd_plugins,
    _cmd_export_fn as _cmd_export,
)


# Sourced from constants.py — single source of truth for thinking budgets.
# Re-exported here for backward compatibility (other modules import from engine).
_THINKING_BUDGET_MAP = _THINKING_BUDGET_MAP_CONST
