"""SalmAlm LLM — Multi-provider API calls with caching and fallback.

Includes streaming support for Anthropic API (SSE token-by-token).
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
from salmalm.core import response_cache, router, track_usage, check_cost_cap, CostCapExceeded, _metrics


_LLM_TIMEOUT = int(_os.environ.get("SALMALM_LLM_TIMEOUT", "30"))

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
            _safe_body = _re_mask.sub(r'(sk-[a-zA-Z0-9]{4})[a-zA-Z0-9-]+', r'\1***', err_body[:300])
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


def _sanitize_messages_for_provider(messages: list, provider: str) -> list:
    """Convert messages between provider formats to avoid role errors.

    - Anthropic only accepts 'user', 'assistant', 'system' roles
    - OpenAI uses 'tool' role for tool results
    - Google uses 'model' instead of 'assistant'
    """
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

    _metrics["llm_calls"] += 1
    _t0 = time.time()
    try:
        result = _call_provider(provider, api_key, model_id, messages, tools, max_tokens, thinking=thinking)
        result["model"] = model
        # Cost tracking — best-effort (never fail the request)
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


def _call_anthropic(
    api_key: str,
    model_id: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[dict]],
    max_tokens: int,
    thinking: bool = False,
    timeout: int = 0,
) -> Dict[str, Any]:
    """Call anthropic."""
    # Defensive: ensure tool-role messages are converted regardless of call path
    messages = _sanitize_messages_for_provider(messages, "anthropic")
    system_msgs = [m["content"] for m in messages if m["role"] == "system"]
    chat_msgs = [m for m in messages if m["role"] != "system"]

    # Extended thinking for Opus/Sonnet — level-based budget
    # thinking can be bool (legacy) or str level: "low"|"medium"|"high"|"xhigh"
    _THINKING_BUDGETS = {"low": 4000, "medium": 10000, "high": 16000, "xhigh": 32000}
    think_level = None
    if isinstance(thinking, str) and thinking in _THINKING_BUDGETS:
        think_level = thinking
    elif thinking is True:
        think_level = "medium"  # legacy bool compat

    use_thinking = think_level is not None and ("opus" in model_id or "sonnet" in model_id)

    body = {
        "model": model_id,
        "messages": chat_msgs,
    }
    if use_thinking:
        budget = _THINKING_BUDGETS[think_level]  # type: ignore[index]
        body["max_tokens"] = max(max_tokens, budget + 4000)  # type: ignore[assignment]
        body["thinking"] = {"type": "enabled", "budget_tokens": budget}  # type: ignore[assignment]
    else:
        body["max_tokens"] = max_tokens  # type: ignore[assignment]

    if not use_thinking:
        body["temperature"] = _get_temperature(tools)
    if system_msgs:
        # Prompt caching: split static/dynamic blocks for better cache hits
        sys_text = "\n".join(system_msgs)
        _BOUNDARY = "<!-- CACHE_BOUNDARY -->"
        if _BOUNDARY in sys_text:
            static_part, dynamic_part = sys_text.split(_BOUNDARY, 1)
            body["system"] = [
                {"type": "text", "text": static_part.strip(), "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": dynamic_part.strip(), "cache_control": {"type": "ephemeral"}},
            ]
        else:
            body["system"] = [{"type": "text", "text": sys_text, "cache_control": {"type": "ephemeral"}}]
    if tools:
        # Mark last tool with cache_control for tool schema caching
        cached_tools = list(tools)
        if cached_tools:
            cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}
        body["tools"] = cached_tools
    resp = _http_post(
        "https://api.anthropic.com/v1/messages",
        {
            "x-api-key": api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31",
        },
        body,
        timeout=timeout or _LLM_TIMEOUT,
    )
    content = ""
    thinking_text = ""
    tool_calls = []
    for block in resp.get("content", []):
        if block["type"] == "text":
            content += block["text"]
        elif block["type"] == "thinking":
            thinking_text += block.get("thinking", "")
        elif block["type"] == "tool_use":
            tool_calls.append({"id": block["id"], "name": block["name"], "arguments": block["input"]})
    usage = resp.get("usage", {})
    result = {
        "content": content,
        "tool_calls": tool_calls,
        "usage": {
            "input": usage.get("input_tokens", 0),
            "output": usage.get("output_tokens", 0),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
            "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
        },
    }
    if thinking_text:
        result["thinking"] = thinking_text
        log.info(f"[AI] Thinking: {len(thinking_text)} chars")
    return result


def _call_openai(
    api_key: str,
    model_id: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[dict]],
    max_tokens: int,
    base_url: str,
    thinking: Any = False,
) -> Dict[str, Any]:
    # Convert Anthropic-style image blocks to OpenAI format
    """Call openai."""
    converted_msgs = []
    for m in messages:
        if isinstance(m.get("content"), list):
            new_content = []
            for block in m["content"]:
                if block.get("type") == "image" and block.get("source", {}).get("type") == "base64":
                    src = block["source"]
                    new_content.append(
                        {"type": "image_url", "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"}}
                    )
                elif block.get("type") == "text":
                    new_content.append({"type": "text", "text": block["text"]})
                else:
                    new_content.append(block)
            converted_msgs.append({**m, "content": new_content})
        else:
            converted_msgs.append(m)
    body = {
        "model": model_id,
        "max_tokens": max_tokens,
        "messages": converted_msgs,
        "temperature": _get_temperature(tools),
    }
    # OpenAI reasoning_effort for o3/o4-mini reasoning models
    _REASONING_MAP = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high"}
    _is_reasoning = any(r in model_id for r in ("o3", "o4", "o1"))
    if _is_reasoning:
        think_level = thinking if isinstance(thinking, str) else ("medium" if thinking else None)
        if think_level and think_level in _REASONING_MAP:
            body["reasoning_effort"] = _REASONING_MAP[think_level]
            body.pop("temperature", None)  # reasoning models don't support temperature
    if tools:
        body["tools"] = [{"type": "function", "function": t} for t in tools]
    headers = {"Content-Type": "application/json"}
    if api_key and api_key not in ("ollama", ""):
        headers["Authorization"] = f"Bearer {api_key}"
    resp = _http_post(f"{base_url}/chat/completions", headers, body)
    choice = resp["choices"][0]["message"]
    tool_calls = []
    for tc in choice.get("tool_calls") or []:
        tool_calls.append(
            {"id": tc["id"], "name": tc["function"]["name"], "arguments": json.loads(tc["function"]["arguments"])}
        )
    usage = resp.get("usage", {})
    return {
        "content": choice.get("content", ""),
        "tool_calls": tool_calls,
        "usage": {"input": usage.get("prompt_tokens", 0), "output": usage.get("completion_tokens", 0)},
    }


def _call_openai_responses(
    api_key: str,
    model_id: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[dict]],
    max_tokens: int,
) -> Dict[str, Any]:
    """Call OpenAI v1/responses endpoint (for models that reject v1/chat/completions).

    Converts OpenAI chat-format messages → Responses API input items:
      user/assistant text  → {"role": "...", "content": "..."}
      assistant tool_calls → {"type": "function_call", "id": ..., "name": ..., "arguments": ...}
      tool result          → {"type": "function_call_output", "call_id": ..., "output": ...}
      system               → body["instructions"]
    """
    input_items: List[Dict] = []
    instructions_parts: List[str] = []

    for m in messages:
        role = m.get("role", "")
        content = m.get("content") or ""

        if role == "system":
            instructions_parts.append(content)

        elif role == "user":
            if isinstance(content, list):
                # Multimodal: keep as-is (Responses API accepts same content block format)
                input_items.append({"role": "user", "content": content})
            else:
                input_items.append({"role": "user", "content": content})

        elif role == "assistant":
            tool_calls = m.get("tool_calls") or []
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    input_items.append({
                        "type": "function_call",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "arguments": fn.get("arguments", "{}"),
                    })
            else:
                if content:
                    input_items.append({"role": "assistant", "content": content})

        elif role == "tool":
            input_items.append({
                "type": "function_call_output",
                "call_id": m.get("tool_call_id", ""),
                "output": str(content),
            })

    body: dict = {
        "model": model_id,
        "input": input_items,
        "max_output_tokens": max_tokens,
    }
    if instructions_parts:
        body["instructions"] = "\n".join(instructions_parts).strip()

    if tools:
        body["tools"] = [
            {
                "type": "function",
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": t.get("parameters", t.get("input_schema", {})),
            }
            for t in tools
        ]

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    resp = _http_post("https://api.openai.com/v1/responses", headers, body)

    # Parse output items
    output_text = ""
    tool_calls_out = []
    for item in resp.get("output", []):
        itype = item.get("type", "")
        if itype == "message":
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    output_text += block.get("text", "")
        elif itype == "function_call":
            raw_args = item.get("arguments", "{}")
            # Store in standard OpenAI chat format so engine/sanitize code works uniformly
            tool_calls_out.append({
                "id": item.get("id", ""),
                "type": "function",
                "function": {
                    "name": item.get("name", ""),
                    "arguments": raw_args if isinstance(raw_args, str) else json.dumps(raw_args),
                },
            })

    usage = resp.get("usage", {})
    return {
        "content": output_text,
        "tool_calls": tool_calls_out,
        "usage": {
            "input": usage.get("input_tokens", 0),
            "output": usage.get("output_tokens", 0),
        },
    }


def _call_google(
    api_key: str, model_id: str, messages: List[Dict[str, Any]], max_tokens: int, tools: Optional[List[dict]] = None
) -> Dict[str, Any]:
    # Gemini API — with optional tool support
    """Call google."""
    merged = _build_gemini_contents(messages)
    body: dict = {
        "contents": merged,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": _get_temperature(tools)},
    }
    gemini_tools = _build_gemini_tools(tools)
    if gemini_tools:
        body["tools"] = gemini_tools
    resp = _http_post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}",
        {"Content-Type": "application/json"},
        body,
    )
    text = ""
    tool_calls = []
    for cand in resp.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            if "text" in part:
                text += part["text"]
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(
                    {
                        "id": f"google_{fc['name']}_{int(time.time() * 1000)}",
                        "name": fc["name"],
                        "arguments": fc.get("args", {}),
                    }
                )
    usage_meta = resp.get("usageMetadata", {})
    return {
        "content": text,
        "tool_calls": tool_calls,
        "usage": {"input": usage_meta.get("promptTokenCount", 0), "output": usage_meta.get("candidatesTokenCount", 0)},
    }


def _build_gemini_contents(messages: List[Dict[str, Any]]) -> list:
    """Convert messages list to Gemini contents format.

    Handles OpenAI tool format → Gemini functionCall/functionResponse:
      assistant + tool_calls → role=model, parts=[{functionCall: ...}]
      role=tool              → role=user,  parts=[{functionResponse: ...}]
    Merges consecutive same-role turns as Gemini requires alternating roles.
    """
    parts = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content") or ""

        if role == "system":
            # Gemini has no system role — treat as user context
            parts.append({"role": "user", "parts": [{"text": str(content)}]})

        elif role == "tool":
            # OpenAI tool result → Gemini functionResponse
            # We need the function name; use tool_call_id as fallback key
            tool_name = m.get("name") or m.get("tool_call_id", "tool")
            parts.append({
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": tool_name,
                        "response": {"content": str(content)},
                    }
                }]
            })

        elif role == "assistant":
            tool_calls = m.get("tool_calls") or []
            gemini_parts = []
            if content:
                if isinstance(content, list):
                    # Anthropic content blocks
                    text = " ".join(b.get("text", "") for b in content
                                   if isinstance(b, dict) and b.get("type") == "text")
                    if text:
                        gemini_parts.append({"text": text})
                else:
                    gemini_parts.append({"text": str(content)})
            for tc in tool_calls:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except Exception:
                    args = {}
                gemini_parts.append({
                    "functionCall": {
                        "name": fn.get("name", ""),
                        "args": args,
                    }
                })
            if gemini_parts:
                parts.append({"role": "model", "parts": gemini_parts})

        else:
            # user / unknown
            if isinstance(content, list):
                text = " ".join(b.get("text", "") for b in content
                               if isinstance(b, dict) and b.get("type") == "text")
                content = text
            parts.append({"role": "user", "parts": [{"text": str(content)}]})

    # Merge consecutive same-role turns (Gemini requires alternating user/model)
    merged: list = []
    for p in parts:
        if merged and merged[-1]["role"] == p["role"]:
            merged[-1]["parts"].extend(p["parts"])
        else:
            merged.append(p)
    return merged


def _build_gemini_tools(tools: Optional[List[dict]]) -> Optional[list]:
    """Convert tool definitions to Gemini functionDeclarations format."""
    if not tools:
        return None
    gemini_tools = []
    for t in tools:
        fn_decl: Dict[str, Any] = {"name": t["name"], "description": t.get("description", "")}
        params = t.get("parameters", t.get("input_schema", {}))
        if params and params.get("properties"):
            fn_decl["parameters"] = params
        gemini_tools.append(fn_decl)
    return [{"functionDeclarations": gemini_tools}]


# ============================================================
# STREAMING API — Token-by-token streaming for Anthropic
# ============================================================
