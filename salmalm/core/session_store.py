"""Session management — Session class, get/rollback/branch/save/restore.

Extracted from core.py to reduce god object. All core.py dependencies
use lazy imports to avoid circular import issues.
"""

import json
import threading
import time
import uuid as _uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from salmalm.constants import DATA_DIR, KST
from salmalm.security.crypto import log, vault


# ── Lazy accessors for core.py globals (break circular import) ──


def _get_db():
    """Get db."""
    from salmalm.core.core import _get_db as _impl

    return _impl()


def _audit_log(*args, **kwargs):
    """Audit log."""
    from salmalm.core.core import audit_log as _impl

    return _impl(*args, **kwargs)


def _restore_compaction_summary(session_id: str) -> Optional[str]:
    """Restore compaction summary."""
    from salmalm.core.compaction import _restore_compaction_summary as _impl

    return _impl(session_id)


class Session:
    """OpenClaw-style isolated session with its own context.

    Each session has:
    - Unique ID and isolated message history
    - No cross-contamination between sessions
    - Automatic memory flush before compaction
    - Session metadata tracking
    """

    def __init__(self, session_id: str, user_id: Optional[int] = None) -> None:
        """Init  ."""
        self.id = session_id
        self.user_id = user_id  # Multi-tenant: owning user (None = legacy/local)
        self.messages: list = []
        self.created = time.time()
        self.last_active = time.time()
        self.metadata: dict = {}  # Arbitrary session metadata
        self._memory_flushed = False  # Track if pre-compaction memory flush happened
        self.thinking_enabled = False  # Extended thinking toggle (default OFF)
        self.thinking_level = "medium"  # Thinking depth: "low"|"medium"|"high"|"xhigh"
        self.model_override = "auto"  # Multi-model routing: 'auto'|'haiku'|'sonnet'|'opus'|full model string
        self.tts_enabled = False  # TTS toggle
        self.tts_voice = "alloy"  # TTS voice selection
        self.last_model = "auto"  # Last used model (for UI display)
        self.last_complexity = "auto"  # Last complexity level

    def add_system(self, content: str) -> None:
        # Replace existing system message
        """Add a system message to the session."""
        self.messages = [m for m in self.messages if m["role"] != "system"]
        self.messages.insert(0, {"role": "system", "content": content})

    def _persist(self):
        """Save session to SQLite (only text messages, skip image data).

        Handles: disk full (OSError), DB lock (sqlite3.OperationalError).
        """
        try:
            # Filter out large binary data from messages
            saveable = []
            for m in self.messages[-50:]:  # Keep last 50 messages
                if isinstance(m.get("content"), list):
                    # Multimodal — save text parts only
                    texts = [b for b in m["content"] if b.get("type") == "text"]
                    if texts:
                        saveable.append({**m, "content": texts})
                elif isinstance(m.get("content"), str):
                    saveable.append(m)
            conn = _get_db()
            # Ensure columns exist
            for _col_sql in [
                "ALTER TABLE session_store ADD COLUMN user_id INTEGER DEFAULT NULL",
                "ALTER TABLE session_store ADD COLUMN session_meta TEXT DEFAULT '{}'",
            ]:
                try:
                    conn.execute(_col_sql)
                except Exception as e:
                    log.debug(f"Suppressed: {e}")
            # Persist session metadata (model_override, thinking, tts)
            _meta = json.dumps({
                "model_override": self.model_override,
                "thinking_enabled": self.thinking_enabled,
                "thinking_level": self.thinking_level,
                "tts_enabled": self.tts_enabled,
                "tts_voice": self.tts_voice,
            }, ensure_ascii=False)
            conn.execute(
                "INSERT OR REPLACE INTO session_store (session_id, messages, updated_at, user_id, session_meta) VALUES (?,?,?,?,?)",
                (
                    self.id,
                    json.dumps(saveable, ensure_ascii=False),
                    datetime.now(KST).isoformat(),
                    self.user_id,
                    _meta,
                ),
            )  # noqa: F405
            conn.commit()
        except Exception as e:
            log.warning(f"Session persist error: {e}")

    def add_user(self, content: str) -> None:
        """Add a user message to the session.

        Auto-compaction: if session exceeds 1000 messages, trim old ones.
        """
        self.messages.append({"role": "user", "content": content})
        self.last_active = time.time()
        # Session size explosion prevention
        if len(self.messages) > 1000:
            system_msgs = [m for m in self.messages if m["role"] == "system"][:1]
            recent = [m for m in self.messages if m["role"] != "system"][-50:]
            self.messages = system_msgs + recent
            log.warning(f"[SESSION] Auto-trimmed session {self.id}: >1000 msgs → {len(self.messages)}")

    def add_assistant(self, content: str) -> None:
        """Add an assistant response to the session."""
        self.messages.append({"role": "assistant", "content": content})
        self.last_active = time.time()
        self._persist()
        # Auto-save to disk after final response (debounced — not on tool calls)
        try:
            save_session_to_disk(self.id)
        except Exception as e:
            log.debug(f"Suppressed: {e}")

    def add_tool_results(self, results: list) -> None:
        """Add tool results as a single user message with all results.
        results: list of {'tool_use_id': str, 'content': str}
        """
        content = [
            {
                "type": "tool_result",
                "tool_use_id": r["tool_use_id"],
                "content": r["content"],
            }
            for r in results
        ]
        self.messages.append({"role": "user", "content": content})


_tg_bot = None  # Set during startup by telegram module


def get_telegram_bot() -> Optional[object]:
    """Accessor for the Telegram bot instance (avoids direct global access)."""
    return _tg_bot


def set_telegram_bot(bot: object) -> None:
    """Set the Telegram bot instance (called during startup)."""
    global _tg_bot
    _tg_bot = bot


_llm_cron = None  # Set during startup by __main__ (LLMCron instance)
_sessions = {}  # type: ignore[var-annotated]
_session_lock = threading.Lock()  # Protects _sessions dict
_session_cleanup_ts = 0.0
_SESSION_TTL = 3600 * 8  # 8 hours
_SESSION_MAX = 200


def _cleanup_sessions():
    """Remove inactive sessions older than TTL."""
    global _session_cleanup_ts
    now = time.time()
    if now - _session_cleanup_ts < 600:  # Check every 10 min
        return
    _session_cleanup_ts = now
    with _session_lock:
        stale = [sid for sid, s in _sessions.items() if now - s.last_active > _SESSION_TTL]
        for sid in stale:
            try:
                _sessions[sid]._persist()
            except Exception as e:
                log.debug(f"Suppressed: {e}")
            del _sessions[sid]
        if stale:
            log.info(f"[CLEAN] Session cleanup: removed {len(stale)} inactive sessions")
        # Hard cap
        if len(_sessions) > _SESSION_MAX:
            by_age = sorted(_sessions.items(), key=lambda x: x[1].last_active)
            for sid, _ in by_age[: len(_sessions) - _SESSION_MAX]:
                del _sessions[sid]


def get_session(session_id: str, user_id: Optional[int] = None) -> Session:
    """Get or create a chat session by ID.

    If user_id is provided and the session already exists with a different user_id,
    access is denied (returns a new isolated session instead of the existing one).
    """
    _cleanup_sessions()
    with _session_lock:
        if session_id in _sessions:
            existing = _sessions[session_id]
            if user_id is not None and existing.user_id is not None and existing.user_id != user_id:
                # Session belongs to another user — create isolated session
                log.warning(f"[SESSION] User {user_id} denied access to session {session_id} (owned by {existing.user_id})")
                isolated_id = f"{session_id}_u{user_id}"
                if isolated_id not in _sessions:
                    _sessions[isolated_id] = Session(isolated_id, user_id=user_id)
                return _sessions[isolated_id]
        if session_id not in _sessions:
            _sessions[session_id] = Session(session_id, user_id=user_id)
            # Try to restore from SQLite
            try:
                conn = _get_db()
                row = conn.execute(
                    "SELECT messages, session_meta FROM session_store WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                if row:
                    try:
                        restored = json.loads(row[0])
                        if not isinstance(restored, list):
                            raise ValueError("Session data is not a list")
                        _sessions[session_id].messages = restored
                        log.info(f"[NOTE] Session restored: {session_id} ({len(restored)} msgs)")
                    except (json.JSONDecodeError, ValueError, TypeError) as je:
                        # Corrupted session JSON — start fresh
                        log.warning(f"[SESSION] Corrupt session JSON for {session_id}: {je}")
                        _sessions[session_id].messages = []
                    # Restore session metadata (model_override, thinking, tts)
                    try:
                        _meta_json = row[1] if len(row) > 1 and row[1] else "{}"
                        _meta = json.loads(_meta_json)
                        if _meta.get("model_override"):
                            _sessions[session_id].model_override = _meta["model_override"]
                        if _meta.get("thinking_enabled") is not None:
                            _sessions[session_id].thinking_enabled = _meta["thinking_enabled"]
                        if _meta.get("thinking_level"):
                            _sessions[session_id].thinking_level = _meta["thinking_level"]
                        if _meta.get("tts_enabled") is not None:
                            _sessions[session_id].tts_enabled = _meta["tts_enabled"]
                        if _meta.get("tts_voice"):
                            _sessions[session_id].tts_voice = _meta["tts_voice"]
                    except (json.JSONDecodeError, IndexError, TypeError) as me:
                        log.debug(f"Session meta restore: {me}")
                    # Refresh system prompt
                    from salmalm.core.prompt import build_system_prompt

                    _sessions[session_id].add_system(build_system_prompt(full=False))
                    return _sessions[session_id]
            except Exception as e:
                log.warning(f"Session restore error: {e}")
            from salmalm.core.prompt import build_system_prompt

            _sessions[session_id].add_system(build_system_prompt(full=True))

            # Cross-session continuity: inject last compaction summary
            prev_summary = _restore_compaction_summary(session_id)
            if prev_summary:
                _sessions[session_id].messages.append(
                    {
                        "role": "system",
                        "content": f"[Previous session context]\n{prev_summary}",
                    }
                )
                log.info(f"[NOTE] Restored compaction summary for {session_id} ({len(prev_summary)} chars)")

            # Apply onboarding model as session default
            try:
                from salmalm.security.crypto import vault

                if vault.is_unlocked:
                    dm = vault.get("default_model")
                    if dm and dm != "auto":
                        _sessions[session_id]._default_model = dm
                        _sessions[session_id].model_override = dm
            except Exception as e:
                log.debug(f"Suppressed: {e}")

            log.info(
                f"[NOTE] New session: {session_id} (system prompt: {len(_sessions[session_id].messages[0]['content'])} chars)"
            )
            _audit_log(
                "session_create",
                f"new session: {session_id}",
                session_id=session_id,
                detail_dict={"session_id": session_id},
            )
        return _sessions[session_id]


def rollback_session(session_id: str, count: int) -> dict:
    """Roll back the last `count` user+assistant message pairs.

    Removed messages are backed up in session_message_backup table.
    Returns {'ok': True, 'removed': <int>} or {'ok': False, 'error': ...}.
    """
    session = get_session(session_id)
    non_system = [(i, m) for i, m in enumerate(session.messages) if m.get("role") != "system"]
    pairs_removed = 0
    indices_to_remove = []
    j = len(non_system) - 1
    while pairs_removed < count and j >= 0:
        idx_j, msg_j = non_system[j]
        if msg_j["role"] == "assistant":
            indices_to_remove.append(idx_j)
            if j - 1 >= 0 and non_system[j - 1][1]["role"] == "user":
                indices_to_remove.append(non_system[j - 1][0])
                j -= 2
            else:
                j -= 1
            pairs_removed += 1
        elif msg_j["role"] == "user":
            indices_to_remove.append(idx_j)
            j -= 1
            pairs_removed += 1
        else:
            j -= 1

    if not indices_to_remove:
        return {"ok": False, "error": "No messages to rollback"}

    removed_msgs = [session.messages[i] for i in sorted(indices_to_remove)]
    conn = _get_db()
    conn.execute(
        "INSERT INTO session_message_backup (session_id, messages_json, removed_at, reason) VALUES (?,?,?,?)",
        (
            session_id,
            json.dumps(removed_msgs, ensure_ascii=False),
            datetime.now(KST).isoformat(),
            "rollback",
        ),
    )  # noqa: F405
    conn.commit()

    for i in sorted(indices_to_remove, reverse=True):
        session.messages.pop(i)

    session._persist()
    try:
        save_session_to_disk(session_id)
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    _audit_log("session_rollback", f"{session_id}: removed {pairs_removed} pairs")
    return {"ok": True, "removed": pairs_removed}


def branch_session(session_id: str, message_index: int) -> dict:
    """Create a new session branching from session_id at message_index.

    Copies messages[0:message_index+1] into a new session.
    Returns {'ok': True, 'new_session_id': ...} or error.
    """

    session = get_session(session_id)
    if message_index < 0 or message_index >= len(session.messages):
        return {"ok": False, "error": f"Invalid message_index: {message_index}"}

    new_id = f"branch-{_uuid.uuid4().hex[:8]}"
    new_session = Session(new_id)
    new_session.messages = json.loads(json.dumps(session.messages[: message_index + 1]))
    new_session.metadata["parent_session_id"] = session_id
    new_session.metadata["branch_index"] = message_index

    with _session_lock:
        _sessions[new_id] = new_session

    new_session._persist()

    conn = _get_db()
    try:
        conn.execute("ALTER TABLE session_store ADD COLUMN parent_session_id TEXT DEFAULT NULL")
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    try:
        conn.execute("ALTER TABLE session_store ADD COLUMN branch_index INTEGER DEFAULT NULL")
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    conn.execute(
        "UPDATE session_store SET parent_session_id=?, branch_index=? WHERE session_id=?",
        (session_id, message_index, new_id),
    )
    conn.commit()

    try:
        save_session_to_disk(new_id)
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    _audit_log("session_branch", f"{session_id} -> {new_id} at index {message_index}")
    return {"ok": True, "new_session_id": new_id, "parent_session_id": session_id}


_SESSIONS_DIR = DATA_DIR / "sessions"


def save_session_to_disk(session_id: str) -> None:
    """Serialize session state to ~/.salmalm/sessions/{id}.json."""
    with _session_lock:
        session = _sessions.get(session_id)
        if not session:
            return
    try:
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        saveable_msgs = []
        for m in session.messages[-50:]:
            if isinstance(m.get("content"), list):
                texts = [b for b in m["content"] if isinstance(b, dict) and b.get("type") == "text"]
                if texts:
                    saveable_msgs.append({**m, "content": texts})
            elif isinstance(m.get("content"), str):
                saveable_msgs.append(m)
        data = {
            "session_id": session.id,
            "messages": saveable_msgs,
            "created": session.created,
            "last_active": session.last_active,
            "metadata": session.metadata,
        }
        path = _SESSIONS_DIR / f"{session_id}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"[DISK] Failed to save session {session_id}: {e}")


def restore_session(session_id: str) -> Optional[Session]:
    """Load session from ~/.salmalm/sessions/{id}.json."""
    path = _SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        session = Session(session_id)
        session.messages = data.get("messages", [])
        session.created = data.get("created", time.time())
        session.last_active = data.get("last_active", time.time())
        session.metadata = data.get("metadata", {})
        with _session_lock:
            _sessions[session_id] = session
        log.info(f"[DISK] Restored session from disk: {session_id} ({len(session.messages)} msgs)")
        return session
    except Exception as e:
        log.warning(f"[DISK] Failed to restore session {session_id}: {e}")
        return None


def restore_all_sessions_from_disk() -> None:
    """On startup, restore all sessions from disk."""
    if not _SESSIONS_DIR.exists():
        return
    count = 0
    for path in _SESSIONS_DIR.glob("*.json"):
        sid = path.stem
        if restore_session(sid):
            count += 1
    if count:
        log.info(f"[DISK] Restored {count} sessions from disk")
