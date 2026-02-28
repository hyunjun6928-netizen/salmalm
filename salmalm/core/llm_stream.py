"""LLM streaming response handlers."""

import json
import logging
import time
import urllib.request
from typing import Any, Dict, Generator, List, Optional

log = logging.getLogger(__name__)

from salmalm.core.core import CostCapExceeded, check_cost_cap, router  # noqa: E402

from salmalm.constants import DEFAULT_MAX_TOKENS  # noqa: E402


def _lazy_track_usage(model, inp, out):
    """Lazy import to avoid circular."""
    from salmalm.core.core import track_usage

    track_usage(model, inp, out)


try:
    from salmalm.constants import VERSION as _VERSION
except Exception:
    _VERSION = "0"
# Honest User-Agent — Chrome impersonation violates provider ToS and may cause
# log/proxy systems to leak the API key embedded in Google URLs.
_UA = f"SalmAlm/{_VERSION} (https://github.com/hyunjun6928-netizen/salmalm)"
from salmalm.security.crypto import vault


def _lazy_get_temperature(tools):
    """Lazy import to avoid circular."""
    from salmalm.core.llm import _get_temperature

    return _get_temperature(tools)


def _lazy_build_gemini_tools(tools):
    """Lazy import to avoid circular."""
    from salmalm.core.llm import _build_gemini_tools

    return _build_gemini_tools(tools)  # noqa: E402


def stream_google(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    tools: Optional[List[dict]] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Generator[Dict[str, Any], None, None]:
    """Stream Google Gemini API responses using streamGenerateContent SSE.

    Yields events compatible with the Anthropic streaming interface:
        {'type': 'text_delta', 'text': '...'}
        {'type': 'tool_use_start', 'id': '...', 'name': '...'}
        {'type': 'tool_use_end', 'id': '...', 'name': '...', 'arguments': {...}}
        {'type': 'message_end', 'content': '...', 'tool_calls': [...], 'usage': {...}, 'model': '...'}
        {'type': 'error', 'error': '...'}
    """
    if not model:
        from salmalm.constants import MODEL_GEMINI_FLASH

        model = MODEL_GEMINI_FLASH

    provider, model_id = model.split("/", 1) if "/" in model else ("google", model)

    try:
        check_cost_cap()
    except CostCapExceeded as e:
        yield {"type": "error", "error": str(e)}
        return

    api_key = vault.get("google_api_key") or vault.get("gemini_api_key")
    if not api_key:
        yield {"type": "error", "error": "❌ Google API key not configured. Set GOOGLE_API_KEY or GEMINI_API_KEY."}
        return

    from salmalm.core.llm import _build_gemini_contents

    contents = _build_gemini_contents(messages)
    body: dict = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": _lazy_get_temperature(tools)},
    }
    gemini_tools = _lazy_build_gemini_tools(tools)
    if gemini_tools:
        body["tools"] = gemini_tools

    data = json.dumps(body).encode("utf-8")
    # NOTE: Google REST API requires the key as a query param — there is no
    # header-based auth alternative for this endpoint. Ensure the URL is never
    # logged in full; use the masked form for any debug output.
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_id}:streamGenerateContent?alt=sse&key={api_key}"
    )
    _url_safe = url.split("&key=")[0] + "&key=***"  # mask for logs
    headers = {"Content-Type": "application/json", "User-Agent": _UA}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    content_text = ""
    tool_calls: List[dict] = []
    usage = {"input": 0, "output": 0}

    try:
        resp = urllib.request.urlopen(req, timeout=180)
        buffer = ""
        for raw_chunk in _iter_chunks(resp):
            buffer += raw_chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                json_str = line[6:]
                if json_str.strip() == "[DONE]":
                    continue
                try:
                    event = json.loads(json_str)
                except json.JSONDecodeError:
                    continue

                # Process candidates
                for cand in event.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        if "text" in part:
                            text = part["text"]
                            content_text += text
                            yield {"type": "text_delta", "text": text}
                        elif "functionCall" in part:
                            fc = part["functionCall"]
                            tc_id = f"google_{fc['name']}_{int(time.time() * 1000)}"
                            args = fc.get("args", {})
                            tool_calls.append(
                                {
                                    "id": tc_id,
                                    "name": fc["name"],
                                    "arguments": args,
                                }
                            )
                            yield {"type": "tool_use_start", "id": tc_id, "name": fc["name"]}
                            yield {"type": "tool_use_end", "id": tc_id, "name": fc["name"], "arguments": args}

                # Update usage from metadata
                usage_meta = event.get("usageMetadata", {})
                if usage_meta:
                    usage["input"] = usage_meta.get("promptTokenCount", usage["input"])
                    usage["output"] = usage_meta.get("candidatesTokenCount", usage["output"])

        _lazy_track_usage(model, usage["input"], usage["output"])

        yield {
            "type": "message_end",
            "content": content_text,
            "tool_calls": tool_calls,
            "usage": usage,
            "model": model,
        }

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        log.error(f"[STREAM-GOOGLE] HTTP {e.code}: {err_body[:300]}")
        yield {"type": "error", "error": f"HTTP {e.code}: {err_body[:200]}"}
    except Exception as e:
        log.error(f"[STREAM-GOOGLE] Error: {e}")
        yield {"type": "error", "error": str(e)[:200]}


def _iter_sse_events(resp, tool_calls, accum, usage):
    """Parse SSE stream and yield events, updating accumulators in-place."""
    buffer = ""
    for raw_chunk in _iter_chunks(resp):
        buffer += raw_chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if not line or not line.startswith("data: "):
                continue
            json_str = line[6:]
            if json_str.strip() == "[DONE]":
                continue
            try:
                event = json.loads(json_str)
            except json.JSONDecodeError:
                continue
            yield from _process_stream_event(
                event, accum["content"], accum["thinking"], tool_calls, accum["tool"], accum.get("tool_json", ""), usage
            )
            accum["content"], accum["thinking"], accum["tool"], accum["tool_json"] = _update_stream_accumulators(
                event, accum["content"], accum["thinking"], tool_calls, accum["tool"], accum.get("tool_json", ""), usage
            )


def _update_stream_accumulators(event, content_text, thinking_text, tool_calls, current_tool, current_tool_json, usage):
    """Update streaming accumulators from an SSE event. Returns updated (content, thinking, tool, tool_json)."""
    etype = event.get("type", "")
    if etype == "content_block_delta":
        delta = event.get("delta", {})
        dt = delta.get("type", "")
        if dt == "text_delta":
            content_text += delta.get("text", "")
        elif dt == "thinking_delta":
            thinking_text += delta.get("thinking", "")
        elif dt == "input_json_delta":
            current_tool_json += delta.get("partial_json", "")
    elif etype == "content_block_start":
        cb = event.get("content_block", {})
        if cb.get("type") == "tool_use":
            current_tool = {"id": cb["id"], "name": cb["name"]}
            current_tool_json = ""
    elif etype == "content_block_stop":
        if current_tool:
            try:
                args = json.loads(current_tool_json) if current_tool_json else {}
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({**current_tool, "arguments": args})
            current_tool = None
            current_tool_json = ""
    elif etype == "message_delta":
        u = event.get("usage", {})
        usage["output"] = u.get("output_tokens", usage["output"])
    elif etype == "message_start":
        msg = event.get("message", {})
        u = msg.get("usage", {})
        usage["input"] = u.get("input_tokens", 0)
        usage["cache_creation_input_tokens"] = u.get("cache_creation_input_tokens", 0)
        usage["cache_read_input_tokens"] = u.get("cache_read_input_tokens", 0)
    return content_text, thinking_text, current_tool, current_tool_json


def stream_anthropic(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    tools: Optional[List[dict]] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    thinking: bool = False,
) -> Generator[Dict[str, Any], None, None]:
    """Stream Anthropic API responses token-by-token using raw urllib SSE.

    Yields events:
        {'type': 'text_delta', 'text': '...'}
        {'type': 'thinking_delta', 'text': '...'}
        {'type': 'tool_use_start', 'id': '...', 'name': '...'}
        {'type': 'tool_use_delta', 'partial_json': '...'}
        {'type': 'tool_use_end', 'id': '...', 'name': '...', 'arguments': {...}}
        {'type': 'message_end', 'content': '...', 'tool_calls': [...], 'usage': {...}, 'model': '...'}
        {'type': 'error', 'error': '...'}
    """
    if not model:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        model = router.route(last_user, has_tools=bool(tools))

    # Hard cost cap check before streaming
    try:
        check_cost_cap()
    except CostCapExceeded as e:
        yield {"type": "error", "error": str(e)}
        return

    provider, model_id = model.split("/", 1) if "/" in model else ("anthropic", model)

    # Only Anthropic supports our streaming implementation
    if provider != "anthropic":
        # Fallback: non-streaming call, yield as single chunk
        result = call_llm(messages, model=model, tools=tools, max_tokens=max_tokens, thinking=thinking)
        if result.get("content"):
            yield {"type": "text_delta", "text": result["content"]}
        yield {"type": "message_end", **result}
        return

    api_key = vault.get("anthropic_api_key")
    if not api_key:
        yield {"type": "error", "error": "❌ Anthropic API key not configured."}
        return

    from salmalm.core.llm import _sanitize_messages_for_provider
    messages = _sanitize_messages_for_provider(messages, "anthropic")
    system_msgs = [m["content"] for m in messages if m["role"] == "system"]
    chat_msgs = [m for m in messages if m["role"] != "system"]

    use_thinking = thinking and ("opus" in model_id or "sonnet" in model_id)

    body: dict = {
        "model": model_id,
        "messages": chat_msgs,
        "stream": True,
    }
    if use_thinking:
        body["max_tokens"] = 16000
        body["thinking"] = {"type": "enabled", "budget_tokens": 10000}
    else:
        body["max_tokens"] = max_tokens
    if system_msgs:
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

    data = json.dumps(body).encode("utf-8")
    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "prompt-caching-2024-07-31",
        "User-Agent": _UA,
    }
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=data, headers=headers, method="POST")

    # Accumulators
    content_text = ""
    thinking_text = ""
    tool_calls: List[dict] = []
    current_tool: Optional[dict] = None
    current_tool_json = ""
    usage = {"input": 0, "output": 0}

    try:
        resp = urllib.request.urlopen(req, timeout=180)
        accum = {"content": "", "thinking": "", "tool": None, "tool_json": ""}
        yield from _iter_sse_events(resp, tool_calls, accum, usage)
        _lazy_track_usage(model, usage["input"], usage["output"])
        result = {
            "type": "message_end",
            "content": accum["content"],
            "tool_calls": tool_calls,
            "usage": usage,
            "model": model,
        }
        if accum["thinking"]:
            result["thinking"] = accum["thinking"]
        yield result
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        log.error(f"[STREAM] HTTP {e.code}: {err_body[:300]}")
        yield {"type": "error", "error": f"HTTP {e.code}: {err_body[:200]}"}
    except Exception as e:
        log.error(f"[STREAM] Error: {e}")
        yield {"type": "error", "error": str(e)[:200]}


def _iter_chunks(resp, chunk_size: int = 4096) -> Generator[str, None, None]:
    """Read HTTP response in chunks, decode to str.

    Uses an incremental UTF-8 decoder to avoid splitting multibyte characters
    (e.g. Korean 3-byte sequences) at chunk boundaries.
    """
    import codecs

    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    while True:
        chunk = resp.read(chunk_size)
        if not chunk:
            text = decoder.decode(b"", final=True)
            if text:
                yield text
            break
        text = decoder.decode(chunk, final=False)
        if text:
            yield text


def _process_stream_event(
    event: dict,
    content_text: str,
    thinking_text: str,
    tool_calls: list,
    current_tool: Optional[dict],
    current_tool_json: str,
    usage: dict,
) -> Generator[Dict[str, Any], None, None]:
    """Process a single SSE event from Anthropic stream and yield UI events."""
    etype = event.get("type", "")

    if etype == "content_block_delta":
        delta = event.get("delta", {})
        dt = delta.get("type", "")
        if dt == "text_delta":
            text = delta.get("text", "")
            if text:
                yield {"type": "text_delta", "text": text}
        elif dt == "thinking_delta":
            text = delta.get("thinking", "")
            if text:
                yield {"type": "thinking_delta", "text": text}
        elif dt == "input_json_delta":
            yield {"type": "tool_use_delta", "partial_json": delta.get("partial_json", "")}

    elif etype == "content_block_start":
        cb = event.get("content_block", {})
        if cb.get("type") == "tool_use":
            yield {"type": "tool_use_start", "id": cb["id"], "name": cb["name"]}

    elif etype == "content_block_stop":
        if current_tool:
            try:
                args = json.loads(current_tool_json) if current_tool_json else {}
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_use_end", "id": current_tool["id"], "name": current_tool["name"], "arguments": args}


def stream_openai(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    tools: Optional[List[dict]] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    thinking: bool = False,
) -> Generator[Dict[str, Any], None, None]:
    """Stream OpenAI-compatible API responses token-by-token using SSE.

    Supports: openai, xai, deepseek, openrouter, meta-llama, mistralai, qwen, ollama.
    Yields same event format as stream_anthropic/stream_google for uniform consumer.

    Yields events:
        {'type': 'text_delta', 'text': '...'}
        {'type': 'tool_use_start', 'id': '...', 'name': '...'}
        {'type': 'tool_use_delta', 'partial_json': '...'}
        {'type': 'tool_use_end', 'id': '...', 'name': '...', 'arguments': {...}}
        {'type': 'message_end', 'content': '...', 'tool_calls': [...], 'usage': {...}, 'model': '...'}
        {'type': 'error', 'error': '...'}
    """
    if not model:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        model = router.route(last_user, has_tools=bool(tools))

    try:
        check_cost_cap()
    except CostCapExceeded as e:
        yield {"type": "error", "error": str(e)}
        return

    provider, model_id = model.split("/", 1) if "/" in model else ("openai", model)

    # ── Resolve API key and base URL ──
    _PROVIDER_KEY_VAULT = {
        "openai": "openai_api_key",
        "xai": "xai_api_key",
        "deepseek": "deepseek_api_key",
        "openrouter": "openrouter_api_key",
    }
    _PROVIDER_BASE_URL = {
        "openai": "https://api.openai.com/v1",
        "xai": "https://api.x.ai/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "ollama": vault.get("ollama_url") or "http://localhost:11434/v1",
    }

    if provider == "ollama":
        api_key = "ollama"
        base_url = _PROVIDER_BASE_URL["ollama"]
    elif provider in ("meta-llama", "mistralai", "qwen"):
        api_key = vault.get("openrouter_api_key") or ""
        base_url = _PROVIDER_BASE_URL["openrouter"]
        model_id = f"{provider}/{model_id}"
    else:
        vault_key = _PROVIDER_KEY_VAULT.get(provider, "openai_api_key")
        api_key = vault.get(vault_key) or ""
        base_url = _PROVIDER_BASE_URL.get(provider, "https://api.openai.com/v1")

    if not api_key and provider not in ("ollama",):
        yield {"type": "error", "error": f"❌ {provider} API key not configured."}
        return

    from salmalm.core.llm import _sanitize_messages_for_provider
    messages = _sanitize_messages_for_provider(messages, provider)

    body: dict = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
        "temperature": _lazy_get_temperature(tools),
    }
    if tools:
        body["tools"] = [{"type": "function", "function": t} for t in tools]
        body["tool_choice"] = "auto"

    headers: dict = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key and api_key != "ollama":
        headers["Authorization"] = f"Bearer {api_key}"
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://salmalm.local"
        headers["X-Title"] = "SalmAlm"

    url = f"{base_url}/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")

    # ── Stream SSE ──
    full_text = ""
    tool_calls_buf: dict = {}   # index → {id, name, json_buf}
    in_tokens = 0
    out_tokens = 0
    finish_reason = ""

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                usage = event.get("usage") or {}
                if usage:
                    in_tokens = usage.get("prompt_tokens", in_tokens)
                    out_tokens = usage.get("completion_tokens", out_tokens)

                choices = event.get("choices", [])
                if not choices:
                    continue
                choice = choices[0]
                finish_reason = choice.get("finish_reason") or finish_reason
                delta = choice.get("delta", {})

                # ── Text delta ──
                text_chunk = delta.get("content") or ""
                if text_chunk:
                    full_text += text_chunk
                    yield {"type": "text_delta", "text": text_chunk}

                # ── Tool call deltas ──
                for tc_delta in delta.get("tool_calls", []):
                    idx = tc_delta.get("index", 0)
                    if idx not in tool_calls_buf:
                        tool_calls_buf[idx] = {"id": "", "name": "", "json_buf": ""}
                        tc_id = tc_delta.get("id") or f"call_{idx}_{int(time.time()*1000)}"
                        tc_name = (tc_delta.get("function") or {}).get("name", "")
                        tool_calls_buf[idx]["id"] = tc_id
                        tool_calls_buf[idx]["name"] = tc_name
                        yield {"type": "tool_use_start", "id": tc_id, "name": tc_name}
                    else:
                        tc_name = (tc_delta.get("function") or {}).get("name", "")
                        if tc_name:
                            tool_calls_buf[idx]["name"] = tc_name
                    args_chunk = (tc_delta.get("function") or {}).get("arguments", "")
                    if args_chunk:
                        tool_calls_buf[idx]["json_buf"] += args_chunk
                        yield {"type": "tool_use_delta", "partial_json": args_chunk}

    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        yield {"type": "error", "error": f"❌ {provider} HTTP {e.code}: {err_body}"}
        return
    except Exception as e:
        yield {"type": "error", "error": f"❌ {provider} streaming error: {e}"}
        return

    # ── Finalize tool calls ──
    tool_calls_out = []
    for idx in sorted(tool_calls_buf.keys()):
        tc = tool_calls_buf[idx]
        try:
            args = json.loads(tc["json_buf"]) if tc["json_buf"] else {}
        except json.JSONDecodeError:
            args = {}
        yield {"type": "tool_use_end", "id": tc["id"], "name": tc["name"], "arguments": args}
        tool_calls_out.append({"id": tc["id"], "name": tc["name"], "arguments": args})

    _lazy_track_usage(model, in_tokens, out_tokens)

    yield {
        "type": "message_end",
        "content": full_text,
        "tool_calls": tool_calls_out,
        "stop_reason": finish_reason,
        "usage": {"input": in_tokens, "output": out_tokens},
        "model": model,
    }
