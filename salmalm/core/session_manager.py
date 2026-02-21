"""Session management — pruning, compaction, cache TTL tracking.

Extracted from engine.py for maintainability.

OpenClaw-style cache-aware pruning:
- Anthropic prompt caching has a 5-minute TTL
- Pruning within TTL invalidates the cache (wasted tokens)
- We track API call times and only prune when TTL has expired
- System prompt + tool schemas are marked cache_control=ephemeral
"""
from __future__ import annotations

import copy
import time as _time


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
_PRUNE_SOFT_LIMIT = 4000
_PRUNE_HARD_LIMIT = 50_000
_PRUNE_HEAD = 1500
_PRUNE_TAIL = 500


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
    _record_prune_time()
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
