"""Model Auto-Detection (모델 자동 감지) — Open WebUI style."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List

from salmalm.crypto import log


class ModelDetector:
    """Auto-detect available models from all configured providers."""

    _cache: List[Dict] = []
    _cache_ts: float = 0
    _CACHE_TTL = 600

    def detect_all(self, force: bool = False) -> List[Dict]:
        now = time.time()
        if not force and self._cache and (now - self._cache_ts) < self._CACHE_TTL:
            return self._cache

        from salmalm.crypto import vault
        from salmalm.constants import MODELS

        models = []

        for label, model_id in MODELS.items():
            provider = model_id.split('/')[0] if '/' in model_id else 'anthropic'
            key_name = f'{provider}_api_key'
            available = bool(vault.is_unlocked and vault.get(key_name))
            models.append({
                'id': model_id, 'name': label, 'provider': provider,
                'available': available, 'source': 'config'
            })

        ollama_url = vault.get('ollama_url') if vault.is_unlocked else None
        if ollama_url:
            try:
                import urllib.request
                req = urllib.request.Request(f"{ollama_url.rstrip('/')}/api/tags")
                resp = urllib.request.urlopen(req, timeout=5)
                data = json.loads(resp.read())
                for m in data.get('models', []):
                    name = m.get('name', '')
                    models.append({
                        'id': f'ollama/{name}', 'name': name,
                        'provider': 'ollama', 'available': True,
                        'source': 'auto-detected',
                        'size': m.get('size', 0),
                        'modified': m.get('modified_at', ''),
                    })
            except Exception as e:
                log.warning(f"Ollama model detection failed: {e}")

        self._cache = models
        self._cache_ts = now
        return models


model_detector = ModelDetector()
