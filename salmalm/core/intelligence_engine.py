"""IntelligenceEngine — core AI reasoning implementation.

Separated from engine.py to break the circular import between engine.py
and engine_pipeline.py, and to eliminate import-time side-effects
(ThreadPoolExecutor creation, singleton init) on every consumer.

Consumers should import from salmalm.core.engine for backward compat.
Direct imports from this module are also supported.
"""

from __future__ import annotations

import asyncio
import json as _json
import os as _os
import threading
import traceback as _traceback
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
        "web_fetch": 6_000, "read_file": 10_000, "rag_search": 4_000,
        "system_monitor": 2_000, "canvas": 2_000, "web_search": 4_000,
        "weather": 2_000, "google_calendar": 3_000, "gmail": 4_000,
        "email_inbox": 4_000, "email_read": 4_000, "email_search": 4_000,
        "calendar_list": 3_000, "node_manage": 4_000, "file_index": 4_000,
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

    # Paths that must never be pre-summarized — even if PRESUMMARY=1
    _PRESUMMARY_PATH_BLOCKLIST = _re.compile(
        r"(?i)(vault|auth\.db|audit\.db|\.env|secret|credential|token|password|keyring|\.ssh|\.gnupg)",
    )
    # Content patterns indicating the file is sensitive — skip summarization
    _PRESUMMARY_CONTENT_BLOCKLIST = _re.compile(
        r"(?i)(api[_-]?key|secret[_\s]*=|token[_\s]*=|password[_\s]*=|BEGIN (RSA|EC|PRIVATE|CERTIFICATE)|SK-|sk-|AKIA[0-9A-Z]{16})",
    )

    def _truncate_tool_result(self, result: str, tool_name: str = "", tool_args: dict | None = None) -> str:
        """Pure truncation — no LLM calls. Safe to call from any thread or async context.
        Presummary (LLM-based) is handled separately in _presummary_if_needed() from
        the async context to avoid blocking thread-pool workers.
        """
        result = self._redact_secrets(result)
        limit = self._TOOL_TRUNCATE_LIMITS.get(tool_name, self.MAX_TOOL_RESULT_CHARS)
        if len(result) > limit:
            return result[:limit] + f"\n\n... [truncated: {len(result)} chars, limit {limit}]"
        return result

    def _should_presummary(self, result: str, tool_name: str, tool_args: dict | None = None) -> bool:
        """Check presummary eligibility without performing any I/O."""
        if _os.environ.get("SALMALM_FILE_PRESUMMARY", "0") != "1":
            return False
        if tool_name not in ("read_file", "web_fetch") or len(result) <= 5000:
            return False
        _path = str((tool_args or {}).get("path", (tool_args or {}).get("url", "")))
        if self._PRESUMMARY_PATH_BLOCKLIST.search(_path):
            log.debug(f"[PRESUMMARY] Blocked path: {_path!r}")
            return False
        if self._PRESUMMARY_CONTENT_BLOCKLIST.search(result[:2000]):
            log.debug("[PRESUMMARY] Blocked: sensitive content pattern detected")
            return False
        return True

    async def _presummary_tool_outputs(self, tool_outputs: dict, valid_tools: list) -> dict:
        """Apply LLM presummary to eligible tool outputs from the async context.
        Runs call_llm in asyncio.to_thread to avoid blocking the event loop.
        """
        if _os.environ.get("SALMALM_FILE_PRESUMMARY", "0") != "1":
            return tool_outputs

        tc_map = {tc["id"]: tc for tc in valid_tools}
        for tc_id, raw in list(tool_outputs.items()):
            tc = tc_map.get(tc_id)
            if not tc or not isinstance(raw, str):
                continue
            if not self._should_presummary(raw, tc["name"], tc.get("arguments")):
                continue
            try:
                from salmalm.core.llm import call_llm

                def _do_summary():
                    return call_llm(
                        model="anthropic/claude-haiku-3.5-20241022",
                        messages=[{"role": "user", "content": f"Summarize concisely (no added commentary):\n\n{raw[:15000]}"}],
                        max_tokens=1024, tools=None,
                    )

                summary = await asyncio.to_thread(_do_summary)
                if summary.get("content"):
                    tool_outputs[tc_id] = f"[Pre-summarized — original {len(raw)} chars]\n\n{summary['content']}"
            except Exception as _exc:
                log.debug(f"[PRESUMMARY] Suppressed: {_exc}")
        return tool_outputs

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
            with session._messages_lock:
                session.messages.append({"role": "assistant", "content": content_blocks})
            session.add_tool_results(
                [{"tool_use_id": tc["id"], "content": tool_outputs[tc["id"]]} for tc in tool_calls]
            )
        else:
            asst_tool_calls = [{
                "id": tc["id"], "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": _json.dumps(tc["arguments"]) if isinstance(tc["arguments"], dict) else str(tc["arguments"]),
                },
            } for tc in tool_calls]
            with session._messages_lock:
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
        if _os.environ.get("SALMALM_REFLECT", "0") != "1":
            return False
        # Guard: reflection is meaningless at high iteration counts — something is
        # already wrong. Use MAX_TOOL_ITERATIONS - 5 as cutoff (not a hardcoded 20).
        return (
            classification["intent"] in ("code", "analysis")
            and iteration < self.MAX_TOOL_ITERATIONS - 5
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

    @staticmethod
    def _role_aware_trim(messages: list, keep_last_exchanges: int) -> list:
        """Trim messages while preserving structural integrity.

        Rules:
        1. System messages (role="system") are always kept at the front.
        2. Tool call sequences are kept atomic:
           - An assistant message with tool_calls must stay with its following
             role="tool" messages (same tool_call_id chain).
        3. We keep the last `keep_last_exchanges` complete exchanges
           (user → assistant → [tool...] groups), discarding middle history.
        4. Never leave an orphaned tool result without its assistant tool_call.
        """
        if not messages:
            return messages

        sys_msgs = [m for m in messages if m.get("role") == "system"]
        non_sys = [m for m in messages if m.get("role") != "system"]

        # Group non-system messages into atomic exchanges.
        # An exchange starts at each "user" message (or assistant without tool_calls).
        exchanges: list[list] = []
        current: list = []

        for msg in non_sys:
            role = msg.get("role", "")
            if role == "user":
                if current:
                    exchanges.append(current)
                current = [msg]
            elif role == "tool":
                # tool result — always glued to the preceding assistant
                current.append(msg)
            else:
                # assistant (with or without tool_calls)
                current.append(msg)

        if current:
            exchanges.append(current)

        # Keep the last N exchanges
        kept = exchanges[-keep_last_exchanges:] if keep_last_exchanges < len(exchanges) else exchanges

        # Flatten and prepend system
        result = sys_msgs[:1] + [m for group in kept for m in group]
        return result

    async def _handle_token_overflow(self, session, model, tools, max_tokens, thinking, on_status):
        """Three-stage token overflow recovery — each stage is role-aware."""
        log.warning(f"[CUT] Token overflow — compacting {len(session.messages)} messages")

        # Stage A: Semantic compaction (summarise middle turns)
        with session._messages_lock:
            session.messages = compact_messages(session.messages, session=session, on_status=on_status)
        result, _ = await self._call_with_failover(
            session.messages, model=model, tools=tools, max_tokens=max_tokens, thinking=thinking
        )
        if not result.get("error"):
            return result, None

        # Stage B: Role-aware trim — keep last 5 complete exchanges
        if len(session.messages) > 12:
            with session._messages_lock:
                session.messages = self._role_aware_trim(session.messages, keep_last_exchanges=5)
            log.warning(f"[CUT] Stage B (role-aware trim, 5 exchanges) → {len(session.messages)} msgs")
            result, _ = await self._call_with_failover(
                session.messages, model=model, tools=tools, max_tokens=max_tokens, thinking=False
            )
        if not result.get("error"):
            return result, None

        # Stage C: Nuclear — keep last 2 complete exchanges only
        if len(session.messages) > 4:
            with session._messages_lock:
                session.messages = self._role_aware_trim(session.messages, keep_last_exchanges=2)
            log.warning(f"[CUT][CUT] Stage C (nuclear, 2 exchanges) → {len(session.messages)} msgs")
            result, _ = await self._call_with_failover(
                session.messages, model=model, tools=tools, max_tokens=max_tokens
            )
        if not result.get("error"):
            return result, None

        session.add_assistant("⚠️ Context too large. Use /clear to reset.")
        return result, "⚠️ Context too large. Use /clear to reset."

    async def _handle_tool_calls(self, result, session, provider, on_tool, on_status, consecutive_errors, recent_tool_calls):
        from salmalm.core.loop_helpers import validate_tool_calls, check_circuit_breaker, check_loop_detection
        if on_status:
            tool_names = ", ".join(tc["name"] for tc in result["tool_calls"][:3])
            _safe_callback(on_status, STATUS_TOOL_RUNNING, f"🔧 Running {tool_names}...")
        valid_tools, tool_outputs = validate_tool_calls(result["tool_calls"])
        if valid_tools:
            exec_outputs = await asyncio.to_thread(self._execute_tools_parallel, valid_tools, on_tool, session)
            # Presummary runs here (async context, not in thread pool) to avoid blocking workers
            exec_outputs = await self._presummary_tool_outputs(exec_outputs, valid_tools)
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
        with session._messages_lock:
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

        # #6: Wire classification thinking — if classifier recommends thinking AND
        # tier >= 2 (moderate complexity), enable it even if session toggle is off.
        # Session toggle always wins if explicitly ON; classifier supplements it.
        _cls_thinks = classification.get("thinking", False) and classification.get("tier", 1) >= 2
        use_thinking = getattr(session, "thinking_enabled", False) or _cls_thinks
        if _cls_thinks and not getattr(session, "thinking_enabled", False):
            log.info(f"[AI] Classifier activated thinking (tier={classification.get('tier')}, budget={classification.get('thinking_budget')})")
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
            # thinking_level: user-set wins; fallback to classifier budget hint
            _sess_think_level = getattr(session, "thinking_level", "medium")
            _cls_budget = classification.get("thinking_budget", 4000)
            _cls_level = "low" if _cls_budget <= 4000 else "medium" if _cls_budget <= 10000 else "high"
            _think_level = _sess_think_level if getattr(session, "thinking_enabled", False) else _cls_level
            _think_eligible = use_thinking and iteration == 0 and any(x in model for x in ("opus", "sonnet", "o3", "o4"))
            think_this_call = _think_level if _think_eligible else False
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

            _tool_calls = result.get("tool_calls")
            _has_tools = isinstance(_tool_calls, list) and len(_tool_calls) > 0

            if _has_tools:
                break_msg, consecutive_errors = await self._handle_tool_calls(
                    result, session, provider, on_tool, on_status, consecutive_errors, _recent_tool_calls,
                )
                if break_msg:
                    return break_msg
                if len(session.messages) > 40:
                    with session._messages_lock:
                        session.messages = compact_messages(session.messages, session=session, on_status=on_status)
                    log.info(f"[CUT] Mid-loop compaction → {len(session.messages)} msgs")
                iteration += 1
                continue

            # tool_calls = [] (empty list, not None) AND content empty → don't re-call LLM
            if isinstance(_tool_calls, list) and not _tool_calls and not result.get("content", "").strip():
                log.warning("[AI] Empty tool_calls + empty content — aborting loop to prevent extra LLM call")
                result["content"] = "(No response from model.)"

            return await self._finalize_loop_response(
                result, session, pruned_messages, model, tools,
                user_message, classification, iteration, _failover_warn,
            )

        log.warning(f"[BREAK] Max iterations ({_max_iter}) reached")
        response = result.get("content") or "Reached maximum tool iterations. Please try a simpler request."
        session.add_assistant(response)
        with session._messages_lock:
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
            log.error(f"Engine.run error: {e}")
            _traceback.print_exc()
            friendly = _friendly_error(e)
            session.add_assistant(friendly)
            try:
                from salmalm.features.hooks import hook_manager
                hook_manager.fire("on_error", {"session_id": getattr(session, "id", ""), "message": friendly})
            except Exception as _exc:
                log.debug(f"Suppressed: {_exc}")
            return friendly
        finally:
            with session._messages_lock:
                session.messages = [m for m in session.messages if not m.get("_plan_injected")]


# ── Lazy singleton ──────────────────────────────────────────────────────────
# Created on first access, NOT at import time, to avoid ThreadPoolExecutor
# side-effects when consumers import this module for type hints only.
_engine: Optional[IntelligenceEngine] = None
_engine_lock = threading.Lock()

# Thinking budget map — referenced by engine_pipeline and external callers
_THINKING_BUDGET_MAP: dict[str, int] = {"low": 4000, "medium": 10000, "high": 16000, "xhigh": 32000}


def _get_engine() -> IntelligenceEngine:
    """Return the module-level singleton, creating it on first call."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = IntelligenceEngine()
    return _engine
