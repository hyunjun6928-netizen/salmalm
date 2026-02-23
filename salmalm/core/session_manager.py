"""Session management — pruning, compaction, cache TTL tracking.

Extracted from engine.py for maintainability.

OpenClaw-style cache-aware pruning (enhanced):
- Anthropic prompt caching has a 5-minute TTL
- Pruning within TTL invalidates the cache (wasted tokens)
- We track API call times and only prune when TTL has expired
- System prompt + tool schemas are marked cache_control=ephemeral
- Tool-type-aware soft/hard thresholds (SalmAlm-original)
- Context-window-proportional hard-clear (OpenClaw parity)
"""

from __future__ import annotations

import copy
import time as _time
from typing import Dict, Optional, Tuple


# ============================================================
# Session Pruning — soft-trim / hard-clear old tool results
# ============================================================
# ── Cache TTL tracking for pruning ──
_last_api_call_time: float = 0.0
_CACHE_TTL_SECONDS = 300  # 5 minutes (Anthropic prompt cache TTL)
_last_prune_time: float = 0.0
_PRUNE_COOLDOWN = 60  # Don't prune more than once per 60s


def _should_prune_for_cache() -> bool:
    """Only prune if cache TTL has expired since last API call.

    OpenClaw pattern: Anthropic charges for cache_creation_input_tokens
    on first use, then cache_read_input_tokens on subsequent calls within
    TTL. Pruning (changing message structure) invalidates the cache,
    forcing re-creation. So we only prune when TTL has already expired.
    Additionally, enforce a cooldown to prevent excessive pruning.
    """
    global _last_api_call_time, _last_prune_time  # noqa: F824
    now = _time.time()
    if _last_api_call_time == 0:
        return True
    if now - _last_prune_time < _PRUNE_COOLDOWN:
        return False
    return (now - _last_api_call_time) >= _CACHE_TTL_SECONDS


def _record_api_call_time():
    """Record timestamp of API call for TTL tracking."""
    global _last_api_call_time
    _last_api_call_time = _time.time()


def _record_prune_time():
    """Record timestamp of pruning for cooldown tracking."""
    global _last_prune_time
    _last_prune_time = _time.time()


_PRUNE_KEEP_LAST_ASSISTANTS = 3
_PRUNE_SOFT_LIMIT = 4000  # Default soft-trim threshold (chars)
_PRUNE_HEAD = 1500
_PRUNE_TAIL = 1500  # OpenClaw parity: 1500 (was 500)

# Context-window-proportional hard-clear (OpenClaw pattern)
# hard_clear_threshold = context_window_chars * _HARD_CLEAR_RATIO
_HARD_CLEAR_RATIO = 0.5  # OpenClaw default: hardClearRatio=0.5
_SOFT_TRIM_RATIO = 0.3  # OpenClaw default: softTrimRatio=0.3
_MIN_PRUNABLE_TOOL_CHARS = 50_000  # Skip prune if total tool chars below this
_PRUNE_HARD_LIMIT = 50_000  # Backward compat fallback (no context window known)

# ── Tool-type-aware prune policy (SalmAlm-original) ──
# Tools that produce verbose output get pruned more aggressively.
# soft_limit: chars before soft-trim kicks in
# hard_mult: multiplier on soft_limit for hard-clear (lower = more aggressive)
_TOOL_PRUNE_POLICY: Dict[str, Dict] = {
    "exec": {"soft_limit": 2000, "hard_mult": 5},
    "exec_session": {"soft_limit": 1500, "hard_mult": 4},
    "sandbox_exec": {"soft_limit": 2000, "hard_mult": 5},
    "python_eval": {"soft_limit": 2000, "hard_mult": 5},
    "browser": {"soft_limit": 1500, "hard_mult": 4},
    "http_request": {"soft_limit": 2000, "hard_mult": 5},
    "web_fetch": {"soft_limit": 2000, "hard_mult": 5},
    "read": {"soft_limit": 3000, "hard_mult": 6},
    "rag_search": {"soft_limit": 1500, "hard_mult": 4},
    "system_info": {"soft_limit": 1000, "hard_mult": 3},
    "canvas": {"soft_limit": 1000, "hard_mult": 3},
}
_DEFAULT_PRUNE_POLICY = {"soft_limit": _PRUNE_SOFT_LIMIT, "hard_mult": 12}


def _get_tool_thresholds(tool_name: str, context_window_chars: Optional[int] = None) -> Tuple[int, int]:
    """Return (soft_threshold, hard_threshold) for a tool type.

    If context_window_chars is provided, hard threshold is also capped
    by context_window * _HARD_CLEAR_RATIO (OpenClaw-style proportional).
    """
    policy = _TOOL_PRUNE_POLICY.get(tool_name, _DEFAULT_PRUNE_POLICY)
    soft = policy["soft_limit"]
    hard = soft * policy["hard_mult"]

    if context_window_chars:
        ctx_hard = int(context_window_chars * _HARD_CLEAR_RATIO)
        hard = min(hard, ctx_hard)
        ctx_soft = int(context_window_chars * _SOFT_TRIM_RATIO)
        soft = min(soft, ctx_soft)

    return soft, hard


def _has_image_block(content: str) -> bool:
    """Check if a content block list contains image data."""
    if not isinstance(content, list):
        return False
    return any(
        (isinstance(b, dict) and b.get("type") in ("image", "image_url"))
        or (isinstance(b, dict) and b.get("source", {}).get("type") == "base64")
        for b in content
    )


def _soft_trim(text: str, head: int = _PRUNE_HEAD, tail: int = _PRUNE_TAIL) -> str:
    """Trim long text to head + ... + tail."""
    if len(text) <= head + tail + 20:
        return text
    return text[:head] + f"\n\n... [{len(text)} chars, trimmed] ...\n\n" + text[-tail:]


# ── Model context window lookup (tokens) ──
# Used for proportional prune thresholds. Conservative defaults.
_MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
    "opus": 200_000,
    "sonnet": 200_000,
    "haiku": 200_000,
    "claude": 200_000,
    "gpt-5": 128_000,
    "gpt-4.1": 1_047_576,
    "gpt-4o": 128_000,
    "o3": 200_000,
    "o4": 200_000,
    "grok": 131_072,
    "gemini": 1_000_000,
    "deepseek": 128_000,
    "llama": 128_000,
    "qwen": 128_000,
}
_DEFAULT_CONTEXT_WINDOW = 128_000


def estimate_context_window(model_name: str) -> int:
    """Estimate context window tokens for a model by substring match."""
    if not model_name:
        return _DEFAULT_CONTEXT_WINDOW
    lower = model_name.lower()
    for key, tokens in _MODEL_CONTEXT_WINDOWS.items():
        if key in lower:
            return tokens
    return _DEFAULT_CONTEXT_WINDOW


def _extract_tool_name(block: dict) -> str:
    """Best-effort extract tool name from a tool_result block."""
    # Anthropic: tool_use_id sometimes encodes the name
    # We also check a 'name' field if present
    return block.get("name", block.get("tool_name", ""))


def _estimate_total_tool_chars(messages: list) -> int:
    """Quick estimate of total tool result chars in message list."""
    total = 0
    for m in messages:
        if m.get("role") == "tool":
            c = m.get("content", "")
            total += len(c) if isinstance(c, str) else 0
        elif m.get("role") == "user" and isinstance(m.get("content"), list):
            for block in m["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    c = block.get("content", "")
                    total += len(c) if isinstance(c, str) else 0
    return total


def prune_context(messages: list, context_window_tokens: Optional[int] = None) -> tuple:
    """Prune old tool_result messages before LLM call.

    Args:
        messages: session message list
        context_window_tokens: model's context window in tokens (optional).
            Used for proportional hard-clear thresholds.

    Returns (pruned_messages, stats_dict).
    Does NOT modify the original list — returns a deep copy.
    """
    _record_prune_time()
    stats = {"soft_trimmed": 0, "hard_cleared": 0, "unchanged": 0, "skipped_min_chars": False}

    # Skip if total tool output is small (OpenClaw: minPrunableToolChars)
    total_tool_chars = _estimate_total_tool_chars(messages)
    if total_tool_chars < _MIN_PRUNABLE_TOOL_CHARS:
        stats["skipped_min_chars"] = True
        return messages, stats  # No copy needed — nothing changed

    pruned = copy.deepcopy(messages)
    ctx_chars = (context_window_tokens * 4) if context_window_tokens else None

    # Find the index of the Nth-last assistant message
    assistant_indices = [i for i, m in enumerate(pruned) if m.get("role") == "assistant"]
    if len(assistant_indices) <= _PRUNE_KEEP_LAST_ASSISTANTS:
        return pruned, stats  # Not enough history to prune
    cutoff_idx = assistant_indices[-_PRUNE_KEEP_LAST_ASSISTANTS]

    for i in range(cutoff_idx):
        m = pruned[i]
        # Anthropic-style tool results in user messages
        if m.get("role") == "user" and isinstance(m.get("content"), list):
            if _has_image_block(m["content"]):
                stats["unchanged"] += 1
                continue
            for j, block in enumerate(m["content"]):
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_result":
                    continue
                text = block.get("content", "")
                if not isinstance(text, str):
                    continue
                tool_name = _extract_tool_name(block)
                soft_th, hard_th = _get_tool_thresholds(tool_name, ctx_chars)
                if len(text) >= hard_th:
                    m["content"][j] = {**block, "content": "[Tool result cleared]"}
                    stats["hard_cleared"] += 1
                elif len(text) > soft_th:
                    m["content"][j] = {**block, "content": _soft_trim(text)}
                    stats["soft_trimmed"] += 1
                else:
                    stats["unchanged"] += 1
        # OpenAI-style tool messages
        elif m.get("role") == "tool":
            text = m.get("content", "")
            if not isinstance(text, str):
                continue
            tool_name = m.get("name", "")
            soft_th, hard_th = _get_tool_thresholds(tool_name, ctx_chars)
            if len(text) >= hard_th:
                pruned[i] = {**m, "content": "[Tool result cleared]"}
                stats["hard_cleared"] += 1
            elif len(text) > soft_th:
                pruned[i] = {**m, "content": _soft_trim(text)}
                stats["soft_trimmed"] += 1
            else:
                stats["unchanged"] += 1

    return pruned, stats
