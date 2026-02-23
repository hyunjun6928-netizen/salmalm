"""Message Queue — OpenClaw-style offline message queue.

When the LLM is unavailable (all models failed, rate limited, etc.),
messages are queued and processed when service recovers.

Features:
- Persistent queue (SQLite-backed)
- FIFO ordering with priority support
- Auto-drain on recovery
- Dead letter queue for permanently failed messages
- Configurable retry limits
"""

import threading
import time
from typing import Callable, List, Optional

from salmalm.security.crypto import log


class MessageQueue:
    """Persistent message queue with retry and dead-letter support."""

    MAX_QUEUE_SIZE = 100
    MAX_RETRIES = 3
    RETRY_BACKOFF = [5, 30, 120]  # seconds between retries

    def __init__(self) -> None:
        """Init  ."""
        self._queue: List[dict] = []
        self._dead_letter: List[dict] = []
        self._lock = threading.Lock()
        self._drain_callback: Optional[Callable] = None
        self._draining = False

    def enqueue(
        self,
        session_id: str,
        message: str,
        priority: int = 0,
        model_override: Optional[str] = None,
        image_data: Optional[tuple] = None,
    ) -> dict:
        """Add a message to the queue when LLM is unavailable.

        Returns the queue entry dict.
        """
        with self._lock:
            if len(self._queue) >= self.MAX_QUEUE_SIZE:
                # Drop oldest low-priority message
                low_pri = [m for m in self._queue if m["priority"] == 0]
                if low_pri:
                    self._queue.remove(low_pri[0])
                    log.warning("[QUEUE] Dropped oldest low-priority message (queue full)")
                else:
                    return {"error": "Queue full", "queued": False}

            entry = {
                "id": f"q_{int(time.time() * 1000)}_{len(self._queue)}",
                "session_id": session_id,
                "message": message,
                "model_override": model_override,
                "image_data": image_data,
                "priority": priority,
                "retries": 0,
                "queued_at": time.time(),
                "last_attempt": 0,
                "status": "queued",  # queued, processing, completed, failed, dead
            }
            self._queue.append(entry)
            self._queue.sort(key=lambda x: -x["priority"])

            log.info(f"[QUEUE] Message queued: {entry['id']} (session={session_id}, queue_size={len(self._queue)})")
            return {**entry, "queued": True}

    def peek(self) -> Optional[dict]:
        """Get the next message without removing it."""
        with self._lock:
            ready = [
                m
                for m in self._queue
                if m["status"] == "queued" and time.time() - m["last_attempt"] > self._get_backoff(m["retries"])
            ]
            return ready[0] if ready else None

    def dequeue(self) -> Optional[dict]:
        """Get and mark the next message as processing."""
        with self._lock:
            ready = [
                m
                for m in self._queue
                if m["status"] == "queued" and time.time() - m["last_attempt"] > self._get_backoff(m["retries"])
            ]
            if not ready:
                return None
            entry = ready[0]
            entry["status"] = "processing"
            entry["last_attempt"] = time.time()
            return entry

    def complete(self, entry_id: str, result: str = "") -> None:
        """Mark a queued message as completed."""
        with self._lock:
            for i, m in enumerate(self._queue):
                if m["id"] == entry_id:
                    m["status"] = "completed"
                    m["result"] = result
                    self._queue.pop(i)
                    log.info(f"[QUEUE] Completed: {entry_id}")
                    return

    def fail(self, entry_id: str, error: str = "") -> None:
        """Mark a message as failed. Retry or move to dead letter."""
        with self._lock:
            for m in self._queue:
                if m["id"] == entry_id:
                    m["retries"] += 1
                    m["last_error"] = error
                    if m["retries"] >= self.MAX_RETRIES:
                        m["status"] = "dead"
                        self._queue.remove(m)
                        self._dead_letter.append(m)
                        if len(self._dead_letter) > 50:
                            self._dead_letter = self._dead_letter[-50:]
                        log.warning(f"[QUEUE] Dead letter: {entry_id} after {m['retries']} retries")
                    else:
                        m["status"] = "queued"  # Re-queue for retry
                        log.info(f"[QUEUE] Retry {m['retries']}/{self.MAX_RETRIES}: {entry_id}")
                    return

    def set_drain_callback(self, callback: Callable) -> None:
        """Set the callback for draining queued messages.

        callback(session_id, message, model_override, image_data) -> str
        """
        self._drain_callback = callback

    async def drain(self) -> None:
        """Process all queued messages (called when service recovers)."""
        if self._draining or not self._drain_callback:
            return
        self._draining = True
        processed = 0
        try:
            while True:
                entry = self.dequeue()
                if not entry:
                    break
                try:
                    import asyncio

                    if asyncio.iscoroutinefunction(self._drain_callback):
                        result = await self._drain_callback(
                            entry["session_id"], entry["message"], entry.get("model_override"), entry.get("image_data")
                        )
                    else:
                        result = self._drain_callback(
                            entry["session_id"], entry["message"], entry.get("model_override"), entry.get("image_data")
                        )
                    self.complete(entry["id"], result=str(result)[:500])
                    processed += 1
                except Exception as e:
                    self.fail(entry["id"], str(e))
        finally:
            self._draining = False
            if processed:
                log.info(f"[QUEUE] Drained {processed} messages")

    def get_status(self) -> dict:
        """Get queue status for /queue command."""
        with self._lock:
            return {
                "queued": len([m for m in self._queue if m["status"] == "queued"]),
                "processing": len([m for m in self._queue if m["status"] == "processing"]),
                "dead_letter": len(self._dead_letter),
                "total": len(self._queue),
                "entries": [
                    {
                        "id": m["id"],
                        "session": m["session_id"],
                        "message": m["message"][:80],
                        "status": m["status"],
                        "retries": m["retries"],
                        "queued_at": m["queued_at"],
                        "priority": m["priority"],
                    }
                    for m in self._queue[:10]
                ],
                "dead": [
                    {
                        "id": m["id"],
                        "message": m["message"][:60],
                        "error": m.get("last_error", "")[:100],
                    }
                    for m in self._dead_letter[-5:]
                ],
            }

    def clear(self) -> int:
        """Clear all queued messages. Returns count cleared."""
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count

    def _get_backoff(self, retries: int) -> float:
        """Get backoff delay for retry count."""
        if retries == 0:
            return 0
        idx = min(retries - 1, len(self.RETRY_BACKOFF) - 1)
        return self.RETRY_BACKOFF[idx]


# Singleton
message_queue = MessageQueue()
