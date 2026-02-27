"""Session Groups (대화 주제 그룹) — LobeChat style."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from salmalm.constants import KST
from salmalm.security.crypto import log


class SessionGroupManager:
    """Manage session groups/folders for organizing conversations."""

    def __init__(self) -> None:
        """Init  ."""
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure tables."""
        try:
            from salmalm.core import _get_db

            conn = _get_db()
            conn.execute("""CREATE TABLE IF NOT EXISTS session_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '#6366f1',
                sort_order INTEGER DEFAULT 0,
                collapsed INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )""")
            try:
                conn.execute("ALTER TABLE session_store ADD COLUMN group_id INTEGER DEFAULT NULL")
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
            conn.commit()
            row = conn.execute("SELECT COUNT(*) FROM session_groups").fetchone()
            if row[0] == 0:
                now = datetime.now(KST).isoformat()
                conn.execute(
                    "INSERT INTO session_groups (name, sort_order, created_at) VALUES (?, 0, ?)", ("기본", now)
                )
                conn.commit()
        except Exception as e:
            log.warning(f"Session groups init: {e}")

    def list_groups(self) -> List[Dict]:
        """List groups."""
        try:
            from salmalm.core import _get_db

            conn = _get_db()
            rows = conn.execute(
                "SELECT id, name, color, sort_order, collapsed, created_at FROM session_groups ORDER BY sort_order, id"
            ).fetchall()
            groups = []
            for r in rows:
                count = conn.execute("SELECT COUNT(*) FROM session_store WHERE group_id=?", (r[0],)).fetchone()[0]
                groups.append(
                    {
                        "id": r[0],
                        "name": r[1],
                        "color": r[2],
                        "sort_order": r[3],
                        "collapsed": bool(r[4]),
                        "created_at": r[5],
                        "session_count": count,
                    }
                )
            return groups
        except Exception as e:  # noqa: broad-except
            return []

    def create_group(self, name: str, color: str = "#6366f1") -> Dict:
        """Create group."""
        from salmalm.core import _get_db

        conn = _get_db()
        now = datetime.now(KST).isoformat()
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM session_groups").fetchone()[0]
        conn.execute(
            "INSERT INTO session_groups (name, color, sort_order, created_at) VALUES (?, ?, ?, ?)",
            (name, color, max_order + 1, now),
        )
        conn.commit()
        gid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return {"id": gid, "name": name, "color": color, "ok": True}

    _ALLOWED_UPDATE_COLS = frozenset({"name", "color", "sort_order", "collapsed"})

    def update_group(self, group_id: int, **kwargs) -> bool:
        """Update group."""
        from salmalm.core import _get_db

        for key in kwargs:
            if key not in self._ALLOWED_UPDATE_COLS:
                raise ValueError(f"Invalid column: {key}")

        conn = _get_db()
        sets = []
        vals = []
        for key in sorted(self._ALLOWED_UPDATE_COLS):
            if key in kwargs:
                sets.append(f"{key}=?")
                vals.append(kwargs[key])
        if not sets:
            return False
        vals.append(group_id)
        conn.execute(f"UPDATE session_groups SET {','.join(sets)} WHERE id=?", vals)
        conn.commit()
        return True

    def delete_group(self, group_id: int) -> bool:
        """Delete group."""
        from salmalm.core import _get_db

        conn = _get_db()
        conn.execute("UPDATE session_store SET group_id=NULL WHERE group_id=?", (group_id,))
        conn.execute("DELETE FROM session_groups WHERE id=?", (group_id,))
        conn.commit()
        return True

    def move_session(self, session_id: str, group_id: Optional[int]) -> bool:
        """Move session."""
        from salmalm.core import _get_db

        conn = _get_db()
        conn.execute("UPDATE session_store SET group_id=? WHERE session_id=?", (group_id, session_id))
        conn.commit()
        return True


session_groups = SessionGroupManager()
