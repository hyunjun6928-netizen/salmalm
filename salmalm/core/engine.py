"""SalmAlm Intelligence Engine — TaskClassifier + IntelligenceEngine + process_message."""

from __future__ import annotations

import asyncio
import json  # noqa: F401
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple  # noqa: F401

from salmalm.constants import (  # noqa: F401
    VERSION,
    INTENT_SHORT_MSG,
    INTENT_COMPLEX_MSG,  # noqa: F401
    INTENT_CONTEXT_DEPTH,
    REFLECT_SNIPPET_LEN,
    MODEL_ALIASES as _CONST_ALIASES,
    COMMAND_MODEL,
)  # noqa: F401
import re as _re
import threading as _threading
import time as _time
from salmalm.security.crypto import log
from salmalm.core.cost import (  # noqa: F401
    estimate_tokens,
    estimate_cost,
    MODEL_PRICING,
    get_pricing as _get_pricing,
)

# Graceful shutdown state
_shutting_down = False
_active_requests = 0
_active_requests_lock = _threading.Lock()
_active_requests_event = _threading.Event()  # signaled when _active_requests == 0
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
from salmalm.core.prompt import build_system_prompt
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
from salmalm.constants import MODELS as _MODELS  # noqa: F401  # noqa: F401

# Backward-compat re-exports
get_routing_config = _load_routing_config


# _select_model delegates to core/model_selection.py (backward compat)
_select_model = _select_model_impl


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
    """Core AI reasoning engine — surpasses OpenClaw's capabilities.

    Architecture:
    1. CLASSIFY — Determine task type, complexity, required resources
    2. PLAN — For complex tasks, generate execution plan before acting
    3. EXECUTE — Run tool loop with parallel execution
    4. REFLECT — Self-evaluate response quality, retry if insufficient
    """

    # Planning prompt — injected before complex tasks
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
        import os as _os

        result = self._redact_secrets(result)
        # File pre-summarization: summarize large file reads with Haiku
        if (
            _os.environ.get("SALMALM_FILE_PRESUMMARY", "0") == "1"
            and tool_name in ("read_file", "web_fetch")
            and len(result) > 5000
        ):
            try:
                from salmalm.core.llm import call_llm

                summary = call_llm(
                    model="anthropic/claude-haiku-3.5-20241022",
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
                    return f"[Pre-summarized by Haiku — original {len(result)} chars]\n\n{summary['content']}"
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

    def _execute_tools_parallel(self, tool_calls: list, on_tool=None) -> dict:
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
            try:
                tc["arguments"]["_session_id"] = getattr(self._session, "id", "")
                tc["arguments"]["_authenticated"] = getattr(self._session, "authenticated", False)
                result = self._truncate_tool_result(execute_tool(tc["name"], tc["arguments"]), tool_name=tc["name"])
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
            tc["arguments"]["_session_id"] = getattr(self._session, "id", "")
            tc["arguments"]["_authenticated"] = getattr(self._session, "authenticated", False)
            f = self._tool_executor.submit(execute_tool, tc["name"], tc["arguments"])
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
            session.add_assistant(result.get("content", ""))
            for tc in tool_calls:
                session.messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "name": tc["name"], "content": tool_outputs[tc["id"]]}
                )

    def _should_reflect(self, classification: dict, response: str, iteration: int) -> bool:
        """Determine if response needs self-reflection pass.
        Disabled by default for token optimization — reflection doubles LLM cost.
        Enable with SALMALM_REFLECT=1 env var."""
        import os as _os

        if _os.environ.get("SALMALM_REFLECT", "0") != "1":
            return False
        if classification["intent"] not in ("code", "analysis"):
            return False
        if iteration > 20:
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
        import os as _os

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
            error_msg = f"❌ Processing error: {type(e).__name__}: {e}"
            session.add_assistant(error_msg)
            # Fire on_error hook (에러 발생 훅)
            try:
                from salmalm.features.hooks import hook_manager

                hook_manager.fire("on_error", {"session_id": getattr(session, "id", ""), "message": error_msg})
            except Exception as _exc:
                log.debug(f"Suppressed: {_exc}")
            return error_msg

    # ── OpenClaw-style limits ──
    MAX_TOOL_ITERATIONS = 15
    MAX_CONSECUTIVE_ERRORS = 3

    async def _handle_token_overflow(self, session, model: str, tools: list, max_tokens: int, thinking, on_status) -> tuple:
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

    async def _handle_tool_calls(self, result, session, provider, on_tool, on_status,
                                 consecutive_errors: int, recent_tool_calls: list) -> Optional[str]:
        """Execute tool calls, check circuit breaker and loop detection. Returns break message or None."""
        from salmalm.core.loop_helpers import validate_tool_calls, check_circuit_breaker, check_loop_detection
        if on_status:
            tool_names = ", ".join(tc["name"] for tc in result["tool_calls"][:3])
            _safe_callback(on_status, STATUS_TOOL_RUNNING, f"🔧 Running {tool_names}...")

        valid_tools, tool_outputs = validate_tool_calls(result["tool_calls"])
        if valid_tools:
            exec_outputs = await asyncio.to_thread(self._execute_tools_parallel, valid_tools, on_tool)
            tool_outputs.update(exec_outputs)

        consecutive_errors, break_msg = check_circuit_breaker(tool_outputs, consecutive_errors, self.MAX_CONSECUTIVE_ERRORS)
        if break_msg:
            session.add_assistant(break_msg)
            return break_msg

        loop_msg = check_loop_detection(result.get("tool_calls", []), recent_tool_calls)
        if loop_msg:
            session.add_assistant(loop_msg)
            return loop_msg

        self._append_tool_results(session, provider, result, result["tool_calls"], tool_outputs)
        return None

    async def _finalize_loop_response(self, result, session, pruned_messages, model: str, tools,
                                       user_message: str, classification: dict, iteration: int,
                                       failover_warn) -> str:
        """Finalize LLM response: empty retry, reflection, logging."""
        from salmalm.core.loop_helpers import handle_empty_response, finalize_response, auto_log_conversation
        response = result.get("content", "")
        if not response or not response.strip():
            response = await handle_empty_response(self._call_with_failover, pruned_messages, model, tools)
        response = finalize_response(result, response)

        if self._should_reflect(classification, response, iteration):
            response = await self._run_reflection(user_message, response)

        if failover_warn:
            response = f"{failover_warn}\n\n{response}"

        session.add_assistant(response)
        log.info(f"[CHAT] Response ({result.get('model', '?')}): {len(response)} chars, iteration {iteration + 1}, intent={classification['intent']}")
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
            auto_log_conversation,
            check_abort,
            select_model,
            trim_history,
            prune_session_context,
            record_usage,
            validate_tool_calls,
            check_circuit_breaker,
            check_loop_detection,
            handle_empty_response,
            finalize_response,
        )

        use_thinking = getattr(session, "thinking_enabled", False)
        iteration = 0
        consecutive_errors = 0
        _recent_tool_calls = []
        _session_id = getattr(session, "id", "")
        import os as _os

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
                _think_level if (use_thinking and iteration == 0 and ("opus" in model or "sonnet" in model or "o3" in model or "o4" in model))
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
            _dynamic_max_tokens = _get_dynamic_max_tokens(classification["intent"], user_message or "")
            result, _failover_warn = await self._call_with_failover(
                pruned_messages,
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
                break_msg = await self._handle_tool_calls(
                    result, session, provider, on_tool, on_status,
                    consecutive_errors, _recent_tool_calls,
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
                result, session, pruned_messages, model, tools, user_message,
                classification, iteration, _failover_warn,
            )

        # Loop exhausted
        log.warning(f"[BREAK] Max iterations ({_max_iter}) reached")
        response = result.get("content", "Reached maximum tool iterations. Please try a simpler request.")  # noqa: F821
        if not response:
            response = "Reached maximum tool iterations. Please try a simpler request."
        session.add_assistant(response)
        session.messages = [m for m in session.messages if not m.get("_plan_injected")]
        return response


# Singleton
_engine = IntelligenceEngine()


_MAX_MESSAGE_LENGTH = 100_000
_SESSION_ID_RE = _re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def _sanitize_input(text: str) -> str:
    """Strip null bytes and control characters (keep newlines/tabs)."""
    return "".join(c for c in text if c == "\n" or c == "\t" or c == "\r" or (ord(c) >= 32) or ord(c) > 127)


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


_THINKING_BUDGET_MAP = {"low": 4000, "medium": 10000, "high": 16000, "xhigh": 32000}


def _classify_task(session, user_message: str) -> dict:
    """Classify task and apply thinking settings."""
    classification = TaskClassifier.classify(user_message, len(session.messages))
    thinking_on = getattr(session, "thinking_enabled", False)
    classification["thinking"] = thinking_on
    level = getattr(session, "thinking_level", "medium") if thinking_on else None
    classification["thinking_level"] = level
    classification["thinking_budget"] = _THINKING_BUDGET_MAP.get(level or "medium", 10000) if thinking_on else 0

    if not thinking_on and classification["tier"] >= 3 and classification["score"] >= 4:
        _suggest_key = f"_thinking_suggested_{getattr(session, 'id', '')}"
        if not getattr(session, _suggest_key, False):
            setattr(session, _suggest_key, True)
            session._thinking_hint = (
                "\n\n💡 *이 작업은 복잡해 보입니다. 🧠 Extended Thinking을 켜면 더 정확한 결과를 얻을 수 있습니다.* "
                "`/thinking on` 또는 🧠 버튼을 눌러주세요."
                "\n💡 *This looks complex. Enable 🧠 Extended Thinking for better results.* "
                "Use `/thinking on` or the 🧠 button."
            )
    return classification


def _route_model(model_override, user_message: str, session) -> tuple:
    """Select model via routing or override. Returns (model, complexity)."""
    if model_override:
        return _fix_model_name(model_override), "auto"
    selected, complexity = _select_model(user_message, session)
    log.info(f"[ROUTE] Multi-model: {complexity} → {selected}")
    return _fix_model_name(selected), complexity


def _prepare_context(session, user_message: str, lang, on_status) -> None:
    """Prepare session context: language, compaction, RAG, mood, self-evolve."""
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
                            session.messages[i]["content"] = m["content"] + f"\n\n[감정 감지: {_detected_mood}] {_tone_hint}"
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
        sla_end = _time.time()
        ttft_ms = (first_token_time - sla_start) * 1000 if first_token_time > 0 else (sla_end - sla_start) * 1000
        total_ms = (sla_end - sla_start) * 1000
        timed_out = total_ms > _sla_cfg.get("response_target_ms", 30000)
        latency_tracker.record(ttft_ms=ttft_ms, total_ms=total_ms, model=model or "auto", timed_out=timed_out, session_id=session_id)
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
    # Input sanitization
    if not _SESSION_ID_RE.match(session_id):
        return "❌ Invalid session ID format (alphanumeric and hyphens only)."
    if len(user_message) > _MAX_MESSAGE_LENGTH:
        return f"❌ Message too long ({len(user_message)} chars). Maximum is {_MAX_MESSAGE_LENGTH}."
    user_message = _sanitize_input(user_message)

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
        session.add_user(user_message)

    _prepare_context(session, user_message, lang, on_status)

    classification = _classify_task(session, user_message)
    selected_model, complexity = _route_model(model_override, user_message, session)

    # ── SLA: Measure latency (레이턴시 측정) + abort token accumulation ──
    _sla_start = _time.time()
    _sla_first_token_time = [0.0]  # mutable for closure
    _orig_on_token = on_token

    # Start streaming accumulator for abort recovery
    from salmalm.features.abort import abort_controller as _abort_ctl

    _abort_ctl.start_streaming(session_id)

    def _sla_on_token(event) -> None:
        """Sla on token."""
        if _sla_first_token_time[0] == 0.0:
            _sla_first_token_time[0] = _time.time()
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
