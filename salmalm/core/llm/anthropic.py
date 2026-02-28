"""Anthropic Claude API provider.

Extracted from salmalm.core.llm.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

from salmalm.core.llm.common import _http_post, _get_temperature, _LLM_TIMEOUT

def _call_anthropic(
    api_key: str,
    model_id: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[dict]],
    max_tokens: int,
    thinking: bool = False,
    timeout: int = 0,
) -> Dict[str, Any]:
    """Call anthropic.

    Callers are responsible for sanitizing messages via
    _sanitize_messages_for_provider(messages, 'anthropic') before calling
    this function.  call_llm() and _try_fallback() both do this.
    Do NOT re-sanitize here — it causes double orphaned-tool-result detection.
    """
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


