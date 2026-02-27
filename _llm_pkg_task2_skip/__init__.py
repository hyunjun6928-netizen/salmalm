"""SalmAlm LLM package — multi-provider API calls with caching and fallback."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from salmalm.constants import DEFAULT_MAX_TOKENS, FALLBACK_MODELS
from salmalm.core.llm_stream import stream_anthropic, stream_google  # noqa: F401

from .anthropic import _call_anthropic
from .common import (
    CostCapExceeded,
    _LLM_TIMEOUT,
    _RESPONSES_API_BLACKLIST,
    _RESPONSES_API_MODELS,
    _adapt_tools_for_provider,
    _get_temperature,
    _http_get,
    _http_post,
    _metrics,
    _resolve_api_key,
    _sanitize_messages_for_provider,
    check_cost_cap,
    log,
    response_cache,
    router,
    track_usage,
    vault,
    _ResponsesOnlyModel,
)
from .google import _build_gemini_contents, _build_gemini_tools, _call_google
from .ollama import _call_ollama
from .openai import _call_openai, _call_openai_responses


def _try_fallback(provider, model, messages, tools, max_tokens, t0) -> Optional[dict]:
    """Try fallback providers when primary fails. Returns result dict or None."""
    for fb_provider in ("anthropic", "xai", "google"):
        if fb_provider == provider:
            continue
        fb_key = _resolve_api_key(fb_provider)
        if not fb_key:
            continue
        fb_model_id = FALLBACK_MODELS.get(fb_provider)
        if not fb_model_id:
            continue
        from salmalm.core.engine import _fix_model_name

        fb_model_id = _fix_model_name(fb_model_id)
        log.info(f"[SYNC] Fallback: {provider} -> {fb_provider}/{fb_model_id} [after {time.time() - t0:.2f}s]")
        try:
            fb_tools = _adapt_tools_for_provider(tools, fb_provider)
            fb_messages = _sanitize_messages_for_provider(messages, fb_provider)
            result = _call_provider(
                fb_provider,
                fb_key,
                fb_model_id,
                fb_messages,
                fb_tools,
                max_tokens,
                timeout=_LLM_TIMEOUT,
            )
            result["model"] = f"{fb_provider}/{fb_model_id}"
            usage = result.get("usage", {})
            track_usage(result["model"], usage.get("input", 0), usage.get("output", 0))
            return result
        except Exception as e2:
            log.error(f"Fallback {fb_provider} also failed: {e2}")
    return None


def call_llm(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    tools: Optional[List[dict]] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    thinking: bool = False,
) -> Dict[str, Any]:
    """Call LLM API. Returns {'content': str, 'tool_calls': list, 'usage': dict}."""
    if not model:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        model = router.route(last_user, has_tools=bool(tools))

    if not tools:
        cached = response_cache.get(model, messages)
        if cached:
            return {"content": cached, "tool_calls": [], "usage": {"input": 0, "output": 0}, "model": model, "cached": True}

    try:
        check_cost_cap()
    except CostCapExceeded as e:
        return {"content": f"⚠️ {e}", "tool_calls": [], "usage": {"input": 0, "output": 0}, "model": model}

    provider, model_id = model.split("/", 1) if "/" in model else ("anthropic", model)
    api_key = _resolve_api_key(provider)
    if not api_key:
        return {
            "content": f"❌ {provider} API key not configured.\n\n💡 In Settings, add `{provider}_api_key` or\ntry switching models: `/model auto`",
            "tool_calls": [],
            "usage": {"input": 0, "output": 0},
            "model": model,
        }

    if provider == "openai" and model_id in _RESPONSES_API_MODELS:
        log.info(f"[RESPONSES] {model} → direct v1/responses (cached route)")
    elif model_id in _RESPONSES_API_BLACKLIST:
        log.warning(f"[BLACKLIST] {model} skipped (both endpoints failed), using fallback")
        fb = _try_fallback(provider, model, messages, tools, max_tokens, time.time())
        if fb:
            return fb
        return {"content": f"❌ {model} is not a chat model and no fallback available.", "tool_calls": [], "usage": {"input": 0, "output": 0}, "model": model}

    messages = _sanitize_messages_for_provider(messages, provider)
    log.info(f"[BOT] LLM call: {model} ({len(messages)} msgs, tools={len(tools or [])})")

    _metrics["llm_calls"] += 1
    _t0 = time.time()
    try:
        result = _call_provider(provider, api_key, model_id, messages, tools, max_tokens, thinking=thinking)
        result["model"] = model
        try:
            usage = result.get("usage", {})
            inp_tok = usage.get("input", 0)
            out_tok = usage.get("output", 0)
            track_usage(model, inp_tok, out_tok)
            _metrics["total_tokens_in"] += inp_tok
            _metrics["total_tokens_out"] += out_tok
        except Exception as e:
            log.warning(f"[COST] Usage tracking failed (ignored): {e}")
        if not result.get("tool_calls") and result.get("content"):
            response_cache.put(model, messages, result["content"])
        return result
    except Exception as e:
        _metrics["llm_errors"] += 1
        _elapsed = time.time() - _t0
        err_str = str(e)
        log.error(f"LLM error ({model}): {err_str} [latency={_elapsed:.2f}s, cost_so_far=${_metrics['total_cost']:.4f}]")

        if isinstance(e, _ResponsesOnlyModel) and provider == "openai":
            log.info(f"[RESPONSES] {model} → retrying with v1/responses endpoint")
            try:
                resp_result = _call_openai_responses(api_key, model_id, messages, tools or [], max_tokens)
                resp_result["model"] = model
                _RESPONSES_API_MODELS.add(model_id)
                log.info(f"[RESPONSES] v1/responses succeeded for {model_id} — registered")
                try:
                    usage = resp_result.get("usage", {})
                    track_usage(model, usage.get("input", 0), usage.get("output", 0))
                except Exception as _e:
                    log.debug("[RESPONSES] track_usage failed: %s", _e)
                return resp_result
            except Exception as e_resp:
                log.error(f"[RESPONSES] v1/responses also failed for {model_id}: {e_resp}")
                _RESPONSES_API_BLACKLIST.add(model_id)
                log.warning(f"[BLACKLIST] {model_id} failed on both endpoints, blacklisted")
        elif "prompt is too long" in err_str or "maximum context" in err_str.lower():
            log.warning(f"[ERR] Token overflow detected ({len(messages)} msgs). Force-truncating.")
            return {"content": "", "tool_calls": [], "error": "token_overflow", "usage": {"input": 0, "output": 0}, "model": model}

        fb_result = _try_fallback(provider, model, messages, tools, max_tokens, _t0)
        if fb_result:
            return fb_result
        return {"content": f"❌ All LLM calls failed. Last error: {str(e)[:200]}", "tool_calls": [], "usage": {"input": 0, "output": 0}, "model": model}


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
    if provider in ("openai", "xai"):
        if provider == "openai" and model_id in _RESPONSES_API_MODELS:
            return _call_openai_responses(api_key, model_id, messages, tools, max_tokens)
        base_url = "https://api.x.ai/v1" if provider == "xai" else "https://api.openai.com/v1"
        return _call_openai(api_key, model_id, messages, tools, max_tokens, base_url)
    if provider == "google":
        return _call_google(api_key, model_id, messages, max_tokens, tools=tools)
    if provider == "ollama":
        return _call_ollama(model_id, messages, tools, max_tokens, thinking=thinking)
    if provider == "openrouter":
        return _call_openai(api_key, model_id, messages, tools, max_tokens, "https://openrouter.ai/api/v1")
    if provider in ("deepseek", "meta-llama", "mistralai", "qwen"):
        or_key = vault.get("openrouter_api_key")
        if not or_key:
            raise ValueError(f"{provider} requires openrouter_api_key in vault")
        full_model = f"{provider}/{model_id}"
        return _call_openai(or_key, full_model, messages, tools, max_tokens, "https://openrouter.ai/api/v1")
    raise ValueError(f"Unknown provider: {provider}")


__all__ = [
    "call_llm",
    "stream_google",
    "stream_anthropic",
    "_http_post",
    "_http_get",
    "_get_temperature",
    "_sanitize_messages_for_provider",
    "_strip_internal_keys",
    "_resolve_api_key",
    "response_cache",
    "_call_anthropic",
    "_call_openai",
    "_call_openai_responses",
    "_call_google",
    "_call_ollama",
    "_build_gemini_contents",
    "_build_gemini_tools",
]

# back-compat names imported from common
from .common import _strip_internal_keys
