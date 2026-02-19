"""SalmAlm Message Queue — per-session serialization + debounce.

Prevents race conditions when users send multiple messages quickly.
- Per-session lock: no concurrent LLM calls for same session
- Debounce: 1s collect window merges rapid messages
- Queue cap: max 20 pending per session, oldest dropped with summary
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Coroutine, Dict, List, Optional

from .crypto import log

# ── Constants ──
DEBOUNCE_SECONDS = 1.0
MAX_QUEUE_PER_SESSION = 20


class _SessionQueue:
    """Per-session message queue with serialization lock."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._lock = asyncio.Lock()
        self._pending: List[dict] = []  # buffered messages during debounce
        self._debounce_task: Optional[asyncio.Task] = None
        self.last_active = time.time()

    async def enqueue_and_process(self, message: str, processor: Callable[..., Coroutine],
                                   **kwargs) -> str:
        """Enqueue a message, debounce, then process with serialization.

        processor: async callable(session_id, merged_message, **kwargs) -> str
        """
        self.last_active = time.time()

        # Queue cap check
        if len(self._pending) >= MAX_QUEUE_PER_SESSION:
            # Drop oldest messages, keep summary
            dropped = self._pending[:len(self._pending) - MAX_QUEUE_PER_SESSION + 1]
            self._pending = self._pending[len(self._pending) - MAX_QUEUE_PER_SESSION + 1:]
            dropped_summary = '; '.join(d['text'][:50] for d in dropped)
            log.warning(f"[QUEUE] Session {self.session_id}: dropped {len(dropped)} old messages")
            # Prepend summary as context
            self._pending.insert(0, {
                'text': f"[이전 메시지 요약 / Previous messages summary: {dropped_summary}]",
                'time': time.time()
            })

        # Add to pending
        self._pending.append({'text': message, 'time': time.time()})

        # Cancel existing debounce timer
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        # Create a future for this batch
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _debounce_and_run():
            await asyncio.sleep(DEBOUNCE_SECONDS)
            # Collect all pending messages
            async with self._lock:
                if not self._pending:
                    if not future.done():
                        future.set_result('')
                    return
                collected = self._pending[:]
                self._pending.clear()

                # Merge messages
                if len(collected) == 1:
                    merged = collected[0]['text']
                else:
                    merged = '\n'.join(m['text'] for m in collected)
                    log.info(f"[QUEUE] Session {self.session_id}: merged {len(collected)} messages")

                try:
                    result = await processor(self.session_id, merged, **kwargs)
                    if not future.done():
                        future.set_result(result)
                except Exception as e:
                    if not future.done():
                        future.set_exception(e)

        self._debounce_task = asyncio.ensure_future(_debounce_and_run())
        return await future


class MessageQueue:
    """Global message queue manager — one queue per session.

    Usage:
        queue = MessageQueue()
        result = await queue.process(session_id, message, processor_fn, **kwargs)
    """

    def __init__(self):
        self._queues: Dict[str, _SessionQueue] = {}
        self._lock = threading.Lock()
        self._cleanup_ts = 0.0

    def _get_queue(self, session_id: str) -> _SessionQueue:
        with self._lock:
            if session_id not in self._queues:
                self._queues[session_id] = _SessionQueue(session_id)
            return self._queues[session_id]

    async def process(self, session_id: str, message: str,
                      processor: Callable[..., Coroutine], **kwargs) -> str:
        """Process a message through the session queue.

        Handles debouncing and serialization automatically.
        processor: async fn(session_id, message, **kwargs) -> str
        """
        queue = self._get_queue(session_id)
        try:
            return await queue.enqueue_and_process(message, processor, **kwargs)
        except Exception as e:
            log.error(f"[QUEUE] Error processing {session_id}: {e}")
            raise

    def cleanup(self, max_idle: float = 3600):
        """Remove idle session queues (called periodically)."""
        now = time.time()
        if now - self._cleanup_ts < 600:
            return
        self._cleanup_ts = now
        with self._lock:
            stale = [sid for sid, q in self._queues.items()
                     if now - q.last_active > max_idle]
            for sid in stale:
                del self._queues[sid]
            if stale:
                log.info(f"[QUEUE] Cleaned up {len(stale)} idle session queues")

    @property
    def active_sessions(self) -> int:
        return len(self._queues)


# Singleton
message_queue = MessageQueue()
