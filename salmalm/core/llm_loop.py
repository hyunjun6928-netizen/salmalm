"""LLM call loop — streaming, failover, cooldowns, routing.

Extracted from engine.py for maintainability.
"""

from __future__ import annotations

import asyncio
import json
import threading as _threading
import time as _time
from salmalm.constants import DATA_DIR as _DATA_DIR
from typing import Any, Dict, Optional, Tuple

from salmalm.security.crypto import log
from salmalm.core.llm import (
    call_llm as _call_llm_sync,
    stream_anthropic as _stream_anthropic,
    stream_google as _stream_google,
)

# ============================================================
# Model Failover — exponential backoff cooldown + fallback chain
# ============================================================
_FAILOVER_CONFIG_FILE = _DATA_DIR / "failover.json"
_COOLDOWN_FILE = _DATA_DIR / "cooldowns.json"
_cooldown_lock = _threading.Lock()

# Default fallback chains (no config needed)
_DEFAULT_FALLBACKS = {
    # Same-provider fallbacks + cross-provider fallbacks
    "anthropic/claude-opus-4-6": ["anthropic/claude-sonnet-4-6", "anthropic/claude-haiku-4-5-20251001", "google/gemini-2.5-pro", "openai/gpt-4.1"],
    "anthropic/claude-sonnet-4-6": ["anthropic/claude-haiku-4-5-20251001", "anthropic/claude-opus-4-6", "google/gemini-2.5-flash", "openai/gpt-4.1-mini"],
    "anthropic/claude-haiku-4-5-20251001": ["anthropic/claude-sonnet-4-6", "google/gemini-2.0-flash", "openai/gpt-4.1-mini"],
    "openai/gpt-5.2": ["openai/gpt-4.1", "anthropic/claude-sonnet-4-6", "google/gemini-2.5-pro"],
    "openai/gpt-4.1": ["openai/gpt-4.1-mini", "anthropic/claude-sonnet-4-6", "google/gemini-2.5-flash"],
    "openai/gpt-4.1-mini": ["openai/gpt-4.1", "google/gemini-2.0-flash", "anthropic/claude-haiku-4-5-20251001"],
    "google/gemini-2.5-pro": ["google/gemini-2.5-flash", "google/gemini-2.0-flash", "anthropic/claude-sonnet-4-6"],
    "google/gemini-2.5-flash": ["google/gemini-2.0-flash", "google/gemini-2.5-pro", "anthropic/claude-haiku-4-5-20251001"],
    "google/gemini-2.0-flash": ["google/gemini-2.5-flash", "anthropic/claude-haiku-4-5-20251001"],
    "google/gemini-3-pro-preview": ["google/gemini-2.5-pro", "google/gemini-3-flash-preview", "anthropic/claude-sonnet-4-6"],
    "google/gemini-3-flash-preview": ["google/gemini-2.0-flash", "google/gemini-2.5-flash", "anthropic/claude-haiku-4-5-20251001"],
    "xai/grok-4": ["xai/grok-3", "anthropic/claude-sonnet-4-6", "google/gemini-2.5-pro"],
    "xai/grok-3": ["xai/grok-4", "anthropic/claude-sonnet-4-6", "google/gemini-2.5-flash"],
}
_COOLDOWN_STEPS = [60, 300, 1500, 3600]  # 1m, 5m, 25m, 1h


def _load_failover_config() -> dict:
    """Load user failover chain config, falling back to defaults."""
    try:
        if _FAILOVER_CONFIG_FILE.exists():
            cfg = json.loads(_FAILOVER_CONFIG_FILE.read_text(encoding="utf-8"))
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
            data = json.loads(_COOLDOWN_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_cooldowns(cd: dict):
    try:
        _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _COOLDOWN_FILE.write_text(json.dumps(cd), encoding="utf-8")
    except Exception:
        pass


def _is_model_cooled_down(model: str) -> bool:
    """Check if a model is in cooldown."""
    with _cooldown_lock:
        cd = _load_cooldowns()
        entry = cd.get(model)
        if not entry:
            return False
        return _time.time() < entry.get("until", 0)


def _cooldown_provider(model: str, cooldown_seconds: int = 3600):
    """Cooldown all models from the same provider (e.g., invalid API key)."""
    provider = model.split("/")[0] if "/" in model else model
    with _cooldown_lock:
        cd = _load_cooldowns()
        # Find all models from this provider in fallback config
        all_models = set()
        for m in _DEFAULT_FALLBACKS:
            if m.startswith(provider + "/"):
                all_models.add(m)
        all_models.add(model)
        for m in all_models:
            cd[m] = {"until": _time.time() + cooldown_seconds, "failures": 99}
        _save_cooldowns(cd)
    log.warning(f"[AUTH] Provider {provider} cooled down for {cooldown_seconds}s ({len(all_models)} models)")


def _record_model_failure(model: str, cooldown_seconds: int = 0):
    """Record a model failure and set cooldown."""
    with _cooldown_lock:
        cd = _load_cooldowns()
        entry = cd.get(model, {"until": 0, "failures": 0})
        failures = entry.get("failures", 0)
        if cooldown_seconds > 0:
            cooldown_secs = cooldown_seconds
        else:
            step = min(failures, len(_COOLDOWN_STEPS) - 1)
            cooldown_secs = _COOLDOWN_STEPS[step]
        cd[model] = {
            "until": _time.time() + cooldown_secs,
            "failures": failures + 1,
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
        _FAILOVER_CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except Exception:
        pass


# ============================================================
# Status callback types for typing indicators
# ============================================================
STATUS_TYPING = "typing"
STATUS_THINKING = "thinking"
STATUS_TOOL_RUNNING = "tool_running"
STATUS_COMPACTING = "compacting"


# ============================================================
# Async LLM call wrappers
# ============================================================


async def _call_llm_async(*args, **kwargs):
    """Non-blocking LLM call — runs urllib in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(_call_llm_sync, *args, **kwargs)


async def _call_google_streaming(messages, model=None, tools=None, max_tokens=4096, on_token=None):
    """Streaming Google Gemini call — yields tokens via on_token callback, returns final result.

    Handles streaming interruptions gracefully — preserves partial content.
    """

    def _run():
        final_result = None
        accumulated_text = []
        try:
            for event in _stream_google(messages, model=model, tools=tools, max_tokens=max_tokens):
                if on_token:
                    on_token(event)
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        accumulated_text.append(delta.get("text", ""))
                if event.get("type") == "message_end":
                    final_result = event
                elif event.get("type") == "error":
                    return {
                        "content": event.get("error", "❌ Google streaming error"),
                        "tool_calls": [],
                        "usage": {"input": 0, "output": 0},
                        "model": model or "?",
                    }
        except Exception as e:
            partial = "".join(accumulated_text)
            if partial:
                log.warning(f"[STREAM] Google streaming interrupted with {len(partial)} chars: {e}")
                return {
                    "content": partial + "\n\n⚠️ [Streaming interrupted]",
                    "tool_calls": [],
                    "usage": {"input": 0, "output": 0},
                    "model": model or "?",
                }
            raise
        return final_result or {
            "content": "".join(accumulated_text) if accumulated_text else "",
            "tool_calls": [],
            "usage": {"input": 0, "output": 0},
            "model": model or "?",
        }

    return await asyncio.to_thread(_run)


async def _call_llm_streaming(messages, model=None, tools=None, max_tokens=4096, thinking=False, on_token=None):
    """Streaming LLM call — yields tokens via on_token callback, returns final result.

    on_token: callback(event_dict) called for each streaming event.
    Returns the same dict format as call_llm.
    Handles streaming interruptions gracefully — preserves partial content.
    """

    def _run():
        import os as _os

        _early_stop = _os.environ.get("SALMALM_EARLY_STOP", "0") == "1"
        final_result = None
        accumulated_text = []
        _has_tool_calls = False
        try:
            for event in _stream_anthropic(
                messages, model=model, tools=tools, max_tokens=max_tokens, thinking=thinking
            ):
                if on_token:
                    on_token(event)
                # Track text deltas for recovery
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        accumulated_text.append(delta.get("text", ""))
                if event.get("type") == "content_block_start":
                    cb = event.get("content_block", {})
                    if cb.get("type") == "tool_use":
                        _has_tool_calls = True
                # Early stop: if text-only response looks complete, break
                if _early_stop and not _has_tool_calls and not tools and len(accumulated_text) > 5:
                    tail = "".join(accumulated_text[-3:]).rstrip()
                    if tail.endswith((".", "!", "?", "。", "！", "？", "```")) and len("".join(accumulated_text)) > 200:
                        log.info("[EARLY_STOP] Response looks complete, stopping stream")
                        break
                if event.get("type") == "message_end":
                    final_result = event
                elif event.get("type") == "error":
                    return {
                        "content": event.get("error", "❌ Streaming error"),
                        "tool_calls": [],
                        "usage": {"input": 0, "output": 0},
                        "model": model or "?",
                    }
        except Exception as e:
            # Streaming interrupted — return partial content if available
            partial = "".join(accumulated_text)
            if partial:
                log.warning(f"[STREAM] Interrupted with {len(partial)} chars partial: {e}")
                return {
                    "content": partial + "\n\n⚠️ [Streaming interrupted]",
                    "tool_calls": [],
                    "usage": {"input": 0, "output": 0},
                    "model": model or "?",
                }
            raise
        return final_result or {
            "content": "".join(accumulated_text) if accumulated_text else "",
            "tool_calls": [],
            "usage": {"input": 0, "output": 0},
            "model": model or "?",
        }

    return await asyncio.to_thread(_run)


# ============================================================
# Failover-aware LLM calls (used by IntelligenceEngine)
# ============================================================


async def call_with_failover(
    messages: list,
    model: str,
    tools: Optional[list] = None,
    max_tokens: int = 4096,
    thinking: bool = False,
    on_token: Optional[object] = None,
    on_status: Optional[object] = None,
) -> Tuple[Dict[str, Any], Optional[str]]:
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
                if not result.get("_failed"):
                    _clear_model_cooldown(fb)
                    return result, warn
                _record_model_failure(fb)
        # All in cooldown — try primary anyway
        pass

    # Try primary model
    result = await try_llm_call(messages, model, tools, max_tokens, thinking, on_token)
    if not result.get("_failed"):
        _clear_model_cooldown(model)
        # Service recovered — drain any queued messages
        try:
            from salmalm.features.message_queue import message_queue

            if message_queue.get_status()["queued"] > 0:
                import asyncio

                asyncio.create_task(message_queue.drain())
        except Exception:
            pass
        return result, None

    # Primary failed — record and try fallbacks
    _record_model_failure(model)
    chain = _load_failover_config().get(model, [])
    for fb in chain:
        if _is_model_cooled_down(fb):
            continue
        log.info(f"[FAILOVER] {model} failed, trying {fb}")
        if on_status:
            _cb_result = on_status(
                STATUS_TYPING, f"⚠️ {model.split('/')[-1]} failed, falling back to {fb.split('/')[-1]}"
            )
            if asyncio.iscoroutine(_cb_result):
                await _cb_result
        result = await try_llm_call(messages, fb, tools, max_tokens, thinking, on_token)
        if not result.get("_failed"):
            _clear_model_cooldown(fb)
            warn = f"⚠️ {model.split('/')[-1]} failed, fell back to {fb.split('/')[-1]}"
            return result, warn
        _record_model_failure(fb)

    # All failed — try to queue the message for later processing
    try:
        from salmalm.features.message_queue import message_queue

        # Extract the last user message for queuing
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if user_msgs:
            last_user = user_msgs[-1]
            content = last_user.get("content", "")
            if isinstance(content, str) and content:
                message_queue.enqueue("unknown", content, model_override=model)
                log.info("[QUEUE] Message queued after all-models-failed")
    except Exception:
        pass

    return result, "⚠️ All models failed"


async def try_llm_call(
    messages: list, model: str, tools: Optional[list], max_tokens: int, thinking: bool, on_token: Optional[object]
) -> Dict[str, Any]:
    """Single LLM call attempt with transient error retry.

    Retries once on transient errors (timeout, 5xx, connection reset).
    Sets _failed=True on persistent failure.
    """
    provider = model.split("/")[0] if "/" in model else "anthropic"
    _TRANSIENT_PATTERNS = (
        "timeout",
        "timed out",
        "529",
        "503",
        "502",
        "connection reset",
        "connection refused",
        "overloaded",
        "rate limit",
        "429",
    )
    _AUTH_PATTERNS = ("401", "invalid api key", "unauthorized", "authentication", "invalid x-api-key")

    last_error = None
    for attempt in range(2):  # 1 initial + 1 retry
        try:
            if on_token and provider == "anthropic":
                result = await _call_llm_streaming(
                    messages, model=model, tools=tools, thinking=thinking, on_token=on_token
                )
            elif on_token and provider == "google":
                result = await _call_google_streaming(
                    messages, model=model, tools=tools, max_tokens=max_tokens, on_token=on_token
                )
            else:
                result = await _call_llm_async(messages, model=model, tools=tools, thinking=thinking)
            # Check for error responses — prefer explicit 'error' field over content sniffing
            if result.get("error"):
                error_str = str(result["error"]).lower()
                # Auth errors: cooldown entire provider (invalid key affects all models)
                if any(p in error_str for p in _AUTH_PATTERNS):
                    log.warning(f"[AUTH] {model} API key invalid — provider cooldown 1h: {result['error']}")
                    _cooldown_provider(model, cooldown_seconds=3600)
                    result["_failed"] = True
                    return result
                if attempt == 0 and any(p in error_str for p in _TRANSIENT_PATTERNS):
                    log.warning(f"[RETRY] Transient error from {model}: {result['error']}")
                    await asyncio.sleep(1.5)
                    continue
                result["_failed"] = True
                return result

            # Fallback: detect error from content (for providers that return errors as text)
            # Only flag as failed if content is ONLY an error message (short + starts with ❌)
            content = result.get("content", "")
            if (
                isinstance(content, str)
                and content.startswith("❌")
                and len(content) < 500
                and "API key" not in content
            ):
                content_lower = content.lower()
                if attempt == 0 and any(p in content_lower for p in _TRANSIENT_PATTERNS):
                    log.warning(f"[RETRY] Transient error from {model}, retrying: {content[:100]}")
                    await asyncio.sleep(1.5)
                    continue
                result["_failed"] = True
            return result
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if attempt == 0 and any(p in err_str for p in _TRANSIENT_PATTERNS):
                log.warning(f"[RETRY] Transient exception from {model}, retrying: {e}")
                await asyncio.sleep(1.5)
                continue
            log.error(f"[FAILOVER] {model} call error: {e}")
            return {
                "content": f"❌ {e}",
                "tool_calls": [],
                "_failed": True,
                "usage": {"input": 0, "output": 0},
                "model": model,
            }

    # Both attempts failed
    log.error(f"[FAILOVER] {model} failed after retry: {last_error}")
    return {
        "content": f"❌ {last_error}",
        "tool_calls": [],
        "_failed": True,
        "usage": {"input": 0, "output": 0},
        "model": model,
    }
