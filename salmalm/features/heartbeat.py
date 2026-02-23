"""SalmAlm Heartbeat — Cache warming for Anthropic prompt caching.

Periodically sends a minimal request to keep the prompt cache warm.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Optional

from salmalm.security.crypto import log
from salmalm.constants import DATA_DIR

_CACHE_CONFIG_FILE = DATA_DIR / "cache.json"

_DEFAULT_CONFIG = {
    "promptCaching": True,
    "cacheTtlMinutes": 60,
    "warmingEnabled": True,
    "warmingIntervalMinutes": 55,
}


def load_cache_config() -> dict:
    """Load cache config from ~/.salmalm/cache.json."""
    try:
        if _CACHE_CONFIG_FILE.exists():
            cfg = json.loads(_CACHE_CONFIG_FILE.read_text(encoding="utf-8"))
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
        _CACHE_CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
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
        if not config.get("warmingEnabled", False):
            log.info("[CACHE] Cache warming disabled")
            return
        if not config.get("promptCaching", True):
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._warming_loop, daemon=True, name="cache-warmer")
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
            interval_sec = config.get("warmingIntervalMinutes", 55) * 60

            # Wait for interval
            if self._stop_event.wait(timeout=interval_sec):
                break  # Stop requested

            if not config.get("warmingEnabled", False):
                continue

            try:
                self._warm_cache()
            except Exception as e:
                log.warning(f"[CACHE] Warming failed: {e}")

    def _warm_cache(self):
        """Send a minimal request to warm the prompt cache.

        Uses a tiny max_tokens to minimize cost while keeping cache alive.
        """
        from salmalm.core.prompt import build_system_prompt
        from salmalm.security.crypto import vault

        api_key = vault.get("anthropic_api_key")
        if not api_key:
            return

        sys_prompt = build_system_prompt(full=False)

        import urllib.request
        import urllib.error

        body = {
            "model": "claude-haiku-4-5-20251001",  # Cheapest model
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
            "system": [{"type": "text", "text": sys_prompt, "cache_control": {"type": "ephemeral"}}],
        }

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=data,
            headers={
                "x-api-key": api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "prompt-caching-2024-07-31",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                usage = result.get("usage", {})
                cache_read = usage.get("cache_read_input_tokens", 0)
                cache_write = usage.get("cache_creation_input_tokens", 0)
                self._last_warm = time.time()
                self._warm_count += 1
                log.info(f"[CACHE] Warm #{self._warm_count}: cache_read={cache_read} cache_write={cache_write}")
        except urllib.error.HTTPError as e:
            log.warning(f"[CACHE] Warm HTTP {e.code}")
        except Exception as e:
            log.warning(f"[CACHE] Warm error: {e}")

    @property
    def stats(self) -> dict:
        return {
            "warm_count": self._warm_count,
            "last_warm": self._last_warm,
            "running": self._thread is not None and self._thread.is_alive(),
        }


class HeartbeatManager:
    """Heartbeat manager with active hours support.

    하트비트 관리자 — 활성 시간대 지원.
    """

    _CONFIG_FILE = DATA_DIR / "heartbeat.json"
    _DEFAULT_CONFIG = {
        "enabled": True,
        "interval_minutes": 30,
        "active_hours": {"start": "08:00", "end": "24:00"},
        "timezone": "Asia/Seoul",
    }

    def __init__(self):
        self._config = self._load_config()

    def _load_config(self) -> dict:
        cfg = dict(self._DEFAULT_CONFIG)
        try:
            if self._CONFIG_FILE.exists():
                data = json.loads(self._CONFIG_FILE.read_text(encoding="utf-8"))
                cfg.update(data)
        except Exception:
            pass
        return cfg

    def reload(self):
        self._config = self._load_config()

    @property
    def config(self) -> dict:
        return dict(self._config)

    def is_active_hours(self) -> bool:
        """Check if current time is within active hours."""
        from datetime import datetime, timezone, timedelta

        tz_name = self._config.get("timezone", "Asia/Seoul")
        # Simple timezone mapping for common cases
        tz_offsets = {
            "Asia/Seoul": 9,
            "Asia/Tokyo": 9,
            "UTC": 0,
            "US/Eastern": -5,
            "US/Pacific": -8,
            "Europe/London": 0,
        }
        offset_hours = tz_offsets.get(tz_name, 9)
        tz = timezone(timedelta(hours=offset_hours))
        now = datetime.now(tz)

        active = self._config.get("active_hours", {})
        start_str = active.get("start", "08:00")
        end_str = active.get("end", "24:00")

        try:
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
        except (ValueError, AttributeError):
            return True  # Default to active if config is invalid

        current_minutes = now.hour * 60 + now.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m

        if end_minutes <= start_minutes:
            # Wraps midnight
            return current_minutes >= start_minutes or current_minutes < end_minutes
        return start_minutes <= current_minutes < end_minutes

    def should_heartbeat(self) -> bool:
        """Check if heartbeat should run now."""
        if not self._config.get("enabled", True):
            return False
        if not self.is_active_hours():
            log.info("[HEARTBEAT] Outside active hours, skipping")
            return False
        return True


# Singletons
cache_warmer = CacheWarmer()
heartbeat_manager = HeartbeatManager()
