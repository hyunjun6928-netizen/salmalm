"""Abort Generation (생성 중지) — LibreChat style."""
from __future__ import annotations

import threading
from typing import Dict, Optional

from salmalm.crypto import log


class AbortController:
    """Per-session abort flag for stopping LLM generation."""

    def __init__(self):
        self._flags: Dict[str, bool] = {}
        self._lock = threading.Lock()
        self._partial_responses: Dict[str, str] = {}

    def set_abort(self, session_id: str):
        with self._lock:
            self._flags[session_id] = True
            log.info(f"[ABORT] Generation abort requested: session={session_id}")

    def is_aborted(self, session_id: str) -> bool:
        with self._lock:
            return self._flags.get(session_id, False)

    def clear(self, session_id: str):
        with self._lock:
            self._flags.pop(session_id, None)

    def save_partial(self, session_id: str, text: str):
        with self._lock:
            self._partial_responses[session_id] = text

    def get_partial(self, session_id: str) -> Optional[str]:
        with self._lock:
            return self._partial_responses.pop(session_id, None)


abort_controller = AbortController()
