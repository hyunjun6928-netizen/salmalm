"""Abort Generation (생성 중지) — OpenClaw/LibreChat style.

Features:
- Per-session abort flags
- Partial response preservation (streaming tokens accumulated)
- Streaming token accumulator for abort recovery
- Thread-safe with fine-grained locking
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional

from salmalm.security.crypto import log


class AbortController:
    """Per-session abort flag + streaming partial response preservation.

    When streaming is active, tokens are accumulated via `accumulate_token()`.
    On abort, the accumulated partial response is preserved so the user
    sees what was generated before the stop.
    """

    def __init__(self) -> None:
        """Init  ."""
        self._flags: Dict[str, bool] = {}
        self._lock = threading.Lock()
        self._partial_responses: Dict[str, str] = {}
        self._accumulators: Dict[str, list] = {}
        self._abort_times: Dict[str, float] = {}

    def set_abort(self, session_id: str) -> None:
        """Set abort."""
        with self._lock:
            self._flags[session_id] = True
            self._abort_times[session_id] = time.time()
            # Freeze current accumulated tokens as partial response
            if session_id in self._accumulators:
                self._partial_responses[session_id] = "".join(self._accumulators[session_id])
                del self._accumulators[session_id]
            log.info(f"[ABORT] Generation abort requested: session={session_id}")

    def is_aborted(self, session_id: str) -> bool:
        """Is aborted."""
        with self._lock:
            return self._flags.get(session_id, False)

    def clear(self, session_id: str) -> None:
        """Clear."""
        with self._lock:
            self._flags.pop(session_id, None)
            self._accumulators.pop(session_id, None)
            self._abort_times.pop(session_id, None)

    def save_partial(self, session_id: str, text: str) -> None:
        """Save partial."""
        with self._lock:
            self._partial_responses[session_id] = text

    def get_partial(self, session_id: str) -> Optional[str]:
        """Get partial."""
        with self._lock:
            return self._partial_responses.pop(session_id, None)

    def accumulate_token(self, session_id: str, token: str) -> None:
        """Accumulate streaming tokens for abort recovery.

        Called from streaming callbacks. Thread-safe.
        If already aborted, does nothing (tokens are frozen).
        """
        with self._lock:
            if self._flags.get(session_id):
                return  # Already aborted, don't accumulate
            if session_id not in self._accumulators:
                self._accumulators[session_id] = []
            self._accumulators[session_id].append(token)

    def start_streaming(self, session_id: str) -> None:
        """Mark the start of a streaming response (reset accumulator)."""
        with self._lock:
            self._accumulators[session_id] = []

    def get_accumulated(self, session_id: str) -> str:
        """Get current accumulated tokens without clearing."""
        with self._lock:
            parts = self._accumulators.get(session_id, [])
            return "".join(parts)


abort_controller = AbortController()
