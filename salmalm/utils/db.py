"""SQLite common patterns — DB 초기화, 연결 래퍼."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional, Union

log = logging.getLogger(__name__)


def connect(
    path: Union[str, Path],
    *,
    wal: bool = True,
    row_factory: bool = False,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open a SQLite connection with common defaults.

    Parameters
    ----------
    path : path to the database file.
    wal : enable WAL journal mode (default True).
    row_factory : set ``sqlite3.Row`` as row factory.
    check_same_thread : passed to ``sqlite3.connect``.
    """
    conn = sqlite3.connect(str(path), check_same_thread=check_same_thread)
    conn.execute("PRAGMA busy_timeout=5000")  # 5s wait on lock instead of immediate failure
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn


def ensure_table(conn: sqlite3.Connection, ddl: str) -> None:
    """Execute a CREATE TABLE IF NOT EXISTS statement."""
    conn.execute(ddl)
    conn.commit()


def query_all(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list:
    """Fetch all rows for a query."""
    return conn.execute(sql, params).fetchall()


def query_one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> Optional[tuple]:
    """Fetch a single row."""
    return conn.execute(sql, params).fetchone()
