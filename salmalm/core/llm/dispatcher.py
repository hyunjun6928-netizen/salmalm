"""Provider dispatcher — routes to the correct _call_* function.

Extracted from salmalm.core.llm.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from salmalm.core.llm.common import _RESPONSES_API_MODELS, _LLM_TIMEOUT
from salmalm.core.llm.anthropic import _call_anthropic
from salmalm.core.llm.openai import _call_openai, _call_openai_responses
from salmalm.core.llm.google import _call_google
from salmalm.security.crypto import vault

def _call_provider(
    provider: str,
    api_key: str,
    model_id: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[dict]],
    max_tokens: int,
    thinking: bool = False,
    timeout: int = 0,
) -> Dict[str, Any]:
    """Call provider."""
    if not timeout:
        timeout = _LLM_TIMEOUT
    if provider == "anthropic":
        return _call_anthropic(api_key, model_id, messages, tools, max_tokens, thinking=thinking, timeout=timeout)
    elif provider in ("openai", "xai"):
        if provider == "openai" and model_id in _RESPONSES_API_MODELS:
            # Known responses-only model — go straight to v1/responses
            return _call_openai_responses(api_key, model_id, messages, tools, max_tokens)
        base_url = "https://api.x.ai/v1" if provider == "xai" else "https://api.openai.com/v1"
        return _call_openai(api_key, model_id, messages, tools, max_tokens, base_url)
    elif provider == "google":
        return _call_google(api_key, model_id, messages, max_tokens, tools=tools)
    elif provider == "ollama":
        ollama_url = vault.get("ollama_url") or "http://localhost:11434/v1"
        return _call_openai("ollama", model_id, messages, tools, max_tokens, ollama_url)
    elif provider == "openrouter":
        return _call_openai(api_key, model_id, messages, tools, max_tokens, "https://openrouter.ai/api/v1")
    elif provider in ("deepseek", "meta-llama", "mistralai", "qwen"):
        # Route through OpenRouter
        or_key = vault.get("openrouter_api_key")
        if not or_key:
            raise ValueError(f"{provider} requires openrouter_api_key in vault")
        full_model = f"{provider}/{model_id}"
        return _call_openai(or_key, full_model, messages, tools, max_tokens, "https://openrouter.ai/api/v1")
    else:
        raise ValueError(f"Unknown provider: {provider}")

