"""Model registry and aliases."""

from __future__ import annotations

MODELS = {
    "opus": "anthropic/claude-opus-4-6",
    "sonnet": "anthropic/claude-sonnet-4-6",
    "haiku": "anthropic/claude-haiku-4-5-20251001",
    "gpt5.2": "openai/gpt-5.2-codex",
    "gpt5.1": "openai/gpt-5.1-codex",
    "gpt4.1": "openai/gpt-4.1",
    "gpt4.1mini": "openai/gpt-4.1-mini",
    "gpt4.1nano": "openai/gpt-4.1-nano",
    "o3": "openai/o3",
    "o4mini": "openai/o4-mini",
    "grok4": "xai/grok-4",
    "grok3": "xai/grok-3",
    "grok3mini": "xai/grok-3-mini",
    "gemini3pro": "google/gemini-3-pro-preview",
    "gemini3flash": "google/gemini-3-flash-preview",
    "gemini2.5pro": "google/gemini-2.5-pro",
    "gemini2.5flash": "google/gemini-2.5-flash",
    "deepseek-r1": "openrouter/deepseek/deepseek-r1",
    "deepseek-chat": "openrouter/deepseek/deepseek-chat",
    "maverick": "openrouter/meta-llama/llama-4-maverick",
    "scout": "openrouter/meta-llama/llama-4-scout",
}

FALLBACK_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "xai": "grok-4",
    "google": "gemini-3-flash-preview",
}

MODEL_ALIASES = {
    "claude": MODELS["sonnet"],
    "sonnet": MODELS["sonnet"],
    "opus": MODELS["opus"],
    "haiku": MODELS["haiku"],
    "gpt": MODELS["gpt5.2"],
    "gpt5": MODELS["gpt5.2"],
    "gpt5.1": MODELS["gpt5.1"],
    "gpt4.1": MODELS["gpt4.1"],
    "4.1mini": MODELS["gpt4.1mini"],
    "4.1nano": MODELS["gpt4.1nano"],
    "o3": MODELS["o3"],
    "o4mini": MODELS["o4mini"],
    "grok": MODELS["grok4"],
    "grok4": MODELS["grok4"],
    "grok3": MODELS["grok3"],
    "grok3mini": MODELS["grok3mini"],
    "gemini": MODELS["gemini3pro"],
    "flash": MODELS["gemini3flash"],
    "deepseek": MODELS["deepseek-r1"],
    "maverick": MODELS["maverick"],
    "scout": MODELS["scout"],
    "llama": "ollama/llama3.3",
    "llama3.2": "ollama/llama3.2",
    "llama3.3": "ollama/llama3.3",
    "qwen": "ollama/qwen3",
    "qwen3": "ollama/qwen3",
}

THINKING_BUDGET_MAP: dict = {
    "low": 4_000,
    "medium": 10_000,
    "high": 16_000,
    "xhigh": 32_000,
}
