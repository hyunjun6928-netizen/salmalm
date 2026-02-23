"""Audit logging subsystem."""

import atexit
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _audit_get_db():
    """Lazy import to avoid circular dependency."""
    from salmalm.core.core import _get_db

    return _get_db()


from salmalm.constants import KST  # noqa: E402
from datetime import datetime  # noqa: E402


def _ensure_audit_v2_table():
    """Create the v2 audit_log_v2 table with session_id and JSON detail."""
    conn = _audit_get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        session_id TEXT DEFAULT '',
        detail TEXT DEFAULT '{}'
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_v2_ts ON audit_log_v2(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_v2_type ON audit_log_v2(event_type)")
    conn.commit()


_audit_buffer: list = []
_audit_flush_timer = None
_AUDIT_BATCH_SIZE = 20  # flush after this many entries


def _schedule_audit_flush() -> None:
    """Schedule a delayed flush if not already pending."""
    global _audit_flush_timer
    if _audit_flush_timer is None:
        _audit_flush_timer = threading.Timer(_AUDIT_FLUSH_INTERVAL, _flush_audit_buffer)  # noqa: F405
        _audit_flush_timer.daemon = True
        _audit_flush_timer.start()


_audit_lock = threading.Lock()  # Audit log writes


def _init_audit_db():
    """Init audit db."""
    conn = _audit_get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL, event TEXT NOT NULL,
        detail TEXT, prev_hash TEXT, hash TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS usage_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL, model TEXT NOT NULL,
        input_tokens INTEGER, output_tokens INTEGER, cost REAL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS session_store (
        session_id TEXT PRIMARY KEY,
        messages TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    try:
        conn.execute("ALTER TABLE session_store ADD COLUMN parent_session_id TEXT DEFAULT NULL")
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    try:
        conn.execute("ALTER TABLE session_store ADD COLUMN branch_index INTEGER DEFAULT NULL")
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    try:
        conn.execute("ALTER TABLE session_store ADD COLUMN user_id INTEGER DEFAULT NULL")
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    conn.execute("""CREATE TABLE IF NOT EXISTS session_message_backup (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        messages_json TEXT NOT NULL,
        removed_at TEXT NOT NULL,
        reason TEXT DEFAULT 'rollback'
    )""")
    conn.commit()
    # Ensure buffered entries are flushed on exit (prevents crash data loss)
    atexit.register(_flush_audit_buffer)


_AUDIT_FLUSH_INTERVAL = 5.0  # seconds — max delay before flush


def _flush_audit_buffer() -> None:
    """Write buffered audit entries to SQLite in a single transaction."""
    global _audit_flush_timer
    with _audit_lock:
        if not _audit_buffer:
            _audit_flush_timer = None
            return
        entries = _audit_buffer[:]
        _audit_buffer.clear()
        _audit_flush_timer = None

    conn = _audit_get_db()
    # Get current chain head
    row = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev = row[0] if row else "0" * 64

    for ts, event, detail, session_id, json_detail in entries:
        # v1: hash-chain
        payload = f"{ts}|{event}|{detail}|{prev}"
        h = hashlib.sha256(payload.encode()).hexdigest()
        conn.execute(
            "INSERT INTO audit_log (ts, event, detail, prev_hash, hash) VALUES (?,?,?,?,?)",
            (ts, event, detail[:500], prev, h),
        )
        prev = h
        # v2: structured
        conn.execute(
            "INSERT INTO audit_log_v2 (timestamp, event_type, session_id, detail) VALUES (?,?,?,?)",
            (ts, event, session_id, json_detail),
        )
    conn.commit()


def audit_log(
    event: str,
    detail: str = "",
    session_id: str = "",
    detail_dict: Optional[dict] = None,
) -> None:
    """Write an audit event to the security log (v1 chain + v2 structured).

    Events are buffered and flushed in batches for performance.
    Flush triggers: batch size (20) or time interval (5s), whichever comes first.

    Args:
        event: event type string (tool_call, api_call, auth_success, etc.)
        detail: plain text detail (for v1 compatibility)
        session_id: associated session ID
        detail_dict: structured detail as dict (serialized to JSON for v2)
    """
    _ensure_audit_v2_table()
    ts = datetime.now(KST).isoformat()  # noqa: F405
    json_detail = json.dumps(detail_dict, ensure_ascii=False) if detail_dict else json.dumps({"text": detail[:500]})

    with _audit_lock:
        _audit_buffer.append((ts, event, detail, session_id, json_detail))
        if len(_audit_buffer) >= _AUDIT_BATCH_SIZE:
            pass  # will flush below
        else:
            _schedule_audit_flush()
            return

    # Flush immediately when batch is full
    _flush_audit_buffer()


def audit_checkpoint() -> Optional[str]:
    """Append current audit chain head hash to a checkpoint file.

    This provides tamper-evidence: if someone modifies the SQLite DB,
    the checkpoint file (append-only) will show a divergence.
    Returns the head hash or None on failure.
    """
    try:
        conn = _audit_get_db()
        row = conn.execute("SELECT hash, id FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        head_hash, head_id = row[0], row[1]
        checkpoint_file = AUDIT_DB.parent / "audit_checkpoint.log"  # noqa: F405
        ts = datetime.now(KST).isoformat()  # noqa: F405
        with open(checkpoint_file, "a") as f:
            f.write(f"{ts} id={head_id} hash={head_hash}\n")
        return head_hash  # type: ignore[no-any-return]
    except Exception as e:  # noqa: broad-except
        return None


def query_audit_log(limit: int = 50, event_type: Optional[str] = None, session_id: Optional[str] = None) -> list:
    """Query structured audit log entries.

    Returns list of dicts with id, timestamp, event_type, session_id, detail.
    """
    try:
        conn = _audit_get_db()
        _ensure_audit_v2_table()
        sql = "SELECT id, timestamp, event_type, session_id, detail FROM audit_log_v2"
        params: list = []
        conditions = []
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(min(limit, 500))
        rows = conn.execute(sql, params).fetchall()
        results = []
        for r in rows:
            try:
                detail = json.loads(r[4]) if r[4] else {}
            except (json.JSONDecodeError, TypeError):
                detail = {"text": r[4]}
            results.append(
                {
                    "id": r[0],
                    "timestamp": r[1],
                    "event_type": r[2],
                    "session_id": r[3],
                    "detail": detail,
                }
            )
        return results
    except Exception as e:
        log.warning(f"Audit query error: {e}")
        return []
