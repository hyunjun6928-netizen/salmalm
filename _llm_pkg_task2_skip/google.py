"""Google Gemini provider implementation."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from .common import _get_temperature, _http_post


def _call_google(
    api_key: str,
    model_id: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    tools: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """Call Google Gemini API."""
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
                tool_calls.append({"id": f"google_{fc['name']}_{int(time.time() * 1000)}", "name": fc["name"], "arguments": fc.get("args", {})})
    usage_meta = resp.get("usageMetadata", {})
    return {"content": text, "tool_calls": tool_calls, "usage": {"input": usage_meta.get("promptTokenCount", 0), "output": usage_meta.get("candidatesTokenCount", 0)}}


def _build_gemini_contents(messages: List[Dict[str, Any]]) -> list:
    """Convert messages list to Gemini contents format."""
    parts = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content") or ""

        if role == "system":
            parts.append({"role": "user", "parts": [{"text": str(content)}]})
        elif role == "tool":
            tool_name = m.get("name") or m.get("tool_call_id", "tool")
            parts.append({"role": "user", "parts": [{"functionResponse": {"name": tool_name, "response": {"content": str(content)}}}]})
        elif role == "assistant":
            tool_calls = m.get("tool_calls") or []
            gemini_parts = []
            if content:
                if isinstance(content, list):
                    text = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
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
                gemini_parts.append({"functionCall": {"name": fn.get("name", ""), "args": args}})
            if gemini_parts:
                parts.append({"role": "model", "parts": gemini_parts})
        else:
            if isinstance(content, list):
                gemini_parts: list = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type", "")
                    if btype == "text":
                        gemini_parts.append({"text": block.get("text", "")})
                    elif btype == "image" and block.get("source", {}).get("type") == "base64":
                        src = block["source"]
                        gemini_parts.append({"inline_data": {"mime_type": src.get("media_type", "image/jpeg"), "data": src.get("data", "")}})
                    elif btype == "image_url":
                        url = block.get("image_url", {}).get("url", "")
                        if url.startswith("data:"):
                            try:
                                header, b64data = url.split(",", 1)
                                mime = header.split(";")[0].split(":")[1]
                                gemini_parts.append({"inline_data": {"mime_type": mime, "data": b64data}})
                            except Exception:
                                pass
                if gemini_parts:
                    parts.append({"role": "user", "parts": gemini_parts})
            else:
                parts.append({"role": "user", "parts": [{"text": str(content)}]})

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
