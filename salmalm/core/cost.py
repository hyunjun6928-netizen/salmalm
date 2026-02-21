"""Cost estimation and token counting — single source of truth.

Extracted from engine.py to unify all pricing/cost logic in one place.
Used by engine, slash commands, usage tracking, and API responses.
"""
from __future__ import annotations

from typing import Dict


def estimate_tokens(text: str) -> int:
    """Estimate tokens: Korean /2, English /4, mixed weighted."""
    if not text:
        return 0
    kr_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7a3' or '\u3131' <= c <= '\u318e')
    kr_ratio = kr_chars / max(len(text), 1)
    if kr_ratio > 0.3:
        # Korean: ~1 token per character (CJK tokenizers split per char)
        return max(1, int(kr_chars + (len(text) - kr_chars) / 4))
    elif kr_ratio < 0.05:
        return int(len(text) / 4)
    return int(len(text) / 3)


# Model pricing (USD per 1M tokens)
MODEL_PRICING: Dict[str, dict] = {
    'claude-opus-4': {'input': 15.0, 'output': 75.0, 'cache_read': 1.5, 'cache_write': 18.75},
    'claude-sonnet-4': {'input': 3.0, 'output': 15.0, 'cache_read': 0.3, 'cache_write': 3.75},
    'claude-haiku-4-5': {'input': 1.0, 'output': 5.0, 'cache_read': 0.1, 'cache_write': 1.25},
    'gemini-2.5-pro': {'input': 1.25, 'output': 10.0, 'cache_read': 0.315, 'cache_write': 1.25},
    'gemini-2.5-flash': {'input': 0.15, 'output': 0.60, 'cache_read': 0.0375, 'cache_write': 0.15},
    'gemini-2.0-flash': {'input': 0.10, 'output': 0.40, 'cache_read': 0.025, 'cache_write': 0.10},
    'gemini-3-pro': {'input': 1.25, 'output': 10.0, 'cache_read': 0.315, 'cache_write': 1.25},
    'gemini-3-flash': {'input': 0.15, 'output': 0.60, 'cache_read': 0.0375, 'cache_write': 0.15},
    'grok-4': {'input': 3.0, 'output': 15.0, 'cache_read': 0.3, 'cache_write': 3.75},
    'grok-3': {'input': 3.0, 'output': 15.0, 'cache_read': 0.3, 'cache_write': 3.75},
    'grok-3-mini': {'input': 0.30, 'output': 0.50, 'cache_read': 0.03, 'cache_write': 0.375},
}


def get_pricing(model: str) -> dict:
    """Get pricing for a model string (fuzzy match)."""
    m = model.lower().replace('-', '').replace('/', '')
    for key, pricing in MODEL_PRICING.items():
        if key.replace('-', '') in m:
            return pricing
    if 'gemini' in m:
        if 'pro' in m:
            return MODEL_PRICING['gemini-2.5-pro']
        return MODEL_PRICING['gemini-2.5-flash']
    return MODEL_PRICING['claude-sonnet-4']


def estimate_cost(model: str, usage: dict) -> float:
    """Estimate cost in USD from usage dict."""
    pricing = get_pricing(model)
    inp = usage.get('input', 0)
    out = usage.get('output', 0)
    cache_write = usage.get('cache_creation_input_tokens', 0)
    cache_read = usage.get('cache_read_input_tokens', 0)
    regular_input = max(0, inp - cache_write - cache_read)
    return (
        regular_input * pricing['input'] / 1_000_000
        + out * pricing['output'] / 1_000_000
        + cache_write * pricing['cache_write'] / 1_000_000
        + cache_read * pricing['cache_read'] / 1_000_000
    )
