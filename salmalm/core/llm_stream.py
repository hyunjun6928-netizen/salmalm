"""LLM streaming response handlers."""

import json
import logging
import time
import urllib.request
from typing import Any, Dict, Generator, List, Optional

log = logging.getLogger(__name__)

from salmalm.core.core import CostCapExceeded, check_cost_cap  # noqa: E402

from salmalm.constants import DEFAULT_MAX_TOKENS  # noqa: E402

def _lazy_track_usage(model, inp, out):
    """Lazy import to avoid circular."""
    from salmalm.core.core import track_usage
    track_usage(model, inp, out)


_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
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
        model = "google/gemini-2.5-flash"

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

    from salmalm.core.llm import _build_gemini_contents; contents = _build_gemini_contents(messages)
    body: dict = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": _lazy_get_temperature(tools)},
    }
    gemini_tools = _lazy_build_gemini_tools(tools)
    if gemini_tools:
        body["tools"] = gemini_tools

    data = json.dumps(body).encode("utf-8")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_id}:streamGenerateContent?alt=sse&key={api_key}"
    )
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
        api_key = None
    if not api_key:
        yield {"type": "error", "error": "❌ Anthropic API key not configured."}
        return

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
        result = {"type": "message_end", "content": accum["content"], "tool_calls": tool_calls, "usage": usage, "model": model}
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


