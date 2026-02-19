"""Graceful Shutdown Manager — drain LLM streams, cancel tools, flush sessions, notify WS.

stdlib-only. Provides enhanced shutdown beyond the basic begin_shutdown/wait_for_active_requests
in engine.py.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

log = logging.getLogger('salmalm')


class ShutdownManager:
    """Coordinates graceful shutdown across all subsystems."""

    def __init__(self):
        self._shutting_down = False
        self._lock = threading.Lock()

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    async def execute(self, timeout: float = 30.0):
        """Run the full shutdown sequence.

        1. Signal engine to reject new requests
        2. Drain in-progress LLM streaming
        3. Cancel/wait for active tool executions
        4. Flush all session states to disk
        5. Notify WebSocket clients
        6. Close DB connections
        """
        with self._lock:
            if self._shutting_down:
                return
            self._shutting_down = True

        log.info("[SHUTDOWN] === Graceful shutdown sequence started ===")

        # Phase 1: Reject new requests
        log.info("[SHUTDOWN] Phase 1: Reject new requests")
        try:
            from salmalm.core.engine import begin_shutdown, wait_for_active_requests
            begin_shutdown()
        except Exception as e:
            log.warning(f"[SHUTDOWN] Engine begin_shutdown error: {e}")

        # Phase 2: Drain active LLM requests (streaming)
        log.info("[SHUTDOWN] Phase 2: Drain active LLM requests")
        try:
            from salmalm.core.engine import wait_for_active_requests
            drained = wait_for_active_requests(timeout=min(timeout, 15.0))
            if not drained:
                log.warning("[SHUTDOWN] Some LLM requests did not complete in time")
        except Exception as e:
            log.warning(f"[SHUTDOWN] LLM drain error: {e}")

        # Phase 3: Cancel active tool executions
        log.info("[SHUTDOWN] Phase 3: Cancel/wait for active tool executions")
        try:
            from salmalm.core.engine import _engine
            if hasattr(_engine, '_tool_executor'):
                _engine._tool_executor.shutdown(wait=True, cancel_futures=True)
                log.info("[SHUTDOWN] Tool executor shut down")
        except Exception as e:
            log.warning(f"[SHUTDOWN] Tool executor shutdown error: {e}")

        # Phase 4: Flush all session states to disk
        log.info("[SHUTDOWN] Phase 4: Flush session states to disk")
        try:
            from salmalm.core.core import _sessions, _session_lock
            with _session_lock:
                count = 0
                for sid, session in _sessions.items():
                    try:
                        session._persist()
                        count += 1
                    except Exception:
                        pass
                log.info(f"[SHUTDOWN] Flushed {count} sessions to disk")
        except Exception as e:
            log.warning(f"[SHUTDOWN] Session flush error: {e}")

        # Phase 5: Notify WebSocket clients
        log.info("[SHUTDOWN] Phase 5: Notify WebSocket clients")
        try:
            from salmalm.ws import ws_server
            await ws_server.shutdown()
        except Exception as e:
            log.warning(f"[SHUTDOWN] WebSocket shutdown error: {e}")

        # Phase 6: Close DB connections
        log.info("[SHUTDOWN] Phase 6: Close DB connections")
        try:
            from salmalm.core.core import close_all_db_connections
            close_all_db_connections()
        except Exception as e:
            log.warning(f"[SHUTDOWN] DB close error: {e}")

        log.info("[SHUTDOWN] === Graceful shutdown sequence complete ===")


# Singleton
shutdown_manager = ShutdownManager()
