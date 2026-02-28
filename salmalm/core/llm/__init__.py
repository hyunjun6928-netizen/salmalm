"""salmalm.core.llm — Multi-provider LLM package.

Re-exports all public symbols for backward compatibility.
Original module: salmalm/core/llm.py (918 lines), now split by provider.

Sub-modules:
  common     — utilities, HTTP helpers, call_llm entrypoint
  dispatcher — _call_provider router
  anthropic  — Anthropic Claude provider
  openai     — OpenAI / xAI / OpenRouter provider
  google     — Google Gemini provider
"""
from __future__ import annotations

from salmalm.core import track_usage  # noqa: F401 — backward-compat re-export

from salmalm.core.llm.common import (  # noqa: F401
    _ResponsesOnlyModel,
    _RESPONSES_API_MODELS,
    _RESPONSES_API_BLACKLIST,
    _LLM_TIMEOUT,
    _get_temperature,
    _http_post,
    _http_get,
    _try_fallback,
    _adapt_tools_for_provider,
    _resolve_api_key,
    _strip_internal_keys,
    _sanitize_messages_for_provider,
    call_llm,
)

from salmalm.core.llm.dispatcher import _call_provider  # noqa: F401

# Streaming — re-exported from llm_stream for backward compat
from salmalm.core.llm_stream import (  # noqa: F401
    stream_google,
    stream_anthropic,
)
from salmalm.core.llm.anthropic import _call_anthropic  # noqa: F401
from salmalm.core.llm.openai import _call_openai, _call_openai_responses  # noqa: F401
from salmalm.core.llm.google import (  # noqa: F401
    _call_google,
    _build_gemini_contents,
    _build_gemini_tools,
)

__all__ = [
    "call_llm",
    "_call_provider",
    "_call_anthropic",
    "_call_openai",
    "_call_openai_responses",
    "_call_google",
    "_build_gemini_contents",
    "_build_gemini_tools",
    "_ResponsesOnlyModel",
    "_RESPONSES_API_MODELS",
    "_RESPONSES_API_BLACKLIST",
    "_LLM_TIMEOUT",
    "_get_temperature",
    "_http_post",
    "_http_get",
    "_try_fallback",
    "_adapt_tools_for_provider",
    "_resolve_api_key",
    "_strip_internal_keys",
    "_sanitize_messages_for_provider",
    "track_usage",
]
