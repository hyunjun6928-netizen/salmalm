"""Message Queue — 5 queue modes for message handling during AI processing.

Modes:
  collect (default) — Queue messages while AI is busy, process all when done
  steer             — Latest message replaces the pending request
  followup          — Queue messages as follow-up context for next turn
  steer-backlog     — Like steer but keeps history of skipped messages
  interrupt         — Cancel current request and process new message immediately
"""
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class QueueMode(Enum):
    COLLECT = 'collect'
    STEER = 'steer'
    FOLLOWUP = 'followup'
    STEER_BACKLOG = 'steer-backlog'
    INTERRUPT = 'interrupt'


@dataclass
class QueuedMessage:
    text: str
    timestamp: float = field(default_factory=time.time)
    session_id: str = ''
    user_id: str = ''


class MessageQueue:
    """Per-session message queue with configurable modes."""

    def __init__(self, mode: str = 'collect', max_size: int = 50):
        self._mode = QueueMode(mode) if isinstance(mode, str) else mode
        self._queue: deque[QueuedMessage] = deque(maxlen=max_size)
        self._backlog: list[QueuedMessage] = []
        self._lock = threading.Lock()
        self._processing = False
        self._cancel_flag = threading.Event()

    @property
    def mode(self) -> str:
        return self._mode.value

    @mode.setter
    def mode(self, value: str):
        self._mode = QueueMode(value)
        logger.info("Queue mode changed to: %s", value)

    @property
    def is_processing(self) -> bool:
        return self._processing

    @is_processing.setter
    def is_processing(self, value: bool):
        self._processing = value

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_flag.is_set()

    def enqueue(self, text: str, session_id: str = '', user_id: str = '') -> dict:
        """Add message to queue. Returns action dict for the caller."""
        msg = QueuedMessage(text=text, session_id=session_id, user_id=user_id)

        with self._lock:
            if not self._processing:
                # Not busy — process immediately
                return {'action': 'process', 'message': msg}

            if self._mode == QueueMode.COLLECT:
                self._queue.append(msg)
                return {'action': 'queued', 'position': len(self._queue)}

            elif self._mode == QueueMode.STEER:
                self._queue.clear()
                self._queue.append(msg)
                return {'action': 'steered', 'message': msg}

            elif self._mode == QueueMode.FOLLOWUP:
                self._queue.append(msg)
                return {'action': 'followup', 'position': len(self._queue)}

            elif self._mode == QueueMode.STEER_BACKLOG:
                # Move current queue to backlog, replace with new
                self._backlog.extend(self._queue)
                self._queue.clear()
                self._queue.append(msg)
                return {'action': 'steered', 'backlog_size': len(self._backlog)}

            elif self._mode == QueueMode.INTERRUPT:
                self._cancel_flag.set()
                self._queue.clear()
                self._queue.append(msg)
                return {'action': 'interrupt', 'message': msg}

        return {'action': 'queued'}

    def drain(self) -> list[QueuedMessage]:
        """Get all queued messages and clear the queue."""
        with self._lock:
            msgs = list(self._queue)
            self._queue.clear()
            self._cancel_flag.clear()
            return msgs

    def drain_as_context(self) -> str:
        """Drain queue and format as follow-up context string."""
        msgs = self.drain()
        if not msgs:
            return ''
        parts = []
        for m in msgs:
            parts.append(f"[follow-up] {m.text}")
        return '\n'.join(parts)

    def get_backlog(self) -> list[QueuedMessage]:
        """Get and clear the backlog (steer-backlog mode)."""
        with self._lock:
            bl = self._backlog.copy()
            self._backlog.clear()
            return bl

    @property
    def pending_count(self) -> int:
        return len(self._queue)

    def clear(self):
        with self._lock:
            self._queue.clear()
            self._backlog.clear()
            self._cancel_flag.clear()

    def status(self) -> dict:
        return {
            'mode': self._mode.value,
            'pending': len(self._queue),
            'backlog': len(self._backlog),
            'processing': self._processing,
        }


# Global queue registry: session_id → MessageQueue
_queues: dict[str, MessageQueue] = {}
_queues_lock = threading.Lock()


def get_queue(session_id: str = 'default', mode: str = 'collect') -> MessageQueue:
    """Get or create a message queue for a session."""
    with _queues_lock:
        if session_id not in _queues:
            _queues[session_id] = MessageQueue(mode=mode)
        return _queues[session_id]


def set_queue_mode(session_id: str, mode: str) -> str:
    """Set queue mode for a session. Returns confirmation message."""
    q = get_queue(session_id)
    old = q.mode
    q.mode = mode
    return f"Queue mode: {old} → {mode}"


def queue_status(session_id: str = 'default') -> dict:
    """Get queue status for a session."""
    q = get_queue(session_id)
    return q.status()
