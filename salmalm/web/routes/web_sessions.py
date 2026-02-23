"""Session management API — list, create, import, delete, rename, rollback, branch."""

from datetime import datetime
from salmalm.security.crypto import vault, log
import json
from salmalm.core import audit_log


class WebSessionsMixin:
    """Mixin providing sessions route handlers."""

    def _get_api_sessions(self):
        """Get api sessions."""
        _auth_user = self._require_auth("user")
        if not _auth_user:
            return
        from salmalm.core import _get_db

        conn = _get_db()
        # User-scoped session list (user_id=0 or NULL = legacy/local = show all)
        _uid = _auth_user.get("id", 0)
        if _uid and _uid > 0:
            rows = conn.execute(
                "SELECT session_id, updated_at, title, parent_session_id FROM session_store "
                "WHERE user_id=? OR user_id IS NULL ORDER BY updated_at DESC",
                (_uid,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT session_id, updated_at, title, parent_session_id FROM session_store ORDER BY updated_at DESC"
            ).fetchall()
        sessions = []
        for r in rows:
            sid = r[0]
            stored_title = r[2] if len(r) > 2 else ""
            parent_sid = r[3] if len(r) > 3 else None
            if stored_title:
                title = stored_title
                msg_count = 0
            else:
                try:
                    msgs = json.loads(
                        conn.execute(
                            "SELECT messages FROM session_store WHERE session_id=?",
                            (sid,),
                        ).fetchone()[0]
                    )
                    title = ""
                    for m in msgs:
                        if m.get("role") == "user" and isinstance(m.get("content"), str):
                            title = m["content"][:60]
                            break
                    msg_count = len([m for m in msgs if m.get("role") in ("user", "assistant")])
                except Exception as e:  # noqa: broad-except
                    title = sid
                    msg_count = 0
            entry = {
                "id": sid,
                "title": title or sid,
                "updated_at": r[1],
                "messages": msg_count,
            }
            if parent_sid:
                entry["parent_session_id"] = parent_sid
            sessions.append(entry)
        self._json({"sessions": sessions})

    def _post_api_sessions_create(self):
        """Post api sessions create."""
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        if not sid:
            self._json({"ok": False, "error": "Missing session_id"}, 400)
            return
        from salmalm.core import _get_db

        conn = _get_db()
        try:
            conn.execute(
                'INSERT OR IGNORE INTO session_store (session_id, messages, updated_at, title) VALUES (?, ?, datetime("now"), ?)',
                (sid, "[]", "New Chat"),
            )
            conn.commit()
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        self._json({"ok": True, "session_id": sid})

    def _post_api_sessions_import(self):
        """Import a chat session from JSON export."""
        body = self._body
        if not self._require_auth("user"):
            return
        messages = body.get("messages", [])
        title = body.get("title", "Imported Chat")
        if not messages or not isinstance(messages, list):
            self._json({"ok": False, "error": "messages array required"}, 400)
            return
        import uuid

        sid = f"imported_{uuid.uuid4().hex[:8]}"
        from salmalm.core import _get_db

        conn = _get_db()
        conn.execute(
            "INSERT OR REPLACE INTO session_store (session_id, messages, title, updated_at) VALUES (?, ?, ?, datetime('now'))",
            (sid, json.dumps(messages, ensure_ascii=False), title),
        )
        conn.commit()
        audit_log("session_import", sid, detail_dict={"title": title, "msg_count": len(messages)})
        self._json({"ok": True, "session_id": sid})

    def _post_api_sessions_delete(self):
        """Post api sessions delete."""
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        if not sid:
            self._json({"ok": False, "error": "Missing session_id"}, 400)
            return
        from salmalm.core import _sessions, _get_db

        if sid in _sessions:
            del _sessions[sid]
        conn = _get_db()
        conn.execute("DELETE FROM session_store WHERE session_id=?", (sid,))
        conn.commit()
        audit_log("session_delete", sid, session_id=sid, detail_dict={"session_id": sid})
        self._json({"ok": True})

    def _post_api_sessions_rename(self):
        """Post api sessions rename."""
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        title = body.get("title", "").strip()[:60]
        if not sid or not title:
            self._json({"ok": False, "error": "Missing session_id or title"}, 400)
            return
        from salmalm.core import _get_db

        conn = _get_db()
        conn.execute("UPDATE session_store SET title=? WHERE session_id=?", (title, sid))
        conn.commit()
        self._json({"ok": True})

    def _post_api_sessions_rollback(self):
        """Post api sessions rollback."""
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        count = int(body.get("count", 1))
        if not sid:
            self._json({"ok": False, "error": "Missing session_id"}, 400)
            return
        from salmalm.core import rollback_session

        result = rollback_session(sid, count)
        self._json(result)

    def _post_api_sessions_branch(self):
        """Post api sessions branch."""
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        message_index = body.get("message_index")
        if not sid or message_index is None:
            self._json({"ok": False, "error": "Missing session_id or message_index"}, 400)
            return
        from salmalm.core import branch_session

        result = branch_session(sid, int(message_index))
        self._json(result)
