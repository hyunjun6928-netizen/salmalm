"""SalmAlm Intelligence Engine — TaskClassifier + IntelligenceEngine + process_message."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from .constants import (VERSION, INTENT_SHORT_MSG, INTENT_COMPLEX_MSG,
                        INTENT_CONTEXT_DEPTH, REFLECT_SNIPPET_LEN,
                        MODEL_ALIASES as _CONST_ALIASES, COMMAND_MODEL)
import re as _re
import threading as _threading
import time as _time
from .crypto import log

# Graceful shutdown state
_shutting_down = False
_active_requests = 0
_active_requests_lock = _threading.Lock()
_active_requests_event = _threading.Event()  # signaled when _active_requests == 0
from .core import router, compact_messages, get_session, _sessions, _metrics, compact_session, auto_compact_if_needed, audit_log
from .prompt import build_system_prompt
from .tool_handlers import execute_tool
from .llm import call_llm as _call_llm_sync, stream_anthropic as _stream_anthropic

# ============================================================
# Session Pruning — soft-trim / hard-clear old tool results
# ============================================================
_PRUNE_KEEP_LAST_ASSISTANTS = 3
_PRUNE_SOFT_LIMIT = 4000
_PRUNE_HARD_LIMIT = 50_000
_PRUNE_HEAD = 1500
_PRUNE_TAIL = 1500


def _has_image_block(content) -> bool:
    """Check if a content block list contains image data."""
    if not isinstance(content, list):
        return False
    return any(
        (isinstance(b, dict) and b.get('type') in ('image', 'image_url'))
        or (isinstance(b, dict) and b.get('source', {}).get('type') == 'base64')
        for b in content
    )


def _soft_trim(text: str) -> str:
    """Trim long text to head + ... + tail."""
    if len(text) <= _PRUNE_SOFT_LIMIT:
        return text
    return text[:_PRUNE_HEAD] + f"\n\n... [{len(text)} chars, trimmed] ...\n\n" + text[-_PRUNE_TAIL:]


def prune_context(messages: list) -> tuple:
    """Prune old tool_result messages before LLM call.

    Returns (pruned_messages, stats_dict).
    Does NOT modify the original list — returns a deep copy.
    """
    import copy
    pruned = copy.deepcopy(messages)
    stats = {'soft_trimmed': 0, 'hard_cleared': 0, 'unchanged': 0}

    # Find the index of the Nth-last assistant message
    assistant_indices = [i for i, m in enumerate(pruned) if m.get('role') == 'assistant']
    if len(assistant_indices) <= _PRUNE_KEEP_LAST_ASSISTANTS:
        return pruned, stats  # Not enough history to prune
    cutoff_idx = assistant_indices[-_PRUNE_KEEP_LAST_ASSISTANTS]

    for i in range(cutoff_idx):
        m = pruned[i]
        # Anthropic-style tool results in user messages
        if m.get('role') == 'user' and isinstance(m.get('content'), list):
            if _has_image_block(m['content']):
                stats['unchanged'] += 1
                continue
            for j, block in enumerate(m['content']):
                if not isinstance(block, dict):
                    continue
                if block.get('type') != 'tool_result':
                    continue
                text = block.get('content', '')
                if not isinstance(text, str):
                    continue
                if len(text) >= _PRUNE_HARD_LIMIT:
                    m['content'][j] = {**block, 'content': '[Tool result cleared]'}
                    stats['hard_cleared'] += 1
                elif len(text) > _PRUNE_SOFT_LIMIT:
                    m['content'][j] = {**block, 'content': _soft_trim(text)}
                    stats['soft_trimmed'] += 1
                else:
                    stats['unchanged'] += 1
        # OpenAI-style tool messages
        elif m.get('role') == 'tool':
            text = m.get('content', '')
            if not isinstance(text, str):
                continue
            if len(text) >= _PRUNE_HARD_LIMIT:
                pruned[i] = {**m, 'content': '[Tool result cleared]'}
                stats['hard_cleared'] += 1
            elif len(text) > _PRUNE_SOFT_LIMIT:
                pruned[i] = {**m, 'content': _soft_trim(text)}
                stats['soft_trimmed'] += 1
            else:
                stats['unchanged'] += 1

    return pruned, stats


# ============================================================
# Model Failover — exponential backoff cooldown + fallback chain
# ============================================================
_FAILOVER_CONFIG_FILE = __import__('pathlib').Path.home() / '.salmalm' / 'failover.json'
_COOLDOWN_FILE = __import__('pathlib').Path.home() / '.salmalm' / 'cooldowns.json'
_cooldown_lock = _threading.Lock()

# Default fallback chains (no config needed)
_DEFAULT_FALLBACKS = {
    'anthropic/claude-opus-4-6': ['anthropic/claude-sonnet-4-20250514', 'anthropic/claude-haiku-3.5-20241022'],
    'anthropic/claude-sonnet-4-20250514': ['anthropic/claude-haiku-3.5-20241022', 'anthropic/claude-opus-4-6'],
    'anthropic/claude-haiku-3.5-20241022': ['anthropic/claude-sonnet-4-20250514'],
}
_COOLDOWN_STEPS = [60, 300, 1500, 3600]  # 1m, 5m, 25m, 1h


def _load_failover_config() -> dict:
    """Load user failover chain config, falling back to defaults."""
    try:
        if _FAILOVER_CONFIG_FILE.exists():
            cfg = json.loads(_FAILOVER_CONFIG_FILE.read_text(encoding='utf-8'))
            if isinstance(cfg, dict):
                merged = dict(_DEFAULT_FALLBACKS)
                merged.update(cfg)
                return merged
    except Exception:
        pass
    return dict(_DEFAULT_FALLBACKS)


def _load_cooldowns() -> dict:
    """Load cooldown state: {model: {until: float, failures: int}}."""
    try:
        if _COOLDOWN_FILE.exists():
            data = json.loads(_COOLDOWN_FILE.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_cooldowns(cd: dict):
    try:
        _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _COOLDOWN_FILE.write_text(json.dumps(cd), encoding='utf-8')
    except Exception:
        pass


def _is_model_cooled_down(model: str) -> bool:
    """Check if a model is in cooldown."""
    with _cooldown_lock:
        cd = _load_cooldowns()
        entry = cd.get(model)
        if not entry:
            return False
        return _time.time() < entry.get('until', 0)


def _record_model_failure(model: str):
    """Record a model failure and set cooldown."""
    with _cooldown_lock:
        cd = _load_cooldowns()
        entry = cd.get(model, {'until': 0, 'failures': 0})
        failures = entry.get('failures', 0)
        step = min(failures, len(_COOLDOWN_STEPS) - 1)
        cooldown_secs = _COOLDOWN_STEPS[step]
        cd[model] = {
            'until': _time.time() + cooldown_secs,
            'failures': failures + 1,
        }
        _save_cooldowns(cd)
        log.warning(f"[FAILOVER] {model} cooled down for {cooldown_secs}s (failure #{failures+1})")


def _clear_model_cooldown(model: str):
    """Clear cooldown on successful call."""
    with _cooldown_lock:
        cd = _load_cooldowns()
        if model in cd:
            del cd[model]
            _save_cooldowns(cd)


def get_failover_config() -> dict:
    """Public getter for failover config (used by web API / settings)."""
    return _load_failover_config()


def save_failover_config(config: dict):
    """Save user's failover chain config."""
    try:
        _FAILOVER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _FAILOVER_CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding='utf-8')
    except Exception:
        pass


# ============================================================
# Status callback types for typing indicators
# ============================================================
STATUS_TYPING = 'typing'
STATUS_THINKING = 'thinking'
STATUS_TOOL_RUNNING = 'tool_running'


async def _call_llm_async(*args, **kwargs):
    """Non-blocking LLM call — runs urllib in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(_call_llm_sync, *args, **kwargs)


async def _call_llm_streaming(messages, model=None, tools=None,
                               max_tokens=4096, thinking=False,
                               on_token=None):
    """Streaming LLM call — yields tokens via on_token callback, returns final result.

    on_token: callback(event_dict) called for each streaming event.
    Returns the same dict format as call_llm.
    """
    def _run():
        final_result = None
        for event in _stream_anthropic(messages, model=model, tools=tools,
                                        max_tokens=max_tokens, thinking=thinking):
            if on_token:
                on_token(event)
            if event.get('type') == 'message_end':
                final_result = event
            elif event.get('type') == 'error':
                return {'content': event.get('error', '❌ Streaming error'),
                        'tool_calls': [], 'usage': {'input': 0, 'output': 0},
                        'model': model or '?'}
        return final_result or {'content': '', 'tool_calls': [],
                                 'usage': {'input': 0, 'output': 0},
                                 'model': model or '?'}
    return await asyncio.to_thread(_run)

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

from .constants import MODELS as _MODELS
import json as _json
from pathlib import Path as _Path

# Routing config: user can override which model to use for each complexity level
_ROUTING_CONFIG_FILE = _Path.home() / '.salmalm' / 'routing.json'

def _load_routing_config() -> dict:
    """Load user's model routing config. Returns {simple, moderate, complex} model IDs."""
    defaults = {'simple': _MODELS['haiku'], 'moderate': _MODELS['sonnet'], 'complex': _MODELS['opus']}
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

    def _get_tools_for_provider(self, provider: str) -> list:
        from .tools import TOOL_DEFINITIONS
        from .core import PluginLoader
        from .mcp import mcp_manager
        # Merge built-in + plugin + MCP tools (deduplicate by name)
        all_tools = list(TOOL_DEFINITIONS)
        seen = {t['name'] for t in all_tools}
        for t in PluginLoader.get_all_tools() + mcp_manager.get_all_tools():
            if t['name'] not in seen:
                all_tools.append(t)
                seen.add(t['name'])
        
        if provider == 'google':
            # Google Gemini: use OpenAI-compatible tool format
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
        if classification['score'] >= 3:  # High confidence complex task
            return True
        return False

    async def _call_with_failover(self, messages, model, tools=None,
                                   max_tokens=4096, thinking=False,
                                   on_token=None, on_status=None):
        """LLM call with automatic failover on failure.

        on_status: optional callback(status_type, detail_str) for typing indicators.
        Returns (result_dict, failover_warning_or_None).
        """
        provider = model.split('/')[0] if '/' in model else 'anthropic'

        # Check if primary model is cooled down
        if _is_model_cooled_down(model):
            log.info(f"[FAILOVER] {model} is in cooldown, trying fallbacks")
            chain = _load_failover_config().get(model, [])
            for fb in chain:
                if not _is_model_cooled_down(fb):
                    warn = f"⚠️ {model.split('/')[-1]} in cooldown, using {fb.split('/')[-1]}"
                    result = await self._try_llm_call(messages, fb, tools, max_tokens, thinking, on_token)
                    if not result.get('_failed'):
                        _clear_model_cooldown(fb)
                        return result, warn
                    _record_model_failure(fb)
            # All in cooldown — try primary anyway
            pass

        # Try primary model
        result = await self._try_llm_call(messages, model, tools, max_tokens, thinking, on_token)
        if not result.get('_failed'):
            _clear_model_cooldown(model)
            return result, None

        # Primary failed — record and try fallbacks
        _record_model_failure(model)
        chain = _load_failover_config().get(model, [])
        for fb in chain:
            if _is_model_cooled_down(fb):
                continue
            log.info(f"[FAILOVER] {model} failed, trying {fb}")
            if on_status:
                on_status(STATUS_TYPING, f"⚠️ {model.split('/')[-1]} failed, falling back to {fb.split('/')[-1]}")
            result = await self._try_llm_call(messages, fb, tools, max_tokens, thinking, on_token)
            if not result.get('_failed'):
                _clear_model_cooldown(fb)
                warn = f"⚠️ {model.split('/')[-1]} failed, fell back to {fb.split('/')[-1]}"
                return result, warn
            _record_model_failure(fb)

        # All failed — return the last error
        return result, f"⚠️ All models failed"

    async def _try_llm_call(self, messages, model, tools, max_tokens, thinking, on_token):
        """Single LLM call attempt. Sets _failed=True on exception."""
        provider = model.split('/')[0] if '/' in model else 'anthropic'
        try:
            if on_token and provider == 'anthropic':
                result = await _call_llm_streaming(
                    messages, model=model, tools=tools,
                    thinking=thinking, on_token=on_token)
            else:
                result = await _call_llm_async(messages, model=model, tools=tools,
                                               thinking=thinking)
            # Check for error responses that indicate API failure
            content = result.get('content', '')
            if isinstance(content, str) and content.startswith('❌') and 'API key' not in content:
                result['_failed'] = True
            return result
        except Exception as e:
            log.error(f"[FAILOVER] {model} call error: {e}")
            return {'content': f'❌ {e}', 'tool_calls': [], '_failed': True,
                    'usage': {'input': 0, 'output': 0}, 'model': model}

    async def run(self, session, user_message: str,
                  model_override: Optional[str] = None, on_tool=None,
                  classification: Optional[dict] = None,
                  on_token=None, on_status=None) -> str:
        """Main execution loop — Plan → Execute → Reflect."""

        if not classification:
            classification = TaskClassifier.classify(
                user_message, len(session.messages))

        tier = classification['tier']
        use_thinking = classification['thinking']
        thinking_budget = classification['thinking_budget']
        log.info(f"[AI] Intent: {classification['intent']} (tier={tier}, "
                 f"think={use_thinking}, budget={thinking_budget}, "
                 f"score={classification['score']})")

        # PHASE 1: PLANNING — inject plan prompt for complex tasks
        if classification['intent'] in ('code', 'analysis') and classification['score'] >= 2:
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
            import traceback; traceback.print_exc()
            error_msg = f'❌ Processing error: {type(e).__name__}: {e}'
            session.add_assistant(error_msg)
            return error_msg

    # ── OpenClaw-style limits ──
    MAX_TOOL_ITERATIONS = 15
    MAX_CONSECUTIVE_ERRORS = 3

    async def _execute_loop(self, session, user_message, model_override,
                             on_tool, classification, tier, on_token=None,
                             on_status=None):
        use_thinking = classification['thinking'] or getattr(session, 'thinking_enabled', False)
        thinking_budget = classification['thinking_budget'] or (10000 if use_thinking else 0)
        iteration = 0
        consecutive_errors = 0
        while iteration < self.MAX_TOOL_ITERATIONS:
            model = model_override or router.route(
                user_message, has_tools=True, iteration=iteration)

            # Force tier upgrade for complex tasks
            if not model_override and tier == 3 and iteration == 0:
                model = router._pick_available(3)
            elif not model_override and tier == 2 and iteration == 0:
                model = router._pick_available(2)

            provider = model.split('/')[0] if '/' in model else 'anthropic'

            # OpenClaw-style: intent별 도구 선별 주입 — chat/memory/creative엔 도구 불필요
            _TOOL_INTENTS = {'code', 'analysis', 'search', 'system'}
            if classification['intent'] in _TOOL_INTENTS:
                tools = self._get_tools_for_provider(provider)
            else:
                tools = None

            # Use thinking for first call on complex tasks
            think_this_call = (use_thinking and iteration == 0
                               and provider == 'anthropic'
                               and ('opus' in model or 'sonnet' in model))

            # Session pruning — trim old tool results before LLM call
            pruned_messages, prune_stats = prune_context(session.messages)
            if prune_stats['soft_trimmed'] or prune_stats['hard_cleared']:
                log.info(f"[PRUNE] soft={prune_stats['soft_trimmed']} hard={prune_stats['hard_cleared']}")

            # Status callback: typing/thinking
            if on_status:
                if think_this_call:
                    on_status(STATUS_THINKING, '🧠 Thinking...')
                else:
                    on_status(STATUS_TYPING, 'typing')

            # LLM call with failover
            _failover_warn = None
            result, _failover_warn = await self._call_with_failover(
                pruned_messages, model=model, tools=tools,
                max_tokens=4096, thinking=think_this_call,
                on_token=on_token, on_status=on_status)
            # Clean internal flag
            result.pop('_failed', None)

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

            # Audit API call
            usage = result.get('usage', {})
            api_detail = {
                'model': result.get('model', model),
                'input_tokens': usage.get('input', 0),
                'output_tokens': usage.get('output', 0),
                'iteration': iteration,
            }
            if usage.get('input', 0) or usage.get('output', 0):
                audit_log('api_call', f"{model} in={usage.get('input',0)} out={usage.get('output',0)}",
                          detail_dict=api_detail)

            if result.get('thinking'):
                log.info(f"[AI] Thinking: {len(result['thinking'])} chars")

            if result.get('tool_calls'):
                # Status: tool running
                if on_status:
                    tool_names = ', '.join(tc['name'] for tc in result['tool_calls'][:3])
                    on_status(STATUS_TOOL_RUNNING, f'🔧 Running {tool_names}...')

                tool_outputs = await asyncio.to_thread(
                    self._execute_tools_parallel,
                    result['tool_calls'], on_tool)

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
            response = result.get('content', 'Could not generate a response.')

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
    """Process a user message through the Intelligence Engine pipeline."""
    # Reject new requests during shutdown
    if _shutting_down:
        return '⚠️ Server is shutting down. Please try again later.'

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
    finally:
        with _active_requests_lock:
            _active_requests -= 1
            if _active_requests == 0:
                _active_requests_event.set()


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

    # --- Slash commands (fast path, no LLM) ---
    cmd = user_message.strip()
    if cmd == '/clear':
        session.messages = [m for m in session.messages if m['role'] == 'system'][:1]
        return 'Conversation cleared.'
    if cmd == '/help':
        from .tools import TOOL_DEFINITIONS
        tool_count = len(TOOL_DEFINITIONS)
        return f"""😈 **SalmAlm v{VERSION}** — Personal AI Gateway

📌 **Commands**
/clear — Clear conversation
/help — This help
/model <name> — Change model
/think <question> — 🧠 Deep reasoning (Opus)
/plan <question> — 📋 Plan → Execute
/status — Usage + Cost
/tools — Tool list

🤖 **Model Aliases** (27)
claude, sonnet, opus, haiku, gpt, gpt5, o3, o4mini,
grok, grok4, gemini, flash, deepseek, llama, auto ...

🔧 **Tools** ({tool_count})
File R/W, code exec, web search, RAG search,
system monitor, cron jobs, image analysis, TTS ...

🧠 **Intelligence Engine**
Auto intent classification (7 levels) → Model routing → Parallel tools → Self-evaluation

💡 **Tip**: Just speak naturally. Read a file, search the web, write code, etc."""
    if cmd == '/status':
        return execute_tool('usage_report', {})
    if cmd == '/tools':
        from .tools import TOOL_DEFINITIONS
        lines = [f'🔧 **Tool List** ({len(TOOL_DEFINITIONS)})\n']
        for t in TOOL_DEFINITIONS:
            lines.append(f"• **{t['name']}** — {t['description'][:60]}")  # type: ignore[index]
        return '\n'.join(lines)
    if cmd.startswith('/think '):
        think_msg = cmd[7:].strip()
        if not think_msg:
            return 'Usage: /think <question>'
        session.add_user(think_msg)
        session.messages = compact_messages(session.messages, session=session)
        classification = {'intent': 'analysis', 'tier': 3, 'thinking': True,
                          'thinking_budget': 16000, 'score': 5}
        return await _engine.run(session, think_msg,
                                  model_override=COMMAND_MODEL,
                                  on_tool=on_tool, classification=classification)
    if cmd.startswith('/plan '):
        plan_msg = cmd[6:].strip()
        if not plan_msg:
            return 'Usage: /plan <task description>'
        session.add_user(plan_msg)
        session.messages = compact_messages(session.messages, session=session)
        classification = {'intent': 'code', 'tier': 3, 'thinking': True,
                          'thinking_budget': 10000, 'score': 5}
        return await _engine.run(session, plan_msg, model_override=model_override,
                                  on_tool=on_tool, classification=classification)
    if cmd == '/prune':
        _, stats = prune_context(session.messages)
        total = stats['soft_trimmed'] + stats['hard_cleared'] + stats['unchanged']
        return (f"🧹 **Session Pruning Results**\n"
                f"• Soft-trimmed: {stats['soft_trimmed']}\n"
                f"• Hard-cleared: {stats['hard_cleared']}\n"
                f"• Unchanged: {stats['unchanged']}\n"
                f"• Total tool results scanned: {total}")
    if cmd == '/soul':
        from .prompt import get_user_soul, USER_SOUL_FILE
        content = get_user_soul()
        if content:
            return f'📜 **SOUL.md** (`{USER_SOUL_FILE}`)\n\n{content}'
        return f'📜 SOUL.md is not set. Create `{USER_SOUL_FILE}` or edit via Settings.'
    if cmd == '/soul reset':
        from .prompt import reset_user_soul
        reset_user_soul()
        # Refresh system prompt
        session.add_system(build_system_prompt(full=True))
        return '📜 SOUL.md reset to default.'
    if cmd.startswith('/model '):
        model_name = cmd[7:].strip()
        # Session-level multi-model routing
        if model_name in ('auto', 'opus', 'sonnet', 'haiku'):
            session.model_override = model_name if model_name != 'auto' else 'auto'
            if model_name == 'auto':
                router.set_force_model(None)
                return 'Model: **auto** (cost-optimized routing) — saved ✅\n• simple → haiku ⚡ • moderate → sonnet • complex → opus 💎'
            labels = {'opus': 'claude-opus-4 💎', 'sonnet': 'claude-sonnet-4', 'haiku': 'claude-haiku-3.5 ⚡'}
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
    if cmd.startswith('/tts'):
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
    if cmd.startswith('/voice'):
        arg = cmd[6:].strip()
        valid_voices = ('alloy', 'nova', 'echo', 'fable', 'onyx', 'shimmer')
        if arg in valid_voices:
            session.tts_voice = arg
            return f'🎙️ Voice: **{arg}** — saved ✅'
        return f'Available voices: {", ".join(valid_voices)}'

    # --- Normal message processing ---
    if not user_message.strip() and not image_data:
        return "Please enter a message."

    if image_data:
        b64, mime = image_data
        log.info(f"[IMG] Image attached: {mime}, {len(b64)//1024}KB base64")
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
        from .rag import inject_rag_context
        for i, m in enumerate(session.messages):
            if m.get('role') == 'system':
                session.messages[i] = dict(m)
                session.messages[i]['content'] = inject_rag_context(
                    session.messages, m['content'], max_chars=2500)
                break
    except Exception as e:
        log.warning(f"RAG injection skipped: {e}")

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

    response = await _engine.run(session, user_message,
                              model_override=selected_model,
                              on_tool=on_tool,
                              classification=classification,
                              on_token=on_token,
                              on_status=on_status)

    # Store model metadata on session for API consumers
    session.last_model = selected_model or 'auto'
    session.last_complexity = complexity

    # ── Auto-title session after first assistant response ──
    try:
        user_msgs = [m for m in session.messages if m.get('role') == 'user' and isinstance(m.get('content'), str)]
        assistant_msgs = [m for m in session.messages if m.get('role') == 'assistant']
        if len(assistant_msgs) == 1 and user_msgs:
            from .core import auto_title_session
            auto_title_session(session_id, user_msgs[0]['content'])
    except Exception as e:
        log.warning(f"Auto-title hook error: {e}")

    # ── Completion Notification Hook ──
    # Notify other channels when a task completes
    try:
        _notify_completion(session_id, user_message, response, classification)
    except Exception as e:
        log.error(f"Notification hook error: {e}")

    return response


def _notify_completion(session_id: str, user_message: str, response: str, classification: dict):
    """Send completion notifications to Telegram + Web chat."""
    from .core import _tg_bot
    from .crypto import vault

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
        from .core import _sessions
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


def begin_shutdown():
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



