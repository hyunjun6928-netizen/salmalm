"""Periodic audit checkpoint automation.

Runs audit_checkpoint() on a configurable interval via a daemon thread timer.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

log = logging.getLogger(__name__)

_timer: Optional[threading.Timer] = None
_lock = threading.Lock()
_DEFAULT_INTERVAL_HOURS = 24


def _run_checkpoint(interval_seconds: float) -> None:
    """Execute audit_checkpoint and reschedule."""
    try:
        from salmalm.core import audit_checkpoint

        audit_checkpoint()
        log.info("Audit checkpoint completed")
    except Exception as exc:
        log.warning("Audit checkpoint failed: %s", exc)
    # Reschedule
    _schedule(interval_seconds)


def _schedule(interval_seconds: float) -> None:
    """Schedule."""
    global _timer
    with _lock:
        _timer = threading.Timer(interval_seconds, _run_checkpoint, args=(interval_seconds,))
        _timer.daemon = True
        _timer.start()


def start_audit_cron(interval_hours: float = _DEFAULT_INTERVAL_HOURS) -> None:
    """Start periodic audit checkpoint. Safe to call multiple times (idempotent)."""
    with _lock:
        if _timer is not None:
            return  # Already running
    interval_seconds = interval_hours * 3600
    _schedule(interval_seconds)
    log.info("Audit cron started (every %.1fh)", interval_hours)


def stop_audit_cron() -> None:
    """Cancel the audit checkpoint timer."""
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
            log.info("Audit cron stopped")
