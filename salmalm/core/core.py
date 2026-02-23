"""SalmAlm core — audit, cache, usage, router, compaction, search,
subagent, skills, session, cron, daily."""

import asyncio
import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import Optional

from salmalm.constants import (
    AUDIT_DB,
    CACHE_TTL,
    COMPLEX_INDICATORS,
    DATA_DIR,
    KST,
    MEMORY_DIR,
    MODEL_COSTS,
    MODEL_TIERS,
    SIMPLE_QUERY_MAX_CHARS,
    TOOL_HINT_KEYWORDS,
)
from salmalm.security.crypto import vault, log

# ============================================================
_audit_lock = threading.Lock()  # Audit log writes
_usage_lock = threading.Lock()  # Usage tracking (separate to avoid contention)
_thread_local = threading.local()  # Thread-local DB connections + user context


_all_db_connections: list = []  # Track all connections for shutdown cleanup
_db_connections_lock = threading.Lock()


def _get_db() -> sqlite3.Connection:
    """Get thread-local SQLite connection (reused across calls, WAL mode)."""
    conn = getattr(_thread_local, "audit_conn", None)
    if conn is None:
        AUDIT_DB.parent.mkdir(parents=True, exist_ok=True)  # noqa: F405
        conn = sqlite3.connect(str(AUDIT_DB), check_same_thread=True)  # noqa: F405
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        # Track for shutdown cleanup
        with _db_connections_lock:
            _all_db_connections.append(conn)
        # Auto-create tables on first connection per thread
        conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL, event TEXT NOT NULL,
            detail TEXT, prev_hash TEXT, hash TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS usage_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL, model TEXT NOT NULL,
            input_tokens INTEGER, output_tokens INTEGER, cost REAL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS session_store (
            session_id TEXT PRIMARY KEY,
            messages TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        try:
            conn.execute("ALTER TABLE session_store ADD COLUMN parent_session_id TEXT DEFAULT NULL")
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        try:
            conn.execute("ALTER TABLE session_store ADD COLUMN branch_index INTEGER DEFAULT NULL")
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        try:
            conn.execute('ALTER TABLE session_store ADD COLUMN title TEXT DEFAULT ""')
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        try:
            conn.execute("ALTER TABLE session_store ADD COLUMN user_id INTEGER DEFAULT NULL")
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        conn.execute("""CREATE TABLE IF NOT EXISTS session_message_backup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            messages_json TEXT NOT NULL,
            removed_at TEXT NOT NULL,
            reason TEXT DEFAULT 'rollback'
        )""")
        conn.commit()
        _thread_local.audit_conn = conn
    return conn


def _init_audit_db():
    """Init audit db."""
    conn = _get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL, event TEXT NOT NULL,
        detail TEXT, prev_hash TEXT, hash TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS usage_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL, model TEXT NOT NULL,
        input_tokens INTEGER, output_tokens INTEGER, cost REAL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS session_store (
        session_id TEXT PRIMARY KEY,
        messages TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    try:
        conn.execute("ALTER TABLE session_store ADD COLUMN parent_session_id TEXT DEFAULT NULL")
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    try:
        conn.execute("ALTER TABLE session_store ADD COLUMN branch_index INTEGER DEFAULT NULL")
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    try:
        conn.execute("ALTER TABLE session_store ADD COLUMN user_id INTEGER DEFAULT NULL")
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    conn.execute("""CREATE TABLE IF NOT EXISTS session_message_backup (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        messages_json TEXT NOT NULL,
        removed_at TEXT NOT NULL,
        reason TEXT DEFAULT 'rollback'
    )""")
    conn.commit()


def _ensure_audit_v2_table():
    """Create the v2 audit_log_v2 table with session_id and JSON detail."""
    conn = _get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        session_id TEXT DEFAULT '',
        detail TEXT DEFAULT '{}'
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_v2_ts ON audit_log_v2(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_v2_type ON audit_log_v2(event_type)")
    conn.commit()


# ── Audit log batching ──
_audit_buffer: list = []  # buffered audit entries
_AUDIT_BATCH_SIZE = 20  # flush after this many entries
_AUDIT_FLUSH_INTERVAL = 5.0  # seconds — max delay before flush
_audit_flush_timer: Optional[threading.Timer] = None  # noqa: F405


def _flush_audit_buffer() -> None:
    """Write buffered audit entries to SQLite in a single transaction."""
    global _audit_flush_timer
    with _audit_lock:
        if not _audit_buffer:
            _audit_flush_timer = None
            return
        entries = _audit_buffer[:]
        _audit_buffer.clear()
        _audit_flush_timer = None

    conn = _get_db()
    # Get current chain head
    row = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev = row[0] if row else "0" * 64

    for ts, event, detail, session_id, json_detail in entries:
        # v1: hash-chain
        payload = f"{ts}|{event}|{detail}|{prev}"
        h = hashlib.sha256(payload.encode()).hexdigest()
        conn.execute(
            "INSERT INTO audit_log (ts, event, detail, prev_hash, hash) VALUES (?,?,?,?,?)",
            (ts, event, detail[:500], prev, h),
        )
        prev = h
        # v2: structured
        conn.execute(
            "INSERT INTO audit_log_v2 (timestamp, event_type, session_id, detail) VALUES (?,?,?,?)",
            (ts, event, session_id, json_detail),
        )
    conn.commit()


def _schedule_audit_flush() -> None:
    """Schedule a delayed flush if not already pending."""
    global _audit_flush_timer
    if _audit_flush_timer is None:
        _audit_flush_timer = threading.Timer(_AUDIT_FLUSH_INTERVAL, _flush_audit_buffer)  # noqa: F405
        _audit_flush_timer.daemon = True
        _audit_flush_timer.start()


def audit_log(
    event: str,
    detail: str = "",
    session_id: str = "",
    detail_dict: Optional[dict] = None,
) -> None:
    """Write an audit event to the security log (v1 chain + v2 structured).

    Events are buffered and flushed in batches for performance.
    Flush triggers: batch size (20) or time interval (5s), whichever comes first.

    Args:
        event: event type string (tool_call, api_call, auth_success, etc.)
        detail: plain text detail (for v1 compatibility)
        session_id: associated session ID
        detail_dict: structured detail as dict (serialized to JSON for v2)
    """
    _ensure_audit_v2_table()
    ts = datetime.now(KST).isoformat()  # noqa: F405
    json_detail = json.dumps(detail_dict, ensure_ascii=False) if detail_dict else json.dumps({"text": detail[:500]})

    with _audit_lock:
        _audit_buffer.append((ts, event, detail, session_id, json_detail))
        if len(_audit_buffer) >= _AUDIT_BATCH_SIZE:
            pass  # will flush below
        else:
            _schedule_audit_flush()
            return

    # Flush immediately when batch is full
    _flush_audit_buffer()


def audit_checkpoint() -> Optional[str]:
    """Append current audit chain head hash to a checkpoint file.

    This provides tamper-evidence: if someone modifies the SQLite DB,
    the checkpoint file (append-only) will show a divergence.
    Returns the head hash or None on failure.
    """
    try:
        conn = _get_db()
        row = conn.execute("SELECT hash, id FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        head_hash, head_id = row[0], row[1]
        checkpoint_file = AUDIT_DB.parent / "audit_checkpoint.log"  # noqa: F405
        ts = datetime.now(KST).isoformat()  # noqa: F405
        with open(checkpoint_file, "a") as f:
            f.write(f"{ts} id={head_id} hash={head_hash}\n")
        return head_hash  # type: ignore[no-any-return]
    except Exception as e:  # noqa: broad-except
        return None


def audit_log_cleanup(days: int = 30) -> None:
    """Delete audit_log_v2 entries older than `days` days."""
    from datetime import timedelta

    cutoff = (datetime.now(KST) - timedelta(days=days)).isoformat()  # noqa: F405
    try:
        conn = _get_db()
        _ensure_audit_v2_table()
        deleted = conn.execute("DELETE FROM audit_log_v2 WHERE timestamp < ?", (cutoff,)).rowcount
        conn.commit()
        if deleted:
            log.info(f"[AUDIT] Cleaned up {deleted} audit entries older than {days} days")
    except Exception as e:
        log.warning(f"Audit cleanup error: {e}")


def query_audit_log(limit: int = 50, event_type: Optional[str] = None, session_id: Optional[str] = None) -> list:
    """Query structured audit log entries.

    Returns list of dicts with id, timestamp, event_type, session_id, detail.
    """
    try:
        conn = _get_db()
        _ensure_audit_v2_table()
        sql = "SELECT id, timestamp, event_type, session_id, detail FROM audit_log_v2"
        params: list = []
        conditions = []
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(min(limit, 500))
        rows = conn.execute(sql, params).fetchall()
        results = []
        for r in rows:
            try:
                detail = json.loads(r[4]) if r[4] else {}
            except (json.JSONDecodeError, TypeError):
                detail = {"text": r[4]}
            results.append(
                {
                    "id": r[0],
                    "timestamp": r[1],
                    "event_type": r[2],
                    "session_id": r[3],
                    "detail": detail,
                }
            )
        return results
    except Exception as e:
        log.warning(f"Audit query error: {e}")
        return []


def close_all_db_connections() -> None:
    """Close all tracked SQLite connections (for graceful shutdown)."""
    with _db_connections_lock:
        for conn in _all_db_connections:
            try:
                conn.close()
            except Exception as e:
                log.debug(f"Suppressed: {e}")
        _all_db_connections.clear()
    log.info("[DB] All database connections closed")


class ResponseCache:
    """Simple TTL cache for LLM responses to avoid duplicate calls."""

    def __init__(self, max_size=100, ttl=CACHE_TTL):  # noqa: F405
        """Init  ."""
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    def _key(self, model: str, messages: list, session_id: str = "") -> str:
        # Include last 5 messages for better session isolation even without explicit session_id
        """Key."""
        content = json.dumps({"s": session_id, "m": model, "msgs": messages[-5:]}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(self, model: str, messages: list, session_id: str = "") -> Optional[str]:
        """Get a cached response by key, or None if expired/missing."""
        k = self._key(model, messages, session_id)
        if k in self._cache:
            entry = self._cache[k]
            if time.time() - entry["ts"] < self._ttl:
                self._cache.move_to_end(k)
                log.info("[COST] Cache hit -- saved API call")
                return entry["response"]  # type: ignore[no-any-return]
            del self._cache[k]
        return None

    def put(self, model: str, messages: list, response: str, session_id: str = "") -> None:
        """Store a response in cache with TTL."""
        k = self._key(model, messages, session_id)
        self._cache[k] = {"response": response, "ts": time.time()}
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)


response_cache = ResponseCache()

# _usage_lock already defined at top of file
_usage = {
    "total_input": 0,
    "total_output": 0,
    "total_cost": 0.0,
    "by_model": {},
    "session_start": time.time(),
}

# Production observability metrics
_metrics = {
    "llm_calls": 0,
    "llm_errors": 0,
    "tool_calls": 0,
    "tool_errors": 0,
    "total_cost": 0.0,
    "total_tokens_in": 0,
    "total_tokens_out": 0,
}

# Hard cost cap — stop all LLM calls after this threshold (per session lifetime)
# Override with SALMALM_COST_CAP env var (in USD)
COST_CAP = float(os.environ.get("SALMALM_COST_CAP", "0"))


class CostCapExceeded(Exception):
    """Raised when cumulative API spend exceeds the cost cap."""

    pass


def _restore_usage():
    """Restore cumulative usage from SQLite on startup."""
    try:
        conn = _get_db()
        rows = conn.execute(
            "SELECT model, SUM(input_tokens), SUM(output_tokens), SUM(cost), COUNT(*) FROM usage_stats GROUP BY model"
        ).fetchall()
        for model, inp, out, cost, calls in rows:
            short = model.split("/")[-1] if "/" in model else model
            _usage["total_input"] += inp or 0  # type: ignore[operator]
            _usage["total_output"] += out or 0  # type: ignore[operator]
            _usage["total_cost"] += cost or 0  # type: ignore[operator]
            _usage["by_model"][short] = {
                "input": inp or 0,
                "output": out or 0,  # type: ignore[index]
                "cost": cost or 0,
                "calls": calls or 0,
            }
        if _usage["total_cost"] > 0:  # type: ignore[operator]
            log.info(f"[STAT] Usage restored: ${_usage['total_cost']:.4f} total")
    except Exception as e:
        log.warning(f"Usage restore failed: {e}")


def check_cost_cap() -> None:
    """Raise CostCapExceeded if cumulative cost exceeds the cap. 0 = disabled."""
    if COST_CAP <= 0:
        return
    with _usage_lock:
        if _usage["total_cost"] >= COST_CAP:
            raise CostCapExceeded(
                f"Cost cap exceeded: ${_usage['total_cost']:.2f} >= ${COST_CAP:.2f}. "
                f"Increase SALMALM_COST_CAP env var or restart."
            )


def set_current_user_id(user_id: Optional[int]) -> None:
    """Set the current user_id for cost tracking (thread-local)."""
    _thread_local.current_user_id = user_id


def get_current_user_id() -> Optional[int]:
    """Get the current user_id from thread-local context."""
    return getattr(_thread_local, "current_user_id", None)


def track_usage(model: str, input_tokens: int, output_tokens: int, user_id: Optional[int] = None) -> None:
    """Record token usage and cost for a model call."""
    # Auto-detect user_id from thread-local if not provided
    if user_id is None:
        user_id = get_current_user_id()
    with _usage_lock:
        short = model.split("/")[-1] if "/" in model else model
        cost_info = MODEL_COSTS.get(short, {"input": 1.0, "output": 5.0})  # noqa: F405
        cost = (input_tokens * cost_info["input"] + output_tokens * cost_info["output"]) / 1_000_000
        _usage["total_input"] += input_tokens  # type: ignore[operator]
        _usage["total_output"] += output_tokens  # type: ignore[operator]
        _usage["total_cost"] += cost  # type: ignore[operator]
        if short not in _usage["by_model"]:  # type: ignore[operator]
            _usage["by_model"][short] = {
                "input": 0,
                "output": 0,
                "cost": 0.0,
                "calls": 0,
            }  # type: ignore[index]
        _usage["by_model"][short]["input"] += input_tokens  # type: ignore[index]
        _usage["by_model"][short]["output"] += output_tokens  # type: ignore[index]
        _usage["by_model"][short]["cost"] += cost  # type: ignore[index]
        _usage["by_model"][short]["calls"] += 1  # type: ignore[index]
        # Persist to SQLite (with user_id for multi-tenant tracking)
        try:
            conn = _get_db()
            # Ensure user_id column exists
            try:
                conn.execute("ALTER TABLE usage_stats ADD COLUMN user_id INTEGER DEFAULT NULL")
            except Exception as e:
                log.debug(f"Suppressed: {e}")
            conn.execute(
                "INSERT INTO usage_stats (ts, model, input_tokens, output_tokens, cost, user_id) VALUES (?,?,?,?,?,?)",
                (
                    datetime.now(KST).isoformat(),
                    model,
                    input_tokens,
                    output_tokens,
                    cost,
                    user_id,
                ),
            )  # noqa: F405
            conn.commit()
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        # Record cost against user quota
        if user_id:
            try:
                from salmalm.features.users import user_manager

                user_manager.record_cost(user_id, cost)
            except Exception as e:
                log.debug(f"Quota record error: {e}")


def get_usage_report() -> dict:
    """Generate a formatted usage report with token counts and costs."""
    with _usage_lock:
        elapsed = time.time() - _usage["session_start"]  # type: ignore[operator]
        return {**_usage, "elapsed_hours": round(elapsed / 3600, 2)}


class ModelRouter:
    """Routes queries to appropriate models based on complexity."""

    # Tier pools sourced from constants.py MODEL_TIERS (single source of truth)
    TIERS = MODEL_TIERS  # noqa: F405

    _MODEL_PREF_FILE = DATA_DIR / ".model_pref"  # noqa: F405

    def __init__(self) -> None:
        """Init  ."""
        self.default_tier = 2
        self.force_model: Optional[str] = None
        # Restore persisted model preference
        try:
            if self._MODEL_PREF_FILE.exists():
                saved = self._MODEL_PREF_FILE.read_text().strip()
                if saved and saved != "auto":
                    self.force_model = saved
                    log.info(f"[FIX] Restored model preference: {saved}")
        except Exception as e:
            log.debug(f"Suppressed: {e}")

    def set_force_model(self, model: Optional[str]) -> None:
        """Set and persist model preference."""
        self.force_model = model
        try:
            if model:
                self._MODEL_PREF_FILE.write_text(model)
            elif self._MODEL_PREF_FILE.exists():
                self._MODEL_PREF_FILE.unlink()
        except Exception as e:
            log.error(f"Failed to persist model pref: {e}")

    def route(self, user_message: str, has_tools: bool = False, iteration: int = 0) -> str:
        """Route a message to the best model based on intent classification."""
        if self.force_model:
            return self.force_model

        msg = user_message.lower()
        msg_len = len(user_message)

        # Tool-heavy iterations → always Tier 2+
        if iteration > 2:
            return self._pick_available(2)

        # Tier 3: complex tasks
        complex_score = sum(1 for kw in COMPLEX_INDICATORS if kw in msg)  # noqa: F405
        tool_hint_score = sum(1 for kw in TOOL_HINT_KEYWORDS if kw in msg)  # noqa: F405
        if complex_score >= 2 or msg_len > 1000 or (complex_score >= 1 and tool_hint_score >= 1):
            return self._pick_available(3)

        # Tier 2: tool usage likely or medium complexity
        if has_tools and (tool_hint_score >= 1 or msg_len > 300):
            return self._pick_available(2)

        # Tier 1: simple queries only
        if msg_len < SIMPLE_QUERY_MAX_CHARS and not has_tools and complex_score == 0:  # noqa: F405
            return self._pick_available(1)

        # Tier 2: default
        return self._pick_available(2)

    _OR_PROVIDERS = frozenset(["deepseek", "meta-llama", "mistralai", "qwen"])

    def _has_key(self, provider: str) -> bool:
        """Has key."""
        if provider == "ollama":
            return True  # Ollama always available (local)
        if provider in self._OR_PROVIDERS:
            return bool(vault.get("openrouter_api_key"))
        return bool(vault.get(f"{provider}_api_key"))

    def _pick_available(self, tier: int) -> str:
        """Pick available."""
        models = self.TIERS.get(tier, self.TIERS[2])
        for m in models:
            provider = m.split("/")[0]
            if self._has_key(provider):
                return m
        # Fallback: try any available model
        for t in [2, 1, 3]:
            for m in self.TIERS.get(t, []):
                provider = m.split("/")[0]
                if self._has_key(provider):
                    return m
        return "google/gemini-3-flash-preview"  # last resort


router = ModelRouter()


# ============================================================
# Compaction Summary Persistence — cross-session continuity
# ============================================================
# Compaction extracted to salmalm/core/compaction.py
from salmalm.core.compaction import (  # noqa: E402
    compact_messages,
    _persist_compaction_summary,
    _restore_compaction_summary,
    _msg_content_str,
)

from salmalm.core.search import TFIDFSearch  # noqa: E402

_tfidf = TFIDFSearch()


# Session + session management extracted to salmalm/core/session_store.py
from salmalm.core.session_store import (  # noqa: E402
    Session,
    _tg_bot,
    get_telegram_bot,
    set_telegram_bot,
    _llm_cron,
    _sessions,
    _session_lock,
    _cleanup_sessions,
    get_session,
    rollback_session,
    branch_session,
    _SESSIONS_DIR,
    save_session_to_disk,
    restore_session,
    restore_all_sessions_from_disk,
)


# CronScheduler + HeartbeatManager extracted to salmalm/core/scheduler.py
from salmalm.core.llm_cron import LLMCronManager  # noqa: E402
from salmalm.core.scheduler import CronScheduler, HeartbeatManager  # noqa: E402

cron = CronScheduler()
heartbeat = HeartbeatManager()


# ============================================================
# CONTEXT COMPACTION — Auto-compress old messages when token count exceeds threshold
# ============================================================
AUTO_COMPACT_TOKEN_THRESHOLD = 80_000  # ~80K tokens (chars/4 approximation = 320K chars)
COMPACT_PRESERVE_RECENT = 10  # Keep last N messages intact


def _estimate_tokens(messages: list) -> int:
    """Estimate token count using chars/4 approximation (stdlib only)."""
    total_chars = sum(len(_msg_content_str(m)) for m in messages)
    return total_chars // 4


def compact_session(session_id: str, force: bool = False) -> str:
    """Compact a session's conversation by summarizing old messages.

    If force=True, compact regardless of token count.
    Returns a status message.
    """
    session = get_session(session_id)
    est_tokens = _estimate_tokens(session.messages)

    if not force and est_tokens < AUTO_COMPACT_TOKEN_THRESHOLD:
        return (
            f"Context size ~{est_tokens:,} tokens — no compaction needed (threshold: {AUTO_COMPACT_TOKEN_THRESHOLD:,})."
        )

    # Separate system messages and conversation
    system_msgs = [m for m in session.messages if m["role"] == "system"][:1]
    non_system = [m for m in session.messages if m["role"] != "system"]

    if len(non_system) <= COMPACT_PRESERVE_RECENT:
        return f"Only {len(non_system)} messages — too few to compact."

    # Split: old messages to summarize, recent to preserve
    old_msgs = non_system[:-COMPACT_PRESERVE_RECENT]
    recent_msgs = non_system[-COMPACT_PRESERVE_RECENT:]

    # Build summary request from old messages
    summary_parts = []
    for m in old_msgs[-30:]:  # Summarize last 30 old messages max
        role = m.get("role", "?")
        text = _msg_content_str(m)[:500]
        if text.strip():
            summary_parts.append(f"[{role}]: {text}")

    if not summary_parts:
        return "No substantial messages to compact."

    summary_text = "\n".join(summary_parts)

    from salmalm.core.llm import call_llm

    summary_model = router._pick_available(1)
    summ_msgs = [
        {
            "role": "system",
            "content": (
                "Summarize the following conversation concisely but thoroughly. "
                "You MUST preserve:\n"
                "1. Key decisions and conclusions\n"
                "2. Task progress and what was accomplished\n"
                "3. Important facts, numbers, file paths, code context\n"
                "4. User preferences and constraints mentioned\n"
                "5. Any pending/blocked items\n"
                "Write in the same language as the conversation. "
                "Use 5-15 sentences. Do NOT start with 'The conversation...' — "
                "write as a factual summary that can serve as context for continued work."
            ),
        },
        {"role": "user", "content": summary_text},
    ]
    try:
        result = call_llm(summ_msgs, model=summary_model, max_tokens=1200)
    except Exception as e:
        # Compaction error: preserve original messages, skip compaction
        # Compaction error: preserve original messages, skip compaction
        log.error(f"[COMPACT] LLM call failed during compaction: {e}")
        return f"❌ Compaction skipped — LLM error: {e}. Original messages preserved."

    summary = result.get("content", "")
    if not summary:
        return "❌ Compaction failed — could not generate summary. Original preserved."

    # Guard: if summary is longer than original, don't use it
    original_chars = sum(len(_msg_content_str(m)) for m in old_msgs)
    if len(summary) > original_chars:
        log.warning(
            f"[COMPACT] Summary ({len(summary)} chars) longer than original ({original_chars} chars) — skipping"
        )
        return "⚠️ Compaction result was longer than original — skipped."

    # Rebuild session messages
    compacted = (
        system_msgs
        + [
            {
                "role": "system",
                "content": f"[Conversation Summary — {len(old_msgs)} messages compacted]\n{summary}",
            }
        ]
        + recent_msgs
    )

    old_tokens = est_tokens
    session.messages = compacted
    new_tokens = _estimate_tokens(session.messages)

    log.info(
        f"[COMPACT] Session {session_id}: {old_tokens:,} → {new_tokens:,} tokens, {len(old_msgs)} messages summarized"
    )
    return f"✅ Compacted: ~{old_tokens:,} → ~{new_tokens:,} tokens ({len(old_msgs)} messages summarized)."


def auto_compact_if_needed(session_id: str) -> None:
    """Check and auto-compact session if over token threshold."""
    session = get_session(session_id)
    est_tokens = _estimate_tokens(session.messages)
    if est_tokens >= AUTO_COMPACT_TOKEN_THRESHOLD:
        log.info(f"[COMPACT] Auto-compacting session {session_id} (~{est_tokens:,} tokens)")
        compact_session(session_id, force=True)


# ============================================================
# DAILY MEMORY LOG
# ============================================================
def auto_title_session(session_id: str, first_message: str) -> None:
    """Generate a title from the first user message (first 50 chars, cleaned up).
    No LLM call — just text extraction for cost savings."""
    if not first_message or not first_message.strip():
        return
    # Clean up: strip leading slashes/commands, take first 50 chars
    title = first_message.strip()
    # Skip command messages
    if title.startswith("/"):
        return
    # Take first line only, then first 50 chars
    title = title.split("\n")[0][:50].strip()
    # Remove trailing incomplete word if cut mid-word
    if len(first_message.strip().split("\n")[0]) > 50 and " " in title:
        title = title[: title.rfind(" ")]
    if not title:
        return
    try:
        conn = _get_db()
        # Ensure title column exists
        try:
            conn.execute('ALTER TABLE session_store ADD COLUMN title TEXT DEFAULT ""')
            conn.commit()
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        conn.execute(
            'UPDATE session_store SET title=? WHERE session_id=? AND (title IS NULL OR title="")',
            (title, session_id),
        )
        conn.commit()
    except Exception as e:
        log.warning(f"Auto-title error: {e}")


def write_daily_log(entry: str) -> None:
    """Append to today's memory log."""
    today = datetime.now(KST).strftime("%Y-%m-%d")  # noqa: F405
    log_file = MEMORY_DIR / f"{today}.md"  # noqa: F405
    MEMORY_DIR.mkdir(exist_ok=True)  # noqa: F405
    header = f"# {today} Daily Log\n\n" if not log_file.exists() else ""
    with open(log_file, "a", encoding="utf-8") as f:
        ts = datetime.now(KST).strftime("%H:%M")  # noqa: F405
        f.write(f"{header}- [{ts}] {entry}\n")


def edit_message(session_id: str, message_index: int, new_content: str) -> dict:
    """Edit a message at the given index in a session.

    Backs up the original messages first, then replaces the content.
    Returns {'ok': True, 'index': int} or {'ok': False, 'error': ...}.
    """
    session = get_session(session_id)
    if message_index < 0 or message_index >= len(session.messages):
        return {"ok": False, "error": f"Invalid message_index: {message_index}"}
    msg = session.messages[message_index]
    if msg.get("role") != "user":
        return {"ok": False, "error": "Can only edit user messages"}
    # Backup current state
    conn = _get_db()
    conn.execute(
        "INSERT INTO session_message_backup (session_id, messages_json, removed_at, reason) VALUES (?,?,?,?)",
        (
            session_id,
            json.dumps(session.messages, ensure_ascii=False),
            datetime.now(KST).isoformat(),
            "edit",
        ),
    )  # noqa: F405
    conn.commit()
    # Update the message content
    session.messages[message_index]["content"] = new_content
    # Remove all messages after this index (assistant response will be regenerated)
    removed_count = len(session.messages) - message_index - 1
    session.messages = session.messages[: message_index + 1]
    session._persist()
    try:
        save_session_to_disk(session_id)
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    audit_log(
        "message_edit",
        f"{session_id}: edited index {message_index}, removed {removed_count} subsequent",
        session_id=session_id,
    )
    return {"ok": True, "index": message_index, "removed_after": removed_count}


def delete_message(session_id: str, message_index: int) -> dict:
    """Delete a user message and its paired assistant response.

    Backs up removed messages to session_message_backup table.
    Returns {'ok': True, 'removed': int} or {'ok': False, 'error': ...}.
    """
    session = get_session(session_id)
    if message_index < 0 or message_index >= len(session.messages):
        return {"ok": False, "error": f"Invalid message_index: {message_index}"}
    msg = session.messages[message_index]
    if msg.get("role") != "user":
        return {"ok": False, "error": "Can only delete user messages"}
    indices_to_remove = [message_index]
    # Also remove the paired assistant message (next one if it's assistant)
    if message_index + 1 < len(session.messages) and session.messages[message_index + 1].get("role") == "assistant":
        indices_to_remove.append(message_index + 1)
    # Backup
    removed_msgs = [session.messages[i] for i in indices_to_remove]
    conn = _get_db()
    conn.execute(
        "INSERT INTO session_message_backup (session_id, messages_json, removed_at, reason) VALUES (?,?,?,?)",
        (
            session_id,
            json.dumps(removed_msgs, ensure_ascii=False),
            datetime.now(KST).isoformat(),
            "delete",
        ),
    )  # noqa: F405
    conn.commit()
    # Remove in reverse order
    for i in sorted(indices_to_remove, reverse=True):
        session.messages.pop(i)
    session._persist()
    try:
        save_session_to_disk(session_id)
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    audit_log(
        "message_delete",
        f"{session_id}: deleted {len(indices_to_remove)} messages at index {message_index}",
        session_id=session_id,
    )
    return {"ok": True, "removed": len(indices_to_remove)}


def search_messages(query: str, limit: int = 20) -> list:
    """Search messages across all sessions using LIKE matching.

    Returns list of {'session_id', 'role', 'content', 'match_snippet', 'updated_at'}.
    """
    if not query or len(query.strip()) < 2:
        return []
    query = query.strip()
    results = []
    try:
        conn = _get_db()
        rows = conn.execute(
            "SELECT session_id, messages, updated_at FROM session_store ORDER BY updated_at DESC"
        ).fetchall()
        for sid, msgs_json, updated_at in rows:
            try:
                msgs = json.loads(msgs_json)
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
            for msg in msgs:
                role = msg.get("role", "")
                if role not in ("user", "assistant"):
                    continue
                content = _msg_content_str(msg)
                if query.lower() in content.lower():
                    # Extract snippet around the match
                    idx = content.lower().index(query.lower())
                    start = max(0, idx - 40)
                    end = min(len(content), idx + len(query) + 40)
                    snippet = ("..." if start > 0 else "") + content[start:end] + ("..." if end < len(content) else "")
                    results.append(
                        {
                            "session_id": sid,
                            "role": role,
                            "content": content[:200],
                            "match_snippet": snippet,
                            "updated_at": updated_at,
                        }
                    )
                    if len(results) >= limit:
                        return results
    except Exception as e:
        log.warning(f"search_messages error: {e}")
    return results


# Re-export from agents.py
from salmalm.features.agents import SubAgent, SkillLoader, PluginLoader

# Module-level exports for convenience
__all__ = [
    "audit_log",
    "audit_log_cleanup",
    "query_audit_log",
    "close_all_db_connections",
    "response_cache",
    "router",
    "track_usage",
    "get_usage_report",
    "check_cost_cap",
    "CostCapExceeded",
    "_metrics",
    "compact_messages",
    "get_session",
    "write_daily_log",
    "cron",
    "compact_session",
    "auto_compact_if_needed",
    "_estimate_tokens",
    "save_session_to_disk",
    "restore_session",
    "restore_all_sessions_from_disk",
    "memory_manager",
    "heartbeat",
    "get_telegram_bot",
    "set_telegram_bot",
    "Session",
    "MemoryManager",
    "HeartbeatManager",
    "LLMCronManager",
    "SubAgent",
    "SkillLoader",
    "PluginLoader",
    "search_messages",
    "edit_message",
    "delete_message",
]
