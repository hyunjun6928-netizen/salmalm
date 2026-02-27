"""Shared helpers and state for LLM provider calls."""

from __future__ import annotations

import json
import os as _os
import urllib.error
import urllib.request
from typing import Dict, Optional

from salmalm.core import CostCapExceeded, _metrics, check_cost_cap, response_cache, router, track_usage
from salmalm.security.crypto import log, vault

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


_LLM_TIMEOUT = int(_os.environ.get("SALMALM_LLM_TIMEOUT", "120"))
_UA: str = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _http_post(url: str, headers: Dict[str, str], body: dict, timeout: int = 120) -> dict:
    """HTTP POST with retry for transient errors (5xx, timeout, 429, 529)."""
    from salmalm.utils.retry import retry_call

    def _do_post():
        data = json.dumps(body).encode("utf-8")
        headers.setdefault("User-Agent", _UA)
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            import re as _re_mask

            _safe_body = _re_mask.sub(r"[a-zA-Z0-9_\-]{20,}", "***", err_body[:300])
            log.error(f"HTTP {e.code}: {_safe_body}")
            if e.code == 401:
                from salmalm.core.exceptions import AuthError

                raise AuthError("Invalid API key (401). Please check your key.") from e
            if e.code == 402:
                from salmalm.core.exceptions import LLMError

                raise LLMError("Insufficient API credits (402). Check billing info.") from e
            if e.code == 404 and "not a chat model" in err_body.lower():
                raise _ResponsesOnlyModel(err_body[:120]) from e
            raise

    return retry_call(_do_post, max_attempts=3)


def _http_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30) -> dict:
    """HTTP GET helper."""
    h: Dict[str, str] = headers or {}
    h.setdefault("User-Agent", _UA)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))  # type: ignore[no-any-return]


_OPENROUTER_PROVIDERS = frozenset(("deepseek", "meta-llama", "mistralai", "qwen"))


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
    """Remove internal marker keys from messages before sending to any provider."""
    if not any(k in m for m in messages for k in _INTERNAL_MSG_KEYS):
        return messages
    return [{k: v for k, v in m.items() if k not in _INTERNAL_MSG_KEYS} for m in messages]


def _sanitize_messages_for_provider(messages: list, provider: str) -> list:
    """Convert messages between provider formats to avoid role errors."""
    messages = _strip_internal_keys(messages)
    if provider == "anthropic":
        import json as _json

        sanitized = []
        for msg in messages:
            role = msg.get("role", "")
            if role == "tool":
                sanitized.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.get("tool_call_id", "unknown"),
                                "content": str(msg.get("content", "")),
                            }
                        ],
                    }
                )
            elif role == "model":
                sanitized.append({**msg, "role": "assistant"})
            elif role == "assistant":
                tool_calls = msg.get("tool_calls") or []
                content = msg.get("content") or ""
                already_converted = isinstance(content, list) and any(b.get("type") == "tool_use" for b in content)
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
                        blocks.append(
                            {
                                "type": "tool_use",
                                "id": tc.get("id", "unknown"),
                                "name": fn.get("name", "unknown"),
                                "input": parsed_args,
                            }
                        )
                    sanitized.append({"role": "assistant", "content": blocks})
                else:
                    sanitized.append(msg)
            else:
                sanitized.append(msg)

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
            if isinstance(content, list) and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                valid = [b for b in content if b.get("tool_use_id") in known_tool_use_ids]
                if valid:
                    cleaned.append({**msg, "content": valid})
            else:
                cleaned.append(msg)
        return cleaned
    if provider == "google":
        return list(messages)
    if provider in ("openai", "xai", "deepseek", "openrouter"):
        sanitized = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
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
