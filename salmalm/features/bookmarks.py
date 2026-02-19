"""Message Bookmarks (메시지 북마크) — LobeChat style."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from salmalm.constants import KST
from salmalm.crypto import log


class BookmarkManager:
    """Manage message bookmarks across sessions."""

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        try:
            from salmalm.core import _get_db
            conn = _get_db()
            conn.execute('''CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                role TEXT DEFAULT 'assistant',
                content_preview TEXT,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(session_id, message_index)
            )''')
            conn.commit()
        except Exception as e:
            log.warning(f"Bookmarks table init: {e}")

    def add(self, session_id: str, message_index: int,
            content_preview: str = '', note: str = '', role: str = 'assistant') -> bool:
        try:
            from salmalm.core import _get_db
            conn = _get_db()
            now = datetime.now(KST).isoformat()
            conn.execute(
                'INSERT OR REPLACE INTO bookmarks '
                '(session_id, message_index, role, content_preview, note, created_at) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (session_id, message_index, role, content_preview[:200], note, now))
            conn.commit()
            return True
        except Exception:
            return False

    def remove(self, session_id: str, message_index: int) -> bool:
        try:
            from salmalm.core import _get_db
            conn = _get_db()
            conn.execute('DELETE FROM bookmarks WHERE session_id=? AND message_index=?',
                         (session_id, message_index))
            conn.commit()
            return True
        except Exception:
            return False

    def list_all(self, limit: int = 50) -> List[Dict]:
        try:
            from salmalm.core import _get_db
            conn = _get_db()
            rows = conn.execute(
                'SELECT id, session_id, message_index, role, content_preview, note, created_at '
                'FROM bookmarks ORDER BY created_at DESC LIMIT ?',
                (limit,)).fetchall()
            return [{'id': r[0], 'session_id': r[1], 'message_index': r[2],
                     'role': r[3], 'preview': r[4], 'note': r[5], 'created_at': r[6]}
                    for r in rows]
        except Exception:
            return []

    def list_session(self, session_id: str) -> List[Dict]:
        try:
            from salmalm.core import _get_db
            conn = _get_db()
            rows = conn.execute(
                'SELECT id, message_index, role, content_preview, note, created_at '
                'FROM bookmarks WHERE session_id=? ORDER BY message_index',
                (session_id,)).fetchall()
            return [{'id': r[0], 'message_index': r[1], 'role': r[2],
                     'preview': r[3], 'note': r[4], 'created_at': r[5]}
                    for r in rows]
        except Exception:
            return []

    def is_bookmarked(self, session_id: str, message_index: int) -> bool:
        try:
            from salmalm.core import _get_db
            conn = _get_db()
            row = conn.execute(
                'SELECT 1 FROM bookmarks WHERE session_id=? AND message_index=?',
                (session_id, message_index)).fetchone()
            return row is not None
        except Exception:
            return False


bookmark_manager = BookmarkManager()
