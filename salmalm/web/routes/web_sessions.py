"""Session management API — list, create, import, delete, rename, rollback, branch."""

from salmalm.security.crypto import log
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
        # Prefixes that are internal/ephemeral — never show in UI
        _HIDDEN_PREFIXES = ("agent_", "subagent_", "cron-", "test_msg_", "e2e-", "save_test")

        sessions = []
        for r in rows:
            sid = r[0]
            # Hide internal agent/cron/test sessions from the sidebar
            if any(sid.startswith(p) for p in _HIDDEN_PREFIXES):
                continue
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
                    import re as _re_title
                    for m in msgs:
                        if m.get("role") == "user" and isinstance(m.get("content"), str):
                            _raw = m["content"].strip()
                            # Skip file upload info lines as title
                            if _raw.startswith("[") and ("uploaded" in _raw or "📎" in _raw or "🖼" in _raw):
                                continue
                            # Strip markdown formatting
                            _raw = _re_title.sub(r'\*\*([^*]+)\*\*', r'\1', _raw)
                            _raw = _re_title.sub(r'\*([^*]+)\*', r'\1', _raw)
                            _raw = _re_title.sub(r'`([^`]+)`', r'\1', _raw)
                            _raw = _raw.replace("*", "").replace("`", "")
                            title = _raw[:60]
                            break
                    msg_count = len([m for m in msgs if m.get("role") in ("user", "assistant")])
                except Exception as e:  # noqa: broad-except
                    title = sid
                    msg_count = 0
            # Skip ghost sessions: no title and no user/assistant messages
            if not stored_title and msg_count == 0 and sid != "web":
                continue
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

    def _get_api_sessions_last(self):
        """GET /api/sessions/{id}/last — return last assistant message for recovery."""
        if not self._require_auth("user"):
            return
        import re as _re

        m = _re.match(r"^/api/sessions/([^/]+)/last$", self.path)
        if not m:
            self._json({"ok": False, "error": "Invalid path"}, 400)
            return
        sid = m.group(1)
        from salmalm.core import get_session

        sess = get_session(sid)
        # Find last assistant message
        last_msg = None
        for msg in reversed(sess.messages):
            if msg.get("role") == "assistant":
                last_msg = msg
                break
        msg_count = len(sess.messages)
        last_active = getattr(sess, "last_active", 0)
        if last_msg:
            self._json({"ok": True, "message": last_msg.get("content", ""), "role": "assistant", "msg_count": msg_count, "last_active": last_active})
        else:
            self._json({"ok": True, "message": None, "msg_count": msg_count, "last_active": last_active})

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
        from salmalm.core.session_store import _SESSIONS_DIR

        if sid in _sessions:
            del _sessions[sid]
        conn = _get_db()
        conn.execute("DELETE FROM session_store WHERE session_id=?", (sid,))
        conn.commit()
        # Also delete the on-disk JSON file — without this the session
        # resurrects on every server restart (dual-persistence bug)
        _json_path = _SESSIONS_DIR / f"{sid}.json"
        try:
            if _json_path.exists():
                _json_path.unlink()
        except Exception as _e:
            log.warning(f"[SESSION] Could not delete session file {_json_path}: {_e}")
        audit_log("session_delete", sid, session_id=sid, detail_dict={"session_id": sid})
        self._json({"ok": True})

    def _post_api_sessions_clear(self):
        """Delete all sessions except the specified one (or 'web')."""
        body = self._body
        if not self._require_auth("user"):
            return
        keep = body.get("keep", "web")
        from salmalm.core import _sessions, _get_db

        from salmalm.core.session_store import _SESSIONS_DIR

        conn = _get_db()
        # Get all session ids except the one to keep
        rows = conn.execute(
            "SELECT session_id FROM session_store WHERE session_id != ?", (keep,)
        ).fetchall()
        deleted = 0
        for r in rows:
            sid = r[0]
            if sid in _sessions:
                del _sessions[sid]
            # Delete on-disk JSON file
            _json_path = _SESSIONS_DIR / f"{sid}.json"
            try:
                if _json_path.exists():
                    _json_path.unlink()
            except Exception:
                pass
            deleted += 1
        conn.execute("DELETE FROM session_store WHERE session_id != ?", (keep,))
        conn.commit()
        audit_log("session_clear", keep, detail_dict={"deleted": deleted, "kept": keep})
        self._json({"ok": True, "deleted": deleted})

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
