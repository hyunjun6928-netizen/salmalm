"""OpenAI / xAI / OpenRouter API provider.

Extracted from salmalm.core.llm.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

from salmalm.core.llm.common import _http_post, _http_get, _ResponsesOnlyModel, _RESPONSES_API_MODELS, _RESPONSES_API_BLACKLIST

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

