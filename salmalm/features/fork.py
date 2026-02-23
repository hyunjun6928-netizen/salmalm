"""Conversation Fork / Regenerate (대화 포크) — LibreChat style."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from salmalm.constants import KST
from salmalm.security.crypto import log


class ConversationFork:
    """Manage alternative responses at the same message index."""

    def __init__(self) -> None:
        """Init  ."""
        self._ensure_table()

    def _ensure_table(self):
        """Ensure table."""
        try:
            from salmalm.core import _get_db

            conn = _get_db()
            conn.execute("""CREATE TABLE IF NOT EXISTS message_alternatives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                model TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 0
            )""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_alt_session_msg
                ON message_alternatives(session_id, message_index)""")
            conn.commit()
        except Exception as e:
            log.warning(f"Alternatives table init: {e}")

    def save_alternative(self, session_id: str, message_index: int, content: str, model: str = "", active: bool = True) -> None:
        """Save alternative."""
        try:
            from salmalm.core import _get_db

            conn = _get_db()
            now = datetime.now(KST).isoformat()
            if active:
                conn.execute(
                    "UPDATE message_alternatives SET is_active=0 WHERE session_id=? AND message_index=?",
                    (session_id, message_index),
                )
            conn.execute(
                "INSERT INTO message_alternatives "
                "(session_id, message_index, content, model, created_at, is_active) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, message_index, content, model, now, 1 if active else 0),
            )
            conn.commit()
        except Exception as e:
            log.warning(f"Save alternative error: {e}")

    def get_alternatives(self, session_id: str, message_index: int) -> List[Dict]:
        """Get alternatives."""
        try:
            from salmalm.core import _get_db

            conn = _get_db()
            rows = conn.execute(
                "SELECT id, content, model, created_at, is_active "
                "FROM message_alternatives "
                "WHERE session_id=? AND message_index=? ORDER BY id",
                (session_id, message_index),
            ).fetchall()
            return [
                {"id": r[0], "content": r[1], "model": r[2], "created_at": r[3], "is_active": bool(r[4])} for r in rows
            ]
        except Exception:
            return []

    def switch_alternative(self, session_id: str, message_index: int, alt_id: int) -> Optional[str]:
        """Switch alternative."""
        try:
            from salmalm.core import _get_db

            conn = _get_db()
            conn.execute(
                "UPDATE message_alternatives SET is_active=0 WHERE session_id=? AND message_index=?",
                (session_id, message_index),
            )
            conn.execute("UPDATE message_alternatives SET is_active=1 WHERE id=?", (alt_id,))
            conn.commit()
            row = conn.execute("SELECT content FROM message_alternatives WHERE id=?", (alt_id,)).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    async def regenerate(self, session_id: str, message_index: int) -> Optional[str]:
        """Regenerate."""
        from salmalm.core import get_session

        session = get_session(session_id)
        msgs = session.messages

        ua_indices = [(i, m) for i, m in enumerate(msgs) if m.get("role") in ("user", "assistant")]

        if message_index < 0 or message_index >= len(ua_indices):
            return None

        real_idx, target_msg = ua_indices[message_index]
        if target_msg.get("role") != "assistant":
            return None

        current_content = target_msg.get("content", "")
        if isinstance(current_content, list):
            current_content = " ".join(
                b.get("text", "") for b in current_content if isinstance(b, dict) and b.get("type") == "text"
            )
        self.save_alternative(session_id, message_index, current_content, active=False)

        user_msg = None
        for i in range(real_idx - 1, -1, -1):
            if msgs[i].get("role") == "user":
                content = msgs[i].get("content", "")
                if isinstance(content, str):
                    user_msg = content
                elif isinstance(content, list):
                    user_msg = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
                    )
                break

        if not user_msg:
            return None

        session.messages = msgs[:real_idx]

        from salmalm.core.engine import process_message

        response = await process_message(session_id, user_msg)

        self.save_alternative(session_id, message_index, response, active=True)

        return response


conversation_fork = ConversationFork()
