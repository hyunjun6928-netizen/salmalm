"""Token estimation helpers for per-intent max_tokens allocation.

Extracted from salmalm.core.classifier.
"""
from __future__ import annotations

import os as _os

import os as _os

INTENT_MAX_TOKENS = {
    "chat": int(_os.environ.get("SALMALM_MAX_TOKENS_CHAT", "512")),
    "memory": 512,
    "creative": 1024,
    "search": 1024,
    "analysis": 2048,
    "code": int(_os.environ.get("SALMALM_MAX_TOKENS_CODE", "4096")),
    "system": 1024,
}

# Keywords that trigger higher max_tokens
_DETAIL_KEYWORDS = {"자세히", "상세", "detail", "detailed", "verbose", "explain", "설명", "thorough", "구체적"}


_MODEL_DEFAULT_MAX = {
    "anthropic": 8192,
    "openai": 16384,
    "google": 8192,
    "xai": 4096,
}


def _get_dynamic_max_tokens(intent: str, user_message: str, model: str = "") -> int:
    """Return max_tokens based on intent + user request.

    If INTENT_MAX_TOKENS[intent] == 0, use model-provider default (dynamic allocation).
    """
    base = INTENT_MAX_TOKENS.get(intent, 2048)
    if base == 0:
        # Dynamic: use provider default
        provider = model.split("/")[0] if "/" in model else "anthropic"
        base = _MODEL_DEFAULT_MAX.get(provider, 8192)
    msg_lower = user_message.lower()
    # Scale up for detailed requests — cap at 4096 to avoid runaway spend
    if any(kw in msg_lower for kw in _DETAIL_KEYWORDS):
        return min(max(base * 2, 2048), 4096)
    # Scale up for long input (long question → likely long answer)
    # Cap at 4096 — 8192 was too aggressive for most queries
    if len(user_message) > 500:
        return min(max(base, 2048), 4096)
    return base
