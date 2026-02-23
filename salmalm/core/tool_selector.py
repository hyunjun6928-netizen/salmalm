"""Dynamic tool selection — intent-based tool filtering for token optimization.

Extracted from IntelligenceEngine._get_tools_for_provider to reduce god object.
"""

import os
import re
from typing import List, Optional

from salmalm.core.classifier import INTENT_TOOLS, _KEYWORD_TOOLS
from salmalm.constants import TOOL_HINT_KEYWORDS
from salmalm.security.crypto import log

def get_tools_for_provider(provider: str, intent: str = None, user_message: str = "") -> list:
    from salmalm.tools import TOOL_DEFINITIONS
    from salmalm.core import PluginLoader
    from salmalm.features.mcp import mcp_manager

    # Merge built-in + plugin + MCP tools (deduplicate by name)
    all_tools = list(TOOL_DEFINITIONS)
    seen = {t["name"] for t in all_tools}
    for t in PluginLoader.get_all_tools() + mcp_manager.get_all_tools():
        if t["name"] not in seen:
            all_tools.append(t)
            seen.add(t["name"])

    # ── Dynamic tool selection (disable with SALMALM_ALL_TOOLS=1) ──
    import os as _os

    if _os.environ.get("SALMALM_ALL_TOOLS", "0") == "1":
        # Legacy mode: send all tools, skip filtering
        if provider == "google":
            return [
                {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}
                for t in all_tools
            ]
        elif provider == "anthropic":
            return [
                {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
                for t in all_tools
            ]
        return [
            {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]} for t in all_tools
        ]

    # chat/memory/creative with no keyword match → NO tools (pure LLM)
    # Other intents → small core set + intent + keyword matched
    _NO_TOOL_INTENTS = {"chat", "memory", "creative"}
    _CORE_TOOLS = {
        "read_file",
        "write_file",
        "edit_file",
        "exec",
        "web_search",
        "web_fetch",
    }

    # Check keyword matches first
    keyword_matched = set()
    if user_message:
        msg_lower = user_message.lower()
        for kw, tool_names in _KEYWORD_TOOLS.items():
            if kw in msg_lower:
                keyword_matched.update(tool_names)

    # Zero-tool path: chat/memory/creative with no keyword triggers
    if intent in _NO_TOOL_INTENTS and not keyword_matched:
        return []  # Pure LLM — no tool schema overhead

    # Tool path: core + intent + keyword
    selected_names = set(_CORE_TOOLS)
    if intent and intent in INTENT_TOOLS:
        selected_names.update(INTENT_TOOLS[intent])
    selected_names.update(keyword_matched)
    # Filter: only include tools that exist in all_tools
    all_tools = [t for t in all_tools if t["name"] in selected_names]

    # ── Schema compression: strip param descriptions, keep only required + type ──
    def _compress_schema(schema) -> dict:
        if not schema or not isinstance(schema, dict):
            return schema
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        compressed = {}
        for k, v in props.items():
            # Keep only type (and enum if present) — drop description
            entry = {"type": v.get("type", "string")}
            if "enum" in v:
                entry["enum"] = v["enum"]
            if "items" in v:
                entry["items"] = (
                    {"type": v["items"].get("type", "string")} if isinstance(v.get("items"), dict) else v["items"]
                )
            compressed[k] = entry
        result = {"type": "object", "properties": compressed}
        if required:
            result["required"] = list(required)
        return result

    def _compress_desc(desc) -> str:
        """Truncate description to first sentence, max 80 chars."""
        if not desc:
            return desc
        # First sentence
        for sep in [". ", ".\n", "; "]:
            idx = desc.find(sep)
            if 0 < idx < 80:
                return desc[: idx + 1]
        return desc[:80].rstrip() + ("…" if len(desc) > 80 else "")

    if provider == "google":
        return [
            {
                "name": t["name"],
                "description": _compress_desc(t["description"]),
                "parameters": _compress_schema(t["input_schema"]),
            }
            for t in all_tools
        ]
    elif provider in ("openai", "xai", "deepseek", "meta-llama"):
        return [
            {
                "name": t["name"],
                "description": _compress_desc(t["description"]),
                "parameters": _compress_schema(t["input_schema"]),
            }
            for t in all_tools
        ]
    elif provider == "anthropic":
        return [
            {
                "name": t["name"],
                "description": _compress_desc(t["description"]),
                "input_schema": _compress_schema(t["input_schema"]),
            }
            for t in all_tools
        ]
    return all_tools

