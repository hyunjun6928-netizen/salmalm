"""Multi-Provider LLM Router — unified API across Anthropic, OpenAI, Google, Groq, Ollama.

stdlib-only. Provides:
  - Provider auto-detection from model string
  - Unified OpenAI-compatible request/response format
  - Automatic fallback on failure
  - /model list, /model switch <name> commands
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider definitions
# ---------------------------------------------------------------------------

PROVIDERS: Dict[str, Dict[str, Any]] = {
    "anthropic": {
        "env_key": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1",
        "chat_endpoint": "/messages",
        "models": [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ],
    },
    "openai": {
        "env_key": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "chat_endpoint": "/chat/completions",
        "models": [
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "o3",
            "o4-mini",
            "gpt-4o",
            "gpt-4o-mini",
        ],
    },
    "google": {
        "env_key": "GOOGLE_API_KEY",
        "alt_env_key": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "chat_endpoint": "/chat/completions",  # OpenAI-compat
        "models": [
            "gemini-3-pro-preview",
            "gemini-3-flash-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
        ],
    },
    "groq": {
        "env_key": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "chat_endpoint": "/chat/completions",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ],
    },
    "xai": {
        "env_key": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "chat_endpoint": "/chat/completions",
        "models": [
            "grok-4-0709",
            "grok-3",
            "grok-3-mini",
        ],
    },
    "ollama": {
        "env_key": "",  # no key needed
        "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        "chat_endpoint": "/api/chat",
        "models": [
            "llama3.2",
            "llama3.3",
            "qwen3",
            "mistral",
        ],
    },
}

# ---------------------------------------------------------------------------
# Dynamic model discovery — fetches real model lists from provider APIs
# Cache TTL: 1 hour. Falls back to PROVIDERS["x"]["models"] on failure.
# ---------------------------------------------------------------------------

_MODEL_CACHE: Dict[str, Dict] = {}   # provider → {models: [...], ts: float}
_MODEL_CACHE_TTL = 3600              # 1 hour


# Models to EXCLUDE from OpenAI/Groq/xAI listings (non-chat)
_OPENAI_EXCLUDE = {
    "tts", "whisper", "dall-e", "embedding", "moderation", "babbage",
    "davinci", "text-", "chatgpt-image", "omni-moderation", "realtime",
    "audio", "gpt-3.5-turbo-instruct",
    "codex",          # v1/responses-only models (gpt-5-codex, gpt-5.2-codex, etc.)
    "computer-use",   # tool-specific, not general chat
}


def _is_chat_model_openai(model_id: str) -> bool:
    """Return True if an OpenAI model ID looks like a chat model."""
    mid = model_id.lower()
    for excl in _OPENAI_EXCLUDE:
        if excl in mid:
            return False
    # Keep gpt-*, o1-*, o3-*, o4-* (but not date-pinned duplicates like gpt-4o-2024-08-06)
    import re
    if re.search(r"-\d{4}-\d{2}-\d{2}$", mid):
        return False   # skip date-pinned versions
    return any(mid.startswith(p) for p in ("gpt-", "o1", "o3", "o4"))


def _fetch_provider_models(provider: str) -> List[str]:
    """Fetch live model list from provider API. Returns [] on failure."""
    key = get_api_key(provider)
    if not key:
        return []
    cfg = PROVIDERS.get(provider, {})
    base = cfg.get("base_url", "")
    try:
        if provider == "anthropic":
            req = urllib.request.Request(
                f"{base}/models?limit=100",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            import re
            return [
                m["id"] for m in data.get("data", [])
                if m.get("type", "model") == "model"
                and not re.search(r"-\d{8}$", m["id"])   # skip date-pinned snapshots
                and not re.search(r"-\d{4}-\d{2}-\d{2}$", m["id"])  # ISO date snapshots
                and "claude-3-" not in m["id"]            # skip legacy claude-3 family
            ]

        elif provider == "google":
            url = f"{base}/models?key={key}&pageSize=100"
            with urllib.request.urlopen(url, timeout=8) as r:
                data = json.loads(r.read())
            return [
                m["name"].replace("models/", "")
                for m in data.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]

        elif provider in ("openai", "groq", "xai"):
            req = urllib.request.Request(
                f"{base}/models",
                headers={"Authorization": f"Bearer {key}"},
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            ids = [m["id"] for m in data.get("data", [])]
            if provider == "openai":
                ids = [m for m in ids if _is_chat_model_openai(m)]
                # Sort: latest first (gpt-4.1 before gpt-4o before gpt-4)
                ids.sort(reverse=True)
            elif provider in ("groq", "xai"):
                ids = [m for m in ids if not any(
                    x in m.lower() for x in ("whisper", "embed", "guard", "vision-tool")
                )]
                ids.sort()
            return ids

    except Exception as e:
        log.debug(f"[MODELS] Live fetch failed for {provider}: {e}")
    return []


def get_provider_models(provider: str) -> List[str]:
    """Return model list for provider — live from API if possible, cached for 1h.

    Falls back to hardcoded PROVIDERS list if fetch fails or provider is local.
    """
    if provider == "ollama":
        result = detect_ollama()
        return result.get("models", PROVIDERS["ollama"]["models"])

    now = time.time()
    cached = _MODEL_CACHE.get(provider)
    if cached and now - cached["ts"] < _MODEL_CACHE_TTL:
        return cached["models"]

    live = _fetch_provider_models(provider)
    if live:
        _MODEL_CACHE[provider] = {"models": live, "ts": now}
        log.info(f"[MODELS] Fetched {len(live)} models for {provider}")
        return live

    # Fall back to hardcoded list
    fallback = PROVIDERS.get(provider, {}).get("models", [])
    log.debug(f"[MODELS] Using hardcoded fallback for {provider} ({len(fallback)} models)")
    return fallback


def refresh_model_cache() -> Dict[str, int]:
    """Force-refresh model cache for all providers. Returns {provider: count}."""
    _MODEL_CACHE.clear()
    result = {}
    for prov in PROVIDERS:
        if prov == "ollama":
            continue
        models = get_provider_models(prov)
        result[prov] = len(models)
    return result


# Provider prefix → provider name
_PREFIX_MAP = {
    "anthropic/": "anthropic",
    "openai/": "openai",
    "google/": "google",
    "groq/": "groq",
    "ollama/": "ollama",
    "xai/": "xai",
    "openrouter/": "openai",  # OpenRouter uses OpenAI-compatible API
}


def detect_provider(model: str) -> Tuple[str, str]:
    """Detect provider from model string. Returns (provider_name, bare_model)."""
    for prefix, prov in _PREFIX_MAP.items():
        if model.startswith(prefix):
            return prov, model[len(prefix) :]
    # Heuristic detection
    ml = model.lower()
    if "claude" in ml:
        return "anthropic", model
    if "gpt" in ml or ml.startswith("o3") or ml.startswith("o4"):
        return "openai", model
    if "gemini" in ml:
        return "google", model
    if "llama" in ml or "mixtral" in ml or "gemma" in ml:
        # Could be groq or ollama — check if groq key exists
        if os.environ.get("GROQ_API_KEY"):
            return "groq", model
        return "ollama", model
    return "openai", model  # default


def get_api_key(provider: str) -> Optional[str]:
    """Get API key for provider from environment or vault."""
    prov_cfg = PROVIDERS.get(provider, {})
    env_key = prov_cfg.get("env_key", "")
    if not env_key:
        return None  # ollama doesn't need key
    key = os.environ.get(env_key)
    if not key:
        alt_key = prov_cfg.get("alt_env_key", "")
        if alt_key:
            key = os.environ.get(alt_key)
    # Fallback: check vault (web UI stores keys there)
    if not key:
        try:
            from salmalm.security.crypto import vault

            if vault.is_unlocked:
                vault_name = env_key.lower()  # ANTHROPIC_API_KEY -> anthropic_api_key
                key = vault.get(vault_name)
                if not key and prov_cfg.get("alt_env_key"):
                    key = vault.get(prov_cfg["alt_env_key"].lower())
        except Exception as e:
            log.debug(f"Suppressed: {e}")
    return key


def detect_ollama(base_url: str = "") -> dict:
    """Auto-detect Ollama and list installed models."""
    import urllib.request
    url = base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        req = urllib.request.Request(f"{url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            return {"available": True, "models": models, "url": url}
    except Exception:
        return {"available": False, "models": [], "url": url}


def is_provider_available(provider: str) -> bool:
    """Check if a provider is available (has API key or is local)."""
    if provider == "ollama":
        return detect_ollama().get("available", False)
    return bool(get_api_key(provider))


def list_available_models() -> List[Dict[str, str]]:
    """List all available models across configured providers (live from API)."""
    result = []
    for prov_name in PROVIDERS:
        if not is_provider_available(prov_name):
            continue
        for m in get_provider_models(prov_name):
            result.append({"provider": prov_name, "model": f"{prov_name}/{m}", "name": m})
    return result


class LLMRouter:
    """Multi-provider LLM router with fallback."""

    def __init__(self) -> None:
        """Init  ."""
        self._current_model: Optional[str] = None
        self._fallback_order: List[str] = ["anthropic", "openai", "google", "groq", "ollama"]
        self._call_history: List[Dict[str, Any]] = []

    @property
    def current_model(self) -> Optional[str]:
        """Current model."""
        return self._current_model

    @current_model.setter
    def current_model(self, model: str) -> None:
        """Current model."""
        self._current_model = model

    def switch_model(self, model: str) -> str:
        """Switch to a new model. Returns confirmation message."""
        if model == "auto":
            self._current_model = "auto"
            return "✅ Switched to **auto routing** (cost-optimized)"
        provider, bare = detect_provider(model)
        if not is_provider_available(provider):
            return f"❌ Provider `{provider}` not configured (missing API key)"
        self._current_model = model
        return f"✅ Switched to `{model}` ({provider})"

    def list_models(self) -> str:
        """Format available models for display."""
        models = list_available_models()
        if not models:
            return "❌ No providers configured. Set API keys in environment."
        lines = ["**Available Models:**\n"]
        by_provider: Dict[str, List[str]] = {}
        for m in models:
            by_provider.setdefault(m["provider"], []).append(m["name"])
        for prov, names in by_provider.items():
            lines.append(f"**{prov}:**")
            for n in names:
                marker = " ← current" if self._current_model and n in self._current_model else ""
                lines.append(f"  • `{prov}/{n}`{marker}")
        return "\n".join(lines)

    def _build_request(
        self, provider: str, model: str, messages: List[Dict], max_tokens: int = 4096, tools: Optional[List] = None
    ) -> Tuple[str, Dict[str, str], dict]:
        """Build HTTP request for provider. Returns (url, headers, body)."""
        prov_cfg = PROVIDERS.get(provider, PROVIDERS["openai"])
        base = prov_cfg["base_url"]
        endpoint = prov_cfg["chat_endpoint"]
        api_key = get_api_key(provider)

        if provider == "anthropic":
            url = f"{base}{endpoint}"
            headers = {
                "x-api-key": api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            # Convert OpenAI format → Anthropic format
            system = ""
            conv_msgs = []
            pending_tool_results: List[Dict] = []  # accumulate tool results for next user turn
            for m in messages:
                role = m.get("role", "")
                if role == "system":
                    system += m.get("content", "") + "\n"
                elif role == "tool":
                    # OpenAI tool result → Anthropic tool_result content block
                    pending_tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id", "unknown"),
                        "content": str(m.get("content", "")),
                    })
                elif role == "assistant":
                    # Flush any pending tool results as a user turn first
                    if pending_tool_results:
                        conv_msgs.append({"role": "user", "content": pending_tool_results})
                        pending_tool_results = []
                    tool_calls = m.get("tool_calls") or []
                    content_text = m.get("content") or ""
                    if tool_calls:
                        # Convert OpenAI tool_calls → Anthropic tool_use blocks
                        content_blocks: List[Dict] = []
                        if content_text:
                            content_blocks.append({"type": "text", "text": content_text})
                        for tc in tool_calls:
                            fn = tc.get("function", {})
                            try:
                                inp = json.loads(fn.get("arguments", "{}"))
                            except Exception:
                                inp = {}
                            content_blocks.append({
                                "type": "tool_use",
                                "id": tc.get("id", ""),
                                "name": fn.get("name", ""),
                                "input": inp,
                            })
                        conv_msgs.append({"role": "assistant", "content": content_blocks})
                    else:
                        conv_msgs.append({"role": "assistant", "content": content_text})
                else:
                    # user or unknown role
                    if pending_tool_results:
                        conv_msgs.append({"role": "user", "content": pending_tool_results})
                        pending_tool_results = []
                    conv_msgs.append({"role": "user", "content": m.get("content", "")})
            # Flush any remaining tool results
            if pending_tool_results:
                conv_msgs.append({"role": "user", "content": pending_tool_results})
            body: dict = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": conv_msgs,
            }
            if system.strip():
                body["system"] = system.strip()
            if tools:
                body["tools"] = tools
        elif provider == "ollama":
            url = f"{base}{endpoint}"
            headers = {"content-type": "application/json"}
            body = {
                "model": model,
                "messages": messages,
                "stream": False,
            }
        else:
            # OpenAI-compatible (OpenAI, Groq, Google, xAI, OpenRouter)
            url = f"{base}{endpoint}"
            headers = {
                "Authorization": f"Bearer {api_key or ''}",
                "content-type": "application/json",
            }
            body = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
            }
            if tools:
                body["tools"] = tools

        return url, headers, body

    def _parse_response(self, provider: str, data: dict) -> Dict[str, Any]:
        """Parse provider response into unified format."""
        if provider == "anthropic":
            content = ""
            tool_calls = []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")
                elif block.get("type") == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.get("id", ""),
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        }
                    )
            usage = data.get("usage", {})
            return {
                "content": content,
                "tool_calls": tool_calls,
                "usage": {
                    "input": usage.get("input_tokens", 0),
                    "output": usage.get("output_tokens", 0),
                },
                "model": data.get("model", ""),
            }
        elif provider == "ollama":
            msg = data.get("message", {})
            return {
                "content": msg.get("content", ""),
                "tool_calls": [],
                "usage": {
                    "input": data.get("prompt_eval_count", 0),
                    "output": data.get("eval_count", 0),
                },
                "model": data.get("model", ""),
            }
        else:
            # OpenAI-compatible
            choices = data.get("choices", [{}])
            msg = choices[0].get("message", {}) if choices else {}
            usage = data.get("usage", {})
            return {
                "content": msg.get("content", "") or "",
                "tool_calls": msg.get("tool_calls", []),
                "usage": {
                    "input": usage.get("prompt_tokens", 0),
                    "output": usage.get("completion_tokens", 0),
                },
                "model": data.get("model", ""),
            }

    def call(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        max_tokens: int = 4096,
        tools: Optional[List] = None,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """Call LLM with automatic fallback.

        Returns unified response dict: {content, tool_calls, usage, model}.
        """
        target_model = model or self._current_model
        if not target_model:
            # Pick first available
            for prov in self._fallback_order:
                if is_provider_available(prov):
                    models = PROVIDERS[prov]["models"]
                    if models:
                        target_model = models[0]
                        break
        if not target_model:
            return {
                "content": "❌ No LLM providers configured",
                "tool_calls": [],
                "usage": {"input": 0, "output": 0},
                "model": "",
            }

        provider, bare_model = detect_provider(target_model)
        errors = []

        # Try primary
        try:
            result = self._do_call(provider, bare_model, messages, max_tokens, tools, timeout)
            self._call_history.append({"model": target_model, "provider": provider, "ok": True, "ts": time.time()})
            return result
        except Exception as e:
            errors.append(f"{provider}/{bare_model}: {e}")
            log.warning(f"LLM call failed for {provider}/{bare_model}: {e}")

        # Fallback
        for fb_prov in self._fallback_order:
            if fb_prov == provider or not is_provider_available(fb_prov):
                continue
            fb_models = PROVIDERS[fb_prov]["models"]
            if not fb_models:
                continue
            fb_model = fb_models[0]
            try:
                log.info(f"Falling back to {fb_prov}/{fb_model}")
                result = self._do_call(fb_prov, fb_model, messages, max_tokens, tools, timeout)
                result["fallback"] = True
                result["original_model"] = target_model
                self._call_history.append(
                    {
                        "model": f"{fb_prov}/{fb_model}",
                        "provider": fb_prov,
                        "ok": True,
                        "ts": time.time(),
                        "fallback": True,
                    }
                )
                return result
            except Exception as e2:
                errors.append(f"{fb_prov}/{fb_model}: {e2}")

        return {
            "content": "❌ All providers failed:\n" + "\n".join(errors),
            "tool_calls": [],
            "usage": {"input": 0, "output": 0},
            "model": target_model,
        }

    def _do_call(
        self, provider: str, model: str, messages: List[Dict], max_tokens: int, tools: Optional[List], timeout: int
    ) -> Dict[str, Any]:
        """Execute a single LLM API call."""
        url, headers, body = self._build_request(provider, model, messages, max_tokens, tools)
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
        return self._parse_response(provider, result)


# Singleton
llm_router = LLMRouter()


# ---------------------------------------------------------------------------
# Command handlers (for CommandRouter registration)
# ---------------------------------------------------------------------------


def handle_model_command(cmd: str, session=None, **kw) -> str:
    """Handle /model list | /model switch <name>."""
    parts = cmd.strip().split()
    # /model list
    if len(parts) >= 2 and parts[1] == "list":
        return llm_router.list_models()
    # /model switch <name>
    if len(parts) >= 3 and parts[1] == "switch":
        return llm_router.switch_model(parts[2])
    # /model (just show current)
    current = llm_router.current_model or "(auto)"
    return f"Current model: `{current}`\nUse `/model list` or `/model switch <name>`"


def register_commands(router: object) -> None:
    """Register /model commands with CommandRouter."""
    router.register_prefix("/model", handle_model_command)


def register_tools(registry_module: Optional[object] = None) -> None:
    """Register LLM router tools."""
    try:
        from salmalm.tools.tool_registry import register_dynamic

        register_dynamic(
            "llm_router_list",
            lambda args: llm_router.list_models(),
            {
                "name": "llm_router_list",
                "description": "List available LLM models across all configured providers",
                "input_schema": {"type": "object", "properties": {}},
            },
        )
        register_dynamic(
            "llm_router_switch",
            lambda args: llm_router.switch_model(args.get("model", "")),
            {
                "name": "llm_router_switch",
                "description": "Switch to a different LLM model",
                "input_schema": {"type": "object", "properties": {"model": {"type": "string"}}, "required": ["model"]},
            },
        )
    except Exception as e:
        log.warning(f"Failed to register LLM router tools: {e}")
