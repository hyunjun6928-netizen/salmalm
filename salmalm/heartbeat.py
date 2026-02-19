"""SalmAlm Heartbeat — Cache warming for Anthropic prompt caching.

Periodically sends a minimal request to keep the prompt cache warm.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from .crypto import log

_CACHE_CONFIG_FILE = Path.home() / '.salmalm' / 'cache.json'

_DEFAULT_CONFIG = {
    'promptCaching': True,
    'cacheTtlMinutes': 60,
    'warmingEnabled': True,
    'warmingIntervalMinutes': 55,
}


def load_cache_config() -> dict:
    """Load cache config from ~/.salmalm/cache.json."""
    try:
        if _CACHE_CONFIG_FILE.exists():
            cfg = json.loads(_CACHE_CONFIG_FILE.read_text(encoding='utf-8'))
            merged = dict(_DEFAULT_CONFIG)
            merged.update(cfg)
            return merged
    except Exception:
        pass
    return dict(_DEFAULT_CONFIG)


def save_cache_config(config: dict):
    """Save cache config."""
    try:
        _CACHE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding='utf-8')
    except Exception:
        pass


class CacheWarmer:
    """Periodically warm Anthropic prompt cache to prevent TTL expiry."""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_warm: float = 0.0
        self._warm_count: int = 0

    def start(self):
        """Start the cache warming background thread."""
        config = load_cache_config()
        if not config.get('warmingEnabled', False):
            log.info("[CACHE] Cache warming disabled")
            return
        if not config.get('promptCaching', True):
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._warming_loop,
            daemon=True,
            name='cache-warmer'
        )
        self._thread.start()
        log.info(f"[CACHE] Cache warmer started (interval={config['warmingIntervalMinutes']}min)")

    def stop(self):
        """Stop the cache warming thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _warming_loop(self):
        """Main warming loop."""
        while not self._stop_event.is_set():
            config = load_cache_config()
            interval_sec = config.get('warmingIntervalMinutes', 55) * 60

            # Wait for interval
            if self._stop_event.wait(timeout=interval_sec):
                break  # Stop requested

            if not config.get('warmingEnabled', False):
                continue

            try:
                self._warm_cache()
            except Exception as e:
                log.warning(f"[CACHE] Warming failed: {e}")

    def _warm_cache(self):
        """Send a minimal request to warm the prompt cache.

        Uses a tiny max_tokens to minimize cost while keeping cache alive.
        """
        from .prompt import build_system_prompt
        from .crypto import vault

        api_key = vault.get('anthropic_api_key')
        if not api_key:
            return

        sys_prompt = build_system_prompt(full=False)

        import urllib.request
        import urllib.error

        body = {
            'model': 'claude-haiku-3.5-20241022',  # Cheapest model
            'max_tokens': 1,
            'messages': [{'role': 'user', 'content': 'ping'}],
            'system': [
                {'type': 'text', 'text': sys_prompt,
                 'cache_control': {'type': 'ephemeral'}}
            ],
        }

        data = json.dumps(body).encode('utf-8')
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=data,
            headers={
                'x-api-key': api_key,
                'content-type': 'application/json',
                'anthropic-version': '2023-06-01',
                'anthropic-beta': 'prompt-caching-2024-07-31',
            },
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                usage = result.get('usage', {})
                cache_read = usage.get('cache_read_input_tokens', 0)
                cache_write = usage.get('cache_creation_input_tokens', 0)
                self._last_warm = time.time()
                self._warm_count += 1
                log.info(f"[CACHE] Warm #{self._warm_count}: "
                         f"cache_read={cache_read} cache_write={cache_write}")
        except urllib.error.HTTPError as e:
            log.warning(f"[CACHE] Warm HTTP {e.code}")
        except Exception as e:
            log.warning(f"[CACHE] Warm error: {e}")

    @property
    def stats(self) -> dict:
        return {
            'warm_count': self._warm_count,
            'last_warm': self._last_warm,
            'running': self._thread is not None and self._thread.is_alive(),
        }


# Singleton
cache_warmer = CacheWarmer()
