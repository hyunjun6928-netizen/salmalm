"""SalmAlm Intelligence Engine — TaskClassifier + IntelligenceEngine + process_message."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple  # noqa: F401

from salmalm.constants import (VERSION, INTENT_SHORT_MSG, INTENT_COMPLEX_MSG,
                               INTENT_CONTEXT_DEPTH, REFLECT_SNIPPET_LEN,
                               MODEL_ALIASES as _CONST_ALIASES, COMMAND_MODEL)
import re as _re
import threading as _threading
import time as _time
from salmalm.crypto import log

# Graceful shutdown state
_shutting_down = False
_active_requests = 0
_active_requests_lock = _threading.Lock()
_active_requests_event = _threading.Event()  # signaled when _active_requests == 0
from salmalm.core import router, compact_messages, get_session, _sessions, _metrics, compact_session, auto_compact_if_needed, audit_log  # noqa: F401
from salmalm.prompt import build_system_prompt
from salmalm.tool_handlers import execute_tool

# ── Imports from extracted modules ──
from salmalm.session_manager import (  # noqa: F401
    _should_prune_for_cache, _record_api_call_time, prune_context,
    _has_image_block, _soft_trim,
    _PRUNE_KEEP_LAST_ASSISTANTS, _PRUNE_SOFT_LIMIT, _PRUNE_HARD_LIMIT, _PRUNE_HEAD,
)
from salmalm.llm_loop import (  # noqa: F401
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
_SIMPLE_PATTERNS = _re.compile(
    r'^(안녕|hi|hello|hey|ㅎㅇ|ㅎㅎ|ㄱㅅ|고마워|감사|ㅋㅋ|ㅎㅎ|ok|lol|yes|no|네|아니|응|ㅇㅇ|뭐해|잘자|굿|bye|잘가|좋아|ㅠㅠ|ㅜㅜ|오|와|대박|진짜|뭐|어|음|흠|뭐야|왜|어떻게|언제|어디|누구|얼마)[\?!？！.\s]*$',
    _re.IGNORECASE)
_MODERATE_KEYWORDS = ['분석', '리뷰', '요약', '코드', 'code', 'analyze', 'review', 'summarize',
                      'summary', 'compare', '비교', 'refactor', '리팩', 'debug', '디버그',
                      'explain', '설명', '번역', 'translate']
_COMPLEX_KEYWORDS = ['설계', '아키텍처', 'architecture', 'design', 'system design',
                     'from scratch', '처음부터', '전체', 'migration', '마이그레이션']

from salmalm.constants import MODELS as _MODELS
import json as _json
from pathlib import Path as _Path

# Model name corrections: constants.py has outdated names → map to real API IDs
_MODEL_NAME_FIXES = {
    # Anthropic
    'claude-haiku-3.5-20241022': 'claude-haiku-4-5-20251001',
    'anthropic/claude-haiku-3.5-20241022': 'anthropic/claude-haiku-4-5-20251001',
    'claude-haiku-4-5-20250414': 'claude-haiku-4-5-20251001',
    'claude-sonnet-4-20250514': 'claude-sonnet-4-6',
    'anthropic/claude-sonnet-4-20250514': 'anthropic/claude-sonnet-4-6',
    # OpenAI (gpt-5.3-codex doesn't exist; latest codex is 5.2)
    'gpt-5.3-codex': 'gpt-5.2-codex',
    'openai/gpt-5.3-codex': 'openai/gpt-5.2-codex',
    # xAI (grok-4 alias may not resolve; use dated version)
    'grok-4': 'grok-4-0709',
    'xai/grok-4': 'xai/grok-4-0709',
}


def _fix_model_name(model: str) -> str:
    """Correct outdated model names to actual API IDs."""
    return _MODEL_NAME_FIXES.get(model, model)

# Routing config: user can override which model to use for each complexity level
_ROUTING_CONFIG_FILE = _Path.home() / '.salmalm' / 'routing.json'


def _load_routing_config() -> dict:
    """Load user's model routing config. Returns {simple, moderate, complex} model IDs."""
    defaults = {'simple': '', 'moderate': '', 'complex': ''}
    try:
        if _ROUTING_CONFIG_FILE.exists():
            cfg = _json.loads(_ROUTING_CONFIG_FILE.read_text(encoding='utf-8'))
            for k in ('simple', 'moderate', 'complex'):
                if k in cfg and cfg[k]:
                    defaults[k] = cfg[k]
    except Exception:
        pass
    return defaults


def _save_routing_config(config: dict):
    """Save user's model routing config."""
    try:
        _ROUTING_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _ROUTING_CONFIG_FILE.write_text(_json.dumps(config, indent=2), encoding='utf-8')
    except Exception:
        pass


def get_routing_config() -> dict:
    """Public getter for routing config (used by web API)."""
    return _load_routing_config()


def _select_model(message: str, session) -> tuple:
    """Select optimal model based on message complexity.

    Returns (model_id, complexity_level) where complexity is 'simple'|'moderate'|'complex'.
    Respects session-level model_override (from /model command).
    """
    # Check session-level override
    override = getattr(session, 'model_override', None)
    if override and override != 'auto':
        if override == 'haiku':
            return _MODELS['haiku'], 'simple'
        elif override == 'sonnet':
            return _MODELS['sonnet'], 'moderate'
        elif override == 'opus':
            return _MODELS['opus'], 'complex'
        else:
            # Direct model string
            return override, 'manual'

    rc = _load_routing_config()
    # If routing not configured, use default model
    _default_fallback = getattr(session, '_default_model', None) or _MODELS.get('sonnet', '')
    for k in ('simple', 'moderate', 'complex'):
        if not rc[k]:
            rc[k] = _default_fallback
    msg_lower = message.lower()
    msg_len = len(message)

    # Check thinking mode
    if getattr(session, 'thinking_enabled', False):
        return rc['complex'], 'complex'

    # Complex: long messages, architecture keywords
    if msg_len > 500:
        return rc['complex'], 'complex'
    for kw in _COMPLEX_KEYWORDS:
        if kw in msg_lower:
            return rc['complex'], 'complex'

    # Moderate: code blocks, analysis keywords
    if '```' in message or 'def ' in message or 'class ' in message:
        return rc['moderate'], 'moderate'
    for kw in _MODERATE_KEYWORDS:
        if kw in msg_lower:
            return rc['moderate'], 'moderate'

    # Simple: short + greeting/simple question pattern
    if msg_len < 50 and _SIMPLE_PATTERNS.match(message.strip()):
        return rc['simple'], 'simple'
    if msg_len < 50:
        return rc['simple'], 'simple'

    # Default: moderate
    return rc['moderate'], 'moderate'


class TaskClassifier:
    """Classify user intent to determine execution strategy."""

    # Intent categories with weighted keywords
    INTENTS = {
        'code': {'keywords': ['code', '코드', 'implement', '구현', 'function', 'class',
                              'bug', '버그', 'fix', '수정', 'refactor', '리팩', 'debug', '디버그',
                              'API', 'server', '서버', 'deploy', '배포', 'build', '빌드',
                              '개발', '코딩', '프로그래밍'],
                 'tier': 3, 'thinking': True},
        'analysis': {'keywords': ['analyze', '분석', 'compare', '비교', 'review', '리뷰',
                                  'audit', '감사', 'security', '보안', 'performance', '성능',
                                  '검토', '조사', '평가', '진단'],
                     'tier': 3, 'thinking': True},
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
        from salmalm.mcp import mcp_manager
        # Merge built-in + plugin + MCP tools (deduplicate by name)
        all_tools = list(TOOL_DEFINITIONS)
        seen = {t['name'] for t in all_tools}
        for t in PluginLoader.get_all_tools() + mcp_manager.get_all_tools():
            if t['name'] not in seen:
                all_tools.append(t)
                seen.add(t['name'])

        # ── Selective tool injection based on intent ──
        if intent:
            allowed = set(INTENT_TOOLS.get(intent, []))
            # Add keyword-triggered tools
            msg_lower = user_message.lower()
            for kw, tools in _KEYWORD_TOOLS.items():
                if kw in msg_lower:
                    allowed.update(tools)
            # Always include memory tools for memory intent
            if intent == 'memory':
                allowed.update(['memory_read', 'memory_write', 'memory_search'])
            if allowed:
                all_tools = [t for t in all_tools if t['name'] in allowed]
            else:
                return []

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

    # Max chars per tool result sent to LLM context
    MAX_TOOL_RESULT_CHARS = 50_000

    def _truncate_tool_result(self, result: str) -> str:
        """Truncate tool result to prevent context explosion."""
        if len(result) > self.MAX_TOOL_RESULT_CHARS:
            return result[:self.MAX_TOOL_RESULT_CHARS] + \
                f'\n\n... [truncated: {len(result)} chars total, showing first {self.MAX_TOOL_RESULT_CHARS}]'
        return result

    def _execute_tools_parallel(self, tool_calls: list, on_tool=None) -> dict:
        """Execute multiple tools in parallel, return {id: result}."""
        for tc in tool_calls:
            if on_tool:
                result = on_tool(tc['name'], tc['arguments'])
                # Handle async callbacks
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        task = loop.create_task(result)
                        task.add_done_callback(
                            lambda t: t.exception() if not t.cancelled() and t.exception() else None
                        )
                    except RuntimeError:
                        pass  # No running event loop

        # Fire on_tool_call hook for each tool (도구 호출 훅)
        try:
            from salmalm.hooks import hook_manager
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
                result = self._truncate_tool_result(execute_tool(tc['name'], tc['arguments']))
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
                outputs[tc_id] = self._truncate_tool_result(f.result(timeout=60))
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
                from salmalm.hooks import hook_manager
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
        use_thinking = classification['thinking'] or getattr(session, 'thinking_enabled', False)
        _thinking_budget = classification['thinking_budget'] or (10000 if use_thinking else 0)  # noqa: F841
        iteration = 0
        consecutive_errors = 0
        _session_id = getattr(session, 'id', '')
        while iteration < self.MAX_TOOL_ITERATIONS:
            # Abort check (생성 중지 체크) — LibreChat style
            from salmalm.edge_cases import abort_controller
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

            # OpenClaw-style: intent별 도구 선별 주입
            cur_intent = classification['intent']
            intent_tool_names = INTENT_TOOLS.get(cur_intent, [])
            # Also check keyword-triggered tools
            _msg_lower = user_message.lower() if user_message else ''
            _has_kw_tools = any(kw in _msg_lower for kw in _KEYWORD_TOOLS)
            if intent_tool_names or _has_kw_tools:
                tools = self._get_tools_for_provider(provider, intent=cur_intent,
                                                     user_message=user_message or '')
            else:
                tools = None

            # Use thinking for first call on complex tasks
            think_this_call = (use_thinking and iteration == 0
                               and provider == 'anthropic'
                               and ('opus' in model or 'sonnet' in model))

            # Session pruning — only when cache TTL expired (preserves Anthropic prompt cache)
            if _should_prune_for_cache():
                pruned_messages, prune_stats = prune_context(session.messages)
                if prune_stats['soft_trimmed'] or prune_stats['hard_cleared']:
                    log.info(f"[PRUNE] soft={prune_stats['soft_trimmed']} hard={prune_stats['hard_cleared']}")
            else:
                pruned_messages = session.messages
                prune_stats = {'soft_trimmed': 0, 'hard_cleared': 0, 'unchanged': 0}

            # Status callback: typing/thinking
            if on_status:
                if think_this_call:
                    on_status(STATUS_THINKING, '🧠 Thinking...')
                else:
                    on_status(STATUS_TYPING, 'typing')

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

            # ── Token overflow: aggressive truncation + retry once ──
            if result.get('error') == 'token_overflow':
                msg_count = len(session.messages)
                # Keep system prompt + last 10 messages
                if msg_count > 12:
                    system_msgs = [m for m in session.messages if m['role'] == 'system'][:1]
                    recent_msgs = session.messages[-10:]
                    session.messages = system_msgs + recent_msgs
                    log.warning(f"[CUT] Force-truncated: {msg_count} -> {len(session.messages)} msgs")
                    # Retry with truncated context
                    result = await _call_llm_async(session.messages, model=model, tools=tools,
                                                   thinking=think_this_call)
                    if result.get('error') == 'token_overflow':
                        # Still too long — nuclear option: keep only last 4
                        session.messages = (system_msgs or []) + session.messages[-4:]
                        log.warning(f"[CUT][CUT] Nuclear truncation: -> {len(session.messages)} msgs")
                        result = await _call_llm_async(session.messages, model=model, tools=tools)
                        if result.get('error'):
                            session.add_assistant("⚠️ Context too large. Use /clear to reset.")
                            return "⚠️ Context too large. Use /clear to reset."
                elif msg_count > 4:
                    session.messages = session.messages[:1] + session.messages[-4:]
                    result = await _call_llm_async(session.messages, model=model, tools=tools)
                    if result.get('error'):
                        session.add_assistant("⚠️ Context too large. Use /clear to reset.")
                        return "⚠️ Context too large. Use /clear to reset."
                else:
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
                    from salmalm.edge_cases import usage_tracker
                    # Estimate cost (rough: Opus=$15/M, Sonnet=$3/M, Haiku=$0.25/M input)
                    _inp, _out = usage.get('input', 0), usage.get('output', 0)
                    _model_lower = model.lower()
                    if 'opus' in _model_lower:
                        _cost = (_inp * 15 + _out * 75) / 1_000_000
                    elif 'sonnet' in _model_lower:
                        _cost = (_inp * 3 + _out * 15) / 1_000_000
                    elif 'haiku' in _model_lower:
                        _cost = (_inp * 0.25 + _out * 1.25) / 1_000_000
                    else:
                        _cost = (_inp * 3 + _out * 15) / 1_000_000
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
                    on_status(STATUS_TOOL_RUNNING, f'🔧 Running {tool_names}...')

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
                    session.messages = compact_messages(session.messages, session=session)
                    log.info(f"[CUT] Mid-loop compaction: -> {len(session.messages)} msgs")

                iteration += 1
                continue

            # Final response
            response = result.get('content', '')

            # ── LLM edge cases ──

            # Empty response: retry once
            if not response or not response.strip():
                log.warning("[LLM] Empty response, retrying once")
                retry_result, _ = await self._call_with_failover(
                    pruned_messages, model=model, tools=tools,
                    max_tokens=4096, thinking=False)
                response = retry_result.get('content', '')
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
                          on_status: Optional[Callable] = None) -> str:
    """Process a user message through the Intelligence Engine pipeline.

    Edge cases:
    - Shutdown rejection
    - Unhandled exceptions → graceful error message
    """
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
                                            on_status=on_status)
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


# ============================================================
# Slash Command Handlers — extracted from _process_message_inner
# ============================================================

def _cmd_clear(cmd, session, **_):
    session.messages = [m for m in session.messages if m['role'] == 'system'][:1]
    return 'Conversation cleared.'


def _cmd_help(cmd, session, **_):
    from salmalm.tools import TOOL_DEFINITIONS
    tool_count = len(TOOL_DEFINITIONS)
    return f"""😈 **SalmAlm v{VERSION}** — Personal AI Gateway

📌 **Commands**
/clear — Clear conversation
/help — This help
/model <name> — Change model
/think <question> — 🧠 Deep reasoning (Opus)
/plan <question> — 📋 Plan → Execute
/status — Usage + Cost
/context — Context window token usage
/tools — Tool list
/uptime — Uptime stats (업타임)
/latency — Latency stats (레이턴시)
/health detail — Detailed health report (상세 헬스)
/security — 🛡️ Security audit report
/evolve — 🧬 Self-evolving prompt (status|apply|reset|history)
/mood — 🎭 Mood-aware response (status|on|off|sensitive)
/think <내용> — 💭 Record a thought (or list|search|tag|stats|export)

🤖 **Model Aliases** (27)
claude, sonnet, opus, haiku, gpt, gpt5, o3, o4mini,
grok, grok4, gemini, flash, deepseek, llama, auto ...

🔧 **Tools** ({tool_count})
File R/W, code exec, web search, RAG search,
system monitor, cron jobs, image analysis, TTS ...

🧠 **Intelligence Engine**
Auto intent classification (7 levels) → Model routing → Parallel tools → Self-evaluation

💡 **Tip**: Just speak naturally. Read a file, search the web, write code, etc."""


def _cmd_status(cmd, session, **_):
    return execute_tool('usage_report', {})


def _cmd_tools(cmd, session, **_):
    from salmalm.tools import TOOL_DEFINITIONS
    lines = [f'🔧 **Tool List** ({len(TOOL_DEFINITIONS)})\n']
    for t in TOOL_DEFINITIONS:
        lines.append(f"• **{t['name']}** — {t['description'][:60]}")
    return '\n'.join(lines)


async def _cmd_think(cmd, session, *, on_tool=None, **_):
    think_msg = cmd[7:].strip()
    if not think_msg:
        return 'Usage: /think <question>'
    # Route thought-stream subcommands
    _thought_subs = ('list', 'search', 'tag', 'timeline', 'stats', 'export')
    first_word = think_msg.split(None, 1)[0].lower() if think_msg else ''
    if first_word in _thought_subs:
        return _cmd_thought(cmd, session)
    session.add_user(think_msg)
    session.messages = compact_messages(session.messages, session=session)
    classification = {'intent': 'analysis', 'tier': 3, 'thinking': True,
                      'thinking_budget': 16000, 'score': 5}
    return await _engine.run(session, think_msg,
                             model_override=COMMAND_MODEL,
                             on_tool=on_tool, classification=classification)


async def _cmd_plan(cmd, session, *, model_override=None, on_tool=None, **_):
    plan_msg = cmd[6:].strip()
    if not plan_msg:
        return 'Usage: /plan <task description>'
    session.add_user(plan_msg)
    session.messages = compact_messages(session.messages, session=session)
    classification = {'intent': 'code', 'tier': 3, 'thinking': True,
                      'thinking_budget': 10000, 'score': 5}
    return await _engine.run(session, plan_msg, model_override=model_override,
                             on_tool=on_tool, classification=classification)


def _cmd_uptime(cmd, session, **_):
    from salmalm.sla import uptime_monitor, sla_config  # noqa: F401
    stats = uptime_monitor.get_stats()
    target = stats['target_pct']
    pct = stats['monthly_uptime_pct']
    status_icon = '🟢' if pct >= target else ('🟡' if pct >= 99.0 else '🔴')
    lines = [
        '📊 **SalmAlm Uptime** / 업타임 현황\n',
        f'{status_icon} Current uptime: **{stats["uptime_human"]}**',
        f'📅 Month ({stats["month"]}): **{pct}%** (target: {target}%)',
        f'📅 Today: **{stats["daily_uptime_pct"]}%**',
        f'🕐 Started: {stats["start_time"][:19]}',
    ]
    incidents = stats.get('recent_incidents', [])
    if incidents:
        lines.append(f'\n⚠️ Recent incidents ({len(incidents)}):')
        for inc in incidents[:5]:
            dur = f'{inc["duration_sec"]:.0f}s' if inc['duration_sec'] else '?'
            lines.append(f'  • {inc["start"][:19]} — {inc["reason"]} ({dur})')
    return '\n'.join(lines)


def _cmd_latency(cmd, session, **_):
    from salmalm.sla import latency_tracker
    stats = latency_tracker.get_stats()
    if stats['count'] == 0:
        return '📊 No latency data yet. / 레이턴시 데이터가 없습니다.'
    tgt = stats['targets']
    ttft = stats['ttft']
    total = stats['total']
    ttft_ok = '✅' if ttft['p95'] <= tgt['ttft_ms'] else '⚠️'
    total_ok = '✅' if total['p95'] <= tgt['response_ms'] else '⚠️'
    lines = [
        f'📊 **Latency Stats** / 레이턴시 통계 ({stats["count"]} requests)\n',
        f'{ttft_ok} **TTFT** (Time To First Token):',
        f'  P50={ttft["p50"]:.0f}ms  P95={ttft["p95"]:.0f}ms  P99={ttft["p99"]:.0f}ms  (target: <{tgt["ttft_ms"]}ms)',
        f'{total_ok} **Total Response Time**:',
        f'  P50={total["p50"]:.0f}ms  P95={total["p95"]:.0f}ms  P99={total["p99"]:.0f}ms  (target: <{tgt["response_ms"]}ms)',
    ]
    if stats['consecutive_timeouts'] > 0:
        lines.append(f'⚠️ Consecutive timeouts: {stats["consecutive_timeouts"]}')
    return '\n'.join(lines)


def _cmd_health_detail(cmd, session, **_):
    from salmalm.sla import watchdog
    report = watchdog.get_detailed_health()
    status = report.get('status', 'unknown')
    icon = {'healthy': '🟢', 'degraded': '🟡', 'unhealthy': '🔴'}.get(status, '⚪')
    lines = [f'{icon} **Health Report** / 상세 헬스 리포트\n', f'Status: **{status}**\n']
    for name, check in report.get('checks', {}).items():
        s = check.get('status', '?')
        ci = {'ok': '✅', 'warning': '⚠️', 'error': '❌'}.get(s, '❔')
        extra = ''
        if 'usage_mb' in check:
            extra = f' ({check["usage_mb"]}MB/{check["limit_mb"]}MB)'
        elif 'usage_pct' in check:
            extra = f' ({check["usage_pct"]}%/{check["limit_pct"]}%)'
        elif 'error' in check:
            extra = f' ({check["error"][:50]})'
        lines.append(f'{ci} {name}: {s}{extra}')
    return '\n'.join(lines)


def _cmd_prune(cmd, session, **_):
    _, stats = prune_context(session.messages)
    total = stats['soft_trimmed'] + stats['hard_cleared'] + stats['unchanged']
    return (f"🧹 **Session Pruning Results**\n"
            f"• Soft-trimmed: {stats['soft_trimmed']}\n"
            f"• Hard-cleared: {stats['hard_cleared']}\n"
            f"• Unchanged: {stats['unchanged']}\n"
            f"• Total tool results scanned: {total}")


def _cmd_usage_daily(cmd, session, **_):
    from salmalm.edge_cases import usage_tracker
    report = usage_tracker.daily_report()
    if not report:
        return '📊 No usage data yet. / 아직 사용량 데이터가 없습니다.'
    lines = ['📊 **Daily Usage Report / 일별 사용량**\n']
    for r in report[:14]:
        lines.append(f"• {r['date']} | {r['model'].split('/')[-1]} | "
                     f"in:{r['input_tokens']} out:{r['output_tokens']} | "
                     f"${r['cost']:.4f} ({r['calls']} calls)")
    return '\n'.join(lines)


def _cmd_usage_monthly(cmd, session, **_):
    from salmalm.edge_cases import usage_tracker
    report = usage_tracker.monthly_report()
    if not report:
        return '📊 No usage data yet. / 아직 사용량 데이터가 없습니다.'
    lines = ['📊 **Monthly Usage Report / 월별 사용량**\n']
    for r in report:
        lines.append(f"• {r['month']} | {r['model'].split('/')[-1]} | "
                     f"in:{r['input_tokens']} out:{r['output_tokens']} | "
                     f"${r['cost']:.4f} ({r['calls']} calls)")
    return '\n'.join(lines)


def _cmd_bookmarks(cmd, session, **_):
    from salmalm.edge_cases import bookmark_manager
    bms = bookmark_manager.list_all(limit=20)
    if not bms:
        return '⭐ No bookmarks yet. / 아직 북마크가 없습니다.'
    lines = ['⭐ **Bookmarks / 북마크**\n']
    for b in bms:
        lines.append(f"• [{b['session_id']}#{b['message_index']}] "
                     f"{b['preview'][:60]}{'...' if len(b.get('preview', '')) > 60 else ''}")
    return '\n'.join(lines)


def _cmd_compare(cmd, session, *, session_id='', **_):
    compare_msg = cmd[9:].strip()
    if not compare_msg:
        return 'Usage: /compare <message> — Compare responses from multiple models'
    from salmalm.edge_cases import compare_models
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                results = pool.submit(lambda: asyncio.run(compare_models(session_id, compare_msg))).result()
        else:
            results = loop.run_until_complete(compare_models(session_id, compare_msg))
    except Exception:
        results = asyncio.run(compare_models(session_id, compare_msg))
    lines = ['🔀 **Model Comparison / 모델 비교**\n']
    for r in results:
        model_name = r['model'].split('/')[-1]
        if r.get('error'):
            lines.append(f"### ❌ {model_name}\n{r['error']}\n")
        else:
            lines.append(f"### 🤖 {model_name} ({r['time_ms']}ms)\n{r['response'][:500]}\n")
    return '\n'.join(lines)


def _cmd_security(cmd, session, **_):
    from salmalm.security import security_auditor
    return security_auditor.format_report()


def estimate_tokens(text: str) -> int:
    """Estimate tokens: Korean /2, English /4, mixed weighted."""
    if not text:
        return 0
    kr_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7a3' or '\u3131' <= c <= '\u318e')
    kr_ratio = kr_chars / max(len(text), 1)
    if kr_ratio > 0.3:
        return int(len(text) / 2)
    elif kr_ratio < 0.05:
        return int(len(text) / 4)
    return int(len(text) / 3)


# ── Model pricing (USD per 1M tokens) ──
MODEL_PRICING = {
    'claude-opus-4': {'input': 15.0, 'output': 75.0, 'cache_read': 1.5, 'cache_write': 18.75},
    'claude-sonnet-4': {'input': 3.0, 'output': 15.0, 'cache_read': 0.3, 'cache_write': 3.75},
    'claude-haiku-4-5': {'input': 1.0, 'output': 5.0, 'cache_read': 0.1, 'cache_write': 1.25},
    'gemini-2.5-pro': {'input': 1.25, 'output': 10.0, 'cache_read': 0.315, 'cache_write': 1.25},
    'gemini-2.5-flash': {'input': 0.15, 'output': 0.60, 'cache_read': 0.0375, 'cache_write': 0.15},
    'gemini-2.0-flash': {'input': 0.10, 'output': 0.40, 'cache_read': 0.025, 'cache_write': 0.10},
    'gemini-3-pro': {'input': 1.25, 'output': 10.0, 'cache_read': 0.315, 'cache_write': 1.25},
    'gemini-3-flash': {'input': 0.15, 'output': 0.60, 'cache_read': 0.0375, 'cache_write': 0.15},
}


def _get_pricing(model: str) -> dict:
    """Get pricing for a model string (fuzzy match)."""
    m = model.lower().replace('-', '').replace('/', '')
    for key, pricing in MODEL_PRICING.items():
        if key.replace('-', '') in m:
            return pricing
    # Gemini fallback
    if 'gemini' in m:
        if 'pro' in m:
            return MODEL_PRICING['gemini-2.5-pro']
        return MODEL_PRICING['gemini-2.5-flash']
    # Default to sonnet pricing
    return MODEL_PRICING['claude-sonnet-4']


def estimate_cost(model: str, usage: dict) -> float:
    """Estimate cost in USD from usage dict."""
    pricing = _get_pricing(model)
    inp = usage.get('input', 0)
    out = usage.get('output', 0)
    cache_write = usage.get('cache_creation_input_tokens', 0)
    cache_read = usage.get('cache_read_input_tokens', 0)
    # Subtract cached tokens from regular input
    regular_input = max(0, inp - cache_write - cache_read)
    cost = (
        regular_input * pricing['input'] / 1_000_000
        + out * pricing['output'] / 1_000_000
        + cache_write * pricing['cache_write'] / 1_000_000
        + cache_read * pricing['cache_read'] / 1_000_000
    )
    return cost


# ── Session usage tracking ──
_session_usage: Dict[str, dict] = {}  # session_id -> {responses: [...], mode: 'off'}


def _get_session_usage(session_id: str) -> dict:
    if session_id not in _session_usage:
        _session_usage[session_id] = {'responses': [], 'mode': 'off', 'total_cost': 0.0}
    return _session_usage[session_id]


def record_response_usage(session_id: str, model: str, usage: dict) -> None:
    """Record per-response usage for /usage command."""
    su = _get_session_usage(session_id)
    cost = estimate_cost(model, usage)
    su['responses'].append({
        'model': model, 'input': usage.get('input', 0),
        'output': usage.get('output', 0),
        'cache_read': usage.get('cache_read_input_tokens', 0),
        'cache_write': usage.get('cache_creation_input_tokens', 0),
        'cost': cost,
    })
    su['total_cost'] += cost


def _cmd_context(cmd, session, **_):
    """Show context window token usage breakdown."""
    sub = cmd.strip().split()
    detail_mode = len(sub) > 1 and sub[1] == 'detail'

    from salmalm.prompt import build_system_prompt
    sys_prompt = build_system_prompt(full=False)
    sys_tokens = estimate_tokens(sys_prompt)

    # Tool schemas
    tool_tokens = 0
    tool_text = ''
    tool_details = []
    try:
        from salmalm.tools import TOOL_DEFINITIONS
        for t in TOOL_DEFINITIONS:
            schema_text = json.dumps({'name': t['name'], 'description': t['description'],
                                      'input_schema': t['input_schema']})
            tool_details.append((t['name'], len(schema_text), estimate_tokens(schema_text)))
        tool_text = json.dumps([{'name': t['name'], 'description': t['description'],
                                 'input_schema': t['input_schema']} for t in TOOL_DEFINITIONS])
        tool_tokens = estimate_tokens(tool_text)
    except Exception:
        TOOL_DEFINITIONS = []

    # Injected files breakdown
    from salmalm.constants import SOUL_FILE, AGENTS_FILE, MEMORY_FILE, USER_FILE, BASE_DIR
    from salmalm.prompt import USER_SOUL_FILE
    file_details = []
    for label, path in [('SOUL.md', SOUL_FILE), ('USER_SOUL.md', USER_SOUL_FILE),
                        ('AGENTS.md', AGENTS_FILE), ('MEMORY.md', MEMORY_FILE),
                        ('USER.md', USER_FILE), ('TOOLS.md', BASE_DIR / 'TOOLS.md')]:
        if path.exists():
            raw = path.read_text(encoding='utf-8')
            file_details.append((label, len(raw), estimate_tokens(raw)))

    # Conversation history
    history_text = ''
    for m in session.messages:
        c = m.get('content', '')
        if isinstance(c, str):
            history_text += c
        elif isinstance(c, list):
            for block in c:
                if isinstance(block, dict):
                    history_text += block.get('content', '') or block.get('text', '') or ''
    history_tokens = estimate_tokens(history_text)

    total = sys_tokens + tool_tokens + history_tokens

    lines = [f"""📊 **Context Window Usage**

| Component | Chars | ~Tokens |
|-----------|------:|--------:|
| System Prompt | {len(sys_prompt):,} | {sys_tokens:,} |
| Tool Schemas ({len(TOOL_DEFINITIONS)}) | {len(tool_text):,} | {tool_tokens:,} |
| Conversation ({len(session.messages)} msgs) | {len(history_text):,} | {history_tokens:,} |
| **Total** | | **{total:,}** |"""]

    if detail_mode:
        lines.append('\n📁 **Injected Files**')
        for label, chars, tokens in sorted(file_details, key=lambda x: -x[2]):
            lines.append(f'  • {label}: {chars:,} chars / ~{tokens:,} tokens')

        lines.append('\n🔧 **Tool Schemas (top 10 by size)**')
        for name, chars, tokens in sorted(tool_details, key=lambda x: -x[2])[:10]:
            lines.append(f'  • {name}: {chars:,} chars / ~{tokens:,} tokens')

    lines.append('\n💡 Intent-based injection reduces tools to ≤15 per call.')
    lines.append('🔒 Prompt caching: system prompt + tool schemas marked ephemeral.')
    return '\n'.join(lines)


def _cmd_usage(cmd, session, *, session_id='', **_):
    """Handle /usage tokens|full|cost|off commands."""
    parts = cmd.strip().split()
    sub = parts[1] if len(parts) > 1 else 'tokens'
    su = _get_session_usage(session_id)

    if sub == 'off':
        su['mode'] = 'off'
        return '📊 Usage footer: **OFF**'
    elif sub == 'tokens':
        su['mode'] = 'tokens'
        if not su['responses']:
            return '📊 Usage tracking: **ON** (tokens mode). No responses yet.'
        last = su['responses'][-1]
        return (f'📊 Usage mode: **tokens**\n'
                f'Last: in={last["input"]:,} out={last["output"]:,} '
                f'(cache_read={last["cache_read"]:,} cache_write={last["cache_write"]:,})')
    elif sub == 'full':
        su['mode'] = 'full'
        if not su['responses']:
            return '📊 Usage tracking: **ON** (full mode). No responses yet.'
        lines = ['📊 **Usage (full)**\n']
        for i, r in enumerate(su['responses'][-10:], 1):
            model_short = r['model'].split('/')[-1][:20]
            lines.append(f'{i}. {model_short} | in:{r["input"]:,} out:{r["output"]:,} | ${r["cost"]:.4f}')
        lines.append(f'\n💰 Session total: **${su["total_cost"]:.4f}**')
        return '\n'.join(lines)
    elif sub == 'cost':
        lines = ['💰 **Session Cost Summary**\n']
        if not su['responses']:
            lines.append('No API calls yet.')
        else:
            lines.append(f'Requests: {len(su["responses"])}')
            total_in = sum(r['input'] for r in su['responses'])
            total_out = sum(r['output'] for r in su['responses'])
            total_cache_read = sum(r['cache_read'] for r in su['responses'])
            total_cache_write = sum(r['cache_write'] for r in su['responses'])
            lines.append(f'Input tokens: {total_in:,} (cache read: {total_cache_read:,}, cache write: {total_cache_write:,})')
            lines.append(f'Output tokens: {total_out:,}')
            lines.append(f'**Total cost: ${su["total_cost"]:.4f}**')
            if total_cache_read > 0:
                # Estimate savings from cache
                pricing = _get_pricing(su['responses'][-1]['model'])
                saved = total_cache_read * (pricing['input'] - pricing['cache_read']) / 1_000_000
                lines.append(f'💡 Cache savings: ~${saved:.4f}')
        return '\n'.join(lines)
    else:
        return '📊 `/usage tokens|full|cost|off`'


def _cmd_soul(cmd, session, **_):
    from salmalm.prompt import get_user_soul, USER_SOUL_FILE
    content = get_user_soul()
    if content:
        return f'📜 **SOUL.md** (`{USER_SOUL_FILE}`)\n\n{content}'
    return f'📜 SOUL.md is not set. Create `{USER_SOUL_FILE}` or edit via Settings.'


def _cmd_soul_reset(cmd, session, **_):
    from salmalm.prompt import reset_user_soul
    reset_user_soul()
    session.add_system(build_system_prompt(full=True))
    return '📜 SOUL.md reset to default.'


def _cmd_model(cmd, session, **_):
    model_name = cmd[7:].strip()
    if model_name in ('auto', 'opus', 'sonnet', 'haiku'):
        session.model_override = model_name if model_name != 'auto' else 'auto'
        if model_name == 'auto':
            router.set_force_model(None)
            return 'Model: **auto** (cost-optimized routing) — saved ✅\n• simple → haiku ⚡ • moderate → sonnet • complex → opus 💎'
        labels = {'opus': 'claude-opus-4-6 💎', 'sonnet': 'claude-sonnet-4-6', 'haiku': 'claude-haiku-4-5 ⚡'}
        return f'Model: **{model_name}** ({labels[model_name]}) — saved ✅'
    if '/' in model_name:
        router.set_force_model(model_name)
        session.model_override = model_name
        return f'Model changed: {model_name} — saved ✅'
    if model_name in MODEL_ALIASES:
        resolved = MODEL_ALIASES[model_name]
        router.set_force_model(resolved)
        session.model_override = resolved
        return f'Model changed: {model_name} → {resolved} — saved ✅'
    return f'Unknown model: {model_name}\\nAvailable: auto, opus, sonnet, haiku, {", ".join(sorted(MODEL_ALIASES.keys()))}'


def _cmd_tts(cmd, session, **_):
    arg = cmd[4:].strip()
    if arg == 'on':
        session.tts_enabled = True
        return '🔊 TTS: **ON** — 응답을 음성으로 전송합니다.'
    elif arg == 'off':
        session.tts_enabled = False
        return '🔇 TTS: **OFF**'
    else:
        status = 'ON' if getattr(session, 'tts_enabled', False) else 'OFF'
        voice = getattr(session, 'tts_voice', 'alloy')
        return f'🔊 TTS: **{status}** (voice: {voice})\n`/tts on` · `/tts off` · `/voice alloy|nova|echo|fable|onyx|shimmer`'


def _cmd_voice(cmd, session, **_):
    arg = cmd[6:].strip()
    valid_voices = ('alloy', 'nova', 'echo', 'fable', 'onyx', 'shimmer')
    if arg in valid_voices:
        session.tts_voice = arg
        return f'🎙️ Voice: **{arg}** — saved ✅'
    return f'Available voices: {", ".join(valid_voices)}'


def _cmd_subagents(cmd, session, **_):
    """Handle /subagents commands: list, stop, log, info."""
    from salmalm.agents import SubAgent
    parts = cmd.split(maxsplit=2)
    sub = parts[1] if len(parts) > 1 else 'list'
    arg = parts[2] if len(parts) > 2 else ''

    if sub == 'list':
        agents = SubAgent.list_agents()
        if not agents:
            return '🤖 No active sub-agents.'
        lines = ['🤖 **Sub-agents**\n']
        for i, a in enumerate(agents, 1):
            icon = {'running': '🔄', 'completed': '✅', 'error': '❌', 'stopped': '⏹'}.get(a['status'], '❓')
            lines.append(f"{icon} #{i} `{a['id']}` — {a['label']} [{a['status']}] "
                         f"({a['runtime_s']}s, ${a.get('estimated_cost', 0):.4f})")
        return '\n'.join(lines)

    elif sub == 'stop':
        if not arg:
            return '❌ Usage: /subagents stop <id|#N|all>'
        return SubAgent.stop_agent(arg)

    elif sub == 'log':
        log_parts = arg.split(maxsplit=1)
        agent_id = log_parts[0] if log_parts else ''
        limit = int(log_parts[1]) if len(log_parts) > 1 and log_parts[1].isdigit() else 20
        if not agent_id:
            return '❌ Usage: /subagents log <id|#N> [limit]'
        return SubAgent.get_log(agent_id, limit)

    elif sub == 'info':
        if not arg:
            return '❌ Usage: /subagents info <id|#N>'
        return SubAgent.get_info(arg)

    return '❌ Usage: /subagents list|stop|log|info <args>'


def _cmd_agent(cmd, session, *, session_id='', **_):
    from salmalm.agents import agent_manager
    parts = cmd.split(maxsplit=2)
    sub = parts[1] if len(parts) > 1 else 'list'
    if sub == 'list':
        agents = agent_manager.list_agents()
        lines = ['🤖 **Agents** (에이전트 목록)\n']
        for a in agents:
            lines.append(f"• **{a['id']}** — {a['display_name']}")
        bindings = agent_manager.list_bindings()
        if bindings:
            lines.append('\n📌 **Bindings** (바인딩)')
            for k, v in bindings.items():
                lines.append(f'• {k} → {v}')
        return '\n'.join(lines)
    elif sub == 'create' and len(parts) > 2:
        return agent_manager.create(parts[2])
    elif sub == 'switch' and len(parts) > 2:
        chat_key = f'session:{session_id}'
        return agent_manager.switch(chat_key, parts[2])
    elif sub == 'delete' and len(parts) > 2:
        return agent_manager.delete(parts[2])
    elif sub == 'bind' and len(parts) > 2:
        bind_parts = parts[2].split()
        if len(bind_parts) == 2:
            return agent_manager.bind(bind_parts[0], bind_parts[1])
        return '❌ Usage: /agent bind <chat_key> <agent_id>'
    return '❌ Usage: /agent list|create|switch|delete|bind <args>'


def _cmd_hooks(cmd, session, **_):
    from salmalm.hooks import hook_manager
    parts = cmd.split(maxsplit=2)
    sub = parts[1] if len(parts) > 1 else 'list'
    if sub == 'list':
        hooks = hook_manager.list_hooks()
        if not hooks:
            return '📋 No hooks configured. Edit ~/.salmalm/hooks.json'
        lines = ['🪝 **Hooks** (이벤트 훅)\n']
        for event, info in hooks.items():
            cmds_list = info['commands']
            pc = info['plugin_callbacks']
            lines.append(f"• **{event}**: {len(cmds_list)} commands, {pc} plugin callbacks")
            for i, c in enumerate(cmds_list):
                lines.append(f"  [{i}] `{c[:60]}`")
        return '\n'.join(lines)
    elif sub == 'test' and len(parts) > 2:
        return hook_manager.test_hook(parts[2].strip())
    elif sub == 'add' and len(parts) > 2:
        add_parts = parts[2].split(maxsplit=1)
        if len(add_parts) == 2:
            return hook_manager.add_hook(add_parts[0], add_parts[1])
        return '❌ Usage: /hooks add <event> <command>'
    elif sub == 'reload':
        hook_manager.reload()
        return '🔄 Hooks reloaded'
    return '❌ Usage: /hooks list|test|add|reload'


def _cmd_plugins(cmd, session, **_):
    from salmalm.plugin_manager import plugin_manager
    parts = cmd.split(maxsplit=2)
    sub = parts[1] if len(parts) > 1 else 'list'
    if sub == 'list':
        plugins = plugin_manager.list_plugins()
        if not plugins:
            return '🔌 No plugins found. Add to ~/.salmalm/plugins/'
        lines = ['🔌 **Plugins** (플러그인)\n']
        for p in plugins:
            status = '✅' if p['enabled'] else '❌'
            err = f" ⚠️ {p['error']}" if p.get('error') else ''
            lines.append(f"• {status} **{p['name']}** v{p['version']} — {p['description'][:40]}{err}")
            if p['tools']:
                lines.append(f"  Tools: {', '.join(p['tools'])}")
        return '\n'.join(lines)
    elif sub == 'reload':
        return plugin_manager.reload_all()
    elif sub == 'enable' and len(parts) > 2:
        return plugin_manager.enable(parts[2].strip())
    elif sub == 'disable' and len(parts) > 2:
        return plugin_manager.disable(parts[2].strip())
    return '❌ Usage: /plugins list|reload|enable|disable <name>'


# ── Self-Evolving Prompt commands ──
def _cmd_evolve(cmd, session, **_):
    parts = cmd.strip().split(None, 2)
    sub = parts[1] if len(parts) > 1 else 'status'
    from salmalm.self_evolve import prompt_evolver
    if sub == 'status':
        return prompt_evolver.get_status()
    elif sub == 'apply':
        from salmalm.prompt import USER_SOUL_FILE
        return prompt_evolver.apply_to_soul(USER_SOUL_FILE)
    elif sub == 'reset':
        return prompt_evolver.reset()
    elif sub == 'history':
        return prompt_evolver.get_history()
    return '❌ Usage: /evolve status|apply|reset|history'

# ── Mood-Aware commands ──


def _cmd_mood(cmd, session, **_):
    parts = cmd.strip().split(None, 2)
    sub = parts[1] if len(parts) > 1 else 'status'
    from salmalm.mood import mood_detector
    if sub == 'status':
        # Use last user message for context
        last_msg = ''
        for m in reversed(session.messages):
            if m.get('role') == 'user':
                last_msg = str(m.get('content', ''))
                break
        return mood_detector.get_status(last_msg)
    elif sub in ('off', 'on', 'sensitive'):
        return mood_detector.set_mode(sub)
    elif sub == 'report':
        period = parts[2] if len(parts) > 2 else 'week'
        return mood_detector.generate_report(period)
    return '❌ Usage: /mood status|off|on|sensitive|report [week|month]'

# ── Thought Stream commands ──


def _cmd_thought(cmd, session, **_):
    from salmalm.thoughts import thought_stream, _format_thoughts, _format_stats
    text = cmd.strip()
    # Remove /think prefix
    if text.startswith('/thought'):
        text = text[8:].strip()
    elif text.startswith('/think'):
        # Only handle /think subcommands here, not /think <question> for deep reasoning
        text = text[6:].strip()

    if not text:
        return '❌ Usage: /think <내용> | /think list | /think search <쿼리> | /think tag <태그> | /think stats'

    parts = text.split(None, 1)
    sub = parts[0]
    arg = parts[1].strip() if len(parts) > 1 else ''

    if sub == 'list':
        n = int(arg) if arg.isdigit() else 10
        thoughts = thought_stream.list_recent(n)
        return _format_thoughts(thoughts, f'💭 **최근 {n}개 생각**\n')
    elif sub == 'search':
        if not arg:
            return '❌ Usage: /think search <쿼리>'
        results = thought_stream.search(arg)
        return _format_thoughts(results, f'🔍 **검색: {arg}**\n')
    elif sub == 'tag':
        if not arg:
            return '❌ Usage: /think tag <태그>'
        results = thought_stream.by_tag(arg)
        return _format_thoughts(results, f'🏷️ **태그: #{arg}**\n')
    elif sub == 'timeline':
        results = thought_stream.timeline(arg if arg else None)
        date_label = arg if arg else '오늘'
        return _format_thoughts(results, f'📅 **타임라인: {date_label}**\n')
    elif sub == 'stats':
        return _format_stats(thought_stream.stats())
    elif sub == 'export':
        md = thought_stream.export_markdown()
        return md
    else:
        # It's a thought to record — detect mood first
        thought_text = text
        mood = 'neutral'
        try:
            from salmalm.mood import mood_detector
            mood, _ = mood_detector.detect(thought_text)
        except Exception:
            pass
        tid = thought_stream.add(thought_text, mood=mood)
        tags = ''
        import re as _re2
        found_tags = _re2.findall(r'#(\w+)', thought_text)
        if found_tags:
            tags = f' 🏷️ {", ".join("#" + t for t in found_tags)}'
        return f'💭 생각 #{tid} 기록됨{tags}'


def _cmd_export_fn(cmd, session, **_):
    """Handle /export [md|json|html] command."""
    from salmalm.core.export import export_session
    parts = cmd.strip().split()
    fmt = parts[1] if len(parts) > 1 else 'md'
    result = export_session(session, fmt=fmt)
    if result.get('ok'):
        return (f'📤 **Conversation exported**\n'
                f'Format: {fmt.upper()}\n'
                f'File: `{result["filename"]}`\n'
                f'Size: {result["size"]:,} bytes\n'
                f'Path: `{result["path"]}`')
    return f'❌ Export failed: {result.get("error", "unknown error")}'


# Public alias
_cmd_export = _cmd_export_fn

# Exact-match slash commands
_SLASH_COMMANDS = {
    '/clear': _cmd_clear,
    '/help': _cmd_help,
    '/status': _cmd_status,
    '/tools': _cmd_tools,
    '/uptime': _cmd_uptime,
    '/latency': _cmd_latency,
    '/health detail': _cmd_health_detail,
    '/health_detail': _cmd_health_detail,
    '/prune': _cmd_prune,
    '/usage daily': _cmd_usage_daily,
    '/usage monthly': _cmd_usage_monthly,
    '/bookmarks': _cmd_bookmarks,
    '/security': _cmd_security,
    '/soul': _cmd_soul,
    '/soul reset': _cmd_soul_reset,
    '/context': _cmd_context,
    '/context detail': _cmd_context,
}

# Also add /usage to prefix commands

# Prefix-match slash commands (checked with startswith)
_SLASH_PREFIX_COMMANDS = [
    ('/usage', _cmd_usage),
    ('/think ', _cmd_think),
    ('/plan ', _cmd_plan),
    ('/compare ', _cmd_compare),
    ('/model ', _cmd_model),
    ('/tts', _cmd_tts),
    ('/voice', _cmd_voice),
    ('/subagents', _cmd_subagents),
    ('/agent', _cmd_agent),
    ('/hooks', _cmd_hooks),
    ('/plugins', _cmd_plugins),
    ('/evolve', _cmd_evolve),
    ('/mood', _cmd_mood),
    ('/thought', _cmd_thought),
    ('/export', _cmd_export_fn),
]


async def _dispatch_slash_command(cmd, session, session_id, model_override, on_tool):
    """Dispatch slash commands. Returns response string or None if not a command."""
    # Exact match first
    handler = _SLASH_COMMANDS.get(cmd)
    if handler is not None:
        result = handler(cmd, session, session_id=session_id,
                         model_override=model_override, on_tool=on_tool)
        if asyncio.iscoroutine(result):
            return await result
        return result

    # Prefix match
    for prefix, handler in _SLASH_PREFIX_COMMANDS:
        if cmd.startswith(prefix) or (not prefix.endswith(' ') and cmd == prefix.rstrip()):
            result = handler(cmd, session, session_id=session_id,
                             model_override=model_override, on_tool=on_tool)
            if asyncio.iscoroutine(result):
                return await result
            return result

    return None


async def _process_message_inner(session_id: str, user_message: str,
                                 model_override: Optional[str] = None,
                                 image_data: Optional[Tuple[str, str]] = None,
                                 on_tool: Optional[Callable[[str, Any], None]] = None,
                                 on_token: Optional[Callable] = None,
                                 on_status: Optional[Callable] = None) -> str:
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
            from salmalm.users import user_manager, QuotaExceeded
            user_manager.check_quota(session.user_id)
        except QuotaExceeded as e:
            return f'⚠️ {e.message}'

    # Fire on_message hook (메시지 수신 훅)
    try:
        from salmalm.hooks import hook_manager
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

    # Context management
    session.messages = compact_messages(session.messages, session=session)
    if len(session.messages) % 20 == 0:
        session.add_system(build_system_prompt(full=False))

    # RAG context injection — augment with relevant memory/docs
    try:
        from salmalm.rag import inject_rag_context
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
        from salmalm.mood import mood_detector
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
        from salmalm.self_evolve import prompt_evolver
        if len(session.messages) > 4 and len(session.messages) % 10 == 0:
            prompt_evolver.record_conversation(session.messages)
    except Exception:
        pass

    # Classify and run through Intelligence Engine
    classification = TaskClassifier.classify(user_message, len(session.messages))

    # Override thinking based on session-level toggle
    if session.thinking_enabled:
        classification['thinking'] = True
        if classification['thinking_budget'] == 0:
            classification['thinking_budget'] = 10000

    # Multi-model routing: select optimal model if no override
    selected_model = model_override
    complexity = 'auto'
    if not model_override:
        selected_model, complexity = _select_model(user_message, session)
        log.info(f"[ROUTE] Multi-model: {complexity} → {selected_model}")
    # Fix outdated model names to actual API IDs
    selected_model = _fix_model_name(selected_model)

    # ── SLA: Measure latency (레이턴시 측정) ──
    _sla_start = _time.time()
    _sla_first_token_time = [0.0]  # mutable for closure
    _orig_on_token = on_token

    def _sla_on_token(event):
        if _sla_first_token_time[0] == 0.0:
            _sla_first_token_time[0] = _time.time()
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
        from salmalm.sla import latency_tracker
        _sla_end = _time.time()
        _ttft_ms = ((_sla_first_token_time[0] - _sla_start) * 1000
                    if _sla_first_token_time[0] > 0 else (_sla_end - _sla_start) * 1000)
        _total_ms = (_sla_end - _sla_start) * 1000
        from salmalm.sla import sla_config as _sla_cfg
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
        from salmalm.hooks import hook_manager
        hook_manager.fire('on_response', {
            'session_id': session_id, 'message': response,
        })
    except Exception:
        pass

    return response


def _notify_completion(session_id: str, user_message: str, response: str, classification: dict):
    """Send completion notifications to Telegram + Web chat."""
    from salmalm.core import _tg_bot
    from salmalm.crypto import vault

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
