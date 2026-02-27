"""WAL-mode SQLite connection helpers."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

_lock = threading.Lock()
_connections: dict = {}


def get_connection(db_path: str | Path, *, timeout: float = 30.0) -> sqlite3.Connection:
    """Get a WAL-mode SQLite connection."""
    path = str(db_path)
    conn = sqlite3.connect(path, timeout=timeout, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_conn(db_path: str | Path, *, timeout: float = 30.0):
    """Context manager for SQLite connection with WAL mode."""
    conn = get_connection(db_path, timeout=timeout)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
