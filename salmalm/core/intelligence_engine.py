"""IntelligenceEngine — core AI reasoning implementation.

Separated from engine.py to break the circular import between engine.py
and engine_pipeline.py, and to eliminate import-time side-effects
(ThreadPoolExecutor creation, singleton init) on every consumer.

Consumers should import from salmalm.core.engine for backward compat.
Direct imports from this module are also supported.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional
import re as _re
import time as _time

from salmalm.constants import (
    REFLECT_SNIPPET_LEN,
    MODEL_ALIASES as _CONST_ALIASES,
    COMMAND_MODEL,
)
from salmalm.security.crypto import log
from salmalm.core import router, compact_messages, _metrics, audit_log
from salmalm.tools.tool_handlers import execute_tool
from salmalm.core.error_messages import friendly_error as _friendly_error
from salmalm.core.session_manager import _record_api_call_time
from salmalm.core.llm_loop import (
    _call_llm_async,
    STATUS_TYPING,
    STATUS_THINKING,
    STATUS_TOOL_RUNNING,
    call_with_failover as _call_with_failover_fn,
    try_llm_call as _try_llm_call_fn,
)
from salmalm.core.model_selection import fix_model_name as _fix_model_name
from salmalm.core.classifier import TaskClassifier, _get_dynamic_max_tokens

# ── Module-level main-loop reference (cross-thread callback dispatch) ──
# Set at the start of every IntelligenceEngine.run() call.
_MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None

# ── Lock protecting _metrics from concurrent thread increments ──
_METRICS_LOCK = threading.Lock()


def _safe_callback(cb, *args) -> None:
    """Call a callback safely — sync or async, from any thread.

    - Async callbacks are scheduled via create_task (async context) or
      run_coroutine_threadsafe against _MAIN_LOOP (sync/thread context).
    - Exceptions inside cb are swallowed so a buggy callback never kills the engine.
    """
    if cb is None:
        return
    try:
        result = cb(*args)
    except Exception as _cb_exc:
        log.debug(f"[ENGINE] callback raised: {_cb_exc}")
        return
    if asyncio.iscoroutine(result):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(result)
        except RuntimeError:
            _loop = _MAIN_LOOP
            if _loop is not None and _loop.is_running():
                asyncio.run_coroutine_threadsafe(result, _loop)
            else:
                log.debug("[ENGINE] Dropping coroutine callback — _MAIN_LOOP not captured yet")
                result.close()


class IntelligenceEngine:
    """Core AI reasoning engine.

    Architecture:
    1. CLASSIFY — Determine task type, complexity, required resources
    2. PLAN     — For complex tasks, generate execution plan before acting
    3. EXECUTE  — Run tool loop with parallel execution
    4. REFLECT  — Self-evaluate response quality, retry if insufficient
    """

    PLAN_PROMPT = """Before answering, briefly plan your approach:
1. What is the user asking? (one sentence)
2. What tools/steps are needed? (bullet list)
3. What could go wrong? (potential issues)
4. Expected output format?
Then execute the plan."""

    REFLECT_PROMPT = """Evaluate your response:
- Did it fully answer the question?
- Are there errors or hallucinations?
- Is the code correct (if any)?
- Could the answer be improved?
If the answer is insufficient, improve it now. If satisfactory, return it as-is."""

    MAX_TOOL_ITERATIONS = 25
    MAX_CONSECUTIVE_ERRORS = 3
    MAX_TOOL_RESULT_CHARS = 20_000

    _TOOL_TRUNCATE_LIMITS = {
        "exec": 8_000, "exec_session": 4_000, "sandbox_exec": 8_000,
        "python_eval": 6_000, "browser": 5_000, "http_request": 6_000,
        "web_fetch": 6_000, "read": 10_000, "rag_search": 4_000,
        "system_info": 2_000, "canvas": 2_000, "web_search": 4_000,
        "weather": 2_000, "google_calendar": 3_000, "gmail": 4_000,
    }
    _TOOL_TIMEOUTS = {
        "exec": 120, "exec_session": 10, "sandbox_exec": 60,
        "python_eval": 30, "browser": 90, "http_request": 30,
        "web_fetch": 30, "mesh": 60, "image_generate": 120,
    }
    _DEFAULT_TOOL_TIMEOUT = 60

    _SECRET_OUTPUT_RE = _re.compile(
        r"(?i)(?:"
        r"(?:sk|pk|api|key|token|secret|bearer|ghp|gho|pypi)-[A-Za-z0-9_\-]{20,}"
        r"|AKIA[0-9A-Z]{16}"
        r"|AIza[0-9A-Za-z_\-]{35}"
        r"|(?:ghp|gho|ghu|ghs|ghr)_\w{36,}"
        r"|pypi-[A-Za-z0-9_\-]{50,}"
        r"|sk-(?:ant-)?[A-Za-z0-9_\-]{20,}"
        r"|xai-[A-Za-z0-9_\-]{20,}"
        r")"
    )

    def __init__(self) -> None:
        self._tool_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool")

    # ── Internal helpers ────────────────────────────────────────────────────

    def _get_tools_for_provider(self, provider: str, intent: str = None, user_message: str = "") -> list:
        from salmalm.core.tool_selector import get_tools_for_provider
        return get_tools_for_provider(provider, intent, user_message)

    def _redact_secrets(self, text: str) -> str:
        return self._SECRET_OUTPUT_RE.sub("[REDACTED]", text) if text else text

    def _truncate_tool_result(self, result: str, tool_name: str = "") -> str:
        import os as _os
        result = self._redact_secrets(result)
        if (
            _os.environ.get("SALMALM_FILE_PRESUMMARY", "0") == "1"
            and tool_name in ("read_file", "web_fetch")
            and len(result) > 5000
        ):
            try:
                from salmalm.core.llm import call_llm
                summary = call_llm(
                    model="anthropic/claude-haiku-3.5-20241022",
                    messages=[{"role": "user", "content": f"Summarize concisely:\n\n{result[:15000]}"}],
                    max_tokens=1024, tools=None,
                )
                if summary.get("content"):
                    return f"[Pre-summarized — original {len(result)} chars]\n\n{summary['content']}"
            except Exception as _exc:
                log.debug(f"Suppressed: {_exc}")
        limit = self._TOOL_TRUNCATE_LIMITS.get(tool_name, self.MAX_TOOL_RESULT_CHARS)
        if len(result) > limit:
            return result[:limit] + f"\n\n... [truncated: {len(result)} chars, limit {limit}]"
        return result

    def _get_tool_timeout(self, tool_name: str) -> int:
        return self._TOOL_TIMEOUTS.get(tool_name, self._DEFAULT_TOOL_TIMEOUT)

    def _execute_tools_parallel(self, tool_calls: list, on_tool=None, session=None) -> dict:
        """Execute tools in parallel via ThreadPoolExecutor. Always applies timeout."""
        for tc in tool_calls:
            if on_tool:
                _safe_callback(on_tool, tc["name"], tc["arguments"])
        try:
            from salmalm.features.hooks import hook_manager
            for tc in tool_calls:
                hook_manager.fire("on_tool_call", {
                    "session_id": "", "message": f"{tc['name']}: {str(tc.get('arguments',''))[:200]}"
                })
        except Exception as _exc:
            log.debug(f"Suppressed: {_exc}")

        def _run_one(tc) -> str:
            # Keep tc["arguments"] clean (model's original); inject into a copy.
            _exec_args = dict(tc["arguments"])
            _exec_args["_session_id"] = getattr(session, "id", "")
            _exec_args["_authenticated"] = getattr(session, "authenticated", False)
            f = self._tool_executor.submit(execute_tool, tc["name"], _exec_args)
            return f.result(timeout=self._get_tool_timeout(tc["name"]))

        def _redacted_summary(args: dict) -> str:
            return self._redact_secrets(str(args)[:200])

        if len(tool_calls) == 1:
            tc = tool_calls[0]
            with _METRICS_LOCK:
                _metrics["tool_calls"] += 1
            t0 = _time.time()
            try:
                result = self._truncate_tool_result(_run_one(tc), tool_name=tc["name"])
                elapsed = _time.time() - t0
                audit_log("tool_call", f"{tc['name']}: ok ({elapsed:.2f}s)", detail_dict={
                    "tool": tc["name"], "args_summary": _redacted_summary(tc["arguments"]),
                    "elapsed_s": round(elapsed, 3), "success": True,
                })
            except Exception as e:
                elapsed = _time.time() - t0
                with _METRICS_LOCK:
                    _metrics["tool_errors"] += 1
                result = f"❌ Tool execution error: {e}"
                audit_log("tool_call", f"{tc['name']}: error ({e})", detail_dict={
                    "tool": tc["name"], "args_summary": _redacted_summary(tc["arguments"]),
                    "elapsed_s": round(elapsed, 3), "success": False, "error": str(e)[:200],
                })
            return {tc["id"]: result}

        futures = {tc["id"]: (self._tool_executor.submit(execute_tool, tc["name"], {
            **tc["arguments"],
            "_session_id": getattr(session, "id", ""),
            "_authenticated": getattr(session, "authenticated", False),
        }), tc) for tc in tool_calls}
        for tc in tool_calls:
            with _METRICS_LOCK:
                _metrics["tool_calls"] += 1
        start_times = {tc["id"]: _time.time() for tc in tool_calls}

        outputs = {}
        for tc_id, (f, tc) in futures.items():
            try:
                outputs[tc_id] = self._truncate_tool_result(
                    f.result(timeout=self._get_tool_timeout(tc["name"])), tool_name=tc["name"]
                )
                elapsed = _time.time() - start_times[tc_id]
                audit_log("tool_call", f"{tc['name']}: ok ({elapsed:.2f}s)", detail_dict={
                    "tool": tc["name"], "args_summary": _redacted_summary(tc["arguments"]),
                    "elapsed_s": round(elapsed, 3), "success": True,
                })
            except Exception as e:
                elapsed = _time.time() - start_times[tc_id]
                with _METRICS_LOCK:
                    _metrics["tool_errors"] += 1
                outputs[tc_id] = f"❌ Tool execution error: {e}"
                audit_log("tool_call", f"{tc['name']}: error", detail_dict={
                    "tool": tc["name"], "args_summary": _redacted_summary(tc["arguments"]),
                    "elapsed_s": round(elapsed, 3), "success": False, "error": str(e)[:200],
                })
        log.info(f"[FAST] Parallel: {len(tool_calls)} tools completed")
        return outputs

    def _append_tool_results(self, session, provider: str, result, tool_calls, tool_outputs) -> None:
        if provider == "anthropic":
            content_blocks = []
            if result.get("content"):
                content_blocks.append({"type": "text", "text": result["content"]})
            for tc in tool_calls:
                content_blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["arguments"]})
            session.messages.append({"role": "assistant", "content": content_blocks})
            session.add_tool_results(
                [{"tool_use_id": tc["id"], "content": tool_outputs[tc["id"]]} for tc in tool_calls]
            )
        else:
            import json as _json
            asst_tool_calls = [{
                "id": tc["id"], "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": _json.dumps(tc["arguments"]) if isinstance(tc["arguments"], dict) else str(tc["arguments"]),
                },
            } for tc in tool_calls]
            session.messages.append({
                "role": "assistant",
                "content": result.get("content", "") or "",
                "tool_calls": asst_tool_calls,
            })
            session.last_active = _time.time()
            for tc in tool_calls:
                session.messages.append({
                    "role": "tool", "tool_call_id": tc["id"],
                    "name": tc["name"], "content": tool_outputs[tc["id"]],
                })

    def _should_reflect(self, classification: dict, response: str, iteration: int) -> bool:
        import os as _os
        if _os.environ.get("SALMALM_REFLECT", "0") != "1":
            return False
        return (
            classification["intent"] in ("code", "analysis")
            and iteration <= 20
            and len(response) >= 100
            and classification.get("score", 0) >= 3
        )

    async def _call_with_failover(
        self, messages, model, tools=None, max_tokens=4096, thinking=False, on_token=None, on_status=None
    ):
        return await _call_with_failover_fn(
            messages, model, tools=tools, max_tokens=max_tokens,
            thinking=thinking, on_token=on_token, on_status=on_status,
        )

    async def _try_llm_call(self, messages, model, tools, max_tokens, thinking, on_token):
        return await _try_llm_call_fn(messages, _fix_model_name(model), tools, max_tokens, thinking, on_token)

    async def _handle_token_overflow(self, session, model, tools, max_tokens, thinking, on_status):
        log.warning(f"[CUT] Token overflow — compacting {len(session.messages)} messages")
        session.messages = compact_messages(session.messages, session=session, on_status=on_status)
        result, _ = await self._call_with_failover(session.messages, model=model, tools=tools, max_tokens=max_tokens, thinking=thinking)
        if result.get("error") == "token_overflow" and len(session.messages) > 12:
            sys_msgs = [m for m in session.messages if m["role"] == "system"][:1]
            session.messages = sys_msgs + session.messages[-10:]
            log.warning(f"[CUT] Force-trim → {len(session.messages)} msgs")
            result, _ = await self._call_with_failover(session.messages, model=model, tools=tools, max_tokens=max_tokens, thinking=False)
        if result.get("error") == "token_overflow" and len(session.messages) > 4:
            sys_msgs = [m for m in session.messages if m["role"] == "system"][:1]
            session.messages = (sys_msgs or []) + session.messages[-4:]
            log.warning(f"[CUT][CUT] Nuclear → {len(session.messages)} msgs")
            result, _ = await self._call_with_failover(session.messages, model=model, tools=tools, max_tokens=max_tokens)
        if result.get("error"):
            session.add_assistant("⚠️ Context too large. Use /clear to reset.")
            return result, "⚠️ Context too large. Use /clear to reset."
        return result, None

    async def _handle_tool_calls(self, result, session, provider, on_tool, on_status, consecutive_errors, recent_tool_calls):
        from salmalm.core.loop_helpers import validate_tool_calls, check_circuit_breaker, check_loop_detection
        if on_status:
            tool_names = ", ".join(tc["name"] for tc in result["tool_calls"][:3])
            _safe_callback(on_status, STATUS_TOOL_RUNNING, f"🔧 Running {tool_names}...")
        valid_tools, tool_outputs = validate_tool_calls(result["tool_calls"])
        if valid_tools:
            exec_outputs = await asyncio.to_thread(self._execute_tools_parallel, valid_tools, on_tool, session)
            tool_outputs.update(exec_outputs)
        consecutive_errors, break_msg = check_circuit_breaker(tool_outputs, consecutive_errors, self.MAX_CONSECUTIVE_ERRORS)
        if break_msg:
            session.add_assistant(break_msg)
            return break_msg, consecutive_errors
        loop_msg = check_loop_detection(result.get("tool_calls", []), recent_tool_calls)
        if loop_msg:
            session.add_assistant(loop_msg)
            return loop_msg, consecutive_errors
        self._append_tool_results(session, provider, result, result["tool_calls"], tool_outputs)
        # Feed loop-detection history (was always empty before this fix)
        recent_tool_calls.append([(tc["name"], str(tc.get("arguments", ""))[:200]) for tc in result["tool_calls"]])
        del recent_tool_calls[:-20]
        return None, consecutive_errors

    async def _finalize_loop_response(self, result, session, pruned_messages, model, tools, user_message, classification, iteration, failover_warn):
        from salmalm.core.loop_helpers import handle_empty_response, finalize_response, is_truncated, auto_log_conversation
        response = result.get("content", "")
        if not response or not response.strip():
            response = await handle_empty_response(self._call_with_failover, pruned_messages, model, tools)
        _cont_count = 0
        while is_truncated(result) and _cont_count < 2:
            _cont_count += 1
            log.info(f"[AI] Response truncated, auto-continuing ({_cont_count}/2)...")
            _cont_msgs = list(pruned_messages) + [
                {"role": "assistant", "content": response},
                {"role": "user", "content": "Continue from where you left off. Do not repeat what you already said."},
            ]
            result, _ = await self._call_with_failover(_cont_msgs, model=model, tools=None, max_tokens=4096, thinking=False)
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
        log.info(f"[CHAT] Response ({result.get('model','?')}): {len(response)} chars, iter={iteration+1}, intent={classification['intent']}")
        auto_log_conversation(user_message, response, classification)
        session.messages = [m for m in session.messages if not m.get("_plan_injected")]
        return response

    async def _run_reflection(self, user_message: str, response: str) -> str:
        reflect_msgs = [
            {"role": "system", "content": self.REFLECT_PROMPT},
            {"role": "user", "content": f"Original question: {user_message[:REFLECT_SNIPPET_LEN]}"},
            {"role": "assistant", "content": response},
            {"role": "user", "content": "Evaluate and improve if needed."},
        ]
        reflect_result = await _call_llm_async(reflect_msgs, model=router._pick_available(2), max_tokens=4000)
        improved = reflect_result.get("content", "")
        if improved and len(improved) > len(response) * 0.5 and len(improved) > 50:
            if not any(p in improved[:100].lower() for p in ("satisfactory", "sufficient", "correct")):
                response = improved
                log.info(f"[SEARCH] Reflection improved: {len(response)} chars")
        return response

    async def _execute_loop(self, session, user_message, model_override, on_tool, classification, tier, on_token=None, on_status=None):
        from salmalm.core.loop_helpers import check_abort, select_model, trim_history, prune_session_context, record_usage
        import os as _os

        use_thinking = getattr(session, "thinking_enabled", False)
        iteration = 0
        consecutive_errors = 0
        _recent_tool_calls: list = []
        _session_id = getattr(session, "id", "")
        result: dict = {}

        _max_iter = int(_os.environ.get("SALMALM_MAX_TOOL_ITER", str(self.MAX_TOOL_ITERATIONS)))
        while iteration < _max_iter:
            abort_msg = check_abort(_session_id)
            if abort_msg:
                session.add_assistant(abort_msg)
                log.info(f"[ABORT] session={_session_id}")
                return abort_msg

            model = select_model(model_override, user_message, tier, iteration, router)
            if "/" in model:
                provider = model.split("/")[0]
            else:
                _pfx = model.split("-")[0].lower()
                provider = {
                    "claude": "anthropic", "gemini": "google",
                    "llama": "groq", "mixtral": "groq", "whisper": "groq",
                    "grok": "xai", "o1": "openai", "o3": "openai", "o4": "openai",
                }.get(_pfx, "openai")

            tools = self._get_tools_for_provider(provider, intent=classification["intent"], user_message=user_message or "")
            _think_level = getattr(session, "thinking_level", "medium") if use_thinking else None
            think_this_call = (
                _think_level if (use_thinking and iteration == 0 and any(x in model for x in ("opus", "sonnet", "o3", "o4")))
                else False
            )
            trim_history(session, classification)
            pruned_messages = prune_session_context(session, model)
            if on_status:
                _safe_callback(on_status, STATUS_THINKING if think_this_call else STATUS_TYPING,
                               "🧠 Thinking..." if think_this_call else "typing")

            _dynamic_max_tokens = _get_dynamic_max_tokens(classification["intent"], user_message or "", model)
            _budget_hint = {"role": "system", "content": (
                f"[Response budget: ~{_dynamic_max_tokens} tokens. "
                "Structure your response to be complete within this limit. "
                "If the topic is too large, prioritize the most important points and summarize the rest. "
                "Never stop mid-sentence.]"
            )}
            result, _failover_warn = await self._call_with_failover(
                list(pruned_messages) + [_budget_hint],
                model=model, tools=tools, max_tokens=_dynamic_max_tokens,
                thinking=think_this_call, on_token=on_token, on_status=on_status,
            )
            result.pop("_failed", None)
            _record_api_call_time()

            if result.get("error") == "token_overflow":
                result, overflow_msg = await self._handle_token_overflow(session, model, tools, _dynamic_max_tokens, think_this_call, on_status)
                if overflow_msg:
                    return overflow_msg

            record_usage(_session_id, model, result, classification, iteration)
            if result.get("thinking"):
                log.info(f"[AI] Thinking: {len(result['thinking'])} chars")

            if result.get("tool_calls"):
                break_msg, consecutive_errors = await self._handle_tool_calls(
                    result, session, provider, on_tool, on_status, consecutive_errors, _recent_tool_calls,
                )
                if break_msg:
                    return break_msg
                if len(session.messages) > 40:
                    session.messages = compact_messages(session.messages, session=session, on_status=on_status)
                    log.info(f"[CUT] Mid-loop compaction → {len(session.messages)} msgs")
                iteration += 1
                continue

            return await self._finalize_loop_response(
                result, session, pruned_messages, model, tools,
                user_message, classification, iteration, _failover_warn,
            )

        log.warning(f"[BREAK] Max iterations ({_max_iter}) reached")
        response = result.get("content") or "Reached maximum tool iterations. Please try a simpler request."
        session.add_assistant(response)
        session.messages = [m for m in session.messages if not m.get("_plan_injected")]
        return response

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
        """Main entry point — Plan → Execute → Reflect."""
        global _MAIN_LOOP
        _MAIN_LOOP = asyncio.get_running_loop()

        if not classification:
            classification = TaskClassifier.classify(user_message, len(session.messages))

        tier = classification["tier"]
        log.info(
            f"[AI] Intent: {classification['intent']} (tier={tier}, "
            f"cls_think={classification['thinking']}, budget={classification['thinking_budget']}, "
            f"score={classification.get('score', 0)})"
        )

        import os as _os
        if _os.environ.get("SALMALM_PLANNING", "0") == "1":
            if classification["intent"] in ("code", "analysis") and classification.get("score", 0) >= 2:
                plan_msg = {"role": "system", "content": self.PLAN_PROMPT, "_plan_injected": True}
                for i in range(len(session.messages) - 1, -1, -1):
                    if session.messages[i].get("role") == "user":
                        session.messages.insert(i, plan_msg)
                        break

        try:
            return await self._execute_loop(
                session, user_message, model_override, on_tool, classification, tier,
                on_token=on_token, on_status=on_status,
            )
        except Exception as e:
            import traceback
            log.error(f"Engine.run error: {e}")
            traceback.print_exc()
            friendly = _friendly_error(e)
            session.add_assistant(friendly)
            try:
                from salmalm.features.hooks import hook_manager
                hook_manager.fire("on_error", {"session_id": getattr(session, "id", ""), "message": friendly})
            except Exception as _exc:
                log.debug(f"Suppressed: {_exc}")
            return friendly
        finally:
            session.messages = [m for m in session.messages if not m.get("_plan_injected")]


# ── Lazy singleton ──────────────────────────────────────────────────────────
# Created on first access, NOT at import time, to avoid ThreadPoolExecutor
# side-effects when consumers import this module for type hints only.
_engine: Optional[IntelligenceEngine] = None
_engine_lock = threading.Lock()


def _get_engine() -> IntelligenceEngine:
    """Return the module-level singleton, creating it on first call."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = IntelligenceEngine()
    return _engine
