"""Common utilities, HTTP helpers, and main call_llm entrypoint.

Extracted from salmalm.core.llm.
"""
from __future__ import annotations


import json
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

import os as _os

from salmalm.constants import DEFAULT_MAX_TOKENS, FALLBACK_MODELS

# Models confirmed to use v1/responses endpoint (auto-populated on first 404).
_RESPONSES_API_MODELS: set = set()

# Legacy blacklist — now used only if v1/responses also fails.
_RESPONSES_API_BLACKLIST: set = set()


class _ResponsesOnlyModel(Exception):
    """Raised when a model is v1/responses-only (404 'not a chat model')."""


def _get_temperature(tools: Optional[list]) -> float:
    """Return temperature based on mode: lower for tool-calling (precision), higher for chat."""
    if tools:
        default = 0.3
        raw = _os.environ.get("SALMALM_TEMP_TOOL", "0.3")
    else:
        default = 0.7
        raw = _os.environ.get("SALMALM_TEMP_CHAT", "0.7")
    try:
        return float(raw)
    except (ValueError, TypeError):
        return default


from salmalm.security.crypto import vault, log
from salmalm.core.llm_stream import (  # noqa: F401
    stream_google,
    stream_anthropic,
)
from salmalm.core import response_cache, router, track_usage, check_cost_cap, CostCapExceeded, _metrics, _metrics_lock


_LLM_TIMEOUT = int(_os.environ.get("SALMALM_LLM_TIMEOUT", "120"))

_UA: str = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


# ── CLI OAuth token reuse (Codex CLI / Claude Code) ──
# CLI OAuth token reuse removed in v0.18.86 (security: reading other apps' credentials).


def _http_post(url: str, headers: Dict[str, str], body: dict, timeout: int = 120) -> dict:
    """HTTP POST with retry for transient errors (5xx, timeout, 429, 529)."""
    from salmalm.utils.retry import retry_call

    def _do_post():
        """Do post."""
        data = json.dumps(body).encode("utf-8")
        headers.setdefault("User-Agent", _UA)
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            # Mask potential API keys in error body
            import re as _re_mask
            # Mask all provider key formats: sk-*, sk-ant-*, AIza*, Bearer tokens, xAI keys, etc.
            _safe_body = _re_mask.sub(r'[a-zA-Z0-9_\-]{20,}', '***', err_body[:300])
            log.error(f"HTTP {e.code}: {_safe_body}")
            if e.code == 401:
                from salmalm.core.exceptions import AuthError

                raise AuthError("Invalid API key (401). Please check your key.") from e
            elif e.code == 402:
                from salmalm.core.exceptions import LLMError

                raise LLMError("Insufficient API credits (402). Check billing info.") from e
            elif e.code == 404 and "not a chat model" in err_body.lower():
                raise _ResponsesOnlyModel(err_body[:120]) from e
            raise  # Let retry logic handle 429, 5xx, 529

    return retry_call(_do_post, max_attempts=3)


def _http_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30) -> dict:
    """Http get."""
    h: Dict[str, str] = headers or {}
    h.setdefault("User-Agent", _UA)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))  # type: ignore[no-any-return]


_OPENROUTER_PROVIDERS = frozenset(("deepseek", "meta-llama", "mistralai", "qwen"))


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
                fb_provider, fb_key, fb_model_id, fb_messages, fb_tools, max_tokens, timeout=_LLM_TIMEOUT
            )
            result["model"] = f"{fb_provider}/{fb_model_id}"
            usage = result.get("usage", {})
            track_usage(result["model"], usage.get("input", 0), usage.get("output", 0))
            return result
        except Exception as e2:
            log.error(f"Fallback {fb_provider} also failed: {e2}")
    return None


def _adapt_tools_for_provider(tools, provider: str) -> Optional[list]:
    """Adapt tool schema format for different providers."""
    if not tools:
        return None
    if provider == "anthropic":
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t.get("input_schema", t.get("parameters", {})),
            }
            for t in tools
        ]
    if provider in ("openai", "xai", "google"):
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t.get("parameters", t.get("input_schema", {})),
            }
            for t in tools
        ]
    return None


def _resolve_api_key(provider: str) -> Optional[str]:
    """Resolve API key for a given provider."""
    if provider in _OPENROUTER_PROVIDERS:
        return vault.get("openrouter_api_key")
    if provider == "ollama":
        return vault.get("ollama_api_key") or "ollama"
    if provider == "google":
        return vault.get("google_api_key") or vault.get("gemini_api_key")
    return vault.get(f"{provider}_api_key")


_INTERNAL_MSG_KEYS = frozenset({"_recall", "_plan_injected", "_rag_injected"})


def _strip_internal_keys(messages: list) -> list:
    """Remove internal marker keys from messages before sending to any provider.

    Keys like _recall, _plan_injected are used internally for cleanup logic
    but must not be forwarded — unknown fields may cause API rejection (400).
    """
    if not any(k in m for m in messages for k in _INTERNAL_MSG_KEYS):
        return messages  # fast path — no markers present
    return [{k: v for k, v in m.items() if k not in _INTERNAL_MSG_KEYS} for m in messages]


def _sanitize_messages_for_provider(messages: list, provider: str) -> list:
    """Convert messages between provider formats to avoid role errors.

    - Anthropic only accepts 'user', 'assistant', 'system' roles
    - OpenAI uses 'tool' role for tool results
    - Google uses 'model' instead of 'assistant'
    - Internal marker keys (_recall, _plan_injected, etc.) are stripped here.
    """
    messages = _strip_internal_keys(messages)
    if provider == "anthropic":
        import json as _json

        # ── Pass 1: convert all messages to Anthropic format ──
        sanitized = []
        for msg in messages:
            role = msg.get("role", "")
            if role == "tool":
                sanitized.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", "unknown"),
                        "content": str(msg.get("content", "")),
                    }],
                })
            elif role == "model":
                sanitized.append({**msg, "role": "assistant"})
            elif role == "assistant":
                tool_calls = msg.get("tool_calls") or []
                content = msg.get("content") or ""
                already_converted = isinstance(content, list) and any(
                    b.get("type") == "tool_use" for b in content
                )
                if tool_calls and not already_converted:
                    blocks = []
                    if isinstance(content, str) and content.strip():
                        blocks.append({"type": "text", "text": content})
                    elif isinstance(content, list):
                        blocks.extend(content)
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        raw_args = fn.get("arguments", "{}")
                        try:
                            parsed_args = _json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        except Exception:
                            parsed_args = {"raw": raw_args}
                        blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", "unknown"),
                            "name": fn.get("name", "unknown"),
                            "input": parsed_args,
                        })
                    sanitized.append({"role": "assistant", "content": blocks})
                else:
                    sanitized.append(msg)
            else:
                sanitized.append(msg)

        # ── Pass 2: drop orphaned tool_result blocks (no matching tool_use) ──
        known_tool_use_ids: set = set()
        for msg in sanitized:
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        known_tool_use_ids.add(block["id"])

        cleaned = []
        for msg in sanitized:
            content = msg.get("content")
            if isinstance(content, list) and all(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content
            ):
                # This is a tool_result-only user message — filter orphans
                valid = [b for b in content if b.get("tool_use_id") in known_tool_use_ids]
                if valid:
                    cleaned.append({**msg, "content": valid})
                # else: drop entire message (all tool_results were orphaned)
            else:
                cleaned.append(msg)
        return cleaned
    elif provider == "google":
        # _build_gemini_contents handles all format conversion:
        #   system → user, assistant+tool_calls → model+functionCall,
        #   tool → user+functionResponse
        # Pass through unchanged; do not pre-convert or drop messages.
        return list(messages)
    elif provider in ("openai", "xai", "deepseek", "openrouter"):
        # OpenAI-compatible: filter out Anthropic-specific content blocks
        sanitized = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                # Convert Anthropic content blocks to text
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_result":
                            text_parts.append(block.get("content", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                if text_parts:
                    sanitized.append({**msg, "content": "\n".join(text_parts)})
            else:
                sanitized.append(msg)
        return sanitized
    return messages


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

    # Check cache (only for tool-free queries, scoped by last few messages)
    if not tools:
        cached = response_cache.get(model, messages)
        if cached:
            return {
                "content": cached,
                "tool_calls": [],
                "usage": {"input": 0, "output": 0},
                "model": model,
                "cached": True,
            }

    # Hard cost cap check before every LLM call
    try:
        check_cost_cap()
    except CostCapExceeded as e:
        return {"content": f"⚠️ {e}", "tool_calls": [], "usage": {"input": 0, "output": 0}, "model": model}

    provider, model_id = model.split("/", 1) if "/" in model else ("anthropic", model)
    api_key = _resolve_api_key(provider)
    if not api_key:
        return {
            "content": f"❌ {provider} API key not configured.\n\n"
            f"💡 In Settings, add `{provider}_api_key` or\n"
            f"try switching models: `/model auto`",
            "tool_calls": [],
            "usage": {"input": 0, "output": 0},
            "model": model,
        }

    # v1/responses models: route directly without chat/completions attempt
    if provider == "openai" and model_id in _RESPONSES_API_MODELS:
        log.info(f"[RESPONSES] {model} → direct v1/responses (cached route)")
    # Hard blacklist: both endpoints failed, skip to cross-provider fallback
    elif model_id in _RESPONSES_API_BLACKLIST:
        log.warning(f"[BLACKLIST] {model} skipped (both endpoints failed), using fallback")
        fb = _try_fallback(provider, model, messages, tools, max_tokens, time.time())
        if fb:
            return fb
        return {"content": f"❌ {model} is not a chat model and no fallback available.",
                "tool_calls": [], "usage": {"input": 0, "output": 0}, "model": model}

    # Sanitize messages for provider compatibility
    messages = _sanitize_messages_for_provider(messages, provider)

    log.info(f"[BOT] LLM call: {model} ({len(messages)} msgs, tools={len(tools or [])})")

    with _metrics_lock:
        _metrics["llm_calls"] += 1
    _t0 = time.time()  # noqa: E303
    try:
        result = _call_provider(provider, api_key, model_id, messages, tools, max_tokens, thinking=thinking)
        result["model"] = model
        # Cost tracking — best-effort (never fail the request)
        try:
            usage = result.get("usage", {})
            inp_tok = usage.get("input", 0)
            out_tok = usage.get("output", 0)
            track_usage(model, inp_tok, out_tok)
            with _metrics_lock:
                _metrics["total_tokens_in"] += inp_tok
                _metrics["total_tokens_out"] += out_tok
            try:
                from salmalm.monitoring.metrics import llm_calls_total, llm_call_duration, token_usage_total
                _elapsed = time.time() - _t0
                llm_calls_total.inc(provider=provider, model=model_id, status="ok")
                llm_call_duration.observe(_elapsed)
                if inp_tok:
                    token_usage_total.inc(inp_tok, provider=provider, type="input")
                if out_tok:
                    token_usage_total.inc(out_tok, provider=provider, type="output")
            except Exception:
                pass
        except Exception as e:
            log.warning(f"[COST] Usage tracking failed (ignored): {e}")
        if not result.get("tool_calls") and result.get("content"):
            response_cache.put(model, messages, result["content"])
        return result
    except Exception as e:
        with _metrics_lock:
            _metrics["llm_errors"] += 1
        try:
            from salmalm.monitoring.metrics import llm_calls_total, llm_call_duration
            llm_calls_total.inc(provider=provider, model=model_id, status="error")
            llm_call_duration.observe(time.time() - _t0)
        except Exception:
            pass
        _elapsed = time.time() - _t0
        err_str = str(e)
        log.error(
            f"LLM error ({model}): {err_str} [latency={_elapsed:.2f}s, cost_so_far=${_metrics['total_cost']:.4f}]"
        )

        # ── v1/responses-only model — retry with v1/responses before cross-provider fallback ──
        if isinstance(e, _ResponsesOnlyModel) and provider == "openai":
            log.info(f"[RESPONSES] {model} → retrying with v1/responses endpoint")
            try:
                resp_result = _call_openai_responses(api_key, model_id, messages, tools or [], max_tokens)
                resp_result["model"] = model
                _RESPONSES_API_MODELS.add(model_id)  # cache for future calls
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

        # ── Token overflow detection — don't fallback, truncate instead ──
        elif "prompt is too long" in err_str or "maximum context" in err_str.lower():
            log.warning(f"[ERR] Token overflow detected ({len(messages)} msgs). Force-truncating.")
            return {
                "content": "",
                "tool_calls": [],
                "error": "token_overflow",
                "usage": {"input": 0, "output": 0},
                "model": model,
            }

        fb_result = _try_fallback(provider, model, messages, tools, max_tokens, _t0)
        if fb_result:
            return fb_result
        return {
            "content": f"❌ All LLM calls failed. Last error: {str(e)[:200]}",
            "tool_calls": [],
            "usage": {"input": 0, "output": 0},
            "model": model,
        }
