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
        _auth_user = self._require_auth("user")
        if not _auth_user:
            return
        import re as _re

        m = _re.match(r"^/api/sessions/([^/]+)/last$", self.path)
        if not m:
            self._json({"ok": False, "error": "Invalid path"}, 400)
            return
        sid = m.group(1)
        from salmalm.core import get_session

        _owner_sess = get_session(sid)
        if _owner_sess.user_id is not None and _owner_sess.user_id != _auth_user.get("id"):
            self._json({"ok": False, "error": "Forbidden"}, 403)
            return
        sess = get_session(sid, user_id=_auth_user.get("id"))
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
        _auth_user = self._require_auth("user")
        if not _auth_user:
            return
        sid = body.get("session_id", "")
        if not sid:
            self._json({"ok": False, "error": "Missing session_id"}, 400)
            return
        from salmalm.core import _get_db

        conn = _get_db()
        try:
            conn.execute(
                'INSERT OR IGNORE INTO session_store (session_id, messages, updated_at, title, user_id) VALUES (?, ?, datetime("now"), ?, ?)',
                (sid, "[]", "New Chat", _auth_user.get("id")),
            )
            conn.commit()
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        self._json({"ok": True, "session_id": sid})

    def _post_api_sessions_import(self):
        """Import a chat session from JSON export."""
        body = self._body
        _auth_user = self._require_auth("user")
        if not _auth_user:
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
        try:
            conn.execute("BEGIN")
            conn.execute(
                "INSERT OR REPLACE INTO session_store (session_id, messages, title, updated_at, user_id) VALUES (?, ?, ?, datetime('now'), ?)",
                (sid, json.dumps(messages, ensure_ascii=False), title, _auth_user.get("id")),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            self._json({"ok": False, "error": f"Import failed: {e}"}, 500)
            return
        audit_log("session_import", sid, detail_dict={"title": title, "msg_count": len(messages)})
        self._json({"ok": True, "session_id": sid})

    def _post_api_sessions_delete(self):
        """Post api sessions delete (owner or admin only)."""
        user = self._require_auth("user")
        if not user:
            return
        sid = self._body.get("session_id", "")
        if not sid:
            self._json({"ok": False, "error": "Missing session_id"}, 400)
            return
        from salmalm.core import _sessions, _get_db
        from salmalm.core.session_store import _SESSIONS_DIR

        uid = user.get("id")
        is_admin = user.get("role") == "admin"
        conn = _get_db()
        # Ownership check: session must belong to this user (or user_id IS NULL for legacy rows)
        row = conn.execute(
            "SELECT user_id FROM session_store WHERE session_id=?", (sid,)
        ).fetchone()
        if not row:
            self._json({"ok": False, "error": "Session not found"}, 404)
            return
        row_uid = row[0]
        if not is_admin and row_uid is not None and row_uid != uid:
            self._json({"ok": False, "error": "Forbidden"}, 403)
            return
        if sid in _sessions:
            del _sessions[sid]
        conn.execute("DELETE FROM session_store WHERE session_id=?", (sid,))
        conn.commit()
        _json_path = _SESSIONS_DIR / f"{sid}.json"
        try:
            if _json_path.exists():
                _json_path.unlink()
        except Exception as _e:
            log.warning(f"[SESSION] Could not delete session file {_json_path}: {_e}")
        audit_log("session_delete", sid, session_id=sid, detail_dict={"session_id": sid})
        self._json({"ok": True})

    def _post_api_sessions_clear(self):
        """Delete caller's sessions except the specified one (admin: all sessions)."""
        user = self._require_auth("user")
        if not user:
            return
        keep = self._body.get("keep", "web")
        uid = user.get("id")
        is_admin = user.get("role") == "admin"
        from salmalm.core import _sessions, _get_db
        from salmalm.core.session_store import _SESSIONS_DIR

        conn = _get_db()
        # Scoped to caller's own sessions only (admin sees all)
        if is_admin:
            rows = conn.execute(
                "SELECT session_id FROM session_store WHERE session_id != ?", (keep,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT session_id FROM session_store WHERE session_id != ? "
                "AND (user_id = ? OR user_id IS NULL)",
                (keep, uid),
            ).fetchall()
        deleted = 0
        for r in rows:
            sid = r[0]
            if sid in _sessions:
                del _sessions[sid]
            _json_path = _SESSIONS_DIR / f"{sid}.json"
            try:
                if _json_path.exists():
                    _json_path.unlink()
            except Exception as _e:
                log.debug("[SESSIONS] JSON cleanup failed for %s: %s", sid, _e)
            deleted += 1
        if is_admin:
            conn.execute("DELETE FROM session_store WHERE session_id != ?", (keep,))
        else:
            conn.execute(
                "DELETE FROM session_store WHERE session_id != ? "
                "AND (user_id = ? OR user_id IS NULL)",
                (keep, uid),
            )
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

        from salmalm.web.auth import extract_auth
        user = extract_auth({k.lower(): v for k, v in self.headers.items()})
        uid = user["id"] if user else None
        conn = _get_db()
        result = conn.execute(
            "UPDATE session_store SET title=? WHERE session_id=? AND (user_id=? OR user_id IS NULL)",
            (title, sid, uid),
        )
        conn.commit()
        if result.rowcount == 0:
            self._json({"ok": False, "error": "Session not found or permission denied"}, 403)
            return
        self._json({"ok": True})

    def _post_api_sessions_rollback(self):
        """Post api sessions rollback (owner or admin only)."""
        user = self._require_auth("user")
        if not user:
            return
        sid = self._body.get("session_id", "")
        count = int(self._body.get("count", 1))
        if not sid:
            self._json({"ok": False, "error": "Missing session_id"}, 400)
            return
        uid = user.get("id")
        is_admin = user.get("role") == "admin"
        from salmalm.core import _get_db, rollback_session
        conn = _get_db()
        row = conn.execute("SELECT user_id FROM session_store WHERE session_id=?", (sid,)).fetchone()
        if not row:
            self._json({"ok": False, "error": "Session not found"}, 404)
            return
        if not is_admin and row[0] is not None and row[0] != uid:
            self._json({"ok": False, "error": "Forbidden"}, 403)
            return
        result = rollback_session(sid, count)
        self._json(result)

    def _post_api_sessions_branch(self):
        """Post api sessions branch (owner or admin only)."""
        user = self._require_auth("user")
        if not user:
            return
        sid = self._body.get("session_id", "")
        message_index = self._body.get("message_index")
        if not sid or message_index is None:
            self._json({"ok": False, "error": "Missing session_id or message_index"}, 400)
            return
        uid = user.get("id")
        is_admin = user.get("role") == "admin"
        from salmalm.core import _get_db, branch_session
        conn = _get_db()
        row = conn.execute("SELECT user_id FROM session_store WHERE session_id=?", (sid,)).fetchone()
        if not row:
            self._json({"ok": False, "error": "Session not found"}, 404)
            return
        if not is_admin and row[0] is not None and row[0] != uid:
            self._json({"ok": False, "error": "Forbidden"}, 403)
            return
        result = branch_session(sid, int(message_index))
        self._json(result)

    def _get_api_sessions_messages(self):
        """GET /api/sessions/{session_id}/messages — full message history (owner or admin only)."""
        import re as _re
        user = self._require_auth("user")
        if not user:
            return
        m = _re.match(r"^/api/sessions/([^/]+)/messages", self.path)
        if not m:
            self._json({"error": "Bad path"}, 400)
            return
        sid = m.group(1)
        uid = user.get("id")
        is_admin = user.get("role") == "admin"
        from salmalm.core import _get_db

        conn = _get_db()
        row = conn.execute(
            "SELECT messages, user_id FROM session_store WHERE session_id=?", (sid,)
        ).fetchone()
        if not row:
            self._json({"messages": []})
            return
        if not is_admin and row[1] is not None and row[1] != uid:
            self._json({"error": "Forbidden"}, 403)
            return
        # Re-alias for downstream usage
        row = (row[0],)
        if not row:
            self._json({"messages": []})
            return
        try:
            raw_msgs = json.loads(row[0]) if row[0] else []
        except (json.JSONDecodeError, TypeError):
            self._json({"messages": []})
            return
        out = []
        for msg in raw_msgs:
            role = msg.get("role", "")
            if role not in ("user", "assistant"):
                continue
            content = msg.get("content", "")
            if isinstance(content, list):
                text = " ".join(
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ).strip()
            else:
                text = str(content)
            model = msg.get("model", "")
            if text:
                out.append({"role": role, "text": text, "model": model})
        self._json({"session_id": sid, "messages": out})
