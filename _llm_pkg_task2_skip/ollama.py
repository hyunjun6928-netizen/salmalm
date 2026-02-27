"""Ollama provider implementation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .common import vault
from .openai import _call_openai


def _call_ollama(
    model_id: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[dict]],
    max_tokens: int,
    thinking: Any = False,
) -> Dict[str, Any]:
    """Call local Ollama endpoint via OpenAI-compatible API."""
    ollama_url = vault.get("ollama_url") or "http://localhost:11434/v1"
    return _call_openai("ollama", model_id, messages, tools, max_tokens, ollama_url, thinking=thinking)
