"""Model Auto-Detection (모델 자동 감지) — Open WebUI style."""

from __future__ import annotations

import json
import time
from typing import Dict, List, Optional

from salmalm.security.crypto import log


class ModelDetector:
    """Auto-detect available models from all configured providers."""

    _cache: List[Dict] = []
    _cache_ts: float = 0
    _CACHE_TTL = 600

    def detect_all(self, force: bool = False) -> List[Dict]:
        """Detect all."""
        now = time.time()
        if not force and self._cache and (now - self._cache_ts) < self._CACHE_TTL:
            return self._cache

        from salmalm.security.crypto import vault
        from salmalm.constants import MODELS

        models = []

        for label, model_id in MODELS.items():
            provider = model_id.split("/")[0] if "/" in model_id else "anthropic"
            key_name = f"{provider}_api_key"
            available = bool(vault.is_unlocked and vault.get(key_name))
            models.append(
                {"id": model_id, "name": label, "provider": provider, "available": available, "source": "config"}
            )

        ollama_url = vault.get("ollama_url") if vault.is_unlocked else None
        if ollama_url:
            ollama_key = vault.get("ollama_api_key") if vault.is_unlocked else None
            local_models = self._detect_local_models(ollama_url, ollama_key)
            models.extend(local_models)

        self._cache = models
        self._cache_ts = now
        return models

    def _detect_local_models(self, base_url: str, api_key: Optional[str] = None) -> List[Dict]:
        """Detect models from local LLM endpoint. Tries /models, /v1/models, /api/tags."""
        import urllib.request

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        base = base_url.rstrip("/")
        # Try endpoints in order: OpenAI-compat /models, /v1/models, Ollama /api/tags
        endpoints = [
            (f"{base}/models", "openai"),
            (f"{base}/v1/models", "openai"),
            (f"{base}/api/tags", "ollama"),
        ]
        # If base already ends with /v1, also try without
        if base.endswith("/v1"):
            base_root = base[:-3]
            endpoints = [
                (f"{base}/models", "openai"),
                (f"{base_root}/models", "openai"),
                (f"{base_root}/api/tags", "ollama"),
            ]

        for url, fmt in endpoints:
            try:
                req = urllib.request.Request(url, headers=headers)
                resp = urllib.request.urlopen(req, timeout=5)
                data = json.loads(resp.read())
                models = []
                if fmt == "openai":
                    for m in data.get("data", []):
                        mid = m.get("id", "")
                        if mid:
                            models.append(
                                {
                                    "id": f"ollama/{mid}",
                                    "name": mid,
                                    "provider": "ollama",
                                    "available": True,
                                    "source": "auto-detected",
                                }
                            )
                elif fmt == "ollama":
                    for m in data.get("models", []):
                        name = m.get("name", "")
                        if name:
                            models.append(
                                {
                                    "id": f"ollama/{name}",
                                    "name": name,
                                    "provider": "ollama",
                                    "available": True,
                                    "source": "auto-detected",
                                    "size": m.get("size", 0),
                                    "modified": m.get("modified_at", ""),
                                }
                            )
                if models:
                    log.info(f"[MODEL-DETECT] Found {len(models)} local models via {url}")
                    return models
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")

        log.warning(f"[MODEL-DETECT] No local models found from {base_url}")
        return []


model_detector = ModelDetector()
