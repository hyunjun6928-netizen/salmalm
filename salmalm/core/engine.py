"""SalmAlm Intelligence Engine — TaskClassifier + IntelligenceEngine + process_message."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple  # noqa: F401

from salmalm.constants import (VERSION, INTENT_SHORT_MSG, INTENT_COMPLEX_MSG,  # noqa: F401
                               INTENT_CONTEXT_DEPTH, REFLECT_SNIPPET_LEN,
                               MODEL_ALIASES as _CONST_ALIASES, COMMAND_MODEL)  # noqa: F401
import re as _re
import threading as _threading
import time as _time
from salmalm.security.crypto import log
from salmalm.core.cost import (  # noqa: F401
    estimate_tokens, estimate_cost, MODEL_PRICING,
    get_pricing as _get_pricing,
)

# Graceful shutdown state
_shutting_down = False
_active_requests = 0
_active_requests_lock = _threading.Lock()
_active_requests_event = _threading.Event()  # signaled when _active_requests == 0
from salmalm.core import router, compact_messages, get_session, _sessions, _metrics, compact_session, auto_compact_if_needed, audit_log  # noqa: F401
from salmalm.core.prompt import build_system_prompt
from salmalm.tools.tool_handlers import execute_tool

# ── Imports from extracted modules ──
from salmalm.core.session_manager import (  # noqa: F401
    _should_prune_for_cache, _record_api_call_time, prune_context,
    _has_image_block, _soft_trim, estimate_context_window,
    _PRUNE_KEEP_LAST_ASSISTANTS, _PRUNE_SOFT_LIMIT, _PRUNE_HARD_LIMIT, _PRUNE_HEAD,
)
from salmalm.core.llm_loop import (  # noqa: F401
    _call_llm_async, _call_llm_streaming,
    _load_failover_config, _load_cooldowns, _save_cooldowns,
    _is_model_cooled_down, _record_model_failure, _clear_model_cooldown,
    get_failover_config, save_failover_config,
    call_with_failover as _call_with_failover_fn,
    try_llm_call as _try_llm_call_fn,
    STATUS_TYPING, STATUS_THINKING, STATUS_TOOL_RUNNING,
)

# Keep _PRUNE_TAIL for backward compat
_PRUNE_TAIL = 500

# ============================================================
# Model aliases — sourced from constants.py (single source of truth)
MODEL_ALIASES = {'auto': None, **_CONST_ALIASES}

# Multi-model routing: cost-optimized model selection
# ── Model selection (extracted to core/model_selection.py) ──
from salmalm.core.model_selection import (  # noqa: F401
    select_model as _select_model_impl,
    fix_model_name as _fix_model_name,
    load_routing_config as _load_routing_config,
    save_routing_config as _save_routing_config,
    _SIMPLE_PATTERNS, _MODERATE_KEYWORDS, _COMPLEX_KEYWORDS,
    _MODEL_NAME_FIXES,
)
from salmalm.constants import MODELS as _MODELS  # noqa: F401

# Backward-compat re-exports
get_routing_config = _load_routing_config


# _select_model delegates to core/model_selection.py (backward compat)
_select_model = _select_model_impl


_main_loop = None  # Captured by process_message for cross-thread scheduling


def _safe_callback(cb, *args):
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
            if _main_loop and _main_loop.is_running():
                asyncio.run_coroutine_threadsafe(result, _main_loop)
            else:
                result.close()


class TaskClassifier:
    """Classify user intent to determine execution strategy."""

    # Intent categories with weighted keywords
    INTENTS = {
        'code': {'keywords': ['code', '코드', 'implement', '구현', 'function', 'class',
                              'bug', '버그', 'fix', '수정', 'refactor', '리팩', 'debug', '디버그',
                              'API', 'server', '서버', 'deploy', '배포', 'build', '빌드',
                              '개발', '코딩', '프로그래밍'],
                 'tier': 3, 'thinking': False},
        'analysis': {'keywords': ['analyze', '분석', 'compare', '비교', 'review', '리뷰',
                                  'audit', '감사', 'security', '보안', 'performance', '성능',
                                  '검토', '조사', '평가', '진단'],
                     'tier': 3, 'thinking': False},
        'creative': {'keywords': ['write', '작성', 'story', '이야기', 'poem', '시',
                                  'translate', '번역', 'summarize', '요약', '글'],
                     'tier': 2, 'thinking': False},
        'search': {'keywords': ['search', '검색', 'find', '찾', 'news', '뉴스',
                                'latest', '최신', 'weather', '날씨', 'price', '가격'],
                   'tier': 2, 'thinking': False},
        'system': {'keywords': ['file', '파일', 'exec', 'run', '실행', 'install', '설치',
                                'process', '프로세스', 'disk', '디스크', 'memory', '메모리'],
                   'tier': 2, 'thinking': False},
        'memory': {'keywords': ['remember', '기억', 'memo', '메모', 'record', '기록',
                                'diary', '일지', 'learn', '학습'],
                   'tier': 1, 'thinking': False},
        'chat': {'keywords': [], 'tier': 1, 'thinking': False},
    }

    @classmethod
    def classify(cls, message: str, context_len: int = 0) -> Dict[str, Any]:
        """Classify user message intent and determine processing tier."""
        msg = message.lower()
        msg_len = len(message)
        scores = {}
        for intent, info in cls.INTENTS.items():
            score = sum(2 for kw in info['keywords'] if kw in msg)  # type: ignore[attr-defined, misc]
            if intent == 'code' and any(c in message for c in ['```', 'def ', 'class ', '{', '}']):
                score += 3
            if intent in ('code', 'analysis') and 'github.com' in msg:
                score += 3
            scores[intent] = score

        best = max(scores, key=scores.get) if any(scores.values()) else 'chat'  # type: ignore[arg-type]
        if scores[best] == 0:
            best = 'chat'

        info = cls.INTENTS[best]
        # Escalate tier for long/complex messages
        tier = info['tier']
        if msg_len > INTENT_SHORT_MSG:
            tier = max(tier, 2)  # type: ignore[call-overload]
        if msg_len > INTENT_COMPLEX_MSG or context_len > INTENT_CONTEXT_DEPTH:
            tier = max(tier, 3)  # type: ignore[call-overload]

        # Adaptive thinking budget
        thinking = info['thinking']
        thinking_budget = 0
        if thinking:
            if msg_len < 300:
                thinking_budget = 5000
            elif msg_len < 1000:
                thinking_budget = 10000
            else:
                thinking_budget = 16000

        return {
            'intent': best, 'tier': tier, 'thinking': thinking,
            'thinking_budget': thinking_budget,
            'score': scores[best],
        }


# ── Intent-based tool selection (token optimization) ──
INTENT_TOOLS = {
    'chat': [],
    'memory': [],
    'creative': [],
    'code': ['exec', 'read_file', 'write_file', 'edit_file', 'diff_files',
             'python_eval', 'sub_agent', 'system_monitor', 'skill_manage'],
    'analysis': ['web_search', 'web_fetch', 'read_file', 'rag_search',
                 'python_eval', 'exec', 'http_request'],
    'search': ['web_search', 'web_fetch', 'rag_search', 'http_request',
               'brave_search', 'brave_context'],
    'system': ['exec', 'read_file', 'write_file', 'edit_file',
               'system_monitor', 'cron_manage', 'health_check', 'plugin_manage'],
}

# Extra tools injected by keyword detection in the user message
_KEYWORD_TOOLS = {
    'calendar': ['google_calendar', 'calendar_list', 'calendar_add', 'calendar_delete'],
    '일정': ['google_calendar', 'calendar_list', 'calendar_add', 'calendar_delete'],
    'email': ['gmail', 'email_inbox', 'email_read', 'email_send', 'email_search'],
    '메일': ['gmail', 'email_inbox', 'email_read', 'email_send', 'email_search'],
    'remind': ['reminder', 'notification'],
    '알림': ['reminder', 'notification'],
    '알려줘': ['reminder', 'notification'],
    'image': ['image_generate', 'image_analyze', 'screenshot'],
    '이미지': ['image_generate', 'image_analyze', 'screenshot'],
    '사진': ['image_generate', 'image_analyze', 'screenshot'],
    'tts': ['tts', 'tts_generate'],
    '음성': ['tts', 'tts_generate', 'stt'],
    'weather': ['weather'],
    '날씨': ['weather'],
    'rss': ['rss_reader'],
    'translate': ['translate'],
    '번역': ['translate'],
    'qr': ['qr_code'],
    'expense': ['expense'],
    '지출': ['expense'],
    'note': ['note'],
    '메모': ['note', 'memory_read', 'memory_write', 'memory_search'],
    'bookmark': ['save_link'],
    '북마크': ['save_link'],
    'pomodoro': ['pomodoro'],
    'routine': ['routine'],
    'briefing': ['briefing'],
    'browser': ['browser'],
    'node': ['node_manage'],
    'mcp': ['mcp_manage'],
    'workflow': ['workflow'],
    'file_index': ['file_index'],
    'clipboard': ['clipboard'],
    'settings': ['ui_control'],
    '설정': ['ui_control'],
    'theme': ['ui_control'],
    '테마': ['ui_control'],
    'dark mode': ['ui_control'],
    'light mode': ['ui_control'],
    '다크모드': ['ui_control'],
    '라이트모드': ['ui_control'],
    'language': ['ui_control'],
    '언어': ['ui_control'],
}

# Dynamic max_tokens per intent
INTENT_MAX_TOKENS = {
    'chat': 1024,
    'memory': 1024,
    'creative': 1024,
    'search': 2048,
    'analysis': 2048,
    'code': 4096,
    'system': 2048,
}

# Keywords that trigger higher max_tokens
_DETAIL_KEYWORDS = {'자세히', '상세', 'detail', 'detailed', 'verbose', 'explain',
                    '설명', 'thorough', '구체적'}


def _get_dynamic_max_tokens(intent: str, user_message: str) -> int:
    """Return max_tokens based on intent + user request."""
    base = INTENT_MAX_TOKENS.get(intent, 2048)
    msg_lower = user_message.lower()
    if any(kw in msg_lower for kw in _DETAIL_KEYWORDS):
        return max(base, 4096)
    return base


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

    def __init__(self):
        self._tool_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='tool')

    def _get_tools_for_provider(self, provider: str, intent: str = None,
                                user_message: str = '') -> list:
        from salmalm.tools import TOOL_DEFINITIONS
        from salmalm.core import PluginLoader
        from salmalm.features.mcp import mcp_manager
        # Merge built-in + plugin + MCP tools (deduplicate by name)
        all_tools = list(TOOL_DEFINITIONS)
        seen = {t['name'] for t in all_tools}
        for t in PluginLoader.get_all_tools() + mcp_manager.get_all_tools():
            if t['name'] not in seen:
                all_tools.append(t)
                seen.add(t['name'])

        # ── Dynamic tool selection: core + intent + keyword matched ──
        # Always include core tools (memory, file, exec basics) to prevent
        # intent misclassification from breaking functionality.
        # Then add intent-specific + keyword-matched tools on top.
        _CORE_TOOLS = {
            'read_file', 'write_file', 'edit_file', 'exec', 'exec_session',
            'memory_read', 'memory_write', 'memory_search',
            'web_search', 'web_fetch', 'sub_agent', 'ui_control',
        }
        selected_names = set(_CORE_TOOLS)
        # Add intent-specific tools
        if intent and intent in INTENT_TOOLS:
            selected_names.update(INTENT_TOOLS[intent])
        # Add keyword-matched tools
        if user_message:
            msg_lower = user_message.lower()
            for kw, tool_names in _KEYWORD_TOOLS.items():
                if kw in msg_lower:
                    selected_names.update(tool_names)
        # Filter: only include tools that exist in all_tools
        all_tools = [t for t in all_tools if t['name'] in selected_names]

        if provider == 'google':
            return [{'name': t['name'], 'description': t['description'],
                     'parameters': t['input_schema']} for t in all_tools]
        elif provider in ('openai', 'xai', 'deepseek', 'meta-llama'):
            return [{'name': t['name'], 'description': t['description'],
                     'parameters': t['input_schema']} for t in all_tools]
        elif provider == 'anthropic':
            return [{'name': t['name'], 'description': t['description'],
                     'input_schema': t['input_schema']} for t in all_tools]
        return all_tools

    # Max chars per tool result sent to LLM context (default + per-type overrides)
    MAX_TOOL_RESULT_CHARS = 50_000
    # Aggressive truncation for tools that produce verbose/binary output
    _TOOL_TRUNCATE_LIMITS = {
        'exec': 20_000,          # Shell output can be huge
        'exec_session': 10_000,  # Background session output
        'sandbox_exec': 20_000,
        'python_eval': 15_000,
        'browser': 10_000,       # HTML/accessibility trees
        'http_request': 15_000,  # API responses
        'web_fetch': 15_000,
        'read': 30_000,          # File content
        'rag_search': 10_000,    # Search results
        'system_info': 5_000,
        'canvas': 5_000,
    }
    # Per-tool hard timeout (seconds) — total wall-clock including subprocess/IO
    _TOOL_TIMEOUTS = {
        'exec': 120,
        'exec_session': 10,      # Just submits, doesn't wait
        'sandbox_exec': 60,
        'python_eval': 30,
        'browser': 90,
        'http_request': 30,
        'web_fetch': 30,
        'mesh': 60,
        'image_generate': 120,
    }
    _DEFAULT_TOOL_TIMEOUT = 60

    # Patterns that look like leaked secrets in tool output
    _SECRET_OUTPUT_RE = _re.compile(
        r'(?i)(?:'
        r'(?:sk|pk|api|key|token|secret|bearer|ghp|gho|pypi)-[A-Za-z0-9_\-]{20,}'
        r'|AKIA[0-9A-Z]{16}'              # AWS access key
        r'|AIza[0-9A-Za-z_\-]{35}'        # Google API key
        r'|(?:ghp|gho|ghu|ghs|ghr)_\w{36,}'  # GitHub tokens
        r'|pypi-[A-Za-z0-9_\-]{50,}'      # PyPI tokens
        r'|sk-(?:ant-)?[A-Za-z0-9_\-]{20,}'  # OpenAI/Anthropic keys
        r'|xai-[A-Za-z0-9_\-]{20,}'       # xAI keys
        r')'
    )

    def _redact_secrets(self, text: str) -> str:
        """Scrub anything that looks like a leaked API key/token from output."""
        return self._SECRET_OUTPUT_RE.sub('[REDACTED]', text) if text else text

    def _truncate_tool_result(self, result: str, tool_name: str = '') -> str:
        """Truncate tool result based on tool type to prevent context explosion."""
        result = self._redact_secrets(result)
        limit = self._TOOL_TRUNCATE_LIMITS.get(tool_name, self.MAX_TOOL_RESULT_CHARS)
        if len(result) > limit:
            return result[:limit] + \
                f'\n\n... [truncated: {len(result)} chars total, limit {limit} for {tool_name or "default"}]'
        return result

    def _get_tool_timeout(self, tool_name: str) -> int:
        """Get hard timeout for a tool (total wall-clock)."""
        return self._TOOL_TIMEOUTS.get(tool_name, self._DEFAULT_TOOL_TIMEOUT)

    def _execute_tools_parallel(self, tool_calls: list, on_tool=None) -> dict:
        """Execute multiple tools in parallel, return {id: result}."""
        for tc in tool_calls:
            if on_tool:
                _safe_callback(on_tool, tc['name'], tc['arguments'])

        # Fire on_tool_call hook for each tool (도구 호출 훅)
        try:
            from salmalm.features.hooks import hook_manager
            for tc in tool_calls:
                hook_manager.fire('on_tool_call', {
                    'session_id': '', 'message': f"{tc['name']}: {str(tc.get('arguments', ''))[:200]}"
                })
        except Exception:
            pass

        if len(tool_calls) == 1:
            tc = tool_calls[0]
            _metrics['tool_calls'] += 1
            t0 = _time.time()
            try:
                result = self._truncate_tool_result(
                    execute_tool(tc['name'], tc['arguments']), tool_name=tc['name'])
                elapsed = _time.time() - t0
                audit_log('tool_call', f"{tc['name']}: ok ({elapsed:.2f}s)",
                          detail_dict={'tool': tc['name'],
                                       'args_summary': str(tc['arguments'])[:200],
                                       'elapsed_s': round(elapsed, 3),
                                       'success': True})
            except Exception as e:
                elapsed = _time.time() - t0
                _metrics['tool_errors'] += 1
                result = f'❌ Tool execution error: {e}'
                audit_log('tool_call', f"{tc['name']}: error ({e})",
                          detail_dict={'tool': tc['name'],
                                       'args_summary': str(tc['arguments'])[:200],
                                       'elapsed_s': round(elapsed, 3),
                                       'success': False, 'error': str(e)[:200]})
            return {tc['id']: result}

        futures = {}
        start_times = {}
        for tc in tool_calls:
            _metrics['tool_calls'] += 1
            start_times[tc['id']] = _time.time()
            f = self._tool_executor.submit(execute_tool, tc['name'], tc['arguments'])
            futures[tc['id']] = (f, tc)
        outputs = {}
        for tc_id, (f, tc) in futures.items():
            try:
                _tool_timeout = self._get_tool_timeout(tc['name'])
                outputs[tc_id] = self._truncate_tool_result(
                    f.result(timeout=_tool_timeout), tool_name=tc['name'])
                elapsed = _time.time() - start_times[tc_id]
                audit_log('tool_call', f"{tc['name']}: ok ({elapsed:.2f}s)",
                          detail_dict={'tool': tc['name'],
                                       'args_summary': str(tc['arguments'])[:200],
                                       'elapsed_s': round(elapsed, 3), 'success': True})
            except Exception as e:
                elapsed = _time.time() - start_times[tc_id]
                _metrics['tool_errors'] += 1
                outputs[tc_id] = f'❌ Tool execution error: {e}'
                audit_log('tool_call', f"{tc['name']}: error",
                          detail_dict={'tool': tc['name'],
                                       'args_summary': str(tc['arguments'])[:200],
                                       'elapsed_s': round(elapsed, 3),
                                       'success': False, 'error': str(e)[:200]})
        log.info(f"[FAST] Parallel: {len(tool_calls)} tools completed")
        return outputs

    def _append_tool_results(self, session, provider, result, tool_calls, tool_outputs):
        """Append tool call + results to session messages."""
        if provider == 'anthropic':
            content_blocks = []
            if result.get('content'):
                content_blocks.append({'type': 'text', 'text': result['content']})
            for tc in tool_calls:
                content_blocks.append({
                    'type': 'tool_use', 'id': tc['id'],
                    'name': tc['name'], 'input': tc['arguments']
                })
            session.messages.append({'role': 'assistant', 'content': content_blocks})
            session.add_tool_results([
                {'tool_use_id': tc['id'], 'content': tool_outputs[tc['id']]}
                for tc in tool_calls
            ])
        else:
            session.add_assistant(result.get('content', ''))
            for tc in tool_calls:
                session.messages.append({
                    'role': 'tool', 'tool_call_id': tc['id'],
                    'name': tc['name'], 'content': tool_outputs[tc['id']]
                })

    def _should_reflect(self, classification: dict, response: str, iteration: int) -> bool:
        """Determine if response needs self-reflection pass."""
        import os as _os
        if _os.environ.get('SALMALM_REFLECT', '1') == '0':
            return False
        # Only reflect on complex tasks with significant responses
        if classification['intent'] not in ('code', 'analysis'):
            return False
        if iteration > 20:  # Already iterated a lot
            return False
        if len(response) < 100:  # Too short to be code/analysis
            return False
        if classification.get('score', 0) >= 3:  # High confidence complex task
            return True
        return False

    async def _call_with_failover(self, messages, model, tools=None,
                                  max_tokens=4096, thinking=False,
                                  on_token=None, on_status=None):
        """LLM call with automatic failover on failure. Delegates to llm_loop."""
        return await _call_with_failover_fn(
            messages, model, tools=tools, max_tokens=max_tokens,
            thinking=thinking, on_token=on_token, on_status=on_status)

    async def _try_llm_call(self, messages, model, tools, max_tokens, thinking, on_token):
        """Single LLM call attempt. Delegates to llm_loop."""
        model = _fix_model_name(model)
        return await _try_llm_call_fn(messages, model, tools, max_tokens, thinking, on_token)

    async def run(self, session: object, user_message: str,
                  model_override: Optional[str] = None, on_tool: Optional[object] = None,
                  classification: Optional[Dict[str, Any]] = None,
                  on_token: Optional[object] = None, on_status: Optional[object] = None) -> str:
        """Main execution loop — Plan → Execute → Reflect."""

        if not classification:
            classification = TaskClassifier.classify(
                user_message, len(session.messages))

        tier = classification['tier']
        use_thinking = classification['thinking']
        thinking_budget = classification['thinking_budget']
        log.info(f"[AI] Intent: {classification['intent']} (tier={tier}, "
                 f"think={use_thinking}, budget={thinking_budget}, "
                 f"score={classification.get('score', 0)})")

        # PHASE 1: PLANNING — inject plan prompt for complex tasks
        if classification['intent'] in ('code', 'analysis') and classification.get('score', 0) >= 2:
            # Inject planning instruction before the last user message
            plan_msg = {'role': 'system', 'content': self.PLAN_PROMPT, '_plan_injected': True}
            # Find the last user message index to insert before it
            last_user_idx = None
            for i in range(len(session.messages) - 1, -1, -1):
                if session.messages[i].get('role') == 'user':
                    last_user_idx = i
                    break
            if last_user_idx is not None:
                session.messages.insert(last_user_idx, plan_msg)
            else:
                session.messages.insert(-1, plan_msg)

        # PHASE 2: EXECUTE — tool loop
        try:
            return await self._execute_loop(session, user_message, model_override,  # type: ignore[no-any-return]
                                            on_tool, classification, tier,
                                            on_token=on_token, on_status=on_status)
        except Exception as e:
            log.error(f"Engine.run error: {e}")
            import traceback
            traceback.print_exc()
            error_msg = f'❌ Processing error: {type(e).__name__}: {e}'
            session.add_assistant(error_msg)
            # Fire on_error hook (에러 발생 훅)
            try:
                from salmalm.features.hooks import hook_manager
                hook_manager.fire('on_error', {'session_id': getattr(session, 'id', ''), 'message': error_msg})
            except Exception:
                pass
            return error_msg

    # ── OpenClaw-style limits ──
    MAX_TOOL_ITERATIONS = 15
    MAX_CONSECUTIVE_ERRORS = 3

    async def _execute_loop(self, session, user_message, model_override,
                            on_tool, classification, tier, on_token=None,
                            on_status=None):
        use_thinking = getattr(session, 'thinking_enabled', False)
        _thinking_budget = 10000 if use_thinking else 0
        iteration = 0
        consecutive_errors = 0
        _session_id = getattr(session, 'id', '')
        while iteration < self.MAX_TOOL_ITERATIONS:
            # Abort check (생성 중지 체크) — LibreChat style
            from salmalm.features.edge_cases import abort_controller
            if abort_controller.is_aborted(_session_id):
                partial = abort_controller.get_partial(_session_id) or ''
                abort_controller.clear(_session_id)
                response = (partial + '\n\n⏹ [생성 중단됨 / Generation aborted]').strip()
                session.add_assistant(response)
                log.info(f"[ABORT] Generation aborted: session={_session_id}")
                return response
            model = model_override or router.route(
                user_message, has_tools=True, iteration=iteration)

            # Force tier upgrade for complex tasks
            if not model_override and tier == 3 and iteration == 0:
                model = router._pick_available(3)
            elif not model_override and tier == 2 and iteration == 0:
                model = router._pick_available(2)

            provider = model.split('/')[0] if '/' in model else 'anthropic'

            # Always provide tools — let the LLM decide what to use
            # Intent/keyword filtering was too restrictive (chat/memory/creative got no tools)
            tools = self._get_tools_for_provider(provider, intent=classification['intent'],
                                                 user_message=user_message or '')

            # Use thinking for first call on complex tasks
            think_this_call = (use_thinking and iteration == 0
                               and provider == 'anthropic'
                               and ('opus' in model or 'sonnet' in model))

            # Session pruning — only when cache TTL expired (preserves Anthropic prompt cache)
            if _should_prune_for_cache():
                _ctx_win = estimate_context_window(model)
                pruned_messages, prune_stats = prune_context(
                    session.messages, context_window_tokens=_ctx_win)
                if prune_stats['soft_trimmed'] or prune_stats['hard_cleared']:
                    log.info(f"[PRUNE] soft={prune_stats['soft_trimmed']} hard={prune_stats['hard_cleared']}")
            else:
                pruned_messages = session.messages
                prune_stats = {'soft_trimmed': 0, 'hard_cleared': 0, 'unchanged': 0}

            # Status callback: typing/thinking
            if on_status:
                if think_this_call:
                    _safe_callback(on_status, STATUS_THINKING, '🧠 Thinking...')
                else:
                    _safe_callback(on_status, STATUS_TYPING, 'typing')

            # Dynamic max_tokens based on intent
            _dynamic_max_tokens = _get_dynamic_max_tokens(
                classification['intent'], user_message or '')

            # LLM call with failover
            _failover_warn = None
            result, _failover_warn = await self._call_with_failover(
                pruned_messages, model=model, tools=tools,
                max_tokens=_dynamic_max_tokens, thinking=think_this_call,
                on_token=on_token, on_status=on_status)
            # Clean internal flag
            result.pop('_failed', None)
            # Record API call time for cache TTL tracking
            _record_api_call_time()

            # ── Token overflow: use compaction first, then aggressive truncation ──
            if result.get('error') == 'token_overflow':
                msg_count = len(session.messages)
                log.warning(f"[CUT] Token overflow with {msg_count} messages — running compaction")

                # Stage A: Try proper compaction first
                session.messages = compact_messages(
                    session.messages, session=session, on_status=on_status)
                result, _ = await self._call_with_failover(
                    session.messages, model=model, tools=tools,
                    max_tokens=_dynamic_max_tokens, thinking=think_this_call)

                if result.get('error') == 'token_overflow' and len(session.messages) > 12:
                    # Stage B: Force truncation — keep system + last 10
                    system_msgs = [m for m in session.messages if m['role'] == 'system'][:1]
                    session.messages = system_msgs + session.messages[-10:]
                    log.warning(f"[CUT] Post-compaction truncation: -> {len(session.messages)} msgs")
                    result, _ = await self._call_with_failover(
                        session.messages, model=model, tools=tools,
                        max_tokens=_dynamic_max_tokens, thinking=False)

                if result.get('error') == 'token_overflow' and len(session.messages) > 4:
                    # Stage C: Nuclear — keep only last 4
                    system_msgs = [m for m in session.messages if m['role'] == 'system'][:1]
                    session.messages = (system_msgs or []) + session.messages[-4:]
                    log.warning(f"[CUT][CUT] Nuclear truncation: -> {len(session.messages)} msgs")
                    result, _ = await self._call_with_failover(
                        session.messages, model=model, tools=tools,
                        max_tokens=_dynamic_max_tokens)

                if result.get('error'):
                    session.add_assistant("⚠️ Context too large. Use /clear to reset.")
                    return "⚠️ Context too large. Use /clear to reset."

            # Record usage for /usage command
            usage = result.get('usage', {})
            record_response_usage(_session_id, result.get('model', model), usage)

            # Audit API call
            api_detail = {
                'model': result.get('model', model),
                'input_tokens': usage.get('input', 0),
                'output_tokens': usage.get('output', 0),
                'iteration': iteration,
            }
            if usage.get('input', 0) or usage.get('output', 0):
                audit_log('api_call', f"{model} in={usage.get('input', 0)} out={usage.get('output', 0)}",
                          detail_dict=api_detail)
                # Detailed usage tracking (LibreChat style)
                try:
                    from salmalm.features.edge_cases import usage_tracker
                    _inp, _out = usage.get('input', 0), usage.get('output', 0)
                    _cost = estimate_cost(model, usage)
                    usage_tracker.record(_session_id, model, _inp, _out, _cost,
                                         classification.get('intent', ''))
                except Exception:
                    pass

            if result.get('thinking'):
                log.info(f"[AI] Thinking: {len(result['thinking'])} chars")

            if result.get('tool_calls'):
                # Status: tool running
                if on_status:
                    tool_names = ', '.join(tc['name'] for tc in result['tool_calls'][:3])
                    _safe_callback(on_status, STATUS_TOOL_RUNNING, f'🔧 Running {tool_names}...')

                # Validate tool calls
                valid_tools = []
                tool_outputs = {}
                for tc in result['tool_calls']:
                    # Invalid arguments (not a dict) — try JSON parse
                    if not isinstance(tc.get('arguments'), dict):
                        try:
                            tc['arguments'] = json.loads(tc['arguments']) if isinstance(tc['arguments'], str) else {}
                        except (json.JSONDecodeError, TypeError):
                            tool_outputs[tc['id']] = f"❌ Invalid tool arguments for {tc['name']} / 잘못된 도구 인자"
                            continue
                    valid_tools.append(tc)

                if valid_tools:
                    exec_outputs = await asyncio.to_thread(
                        self._execute_tools_parallel,
                        valid_tools, on_tool)
                    tool_outputs.update(exec_outputs)

                # Circuit breaker: 연속 에러 감지
                errors = sum(1 for v in tool_outputs.values()
                             if '❌' in str(v) or 'error' in str(v).lower())
                if errors > 0:
                    consecutive_errors += errors
                    if consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                        log.warning(f"[BREAK] {consecutive_errors} consecutive tool errors — stopping loop")
                        err_summary = '\n'.join(f"• {v}" for v in tool_outputs.values() if '❌' in str(v))
                        response = f"⚠️ Tool errors detected, stopping:\n{err_summary}"
                        session.add_assistant(response)
                        return response
                else:
                    consecutive_errors = 0

                self._append_tool_results(
                    session, provider, result,
                    result['tool_calls'], tool_outputs)

                # Mid-loop compaction: 메시지 40개 넘으면 즉시 압축
                if len(session.messages) > 40:
                    session.messages = compact_messages(
                        session.messages, session=session, on_status=on_status)
                    log.info(f"[CUT] Mid-loop compaction: -> {len(session.messages)} msgs")

                iteration += 1
                continue

            # Final response
            response = result.get('content', '')

            # ── LLM edge cases ──

            # Empty response: retry up to 2 times with backoff
            if not response or not response.strip():
                for _retry in range(2):
                    log.warning(f"[LLM] Empty response, retry #{_retry + 1}")
                    await asyncio.sleep(0.5 * (_retry + 1))  # 0.5s, 1.0s backoff
                    retry_result, _ = await self._call_with_failover(
                        pruned_messages, model=model, tools=tools,
                        max_tokens=4096, thinking=False)
                    response = retry_result.get('content', '')
                    if response and response.strip():
                        break
                if not response or not response.strip():
                    response = '⚠️ 응답을 생성할 수 없습니다. / Could not generate a response.'

            # Truncated response (max_tokens reached)
            stop_reason = result.get('stop_reason', '')
            if stop_reason == 'max_tokens' or result.get('usage', {}).get('output', 0) >= 4090:
                response += '\n\n⚠️ [응답이 잘렸습니다 / Response was truncated]'

            # Content filter / safety block
            if stop_reason in ('content_filter', 'safety'):
                response = '⚠️ 안전 필터에 의해 응답이 차단되었습니다. / Response blocked by content filter.'

            # PHASE 3: REFLECT — self-evaluation for complex tasks
            if self._should_reflect(classification, response, iteration):
                log.info(f"[SEARCH] Reflection pass on {classification['intent']} response")
                reflect_msgs = [
                    {'role': 'system', 'content': self.REFLECT_PROMPT},
                    {'role': 'user', 'content': f'Original question: {user_message[:REFLECT_SNIPPET_LEN]}'},
                    {'role': 'assistant', 'content': response},
                    {'role': 'user', 'content': 'Evaluate and improve if needed.'}
                ]
                reflect_result = await _call_llm_async(reflect_msgs,
                                                       model=router._pick_available(2),
                                                       max_tokens=4000)
                improved = reflect_result.get('content', '')
                if improved and len(improved) > len(response) * 0.5 and len(improved) > 50:
                    # Only use reflection if it's substantive and not a degradation
                    # Skip if reflection is just "the answer is fine" or similar
                    skip_phrases = ['satisfactory', 'sufficient', 'correct', ]
                    if not any(p in improved[:100].lower() for p in skip_phrases):
                        response = improved
                    log.info(f"[SEARCH] Reflection improved: {len(response)} chars")

            # Prepend failover warning if applicable
            if _failover_warn:
                response = f"{_failover_warn}\n\n{response}"

            session.add_assistant(response)
            log.info(f"[CHAT] Response ({result.get('model', '?')}): {len(response)} chars, "
                     f"iteration {iteration + 1}, intent={classification['intent']}")

            # Clean up planning message if added (use marker, not content comparison)
            session.messages = [m for m in session.messages
                                if not m.get('_plan_injected')]
            return response

        # Loop exhausted — MAX_TOOL_ITERATIONS reached
        log.warning(f"[BREAK] Max iterations ({self.MAX_TOOL_ITERATIONS}) reached")
        response = result.get('content', 'Reached maximum tool iterations. Please try a simpler request.')  # noqa: F821
        if not response:
            response = 'Reached maximum tool iterations. Please try a simpler request.'
        session.add_assistant(response)
        session.messages = [m for m in session.messages if not m.get('_plan_injected')]
        return response


# Singleton
_engine = IntelligenceEngine()


_MAX_MESSAGE_LENGTH = 100_000
_SESSION_ID_RE = _re.compile(r'^[a-zA-Z0-9_\-\.]+$')


def _sanitize_input(text: str) -> str:
    """Strip null bytes and control characters (keep newlines/tabs)."""
    return ''.join(c for c in text if c == '\n' or c == '\t' or c == '\r' or (ord(c) >= 32) or ord(c) > 127)


async def process_message(session_id: str, user_message: str,
                          model_override: Optional[str] = None,
                          image_data: Optional[Tuple[str, str]] = None,
                          on_tool: Optional[Callable[[str, Any], None]] = None,
                          on_token: Optional[Callable] = None,
                          on_status: Optional[Callable] = None,
                          lang: Optional[str] = None) -> str:
    """Process a user message through the Intelligence Engine pipeline.

    Edge cases:
    - Shutdown rejection
    - Unhandled exceptions → graceful error message
    """
    global _main_loop
    try:
        _main_loop = asyncio.get_running_loop()
    except RuntimeError:
        pass
    # Reject new requests during shutdown
    if _shutting_down:
        return '⚠️ Server is shutting down. Please try again later. / 서버가 종료 중입니다.'

    with _active_requests_lock:
        global _active_requests
        _active_requests += 1
        _active_requests_event.clear()

    try:
        return await _process_message_inner(session_id, user_message,
                                            model_override=model_override,
                                            image_data=image_data,
                                            on_tool=on_tool,
                                            on_token=on_token,
                                            on_status=on_status,
                                            lang=lang)
    except Exception as e:
        log.error(f"[ENGINE] Unhandled error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return f'❌ Internal error / 내부 오류: {type(e).__name__}. Please try again.'
    finally:
        with _active_requests_lock:
            _active_requests -= 1
            if _active_requests == 0:
                _active_requests_event.set()


# ── Slash commands + usage tracking — extracted to slash_commands.py ──
from salmalm.core.slash_commands import (  # noqa: F401, E402
    _session_usage, _get_session_usage, record_response_usage,
    _SLASH_COMMANDS, _SLASH_PREFIX_COMMANDS, _dispatch_slash_command,
    # Re-export for backward compatibility (tests import from engine)
    _cmd_context, _cmd_usage, _cmd_plugins, _cmd_export_fn as _cmd_export,
)


async def _process_message_inner(session_id: str, user_message: str,
                                 model_override: Optional[str] = None,
                                 image_data: Optional[Tuple[str, str]] = None,
                                 on_tool: Optional[Callable[[str, Any], None]] = None,
                                 on_token: Optional[Callable] = None,
                                 on_status: Optional[Callable] = None,
                                 lang: Optional[str] = None) -> str:
    """Inner implementation of process_message."""
    # Input sanitization
    if not _SESSION_ID_RE.match(session_id):
        return '❌ Invalid session ID format (alphanumeric and hyphens only).'
    if len(user_message) > _MAX_MESSAGE_LENGTH:
        return f'❌ Message too long ({len(user_message)} chars). Maximum is {_MAX_MESSAGE_LENGTH}.'
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
            return f'⚠️ {e.message}'

    # Fire on_message hook (메시지 수신 훅)
    try:
        from salmalm.features.hooks import hook_manager
        hook_manager.fire('on_message', {'session_id': session_id, 'message': user_message})
    except Exception:
        pass

    # --- Slash commands (fast path, no LLM) ---
    cmd = user_message.strip()
    slash_result = await _dispatch_slash_command(
        cmd, session, session_id, model_override, on_tool)
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
            {'type': 'image', 'source': {'type': 'base64', 'media_type': mime, 'data': b64}},
            {'type': 'text', 'text': user_message or 'Analyze this image.'}
        ]
        session.messages.append({'role': 'user', 'content': content})
    else:
        session.add_user(user_message)

    # Language directive — match UI language setting
    if lang and lang in ('en', 'ko'):
        lang_directive = 'Respond in English.' if lang == 'en' else '한국어로 응답하세요.'
        # Inject as lightweight system hint (not persisted)
        session.messages.append({'role': 'system', 'content': f'[Language: {lang_directive}]'})

    # Context management
    session.messages = compact_messages(session.messages, session=session,
                                        on_status=on_status)
    if len(session.messages) % 20 == 0:
        session.add_system(build_system_prompt(full=False))

    # RAG context injection — augment with relevant memory/docs
    try:
        from salmalm.features.rag import inject_rag_context
        for i, m in enumerate(session.messages):
            if m.get('role') == 'system':
                session.messages[i] = dict(m)
                session.messages[i]['content'] = inject_rag_context(
                    session.messages, m['content'], max_chars=2500)
                break
    except Exception as e:
        log.warning(f"RAG injection skipped: {e}")

    # Mood-aware tone injection
    try:
        from salmalm.features.mood import mood_detector
        if mood_detector.enabled:
            _detected_mood, _mood_conf = mood_detector.detect(user_message)
            if _detected_mood != 'neutral' and _mood_conf > 0.3:
                _tone_hint = mood_detector.get_tone_injection(_detected_mood)
                if _tone_hint:
                    for i, m in enumerate(session.messages):
                        if m.get('role') == 'system':
                            session.messages[i] = dict(m)
                            session.messages[i]['content'] = m['content'] + f'\n\n[감정 감지: {_detected_mood}] {_tone_hint}'
                            break
                mood_detector.record_mood(_detected_mood, _mood_conf)
    except Exception as _mood_err:
        log.debug(f"Mood detection skipped: {_mood_err}")

    # Self-evolving prompt — record conversation periodically
    try:
        from salmalm.features.self_evolve import prompt_evolver
        if len(session.messages) > 4 and len(session.messages) % 10 == 0:
            prompt_evolver.record_conversation(session.messages)
    except Exception:
        pass

    # Classify and run through Intelligence Engine
    classification = TaskClassifier.classify(user_message, len(session.messages))

    # Thinking is user-controlled only (via /thinking toggle or 🧠 button)
    classification['thinking'] = getattr(session, 'thinking_enabled', False)
    classification['thinking_budget'] = 10000 if classification['thinking'] else 0

    # Suggest thinking mode for complex tasks when it's OFF
    if not classification['thinking'] and classification['tier'] >= 3 and classification['score'] >= 4:
        _suggest_key = f"_thinking_suggested_{getattr(session, 'id', '')}"
        if not getattr(session, _suggest_key, False):
            setattr(session, _suggest_key, True)  # Only suggest once per session
            _hint = ("\n\n💡 *이 작업은 복잡해 보입니다. "
                     "🧠 Extended Thinking을 켜면 더 정확한 결과를 얻을 수 있습니다.* "
                     "`/thinking on` 또는 🧠 버튼을 눌러주세요."
                     "\n💡 *This looks complex. Enable 🧠 Extended Thinking for better results.* "
                     "Use `/thinking on` or the 🧠 button.")
            # Inject as a system hint that will be appended to the response later
            session._thinking_hint = _hint

    # Multi-model routing: select optimal model if no override
    selected_model = model_override
    complexity = 'auto'
    if not model_override:
        selected_model, complexity = _select_model(user_message, session)
        log.info(f"[ROUTE] Multi-model: {complexity} → {selected_model}")
    # Fix outdated model names to actual API IDs
    selected_model = _fix_model_name(selected_model)

    # ── SLA: Measure latency (레이턴시 측정) + abort token accumulation ──
    _sla_start = _time.time()
    _sla_first_token_time = [0.0]  # mutable for closure
    _orig_on_token = on_token

    # Start streaming accumulator for abort recovery
    from salmalm.features.abort import abort_controller as _abort_ctl
    _abort_ctl.start_streaming(session_id)

    def _sla_on_token(event):
        if _sla_first_token_time[0] == 0.0:
            _sla_first_token_time[0] = _time.time()
        # Accumulate tokens for abort recovery
        if isinstance(event, dict):
            delta = event.get('delta', {})
            if isinstance(delta, dict) and delta.get('type') == 'text_delta':
                _abort_ctl.accumulate_token(session_id, delta.get('text', ''))
            elif event.get('type') == 'text' and event.get('text'):
                _abort_ctl.accumulate_token(session_id, event['text'])
        if _orig_on_token:
            _orig_on_token(event)

    response = await _engine.run(session, user_message,
                                 model_override=selected_model,
                                 on_tool=on_tool,
                                 classification=classification,
                                 on_token=_sla_on_token,
                                 on_status=on_status)

    # ── SLA: Record latency (레이턴시 기록) ──
    try:
        from salmalm.features.sla import latency_tracker
        _sla_end = _time.time()
        _ttft_ms = ((_sla_first_token_time[0] - _sla_start) * 1000
                    if _sla_first_token_time[0] > 0 else (_sla_end - _sla_start) * 1000)
        _total_ms = (_sla_end - _sla_start) * 1000
        from salmalm.features.sla import sla_config as _sla_cfg
        _timed_out = _total_ms > _sla_cfg.get('response_target_ms', 30000)
        latency_tracker.record(
            ttft_ms=_ttft_ms, total_ms=_total_ms,
            model=selected_model or 'auto',
            timed_out=_timed_out, session_id=session_id)
        # Check failover trigger
        if latency_tracker.should_failover():
            log.warning("[SLA] Consecutive timeout threshold reached — failover recommended")
            latency_tracker.reset_timeout_counter()
    except Exception as _sla_err:
        log.debug(f"[SLA] Latency tracking error: {_sla_err}")

    # Store model metadata on session for API consumers
    session.last_model = selected_model or 'auto'
    session.last_complexity = complexity

    # ── Auto-title session after first assistant response ──
    try:
        user_msgs = [m for m in session.messages if m.get('role') == 'user' and isinstance(m.get('content'), str)]
        assistant_msgs = [m for m in session.messages if m.get('role') == 'assistant']
        if len(assistant_msgs) == 1 and user_msgs:
            from salmalm.core import auto_title_session
            auto_title_session(session_id, user_msgs[0]['content'])
    except Exception as e:
        log.warning(f"Auto-title hook error: {e}")

    # ── Completion Notification Hook ──
    # Notify other channels when a task completes
    try:
        _notify_completion(session_id, user_message, response, classification)
    except Exception as e:
        log.error(f"Notification hook error: {e}")

    # Fire on_response hook (응답 완료 훅)
    try:
        from salmalm.features.hooks import hook_manager
        hook_manager.fire('on_response', {
            'session_id': session_id, 'message': response,
        })
    except Exception:
        pass

    # Append thinking mode suggestion if flagged
    _hint = getattr(session, '_thinking_hint', None)
    if _hint:
        response = response + _hint
        del session._thinking_hint

    return response


def _notify_completion(session_id: str, user_message: str, response: str, classification: dict):
    """Send completion notifications to Telegram + Web chat."""
    from salmalm.core import _tg_bot
    from salmalm.security.crypto import vault

    # Only notify for complex tasks (tier 3 or high-score tool-using)
    tier = classification.get('tier', 1)
    intent = classification.get('intent', 'chat')
    score = classification.get('score', 0)
    if tier < 3 and score < 3:
        return  # Skip simple/medium tasks — avoid notification spam

    # Build summary
    task_preview = user_message[:80] + ('...' if len(user_message) > 80 else '')
    resp_preview = response[:150] + ('...' if len(response) > 150 else '')
    notify_text = f"✅ Task completed [{intent}]\n📝 Request: {task_preview}\n💬 Result: {resp_preview}"

    # Telegram notification (if task came from web)
    if session_id != 'telegram' and _tg_bot and _tg_bot.token:
        owner_id = vault.get('telegram_owner_id') if vault.is_unlocked else None
        if owner_id:
            try:
                _tg_bot.send_message(owner_id, f"🔔 SalmAlm webchat Task completed\n{notify_text}")
            except Exception as e:
                log.error(f"TG notify error: {e}")

    # Web notification (if task came from telegram)
    if session_id == 'telegram':
        # Store notification for web polling
        from salmalm.core import _sessions  # noqa: F811
        web_session = _sessions.get('web')
        if web_session:
            if not hasattr(web_session, '_notifications'):
                web_session._notifications = []  # type: ignore[attr-defined]
            web_session._notifications.append({  # type: ignore[attr-defined]
                'time': __import__('time').time(),
                'text': f"🔔 SalmAlm telegram Task completed\n{notify_text}"
            })
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
