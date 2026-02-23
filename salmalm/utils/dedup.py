"""Message deduplication and channel-aware debouncing.

메시지 중복 제거 및 채널별 디바운싱.
"""

from __future__ import annotations

import time
import threading
from typing import Dict


class MessageDeduplicator:
    """Deduplicates inbound messages using a TTL cache.

    Cache key: {channel}:{account}:{peer}:{message_id}
    TTL: 60 seconds (default).
    """

    def __init__(self, ttl: float = 60.0) -> None:
        """Init  ."""
        self._cache: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._last_cleanup = time.time()

    def is_duplicate(self, channel: str, account: str, peer: str, message_id: str) -> bool:
        """Return True if this message was already seen within the TTL window."""
        key = f"{channel}:{account}:{peer}:{message_id}"
        now = time.time()
        with self._lock:
            self._maybe_cleanup(now)
            if key in self._cache:
                return True
            self._cache[key] = now
            return False

    def _maybe_cleanup(self, now: float) -> None:
        """Remove expired entries (called under lock)."""
        if now - self._last_cleanup < 10.0:
            return
        self._last_cleanup = now
        expired = [k for k, ts in self._cache.items() if now - ts > self._ttl]
        for k in expired:
            del self._cache[k]

    @property
    def size(self) -> int:
        """Size."""
        with self._lock:
            return len(self._cache)

    def clear(self) -> None:
        """Clear."""
        with self._lock:
            self._cache.clear()


# ── Channel-aware debounce times (ms) ──

CHANNEL_DEBOUNCE_MS: Dict[str, int] = {
    "telegram": 2000,
    "discord": 1500,
    "slack": 1500,
    "whatsapp": 5000,
    "web": 1000,
}

DEFAULT_DEBOUNCE_MS = 1000


def get_debounce_ms(channel: str) -> int:
    """Get debounce time in ms for a channel."""
    return CHANNEL_DEBOUNCE_MS.get(channel, DEFAULT_DEBOUNCE_MS)


def should_skip_debounce(message: str, has_media: bool = False) -> bool:
    """Return True if this message should skip debouncing.

    Media/attachment messages and command messages flush immediately.
    """
    if has_media:
        return True
    stripped = message.strip()
    if stripped.startswith("/"):
        return True
    return False


# Singleton
message_deduplicator = MessageDeduplicator()
