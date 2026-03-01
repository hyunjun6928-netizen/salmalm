"""Session management API — list, create, import, delete, rename, rollback, branch."""

from salmalm.security.crypto import log
import json
import re as _re
from salmalm.core import audit_log

# Precompiled regex for title extraction (used in hot session-list loops)
_RE_BOLD = _re.compile(r'\*\*([^*]+)\*\*')
_RE_ITALIC = _re.compile(r'\*([^*]+)\*')
_RE_CODE = _re.compile(r'`([^`]+)`')


class WebSessionsMixin:
    GET_ROUTES = {
        "/api/sessions": "_get_api_sessions",
    }
    POST_ROUTES = {
        "/api/sessions/create": "_post_api_sessions_create",
        "/api/sessions/delete": "_post_api_sessions_delete",
        "/api/sessions/clear": "_post_api_sessions_clear",
        "/api/sessions/import": "_post_api_sessions_import",
        "/api/sessions/rename": "_post_api_sessions_rename",
        "/api/sessions/rollback": "_post_api_sessions_rollback",
        "/api/sessions/branch": "_post_api_sessions_branch",
    }
    GET_PREFIX_ROUTES = [
        ("/api/sessions/", "_get_api_sessions_messages", "/messages"),
        ("/api/sessions/", "_get_api_sessions_last", "/last"),
    ]

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
                    _row = conn.execute(
                        "SELECT messages FROM session_store WHERE session_id=?",
                        (sid,),
                    ).fetchone()
                    if _row is None:
                        title = stored_title or ""
                        msg_count = 0
                        continue
                    msgs = json.loads(_row[0])
                    title = ""
                    for m in msgs:
                        if m.get("role") == "user" and isinstance(m.get("content"), str):
                            _raw = m["content"].strip()
                            # Skip file upload info lines as title
                            if _raw.startswith("[") and ("uploaded" in _raw or "📎" in _raw or "🖼" in _raw):
                                continue
                            # Strip markdown formatting (precompiled at module level)
                            _raw = _RE_BOLD.sub(r'\1', _raw)
                            _raw = _RE_ITALIC.sub(r'\1', _raw)
                            _raw = _RE_CODE.sub(r'\1', _raw)
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
        _u = self._require_auth("user")
        if not _u:
            return
        sid = body.get("session_id", "")
        if not sid:
            self._json({"ok": False, "error": "Missing session_id"}, 400)
            return
        from salmalm.core import _sessions, _get_db
        from salmalm.core.session_store import _SESSIONS_DIR

        conn = _get_db()
        _uid = _u.get("id") if _u.get("role") != "admin" else None
        if _uid is not None:
            row = conn.execute(
                "SELECT 1 FROM session_store WHERE session_id=? AND (user_id=? OR user_id IS NULL)",
                (sid, _uid),
            ).fetchone()
            if not row:
                self._json({"ok": False, "error": "Session not found or access denied"}, 403)
                return
        if sid in _sessions:
            del _sessions[sid]
        conn.execute(
            "DELETE FROM session_store WHERE session_id=? AND (user_id=? OR user_id IS NULL)",
            (sid, _uid if _uid is not None else _u.get("id", 0)),
        ) if _uid is not None else conn.execute("DELETE FROM session_store WHERE session_id=?", (sid,))
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
        _u = self._require_auth("user")
        if not _u:
            return
        keep = body.get("keep", "web")
        from salmalm.core import _sessions, _get_db

        from salmalm.core.session_store import _SESSIONS_DIR

        conn = _get_db()
        _uid = _u.get("id") if _u.get("role") != "admin" else None
        # Scope deletion to the requesting user's sessions only
        if _uid is not None:
            rows = conn.execute(
                "SELECT session_id FROM session_store WHERE session_id != ? AND (user_id=? OR user_id IS NULL)",
                (keep, _uid),
            ).fetchall()
        else:
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
            except Exception as _e:
                log.debug("[SESSIONS] JSON cleanup failed for %s: %s", sid, _e)
            deleted += 1
        if _uid is not None:
            conn.execute(
                "DELETE FROM session_store WHERE session_id != ? AND (user_id=? OR user_id IS NULL)",
                (keep, _uid),
            )
        else:
            conn.execute("DELETE FROM session_store WHERE session_id != ?", (keep,))
        conn.commit()
        audit_log("session_clear", keep, detail_dict={"deleted": deleted, "kept": keep})
        self._json({"ok": True, "deleted": deleted})

    def _post_api_sessions_rename(self):
        """Post api sessions rename."""
        body = self._body
        _u = self._require_auth("user")
        if not _u:
            return
        sid = body.get("session_id", "")
        title = body.get("title", "").strip()[:60]
        if not sid or not title:
            self._json({"ok": False, "error": "Missing session_id or title"}, 400)
            return
        from salmalm.core import _get_db

        conn = _get_db()
        _uid = _u.get("id") if _u.get("role") != "admin" else None
        if _uid is not None:
            row = conn.execute(
                "SELECT 1 FROM session_store WHERE session_id=? AND (user_id=? OR user_id IS NULL)",
                (sid, _uid),
            ).fetchone()
            if not row:
                self._json({"ok": False, "error": "Session not found or access denied"}, 403)
                return
            conn.execute(
                "UPDATE session_store SET title=? WHERE session_id=? AND (user_id=? OR user_id IS NULL)",
                (title, sid, _uid),
            )
        else:
            conn.execute("UPDATE session_store SET title=? WHERE session_id=?", (title, sid))
        conn.commit()
        self._json({"ok": True})

    def _post_api_sessions_rollback(self):
        """Post api sessions rollback."""
        body = self._body
        _u = self._require_auth("user")
        if not _u:
            return
        _uid = _u.get("id") if _u.get("role") != "admin" else None
        sid = body.get("session_id", "")
        try:
            count = max(1, min(int(body.get("count", 1)), 50))
        except (TypeError, ValueError):
            count = 1
        if not sid:
            self._json({"ok": False, "error": "Missing session_id"}, 400)
            return
        from salmalm.core import rollback_session

        result = rollback_session(sid, count, user_id=_uid)
        self._json(result)

    def _post_api_sessions_branch(self):
        """Post api sessions branch."""
        body = self._body
        _u = self._require_auth("user")
        if not _u:
            return
        _uid = _u.get("id") if _u.get("role") != "admin" else None
        sid = body.get("session_id", "")
        message_index = body.get("message_index")
        if not sid or message_index is None:
            self._json({"ok": False, "error": "Missing session_id or message_index"}, 400)
            return
        from salmalm.core import branch_session

        try:
            _mi = max(0, int(message_index))
        except (TypeError, ValueError):
            self._json({"ok": False, "error": "Invalid message_index"}, 400)
            return
        result = branch_session(sid, _mi, user_id=_uid)
        self._json(result)

    def _get_api_sessions_messages(self):
        """GET /api/sessions/{session_id}/messages — full message history.

        Used by the web UI to load cross-channel sessions (Telegram, Discord, etc.)
        that are not stored in the browser's localStorage.
        """
        if not self._require_auth("user"):
            return
        m = _re.match(r"^/api/sessions/([^/]+)/messages", self.path)
        if not m:
            self._json({"error": "Bad path"}, 400)
            return
        sid = m.group(1)
        from salmalm.core import _get_db

        conn = _get_db()
        row = conn.execute(
            "SELECT messages FROM session_store WHERE session_id=?", (sid,)
        ).fetchone()
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


# ── FastAPI router ────────────────────────────────────────────────────────────
import asyncio as _asyncio
from fastapi import APIRouter as _APIRouter, Request as _Request, Depends as _Depends, Query as _Query
from fastapi.responses import JSONResponse as _JSON, Response as _Response, HTMLResponse as _HTML, StreamingResponse as _SR, RedirectResponse as _RR
from salmalm.web.fastapi_deps import require_auth as _auth, optional_auth as _optauth
from salmalm.web.schemas import CreateSessionRequest, SessionListResponse, SessionInfo

router = _APIRouter()

@router.get("/api/sessions")
async def get_sessions(_u=_Depends(_auth)):
    import json as _json, re as _re
    from salmalm.core import _get_db
    conn = _get_db()
    _uid = _u.get("id", 0)
    if _uid and _uid > 0:
        rows = conn.execute("SELECT session_id, updated_at, title, parent_session_id FROM session_store WHERE user_id=? OR user_id IS NULL ORDER BY updated_at DESC", (_uid,)).fetchall()
    else:
        rows = conn.execute("SELECT session_id, updated_at, title, parent_session_id FROM session_store ORDER BY updated_at DESC").fetchall()
    _HIDDEN_PREFIXES = ("agent_", "subagent_", "cron-", "test_msg_", "e2e-", "save_test")
    sessions = []
    for r in rows:
        sid = r[0]
        if any(sid.startswith(p) for p in _HIDDEN_PREFIXES):
            continue
        stored_title = r[2] if len(r) > 2 else ""
        parent_sid = r[3] if len(r) > 3 else None
        if stored_title:
            title = stored_title
            msg_count = 0
        else:
            try:
                _row2 = conn.execute("SELECT messages FROM session_store WHERE session_id=?", (sid,)).fetchone()
                if _row2 is None:
                    title = stored_title or ""
                    msg_count = 0
                    continue
                msgs = _json.loads(_row2[0])
                title = ""
                for m in msgs:
                    if m.get("role") == "user" and isinstance(m.get("content"), str):
                        _raw = m["content"].strip()
                        if _raw.startswith("[") and ("uploaded" in _raw or "📎" in _raw or "🖼" in _raw):
                            continue
                        _raw = _RE_BOLD.sub(r'\1', _raw)
                        _raw = _RE_ITALIC.sub(r'\1', _raw)
                        _raw = _RE_CODE.sub(r'\1', _raw).replace("*", "").replace("`", "")
                        title = _raw[:60]
                        break
                msg_count = len([m for m in msgs if m.get("role") in ("user", "assistant")])
            except Exception:
                title = sid
                msg_count = 0
        if not stored_title and msg_count == 0 and sid != "web":
            continue
        entry = {"id": sid, "title": title or sid, "updated_at": r[1], "messages": msg_count}
        if parent_sid:
            entry["parent_session_id"] = parent_sid
        sessions.append(entry)
    return _JSON(content={"sessions": sessions})

@router.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, _u=_Depends(_auth)):
    import json as _json
    from salmalm.core import _get_db
    from fastapi import HTTPException as _HTTPException
    uid = _u.get("id") or _u.get("uid") or _u.get("username")
    conn = _get_db()
    row = conn.execute(
        "SELECT messages FROM session_store WHERE session_id=? AND (user_id=? OR user_id IS NULL)",
        (session_id, uid)
    ).fetchone()
    if not row:
        raise _HTTPException(status_code=404, detail="Session not found or access denied")
    try:
        raw_msgs = _json.loads(row[0]) if row[0] else []
    except Exception:
        return _JSON(content={"messages": []})
    out = []
    for msg in raw_msgs:
        role = msg.get("role", "")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            text = " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text").strip()
        else:
            text = str(content)
        if text:
            out.append({"role": role, "text": text, "model": msg.get("model", "")})
    return _JSON(content={"session_id": session_id, "messages": out})

@router.get("/api/sessions/{session_id}/last")
async def get_session_last(session_id: str, _u=_Depends(_auth)):
    from fastapi import HTTPException as _HTTPException
    from salmalm.core import get_session, _get_db
    uid = _u.get("id") or _u.get("uid") or _u.get("username")
    _conn = _get_db()
    _row = _conn.execute(
        "SELECT 1 FROM session_store WHERE session_id=? AND (user_id=? OR user_id IS NULL)",
        (session_id, uid)
    ).fetchone()
    if not _row:
        raise _HTTPException(status_code=404, detail="Session not found or access denied")
    sess = get_session(session_id)
    last_msg = None
    for msg in reversed(sess.messages):
        if msg.get("role") == "assistant":
            last_msg = msg
            break
    msg_count = len(sess.messages)
    last_active = getattr(sess, "last_active", 0)
    if last_msg:
        return _JSON(content={"ok": True, "message": last_msg.get("content", ""), "role": "assistant", "msg_count": msg_count, "last_active": last_active})
    return _JSON(content={"ok": True, "message": None, "msg_count": msg_count, "last_active": last_active})

@router.get("/api/sessions/{session_id}/summary")
async def get_session_summary(session_id: str, _u=_Depends(_auth)):
    from fastapi import HTTPException as _HTTPException
    from salmalm.core import _get_db
    from salmalm.features.edge_cases import get_summary_card
    uid = _u.get("id") or _u.get("uid") or _u.get("username")
    _conn = _get_db()
    _row = _conn.execute(
        "SELECT 1 FROM session_store WHERE session_id=? AND (user_id=? OR user_id IS NULL)",
        (session_id, uid)
    ).fetchone()
    if not _row:
        raise _HTTPException(status_code=404, detail="Session not found or access denied")
    card = get_summary_card(session_id)
    return _JSON(content={"summary": card})

@router.get("/api/sessions/{session_id}/alternatives")
async def get_session_alternatives(session_id: str, msg_index: int = _Query(0), _u=_Depends(_auth)):
    from fastapi import HTTPException as _HTTPException
    from salmalm.core import _get_db
    from salmalm.features.edge_cases import conversation_fork
    uid = _u.get("id") or _u.get("uid") or _u.get("username")
    _conn = _get_db()
    _row = _conn.execute(
        "SELECT 1 FROM session_store WHERE session_id=? AND (user_id=? OR user_id IS NULL)",
        (session_id, uid)
    ).fetchone()
    if not _row:
        raise _HTTPException(status_code=404, detail="Session not found or access denied")
    alts = conversation_fork.get_alternatives(session_id, msg_index)
    return _JSON(content={"alternatives": alts})

@router.post("/api/sessions/create")
async def post_sessions_create(req: CreateSessionRequest, _u=_Depends(_auth)):
    from salmalm.core import _get_db
    sid = req.session_id or ""
    if not sid:
        return _JSON(content={"ok": False, "error": "Missing session_id"}, status_code=400)
    conn = _get_db()
    try:
        conn.execute('INSERT OR IGNORE INTO session_store (session_id, messages, updated_at, title) VALUES (?, ?, datetime("now"), ?)', (sid, "[]", "New Chat"))
        conn.commit()
    except Exception:
        pass
    return _JSON(content={"ok": True, "session_id": sid})

@router.post("/api/sessions/delete")
async def post_sessions_delete(request: _Request, _u=_Depends(_auth)):
    from salmalm.security.crypto import log
    from salmalm.core import _sessions, _get_db
    from salmalm.core.session_store import _SESSIONS_DIR
    from salmalm.core import audit_log
    body = await request.json()
    sid = body.get("session_id", "")
    if not sid:
        return _JSON(content={"ok": False, "error": "Missing session_id"}, status_code=400)
    uid = _u.get("id") or _u.get("uid") or _u.get("username")
    conn = _get_db()
    # Ownership check: only delete if session belongs to this user (or is legacy/local)
    _row = conn.execute(
        "SELECT 1 FROM session_store WHERE session_id=? AND (user_id=? OR user_id IS NULL)",
        (sid, uid)
    ).fetchone()
    if not _row:
        return _JSON(content={"ok": False, "error": "Session not found or access denied"}, status_code=403)
    if sid in _sessions:
        del _sessions[sid]
    conn.execute("DELETE FROM session_store WHERE session_id=? AND (user_id=? OR user_id IS NULL)", (sid, uid))
    conn.commit()
    _json_path = _SESSIONS_DIR / f"{sid}.json"
    try:
        if _json_path.exists():
            _json_path.unlink()
    except Exception as _e:
        log.warning(f"[SESSION] Could not delete session file {_json_path}: {_e}")
    audit_log("session_delete", sid, session_id=sid, detail_dict={"session_id": sid})
    return _JSON(content={"ok": True})

@router.post("/api/sessions/clear")
async def post_sessions_clear(request: _Request, _u=_Depends(_auth)):
    from salmalm.security.crypto import log
    from salmalm.core import _sessions, _get_db, audit_log
    from salmalm.core.session_store import _SESSIONS_DIR
    body = await request.json()
    keep = body.get("keep", "web")
    uid = _u.get("id") or _u.get("uid") or _u.get("username")
    conn = _get_db()
    # Only delete sessions belonging to this user (or legacy null-owner sessions)
    rows = conn.execute(
        "SELECT session_id FROM session_store WHERE session_id != ? AND (user_id=? OR user_id IS NULL)",
        (keep, uid)
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
        except Exception:
            pass
        deleted += 1
    conn.execute(
        "DELETE FROM session_store WHERE session_id != ? AND (user_id=? OR user_id IS NULL)",
        (keep, uid)
    )
    conn.commit()
    audit_log("session_clear", keep, detail_dict={"deleted": deleted, "kept": keep})
    return _JSON(content={"ok": True, "deleted": deleted})

@router.post("/api/sessions/import")
async def post_sessions_import(request: _Request, _u=_Depends(_auth)):
    import json as _json, uuid
    from salmalm.core import _get_db, audit_log
    body = await request.json()
    messages = body.get("messages", [])
    title = body.get("title", "Imported Chat")
    if not messages or not isinstance(messages, list):
        return _JSON(content={"ok": False, "error": "messages array required"}, status_code=400)
    sid = f"imported_{uuid.uuid4().hex[:8]}"
    conn = _get_db()
    conn.execute("INSERT OR REPLACE INTO session_store (session_id, messages, title, updated_at) VALUES (?, ?, ?, datetime('now'))",
                 (sid, _json.dumps(messages, ensure_ascii=False), title))
    conn.commit()
    audit_log("session_import", sid, detail_dict={"title": title, "msg_count": len(messages)})
    return _JSON(content={"ok": True, "session_id": sid})

@router.post("/api/sessions/rename")
async def post_sessions_rename(request: _Request, _u=_Depends(_auth)):
    from salmalm.core import _get_db
    body = await request.json()
    sid = body.get("session_id", "")
    title = body.get("title", "").strip()[:60]
    if not sid or not title:
        return _JSON(content={"ok": False, "error": "Missing session_id or title"}, status_code=400)
    uid = _u.get("id") or _u.get("uid") or _u.get("username")
    conn = _get_db()
    # Ownership check before rename
    _row = conn.execute(
        "SELECT 1 FROM session_store WHERE session_id=? AND (user_id=? OR user_id IS NULL)",
        (sid, uid)
    ).fetchone()
    if not _row:
        return _JSON(content={"ok": False, "error": "Session not found or access denied"}, status_code=403)
    conn.execute(
        "UPDATE session_store SET title=? WHERE session_id=? AND (user_id=? OR user_id IS NULL)",
        (title, sid, uid)
    )
    conn.commit()
    return _JSON(content={"ok": True})

@router.post("/api/sessions/rollback")
async def post_sessions_rollback(request: _Request, _u=_Depends(_auth)):
    from salmalm.core import rollback_session
    body = await request.json()
    sid = body.get("session_id", "")
    try:
        count = max(1, min(int(body.get("count", 1)), 50))
    except (TypeError, ValueError):
        count = 1
    if not sid:
        return _JSON(content={"ok": False, "error": "Missing session_id"}, status_code=400)
    _uid = _u.get("id") if _u and _u.get("role") != "admin" else None
    return _JSON(content=rollback_session(sid, count, user_id=_uid))

@router.post("/api/sessions/branch")
async def post_sessions_branch(request: _Request, _u=_Depends(_auth)):
    from salmalm.core import branch_session
    body = await request.json()
    sid = body.get("session_id", "")
    message_index = body.get("message_index")
    if not sid or message_index is None:
        return _JSON(content={"ok": False, "error": "Missing session_id or message_index"}, status_code=400)
    try:
        _mi = max(0, int(message_index))
    except (TypeError, ValueError):
        return _JSON(content={"ok": False, "error": "Invalid message_index"}, status_code=400)
    _uid = _u.get("id") if _u and _u.get("role") != "admin" else None
    return _JSON(content=branch_session(sid, _mi, user_id=_uid))
