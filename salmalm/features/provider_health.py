"""Provider Health Check (프로바이더 상태 확인) — Open WebUI style."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Dict

from salmalm.constants import KST


class ProviderHealthCheck:
    """Check health of all configured LLM providers."""

    _cache: Dict[str, Any] = {}
    _cache_ts: float = 0
    _CACHE_TTL = 300

    def check_all(self, force: bool = False) -> Dict[str, Any]:
        now = time.time()
        if not force and self._cache and (now - self._cache_ts) < self._CACHE_TTL:
            return self._cache

        from salmalm.security.crypto import vault

        results = {}

        if vault.is_unlocked and vault.get("anthropic_api_key"):
            results["anthropic"] = self._test_anthropic(vault.get("anthropic_api_key"))
        else:
            results["anthropic"] = "not configured"

        if vault.is_unlocked and vault.get("openai_api_key"):
            results["openai"] = self._test_openai(vault.get("openai_api_key"))
        else:
            results["openai"] = "not configured"

        if vault.is_unlocked and vault.get("xai_api_key"):
            results["xai"] = self._test_xai(vault.get("xai_api_key"))
        else:
            results["xai"] = "not configured"

        if vault.is_unlocked and vault.get("google_api_key"):
            results["google"] = self._test_google(vault.get("google_api_key"))
        else:
            results["google"] = "not configured"

        ollama_url = vault.get("ollama_url") if vault.is_unlocked else None
        if ollama_url:
            ollama_key = vault.get("ollama_api_key") if vault.is_unlocked else None
            results["ollama"] = self._test_ollama(ollama_url, ollama_key)
        else:
            results["ollama"] = "not configured"

        if vault.is_unlocked and vault.get("deepseek_api_key"):
            results["deepseek"] = self._test_deepseek(vault.get("deepseek_api_key"))
        else:
            results["deepseek"] = "not configured"

        overall = "ok" if any(v == "ok" for v in results.values()) else "error"
        result = {"status": overall, "providers": results, "checked_at": datetime.now(KST).isoformat()}
        self._cache = result
        self._cache_ts = now
        return result

    def _test_anthropic(self, key: str) -> str:
        try:
            from salmalm.core.llm import _http_post

            _http_post(
                "https://api.anthropic.com/v1/messages",
                {"x-api-key": key, "content-type": "application/json", "anthropic-version": "2023-06-01"},
                {
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=10,
            )
            return "ok"
        except Exception as e:
            return f"error: {str(e)[:100]}"

    def _test_openai(self, key: str) -> str:
        try:
            from salmalm.core.llm import _http_post

            _http_post(
                "https://api.openai.com/v1/chat/completions",
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                {"model": "gpt-4.1-nano", "max_tokens": 5, "messages": [{"role": "user", "content": "ping"}]},
                timeout=10,
            )
            return "ok"
        except Exception as e:
            return f"error: {str(e)[:100]}"

    def _test_xai(self, key: str) -> str:
        try:
            from salmalm.core.llm import _http_post

            _http_post(
                "https://api.x.ai/v1/chat/completions",
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                {"model": "grok-3-mini-fast", "max_tokens": 5, "messages": [{"role": "user", "content": "ping"}]},
                timeout=10,
            )
            return "ok"
        except Exception as e:
            return f"error: {str(e)[:100]}"

    def _test_google(self, key: str) -> str:
        try:
            import urllib.request

            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
                data=json.dumps({"contents": [{"parts": [{"text": "ping"}]}]}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
            return "ok"
        except Exception as e:
            return f"error: {str(e)[:100]}"

    def _test_deepseek(self, key: str) -> str:
        try:
            from salmalm.core.llm import _http_post

            _http_post(
                "https://api.deepseek.com/v1/chat/completions",
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                {"model": "deepseek-chat", "max_tokens": 5, "messages": [{"role": "user", "content": "ping"}]},
                timeout=10,
            )
            return "ok"
        except Exception as e:
            return f"error: {str(e)[:100]}"

    def _test_ollama(self, url: str, api_key: str = None) -> str:
        try:
            import urllib.request

            base = url.rstrip("/")
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            # Try /api/tags first (native Ollama), then /models (OpenAI-compat)
            for endpoint in (f"{base}/api/tags", f"{base}/models"):
                try:
                    req = urllib.request.Request(endpoint, headers=headers)
                    resp = urllib.request.urlopen(req, timeout=5)
                    data = json.loads(resp.read())
                    count = len(data.get("models", data.get("data", [])))
                    return f"ok ({count} models)"
                except Exception:
                    continue
            return "offline: no models endpoint responded"
        except Exception as e:
            return f"offline: {str(e)[:100]}"


provider_health = ProviderHealthCheck()
