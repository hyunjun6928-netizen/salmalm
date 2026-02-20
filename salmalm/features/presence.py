"""SalmAlm Presence System — Track connected clients."""
from __future__ import annotations

import time
import threading
from typing import Any, Dict, List, Optional

from salmalm import log

DEFAULT_TTL = 300  # 5 minutes
MAX_ENTRIES = 200

# State thresholds (seconds since last activity)
ACTIVE_THRESHOLD = 60
IDLE_THRESHOLD = 180


class PresenceEntry:
    __slots__ = ('instance_id', 'host', 'ip', 'mode', 'last_activity',
                 'connected_at', 'user_agent', 'extra')

    def __init__(self, instance_id: str, *, host: str = '', ip: str = '',
                 mode: str = 'web', user_agent: str = '', extra: Optional[Dict] = None):
        self.instance_id = instance_id
        self.host = host
        self.ip = ip
        self.mode = mode
        self.user_agent = user_agent
        self.last_activity = time.time()
        self.connected_at = time.time()
        self.extra = extra or {}

    @property
    def state(self) -> str:
        elapsed = time.time() - self.last_activity
        if elapsed < ACTIVE_THRESHOLD:
            return 'active'
        elif elapsed < IDLE_THRESHOLD:
            return 'idle'
        return 'stale'

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.last_activity) > DEFAULT_TTL

    def touch(self, **kwargs) -> None:
        """Update last activity and optional fields."""
        self.last_activity = time.time()
        for k, v in kwargs.items():
            if hasattr(self, k) and k != 'instance_id':
                setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'instanceId': self.instance_id,
            'host': self.host,
            'ip': self.ip,
            'mode': self.mode,
            'state': self.state,
            'lastActivity': self.last_activity,
            'connectedAt': self.connected_at,
            'userAgent': self.user_agent,
        }


class PresenceManager:
    """Track connected client instances with TTL-based expiry."""

    def __init__(self, ttl: int = DEFAULT_TTL, max_entries: int = MAX_ENTRIES):
        self._entries: Dict[str, PresenceEntry] = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._max_entries = max_entries

    def register(self, instance_id: str, **kwargs) -> PresenceEntry:
        """Register or update a client instance."""
        with self._lock:
            self._evict_expired()
            if instance_id in self._entries:
                self._entries[instance_id].touch(**kwargs)
                return self._entries[instance_id]
            # Enforce max entries
            if len(self._entries) >= self._max_entries:
                self._evict_oldest()
            entry = PresenceEntry(instance_id, **kwargs)
            self._entries[instance_id] = entry
            log.info(f'Presence: {instance_id} registered (mode={entry.mode})')
            return entry

    def heartbeat(self, instance_id: str, **kwargs) -> Optional[PresenceEntry]:
        """Update last activity for a client."""
        with self._lock:
            entry = self._entries.get(instance_id)
            if entry:
                entry.touch(**kwargs)
                return entry
        return None

    def unregister(self, instance_id: str) -> bool:
        with self._lock:
            if instance_id in self._entries:
                del self._entries[instance_id]
                return True
        return False

    def get(self, instance_id: str) -> Optional[PresenceEntry]:
        entry = self._entries.get(instance_id)
        if entry and (time.time() - entry.last_activity) <= self._ttl:
            return entry
        return None

    def list_all(self, include_expired: bool = False) -> List[Dict[str, Any]]:
        """List all presence entries."""
        with self._lock:
            if not include_expired:
                self._evict_expired()
            return [e.to_dict() for e in self._entries.values()]

    def count(self) -> int:
        with self._lock:
            self._evict_expired()
            return len(self._entries)

    def count_by_state(self) -> Dict[str, int]:
        with self._lock:
            self._evict_expired()
            counts = {'active': 0, 'idle': 0, 'stale': 0}
            for e in self._entries.values():
                counts[e.state] = counts.get(e.state, 0) + 1
            return counts

    def _evict_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = time.time()
        expired = [k for k, v in self._entries.items()
                   if (now - v.last_activity) > self._ttl]
        for k in expired:
            del self._entries[k]
        return len(expired)

    def _evict_oldest(self) -> None:
        """Remove the oldest entry to make room."""
        if not self._entries:
            return
        oldest_id = min(self._entries, key=lambda k: self._entries[k].last_activity)
        del self._entries[oldest_id]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# Singleton
presence_manager = PresenceManager()
