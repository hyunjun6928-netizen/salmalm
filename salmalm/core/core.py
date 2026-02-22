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
from pathlib import Path
from typing import Callable, Optional

from salmalm.constants import (
    AUDIT_DB,
    BASE_DIR,
    CACHE_TTL,
    COMPACTION_THRESHOLD,
    COMPLEX_INDICATORS,
    DATA_DIR,
    KST,
    MEMORY_DIR,
    MEMORY_FILE,
    MODEL_COSTS,
    MODEL_TIERS,
    SIMPLE_QUERY_MAX_CHARS,
    TOOL_HINT_KEYWORDS,
    WORKSPACE_DIR,
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
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE session_store ADD COLUMN branch_index INTEGER DEFAULT NULL")
        except Exception:
            pass
        try:
            conn.execute('ALTER TABLE session_store ADD COLUMN title TEXT DEFAULT ""')
        except Exception:
            pass
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
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE session_store ADD COLUMN branch_index INTEGER DEFAULT NULL")
    except Exception:
        pass
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
    except Exception:
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
            except Exception:
                pass
        _all_db_connections.clear()
    log.info("[DB] All database connections closed")


class ResponseCache:
    """Simple TTL cache for LLM responses to avoid duplicate calls."""

    def __init__(self, max_size=100, ttl=CACHE_TTL):  # noqa: F405
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    def _key(self, model: str, messages: list, session_id: str = "") -> str:
        # Include last 5 messages for better session isolation even without explicit session_id
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
            except Exception:
                pass
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

    def __init__(self):
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
        if provider == "ollama":
            return True  # Ollama always available (local)
        if provider in self._OR_PROVIDERS:
            return bool(vault.get("openrouter_api_key"))
        return bool(vault.get(f"{provider}_api_key"))

    def _pick_available(self, tier: int) -> str:
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
def _persist_compaction_summary(session_id: str, summary: str) -> None:
    """Save compaction summary to DB for cross-session restoration.

    OpenClaw-style: when a session is restored after restart, the last
    compaction summary is injected so the AI retains prior context.
    """
    if not summary or not session_id:
        return
    try:
        conn = _get_db()
        conn.execute("""CREATE TABLE IF NOT EXISTS compaction_summaries (
            session_id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL,
            message_count INTEGER DEFAULT 0
        )""")
        conn.execute(
            "INSERT OR REPLACE INTO compaction_summaries (session_id, summary, created_at) VALUES (?,?,?)",
            (session_id, summary[:10000], datetime.now(KST).isoformat()),
        )
        conn.commit()
    except Exception as e:
        log.warning(f"[PKG] Summary persist error: {e}")


def _restore_compaction_summary(session_id: str) -> Optional[str]:
    """Restore last compaction summary for a session (cross-session continuity)."""
    try:
        conn = _get_db()
        row = conn.execute(
            "SELECT summary FROM compaction_summaries WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _msg_content_str(msg: dict) -> str:
    """Extract text content from a message (handles list content blocks)."""
    c = msg.get("content", "")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return str(c)


def compact_messages(
    messages: list,
    model: Optional[str] = None,
    session: Optional["Session"] = None,
    on_status: Optional[Callable] = None,
) -> list:
    """Multi-stage compaction: trim tool results → drop old tools → summarize.

    OpenClaw-quality compaction with 5 stages:
      1. Strip binary/image data from old messages
      2. Trim long tool results (keep first 500 chars)
      3. Drop old tool messages, keep user/assistant
      4. Truncate verbose old assistant messages
      5. LLM summarization of remaining old context

    Hard limits: max 100 messages, max 500K chars (≈125K tokens).
    Pre-compaction: flush memory to persistent store.
    Post-compaction: inject summary as system message, not user message.
    """
    # Empty conversation guard
    if not messages:
        return messages

    MAX_MESSAGES = 100
    MAX_CHARS = 500_000

    # OpenClaw-style: pre-compaction memory flush
    total_chars_check = sum(len(_msg_content_str(m)) for m in messages)
    if session and total_chars_check > COMPACTION_THRESHOLD * 0.8:  # noqa: F405
        try:
            memory_manager.flush_before_compaction(session)
        except Exception as e:
            log.warning(f"[MEM] Memory flush error: {e}")

    # Hard message count limit
    if len(messages) > MAX_MESSAGES:
        system_msgs = [m for m in messages if m["role"] == "system"][:1]
        recent = [m for m in messages if m["role"] != "system"][-40:]
        messages = system_msgs + recent
        log.warning(f"[CUT] Hard msg limit: truncated to {len(messages)} messages")

    total_chars = sum(len(_msg_content_str(m)) for m in messages)

    # Hard char limit — emergency truncation
    if total_chars > MAX_CHARS:
        system_msgs = [m for m in messages if m["role"] == "system"][:1]
        recent = [m for m in messages if m["role"] != "system"][-20:]
        messages = system_msgs + recent
        total_chars = sum(len(_msg_content_str(m)) for m in messages)
        log.warning(f"[CUT] Hard char limit: truncated to {len(messages)} msgs ({total_chars} chars)")

    if total_chars < COMPACTION_THRESHOLD:  # noqa: F405
        return messages

    # Notify UI that compaction is in progress
    if on_status:
        try:
            on_status("compacting", "✨ Compacting context...")
        except Exception:
            pass

    log.info(f"[PKG] Compacting {len(messages)} messages ({total_chars} chars)")

    # Stage 1: Strip binary/image data from old messages
    trimmed = []
    for m in messages:
        if m["role"] == "user" and isinstance(m.get("content"), list):
            new_content = []
            for block in m["content"]:
                if isinstance(block, dict) and block.get("type") == "image":
                    new_content.append({"type": "text", "text": "[Image attached]"})
                elif isinstance(block, dict) and block.get("type") == "image_url":
                    new_content.append({"type": "text", "text": "[Image attached]"})
                else:
                    new_content.append(block)
            trimmed.append({**m, "content": new_content})
        else:
            trimmed.append(m)

    # Stage 2: Trim long tool results (keep first 500 chars)
    for i, m in enumerate(trimmed):
        if m["role"] == "tool" and len(_msg_content_str(m)) > 500:
            trimmed[i] = {**m, "content": _msg_content_str(m)[:500] + "\n... [truncated]"}
        # Also trim tool_result blocks inside user messages (Anthropic format)
        elif m["role"] == "user" and isinstance(m.get("content"), list):
            new_blocks = []
            for block in m["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    content = block.get("content", "")
                    if isinstance(content, str) and len(content) > 500:
                        new_blocks.append({**block, "content": content[:500] + "\n... [truncated]"})
                    else:
                        new_blocks.append(block)
                else:
                    new_blocks.append(block)
            trimmed[i] = {**m, "content": new_blocks}

    total_after_trim = sum(len(_msg_content_str(m)) for m in trimmed)
    if total_after_trim < COMPACTION_THRESHOLD:  # noqa: F405
        log.info(f"[PKG] Stage 2 sufficient: {total_chars} -> {total_after_trim} chars")
        return trimmed

    # Stage 3: Drop old tool messages entirely, keep last 10 messages
    system_msgs = [m for m in trimmed if m["role"] == "system"]
    non_system = [m for m in trimmed if m["role"] != "system"]
    recent = non_system[-10:]
    old = non_system[:-10]

    # Drop tool/tool_result messages from old, keep user/assistant
    old_important = [m for m in old if m["role"] in ("user", "assistant")]

    stage3 = system_msgs + old_important + recent
    total_after_drop = sum(len(_msg_content_str(m)) for m in stage3)
    if total_after_drop < COMPACTION_THRESHOLD:  # noqa: F405
        log.info(f"[PKG] Stage 3 sufficient: {total_chars} -> {total_after_drop} chars")
        return stage3

    # Stage 4: Truncate verbose old assistant messages (keep first 800 chars each)
    stage4_old = []
    for m in old_important:
        txt = _msg_content_str(m)
        if m["role"] == "assistant" and len(txt) > 800:
            stage4_old.append({**m, "content": txt[:800] + "\n... [compacted]"})
        elif m["role"] == "user" and len(txt) > 500:
            stage4_old.append({**m, "content": txt[:500] + "\n... [compacted]"})
        else:
            stage4_old.append(m)

    stage4 = system_msgs + stage4_old + recent
    total_after_trunc = sum(len(_msg_content_str(m)) for m in stage4)
    if total_after_trunc < COMPACTION_THRESHOLD:  # noqa: F405
        log.info(f"[PKG] Stage 4 sufficient: {total_chars} -> {total_after_trunc} chars")
        return stage4

    # Stage 5: LLM summarization of old context
    to_summarize = stage4_old
    if not to_summarize:
        return system_msgs + recent

    # Build structured summary input (preserve more context than before)
    summary_parts = []
    for m in to_summarize[-30:]:  # Up to 30 old messages
        role = m["role"]
        txt = _msg_content_str(m)[:400]
        if txt.strip():
            summary_parts.append(f"[{role}]: {txt}")

    summary_text = "\n".join(summary_parts)

    from salmalm.core.llm import call_llm

    # Pick cheapest available model for summarization (avoid hardcoded google)
    summary_model = router._pick_available(1)
    _summ_msgs = [
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
    # Note: call_llm is sync (urllib). Always call directly since compact_messages
    # is invoked from sync context. If ever called from async, wrap in run_in_executor.
    try:
        summary_result = call_llm(_summ_msgs, model=summary_model, max_tokens=1200)
    except Exception as e:
        # Compaction LLM failed — fall back to stage 4 result (no summary)
        log.error(f"[PKG] Stage 5 LLM failed: {e} — using stage 4 result")
        return stage4

    summary_content = summary_result.get("content", "")
    if not summary_content or len(summary_content) < 20:
        log.warning("[PKG] Stage 5 produced empty/short summary — using stage 4 result")
        return stage4

    # Guard: if summary is longer than what it replaces, skip it
    original_chars = sum(len(_msg_content_str(m)) for m in to_summarize)
    if len(summary_content) > original_chars:
        log.warning(f"[PKG] Summary ({len(summary_content)}) > original ({original_chars}) — using stage 4")
        return stage4

    compacted = (
        system_msgs
        + [
            {
                "role": "system",
                "content": f"[Previous conversation summary — {len(to_summarize)} messages compacted]\n{summary_content}",
            }
        ]
        + recent
    )

    # Persist compaction summary for cross-session continuity
    if session:
        try:
            _persist_compaction_summary(getattr(session, "id", ""), summary_content)
        except Exception as e:
            log.warning(f"[PKG] Summary persistence error: {e}")

    log.info(
        f"[PKG] Stage 5 compacted: {len(messages)} -> {len(compacted)} messages, "
        f"{total_chars} → {sum(len(_msg_content_str(m)) for m in compacted)} chars"
    )
    return compacted


# ============================================================
import math  # noqa: F811


class TFIDFSearch:
    """Lightweight TF-IDF + cosine similarity search. No external deps."""

    def __init__(self):
        self._docs: list = []  # [(label, line_no, text, tokens)]
        self._idf: dict = {}  # term -> IDF score
        self._built = False
        self._last_index_time = 0
        self._stop_words = frozenset(
            [
                "의",
                "가",
                "이",
                "은",
                "는",
                "을",
                "를",
                "에",
                "에서",
                "로",
                "으로",
                "와",
                "과",
                "도",
                "만",
                "부터",
                "까지",
                "에게",
                "한테",
                "에서의",
                "the",
                "a",
                "an",
                "is",
                "are",
                "was",
                "were",
                "be",
                "been",
                "and",
                "or",
                "but",
                "in",
                "on",
                "at",
                "to",
                "for",
                "of",
                "with",
                "that",
                "this",
                "it",
                "not",
                "no",
                "if",
                "then",
                "so",
                "as",
                "by",
            ]
        )

    def _tokenize(self, text: str) -> list:
        """Split text into normalized tokens."""
        text = text.lower()
        # Split on non-alphanumeric (keeping Korean chars)
        tokens = re.findall(r"[\w가-힣]+", text)
        return [t for t in tokens if len(t) > 1 and t not in self._stop_words]

    def _index_files(self):
        """Build index from MEMORY.md, memory/*.md, uploads/*.txt etc."""
        now = time.time()
        if self._built and now - self._last_index_time < 300:  # Re-index every 5 min
            return

        self._docs = []
        doc_freq: dict = {}  # term -> number of docs containing it  # type: ignore[var-annotated]
        search_files = []

        if MEMORY_FILE.exists():  # noqa: F405
            search_files.append(("MEMORY.md", MEMORY_FILE))  # noqa: F405
        for f in sorted(MEMORY_DIR.glob("*.md")):  # noqa: F405
            search_files.append((f"memory/{f.name}", f))
        uploads_dir = WORKSPACE_DIR / "uploads"  # noqa: F405
        if uploads_dir.exists():
            for f in uploads_dir.glob("*"):
                if f.suffix.lower() in (
                    ".txt",
                    ".md",
                    ".py",
                    ".js",
                    ".json",
                    ".csv",
                    ".html",
                    ".css",
                    ".log",
                    ".xml",
                    ".yaml",
                    ".yml",
                ):
                    search_files.append((f"uploads/{f.name}", f))
        # Also index skills
        skills_dir = WORKSPACE_DIR / "skills"  # noqa: F405
        if skills_dir.exists():
            for f in skills_dir.glob("**/*.md"):
                search_files.append((f"skills/{f.relative_to(skills_dir)}", f))

        for label, fpath in search_files:
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines()
                # Index in chunks of 3 lines for context
                for i in range(0, len(lines), 2):
                    chunk = "\n".join(lines[i : i + 3])
                    if not chunk.strip():
                        continue
                    tokens = self._tokenize(chunk)
                    if not tokens:
                        continue
                    # TF for this chunk
                    tf = {}  # type: ignore[var-annotated]
                    for t in tokens:
                        tf[t] = tf.get(t, 0) + 1
                    self._docs.append((label, i + 1, chunk, tf))
                    # Doc frequency
                    for t in set(tokens):
                        doc_freq[t] = doc_freq.get(t, 0) + 1
            except Exception:
                continue

        # Compute IDF
        n_docs = len(self._docs)
        if n_docs > 0:
            self._idf = {t: math.log(n_docs / (1 + df)) for t, df in doc_freq.items()}
        self._built = True
        self._last_index_time = now  # type: ignore[assignment]
        log.info(f"[SEARCH] TF-IDF index built: {len(self._docs)} chunks from {len(search_files)} files")

    def search(self, query: str, max_results: int = 5) -> list:
        """Search with TF-IDF + cosine similarity. Returns [(score, label, lineno, snippet)]."""
        self._index_files()
        if not self._docs:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Query TF-IDF vector
        query_tf = {}  # type: ignore[var-annotated]
        for t in query_tokens:
            query_tf[t] = query_tf.get(t, 0) + 1
        query_vec = {t: tf * self._idf.get(t, 0) for t, tf in query_tf.items()}
        query_norm = math.sqrt(sum(v**2 for v in query_vec.values()))
        if query_norm == 0:
            return []

        # Score each document
        scored = []
        for label, lineno, chunk, doc_tf in self._docs:
            doc_vec = {t: tf * self._idf.get(t, 0) for t, tf in doc_tf.items()}
            # Cosine similarity
            dot = sum(query_vec.get(t, 0) * doc_vec.get(t, 0) for t in set(query_vec) | set(doc_vec))
            doc_norm = math.sqrt(sum(v**2 for v in doc_vec.values()))
            if doc_norm == 0:
                continue
            similarity = dot / (query_norm * doc_norm)
            if similarity > 0.05:  # Threshold
                scored.append((similarity, label, lineno, chunk))

        scored.sort(key=lambda x: -x[0])
        return scored[:max_results]


_tfidf = TFIDFSearch()


# ============================================================
# MEMORY MANAGER — delegated to salmalm.memory module
# ============================================================
from salmalm.core.memory import MemoryManager, memory_manager


# ============================================================
# LLM CRON MANAGER — Scheduled tasks with LLM execution
# ============================================================
class LLMCronManager:
    """OpenClaw-style LLM cron with isolated session execution.

    Each cron job runs in its own isolated session (no cross-contamination).
    Completed tasks announce results to configured channels.
    """

    _JOBS_FILE = BASE_DIR / ".cron_jobs.json"  # noqa: F405

    def __init__(self):
        self.jobs = []

    def load_jobs(self) -> None:
        """Load persisted cron jobs from file."""
        try:
            if self._JOBS_FILE.exists():
                self.jobs = json.loads(self._JOBS_FILE.read_text())
                log.info(f"[CRON] Loaded {len(self.jobs)} LLM cron jobs")
        except Exception as e:
            log.error(f"Failed to load cron jobs: {e}")
            self.jobs = []

    def save_jobs(self) -> None:
        """Persist cron jobs to file."""
        try:
            self._JOBS_FILE.write_text(json.dumps(self.jobs, ensure_ascii=False, indent=2))
        except Exception as e:
            log.error(f"Failed to save cron jobs: {e}")

    def add_job(
        self,
        name: str,
        schedule: dict,
        prompt: str,
        model: Optional[str] = None,
        notify=True,
    ) -> dict:
        """Add a new LLM cron job.
        schedule: {'kind': 'cron', 'expr': '0 6 * * *', 'tz': 'Asia/Seoul'}
                  {'kind': 'every', 'seconds': 3600}
        notify: True/False or dict e.g. {"channel":"telegram","chat_id":"123"}
                  {'kind': 'at', 'time': '2026-02-18T06:00:00+09:00'}
        """
        import uuid as _uuid

        job = {
            "id": str(_uuid.uuid4())[:8],
            "name": name,
            "schedule": schedule,
            "prompt": prompt,
            "model": model,
            "notify": notify,
            "enabled": True,
            "created": datetime.now(KST).isoformat(),  # noqa: F405
            "last_run": None,
            "run_count": 0,
        }
        self.jobs.append(job)
        self.save_jobs()
        log.info(f"[CRON] LLM cron job added: {name} ({job['id']})")
        return job

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled cron job by ID."""
        before = len(self.jobs)
        self.jobs = [j for j in self.jobs if j["id"] != job_id]
        if len(self.jobs) < before:
            self.save_jobs()
            return True
        return False

    def list_jobs(self) -> list:
        """List all registered cron jobs with their schedules."""
        return [
            {
                "id": j["id"],
                "name": j["name"],
                "schedule": j["schedule"],
                "enabled": j["enabled"],
                "last_run": j["last_run"],
                "run_count": j["run_count"],
            }
            for j in self.jobs
        ]

    def _should_run(self, job: dict) -> bool:
        """Check if a job should run now."""
        if not job["enabled"]:
            return False
        sched = job["schedule"]
        now = datetime.now(KST)  # noqa: F405

        if sched["kind"] == "every":
            if not job["last_run"]:
                return True
            elapsed = (now - datetime.fromisoformat(job["last_run"])).total_seconds()
            return elapsed >= sched["seconds"]  # type: ignore[no-any-return]

        elif sched["kind"] == "cron":
            # Simple cron: minute hour day month weekday
            expr = sched["expr"].split()
            if len(expr) != 5:
                return False
            checks = [
                (expr[0], now.minute),
                (expr[1], now.hour),
                (expr[2], now.day),
                (expr[3], now.month),
                (expr[4], now.weekday()),  # 0=Monday
            ]
            for field, val in checks:
                if field == "*":
                    continue
                try:
                    if "," in field:
                        if val not in [int(x) for x in field.split(",")]:
                            return False
                    elif "-" in field:
                        lo, hi = field.split("-")
                        if not (int(lo) <= val <= int(hi)):
                            return False
                    elif int(field) != val:
                        return False
                except ValueError:
                    return False
            # Don't run twice in same minute
            if job["last_run"]:
                last = datetime.fromisoformat(job["last_run"])
                if (now - last).total_seconds() < 60:
                    return False
            return True

        elif sched["kind"] == "at":
            target = datetime.fromisoformat(sched["time"])
            if job["last_run"]:
                return False  # One-shot, already ran
            return now >= target

        return False

    async def tick(self) -> None:
        """Check and execute due jobs. Also runs heartbeat if due."""
        # OpenClaw-style heartbeat check
        if heartbeat.should_beat():
            try:
                await heartbeat.beat()
            except Exception as e:
                log.error(f"[HEARTBEAT] Tick error: {e}")

        for job in self.jobs:
            if not self._should_run(job):
                continue
            log.info(f"[CRON] LLM cron firing: {job['name']} ({job['id']})")
            try:
                from salmalm.core.engine import process_message

                # Track cost before/after to enforce per-cron-job cap
                cost_before = _usage["total_cost"]
                response = await process_message(f"cron-{job['id']}", job["prompt"], model_override=job.get("model"))
                cost_after = _usage["total_cost"]
                cron_cost = cost_after - cost_before
                MAX_CRON_JOB_COST = 2.0  # $2 max per cron execution
                if cron_cost > MAX_CRON_JOB_COST:
                    log.warning(f"[CRON] Job {job['name']} cost ${cron_cost:.2f} — exceeds ${MAX_CRON_JOB_COST} cap")
                job["last_run"] = datetime.now(KST).isoformat()  # noqa: F405
                job["run_count"] = job.get("run_count", 0) + 1
                self.save_jobs()
                log.info(f"[CRON] Cron completed: {job['name']} ({len(response)} chars)")

                # Notification routing
                notify_cfg = job.get("notify")
                notified = False
                summary = response[:800] + ("..." if len(response) > 800 else "")
                notify_text = f"⏰ SalmAlm scheduled task completed: {job['name']}\n\n{summary}"

                if isinstance(notify_cfg, dict):
                    ch = notify_cfg.get("channel", "")
                    try:
                        if ch == "telegram":
                            chat_id = notify_cfg.get("chat_id", "")
                            if chat_id and _tg_bot and _tg_bot.token:
                                _tg_bot.send_message(chat_id, notify_text)
                                notified = True
                        elif ch == "discord":
                            channel_id = notify_cfg.get("channel_id", "")
                            if channel_id:
                                try:
                                    import salmalm.channels.discord_bot as _dmod

                                    dbot = getattr(_dmod, "_bot", None)
                                    if dbot and hasattr(dbot, "send_message"):
                                        dbot.send_message(channel_id, notify_text)
                                        notified = True
                                except Exception:
                                    pass
                    except Exception as e:
                        log.warning(f"[CRON] Notification routing failed for {job['name']}: {e}")
                elif notify_cfg:
                    if _tg_bot and _tg_bot.token and _tg_bot.owner_id:
                        try:
                            _tg_bot.send_message(_tg_bot.owner_id, notify_text)
                            notified = True
                        except Exception as e:
                            log.warning(f"[CRON] Telegram notify failed: {e}")

                # Fallback to web notification on failure, or always store for UI
                if notify_cfg:
                    web_session = _sessions.get("web")
                    if web_session:
                        if not notified or True:  # Always store in web for visibility
                            if not hasattr(web_session, "_notifications"):
                                web_session._notifications = []
                            web_session._notifications.append(
                                {
                                    "time": time.time(),
                                    "text": f"⏰ Cron [{job['name']}]: {response[:200]}",
                                }
                            )

                # Log to daily memory
                write_daily_log(f"[CRON] {job['name']}: {response[:150]}")

                # One-shot jobs: auto-disable
                if job["schedule"]["kind"] == "at":
                    job["enabled"] = False
                    self.save_jobs()

            except Exception as e:
                log.error(f"LLM cron error ({job['name']}): {e}")
                job["last_run"] = datetime.now(KST).isoformat()  # noqa: F405
                self.save_jobs()


# ============================================================
# PLUGIN LOADER — Auto-load tools from plugins/ directory
class Session:
    """OpenClaw-style isolated session with its own context.

    Each session has:
    - Unique ID and isolated message history
    - No cross-contamination between sessions
    - Automatic memory flush before compaction
    - Session metadata tracking
    """

    def __init__(self, session_id: str, user_id: Optional[int] = None):
        self.id = session_id
        self.user_id = user_id  # Multi-tenant: owning user (None = legacy/local)
        self.messages: list = []
        self.created = time.time()
        self.last_active = time.time()
        self.metadata: dict = {}  # Arbitrary session metadata
        self._memory_flushed = False  # Track if pre-compaction memory flush happened
        self.thinking_enabled = False  # Extended thinking toggle (default OFF)
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
            # Ensure user_id column exists
            try:
                conn.execute("ALTER TABLE session_store ADD COLUMN user_id INTEGER DEFAULT NULL")
            except Exception:
                pass
            conn.execute(
                "INSERT OR REPLACE INTO session_store (session_id, messages, updated_at, user_id) VALUES (?,?,?,?)",
                (
                    self.id,
                    json.dumps(saveable, ensure_ascii=False),
                    datetime.now(KST).isoformat(),
                    self.user_id,
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
        except Exception:
            pass

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
            except Exception:
                pass
            del _sessions[sid]
        if stale:
            log.info(f"[CLEAN] Session cleanup: removed {len(stale)} inactive sessions")
        # Hard cap
        if len(_sessions) > _SESSION_MAX:
            by_age = sorted(_sessions.items(), key=lambda x: x[1].last_active)
            for sid, _ in by_age[: len(_sessions) - _SESSION_MAX]:
                del _sessions[sid]


def get_session(session_id: str, user_id: Optional[int] = None) -> Session:
    """Get or create a chat session by ID."""
    _cleanup_sessions()
    with _session_lock:
        if session_id not in _sessions:
            _sessions[session_id] = Session(session_id, user_id=user_id)
            # Try to restore from SQLite
            try:
                conn = _get_db()
                row = conn.execute(
                    "SELECT messages FROM session_store WHERE session_id=?",
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
            except Exception:
                pass

            log.info(
                f"[NOTE] New session: {session_id} (system prompt: {len(_sessions[session_id].messages[0]['content'])} chars)"
            )
            audit_log(
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
    except Exception:
        pass
    audit_log("session_rollback", f"{session_id}: removed {pairs_removed} pairs")
    return {"ok": True, "removed": pairs_removed}


def branch_session(session_id: str, message_index: int) -> dict:
    """Create a new session branching from session_id at message_index.

    Copies messages[0:message_index+1] into a new session.
    Returns {'ok': True, 'new_session_id': ...} or error.
    """
    import uuid as _uuid

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
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE session_store ADD COLUMN branch_index INTEGER DEFAULT NULL")
    except Exception:
        pass
    conn.execute(
        "UPDATE session_store SET parent_session_id=?, branch_index=? WHERE session_id=?",
        (session_id, message_index, new_id),
    )
    conn.commit()

    try:
        save_session_to_disk(new_id)
    except Exception:
        pass
    audit_log("session_branch", f"{session_id} -> {new_id} at index {message_index}")
    return {"ok": True, "new_session_id": new_id, "parent_session_id": session_id}


_SESSIONS_DIR = Path.home() / ".salmalm" / "sessions"


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


class CronScheduler:
    """OpenClaw-style cron scheduler with isolated session execution."""

    def __init__(self):
        self.jobs = []
        self._running = False

    def add_job(self, name: str, interval_seconds: int, callback: object, **kwargs: object) -> None:
        """Add a new cron job with the given schedule and callback."""
        self.jobs.append(
            {
                "name": name,
                "interval": interval_seconds,
                "callback": callback,
                "kwargs": kwargs,
                "last_run": 0,
                "enabled": True,
            }
        )

    async def run(self) -> None:
        """Start the cron scheduler loop."""
        self._running = True
        log.info(f"[CRON] Cron scheduler started ({len(self.jobs)} jobs)")
        while self._running:
            now = time.time()
            for job in self.jobs:
                if not job["enabled"]:
                    continue
                if now - job["last_run"] >= job["interval"]:
                    try:
                        log.info(f"[CRON] Running cron: {job['name']}")
                        if asyncio.iscoroutinefunction(job["callback"]):
                            await job["callback"](**job["kwargs"])
                        else:
                            job["callback"](**job["kwargs"])
                        job["last_run"] = now
                    except Exception as e:
                        log.error(f"Cron error ({job['name']}): {e}")
            await asyncio.sleep(10)

    def stop(self) -> None:
        """Stop the cron scheduler loop."""
        self._running = False


cron = CronScheduler()


# ============================================================
# HEARTBEAT SYSTEM — OpenClaw-style periodic self-check
# ============================================================


class HeartbeatManager:
    """OpenClaw-style heartbeat: periodic self-check with HEARTBEAT.md.

    Reads HEARTBEAT.md for a checklist of things to do on each heartbeat.
    Runs in an isolated session to avoid polluting main conversation.
    Announces results to configured channels.
    Tracks check state in heartbeat-state.json.
    """

    _HEARTBEAT_FILE = BASE_DIR / "HEARTBEAT.md"  # noqa: F405
    _STATE_FILE = MEMORY_DIR / "heartbeat-state.json"  # noqa: F405
    _DEFAULT_INTERVAL = 1800  # 30 minutes
    _last_beat = 0.0
    _enabled = True
    _beat_count = 0

    @classmethod
    def _load_state(cls) -> dict:
        """Load heartbeat state from JSON file."""
        try:
            if cls._STATE_FILE.exists():
                return json.loads(cls._STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"lastChecks": {}, "history": [], "totalBeats": 0}

    @classmethod
    def _save_state(cls, state: dict):
        """Persist heartbeat state to JSON file."""
        try:
            MEMORY_DIR.mkdir(exist_ok=True)  # noqa: F405
            cls._STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.error(f"[HEARTBEAT] Failed to save state: {e}")

    @classmethod
    def get_prompt(cls) -> str:
        """Read HEARTBEAT.md for the heartbeat checklist."""
        if cls._HEARTBEAT_FILE.exists():
            try:
                content = cls._HEARTBEAT_FILE.read_text(encoding="utf-8", errors="replace")
                if content.strip():
                    return content
            except Exception:
                pass
        return ""

    @classmethod
    def should_beat(cls) -> bool:
        """Check if it's time for a heartbeat."""
        if not cls._enabled:
            return False
        now = time.time()
        if now - cls._last_beat < cls._DEFAULT_INTERVAL:
            return False
        # Respect quiet hours (23:00-08:00 KST)
        hour = datetime.now(KST).hour  # noqa: F405
        if hour >= 23 or hour < 8:
            return False
        return True

    @classmethod
    def get_state(cls) -> dict:
        """Get current heartbeat state (for tools/API)."""
        state = cls._load_state()
        state["enabled"] = cls._enabled
        state["interval"] = cls._DEFAULT_INTERVAL
        state["lastBeat"] = cls._last_beat
        state["beatCount"] = cls._beat_count
        return state

    @classmethod
    def update_check(cls, check_name: str) -> None:
        """Record that a specific check was performed (email, calendar, etc)."""
        state = cls._load_state()
        state["lastChecks"][check_name] = time.time()
        cls._save_state(state)

    @classmethod
    def time_since_check(cls, check_name: str) -> Optional[float]:
        """Seconds since a named check was last performed. None if never."""
        state = cls._load_state()
        ts = state.get("lastChecks", {}).get(check_name)
        if ts:
            return time.time() - ts
        return None

    @classmethod
    async def beat(cls) -> Optional[str]:
        """Execute a heartbeat check in an isolated session.

        Returns the heartbeat result or None if nothing to do.
        """
        prompt = cls.get_prompt()
        if not prompt:
            cls._last_beat = time.time()
            return None

        cls._last_beat = time.time()
        cls._beat_count += 1
        log.info("[HEARTBEAT] Running periodic heartbeat check")

        # Load state for context injection
        state = cls._load_state()
        state_ctx = ""
        if state.get("lastChecks"):
            checks = []
            for name, ts in state["lastChecks"].items():
                ago = int((time.time() - ts) / 60)
                checks.append(f"  {name}: {ago}min ago")
            state_ctx = "\n\nLast checks:\n" + "\n".join(checks)

        try:
            from salmalm.core.engine import process_message

            # Run in isolated session (OpenClaw pattern: no cross-contamination)
            result = await process_message(
                f"heartbeat-{int(time.time())}",
                f"[Heartbeat check]\n{prompt}{state_ctx}\n\nIf nothing needs attention, reply HEARTBEAT_OK.",
                model_override=None,  # Use auto-routing
            )

            # Update state
            state["totalBeats"] = state.get("totalBeats", 0) + 1
            state["lastBeatTime"] = time.time()
            state["lastBeatResult"] = "ok" if (result and "HEARTBEAT_OK" in result) else "action"
            # Keep last 20 history entries
            history = state.get("history", [])
            history.append(
                {
                    "time": time.time(),
                    "result": state["lastBeatResult"],
                    "summary": (result or "")[:200],
                }
            )
            state["history"] = history[-20:]
            cls._save_state(state)

            # Announce if result is meaningful
            if result and "HEARTBEAT_OK" not in result:
                cls._announce(result)
                write_daily_log(f"[HEARTBEAT] {result[:200]}")

            return result
        except Exception as e:
            log.error(f"[HEARTBEAT] Error: {e}")
            return None

    @classmethod
    def _announce(cls, result: str):
        """Announce heartbeat results to configured channels."""
        # Telegram notification
        if _tg_bot and _tg_bot.token and _tg_bot.owner_id:
            try:
                summary = result[:800] + ("..." if len(result) > 800 else "")
                _tg_bot.send_message(_tg_bot.owner_id, f"💓 Heartbeat alert:\n{summary}")
            except Exception as e:
                log.error(f"[HEARTBEAT] Announce error: {e}")

        # Store for web polling
        web_session = _sessions.get("web")
        if web_session:
            if not hasattr(web_session, "_notifications"):
                web_session._notifications = []
            web_session._notifications.append({"time": time.time(), "text": f"💓 Heartbeat: {result[:200]}"})


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
        except Exception:
            pass
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
    except Exception:
        pass
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
    except Exception:
        pass
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
            except Exception:
                continue
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
