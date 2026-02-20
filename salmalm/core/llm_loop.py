"""LLM call loop — streaming, failover, cooldowns, routing.

Extracted from engine.py for maintainability.
"""
from __future__ import annotations

import asyncio
import json
import threading as _threading
import time as _time
from pathlib import Path as _Path
from typing import Any, Dict, Optional, Tuple

from salmalm.crypto import log
from salmalm.llm import call_llm as _call_llm_sync, stream_anthropic as _stream_anthropic, stream_google as _stream_google

# ============================================================
# Model Failover — exponential backoff cooldown + fallback chain
# ============================================================
_FAILOVER_CONFIG_FILE = _Path.home() / '.salmalm' / 'failover.json'
_COOLDOWN_FILE = _Path.home() / '.salmalm' / 'cooldowns.json'
_cooldown_lock = _threading.Lock()

# Default fallback chains (no config needed)
_DEFAULT_FALLBACKS = {
    'anthropic/claude-opus-4-6': ['anthropic/claude-sonnet-4-20250514', 'anthropic/claude-haiku-3.5-20241022'],
    'anthropic/claude-sonnet-4-20250514': ['anthropic/claude-haiku-3.5-20241022', 'anthropic/claude-opus-4-6'],
    'anthropic/claude-haiku-3.5-20241022': ['anthropic/claude-sonnet-4-20250514'],
    'google/gemini-2.5-pro': ['google/gemini-2.5-flash', 'google/gemini-2.0-flash'],
    'google/gemini-2.5-flash': ['google/gemini-2.0-flash', 'google/gemini-2.5-pro'],
    'google/gemini-2.0-flash': ['google/gemini-2.5-flash'],
    'google/gemini-3-pro-preview': ['google/gemini-2.5-pro', 'google/gemini-3-flash-preview'],
    'google/gemini-3-flash-preview': ['google/gemini-2.0-flash', 'google/gemini-2.5-flash'],
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
        log.warning(f"[FAILOVER] {model} cooled down for {cooldown_secs}s (failure #{failures + 1})")


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


def save_failover_config(config: dict) -> None:
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


# ============================================================
# Async LLM call wrappers
# ============================================================

async def _call_llm_async(*args, **kwargs):
    """Non-blocking LLM call — runs urllib in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(_call_llm_sync, *args, **kwargs)


async def _call_google_streaming(messages, model=None, tools=None,
                                 max_tokens=4096, on_token=None):
    """Streaming Google Gemini call — yields tokens via on_token callback, returns final result."""
    def _run():
        final_result = None
        for event in _stream_google(messages, model=model, tools=tools,
                                    max_tokens=max_tokens):
            if on_token:
                on_token(event)
            if event.get('type') == 'message_end':
                final_result = event
            elif event.get('type') == 'error':
                return {'content': event.get('error', '❌ Google streaming error'),
                        'tool_calls': [], 'usage': {'input': 0, 'output': 0},
                        'model': model or '?'}
        return final_result or {'content': '', 'tool_calls': [],
                                'usage': {'input': 0, 'output': 0},
                                'model': model or '?'}
    return await asyncio.to_thread(_run)


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
# Failover-aware LLM calls (used by IntelligenceEngine)
# ============================================================

async def call_with_failover(messages: list, model: str, tools: Optional[list] = None,
                             max_tokens: int = 4096, thinking: bool = False,
                             on_token: Optional[object] = None,
                             on_status: Optional[object] = None) -> Tuple[Dict[str, Any], Optional[str]]:
    """LLM call with automatic failover on failure.

    on_status: optional callback(status_type, detail_str) for typing indicators.
    Returns (result_dict, failover_warning_or_None).
    """
    # Check if primary model is cooled down
    if _is_model_cooled_down(model):
        log.info(f"[FAILOVER] {model} is in cooldown, trying fallbacks")
        chain = _load_failover_config().get(model, [])
        for fb in chain:
            if not _is_model_cooled_down(fb):
                warn = f"⚠️ {model.split('/')[-1]} in cooldown, using {fb.split('/')[-1]}"
                result = await try_llm_call(messages, fb, tools, max_tokens, thinking, on_token)
                if not result.get('_failed'):
                    _clear_model_cooldown(fb)
                    return result, warn
                _record_model_failure(fb)
        # All in cooldown — try primary anyway
        pass

    # Try primary model
    result = await try_llm_call(messages, model, tools, max_tokens, thinking, on_token)
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
        result = await try_llm_call(messages, fb, tools, max_tokens, thinking, on_token)
        if not result.get('_failed'):
            _clear_model_cooldown(fb)
            warn = f"⚠️ {model.split('/')[-1]} failed, fell back to {fb.split('/')[-1]}"
            return result, warn
        _record_model_failure(fb)

    # All failed — return the last error
    return result, "⚠️ All models failed"


async def try_llm_call(messages: list, model: str, tools: Optional[list],
                       max_tokens: int, thinking: bool,
                       on_token: Optional[object]) -> Dict[str, Any]:
    """Single LLM call attempt. Sets _failed=True on exception."""
    provider = model.split('/')[0] if '/' in model else 'anthropic'
    try:
        if on_token and provider == 'anthropic':
            result = await _call_llm_streaming(
                messages, model=model, tools=tools,
                thinking=thinking, on_token=on_token)
        elif on_token and provider == 'google':
            result = await _call_google_streaming(
                messages, model=model, tools=tools,
                max_tokens=max_tokens, on_token=on_token)
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
