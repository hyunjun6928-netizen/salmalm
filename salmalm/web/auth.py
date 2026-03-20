"""SalmAlm Auth — Multi-user authentication, session isolation, RBAC, rate limiting.

Features:
  - JWT-like token auth (HMAC-SHA256, no external deps)
  - SQLite user database (username/password/role/api_key)
  - Session isolation per user
  - Role-based access control (admin/user/readonly)
  - Token bucket rate limiter (per user + per IP)
  - API key authentication for programmatic access
  - Login attempt tracking + lockout

Usage:
  from salmalm.web.auth import auth_manager, rate_limiter
  user = auth_manager.authenticate(username, password)
  token = auth_manager.create_token(user)
  auth_manager.verify_token(token)
  rate_limiter.check("user_id")  # raises RateLimitExceeded
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import functools
import sqlite3
import threading
import time
from typing import Dict, List, Optional, Tuple

from salmalm.constants import DATA_DIR, KST, PBKDF2_ITER
from salmalm.security.crypto import log

AUTH_DB = DATA_DIR / "auth.db"

# ── Thread-local auth.db connection pool ──────────────────────────────────────
# H-3 fix: was opening a new sqlite3.connect() on every request (verified at 17
# call sites). Switching to thread-local reuse cuts per-request overhead from
# ~0.5ms open+close to near-zero and eliminates "database is locked" under load.
_auth_local = threading.local()


def _reset_auth_db_cache() -> None:
    """Invalidate the thread-local auth.db connection.

    Call this when the underlying DB file is replaced (e.g. in tests).
    """
    try:
        if getattr(_auth_local, "conn", None) is not None:
            _auth_local.conn.close()
    except Exception:
        pass
    _auth_local.conn = None
    _auth_local.db_path = None


def _get_auth_db(db_path=None) -> sqlite3.Connection:
    """Return a thread-local connection to auth.db (WAL mode, 5s busy timeout).

    db_path: override path — used by AuthManager when AUTH_DB changes between
    tests or when the instance uses a custom path.  A path mismatch clears
    the cached connection so the correct file is always opened.
    """
    target = str(db_path or AUTH_DB)
    conn = getattr(_auth_local, "conn", None)
    cached_path = getattr(_auth_local, "db_path", None)
    if conn is not None:
        # Invalidate if path changed OR connection was closed
        if cached_path != target:
            try:
                conn.close()
            except Exception:
                pass
            conn = None
            _auth_local.conn = None
        else:
            try:
                conn.execute("SELECT 1")
            except Exception:
                conn = None
                _auth_local.conn = None
    if conn is None:
        import pathlib as _pl
        _pl.Path(target).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(target, check_same_thread=True)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        _auth_local.conn = conn
        _auth_local.db_path = target
    return conn

# ── Password hashing (PBKDF2-HMAC-SHA256) ──────────────────


def _hash_password(password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    """Hash password with PBKDF2. Returns (hash, salt)."""
    if salt is None:
        salt = os.urandom(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITER)
    return dk, salt


def _verify_password(password: str, stored_hash: bytes, salt: bytes) -> bool:
    """Verify password."""
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITER)
    return hmac.compare_digest(dk, stored_hash)


# Dummy hash for timing equalization (prevents username enumeration)
_DUMMY_HASH, _DUMMY_SALT = _hash_password("salmalm_dummy_constant_timer")


# ── JWT-like tokens (HMAC-SHA256) ───────────────────────────


class TokenManager:
    """Token creation/verification using HMAC-SHA256 with jti revocation support.

    Each token gets a unique jti (JWT ID). Tokens can be revoked by storing
    their jti in a SQLite table. Expired revocation entries are cleaned up
    automatically.
    """

    _SECRET_DIR = DATA_DIR / ".token_keys"
    _SECRET_FILE = DATA_DIR / ".token_secret"  # Legacy location

    def __init__(self, secret: Optional[bytes] = None) -> None:
        """Init  ."""
        self._keys: Dict[str, bytes] = {}  # kid -> secret
        self._current_kid: str = ""
        if secret:
            self._current_kid = "manual"
            self._keys["manual"] = secret
        else:
            self._load_or_create_keys()
        self._revoked_lock = threading.Lock()
        self._ensure_revocation_table()

    def _load_or_create_keys(self):
        """Load key ring from disk, or migrate from legacy single-key file."""
        self._SECRET_DIR.mkdir(parents=True, exist_ok=True)
        # Load existing keys
        for f in sorted(self._SECRET_DIR.iterdir()):
            if f.suffix == ".key" and f.stat().st_size == 32:
                kid = f.stem
                self._keys[kid] = f.read_bytes()
                self._current_kid = kid  # Latest by sort order
        # Migrate legacy single-key file
        if not self._keys and self._SECRET_FILE.exists():
            legacy = self._SECRET_FILE.read_bytes()
            if len(legacy) == 32:
                kid = "k0"
                self._keys[kid] = legacy
                self._current_kid = kid
                self._write_key_file(kid, legacy)
        # No keys at all — generate first key
        if not self._keys:
            self._rotate()

    def _write_key_file(self, kid: str, secret: bytes):
        """Write a key file with restricted permissions."""
        path = self._SECRET_DIR / f"{kid}.key"
        path.write_bytes(secret)
        try:
            path.chmod(0o600)
        except (OSError, NotImplementedError):
            pass
        import sys

        if sys.platform == "win32":
            try:
                import subprocess

                subprocess.run(
                    [
                        "icacls",
                        str(path),
                        "/inheritance:r",
                        "/grant:r",
                        f"{os.environ.get('USERNAME', 'SYSTEM')}:(R,W)",
                    ],
                    capture_output=True,
                    timeout=5,
                )
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")

    def rotate(self) -> str:
        """Create a new signing key. Old keys kept for verification.

        Returns the new kid.
        """
        return self._rotate()

    def _rotate(self) -> str:
        """Internal: generate new key and set as current."""
        # kid = k{N} where N increments
        existing = [k for k in self._keys if k.startswith("k") and k[1:].isdigit()]
        n = max((int(k[1:]) for k in existing), default=-1) + 1
        kid = f"k{n}"
        secret = os.urandom(32)
        self._keys[kid] = secret
        self._current_kid = kid
        self._write_key_file(kid, secret)
        return kid

    def _ensure_revocation_table(self):
        """Create revoked_tokens table if it doesn't exist."""
        try:
            AUTH_DB.parent.mkdir(parents=True, exist_ok=True)
            conn = _get_auth_db(AUTH_DB)
            conn.execute("""CREATE TABLE IF NOT EXISTS revoked_tokens (
                jti TEXT PRIMARY KEY,
                revoked_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )""")
            conn.commit()
            # conn.close()  # omitted: thread-local connection
        except Exception as e:  # noqa: broad-except
            pass  # Will work in-memory if DB unavailable

    def create(self, payload: dict, expires_in: int = 86400) -> str:
        """Create a signed token with unique jti + kid. Default expiry: 24h."""
        now = int(time.time())
        jti = secrets.token_urlsafe(16)
        payload = {
            **payload,
            "jti": jti,
            "kid": self._current_kid,
            "exp": now + expires_in,
            "iat": now,
        }
        data = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
        secret = self._keys[self._current_kid]
        sig = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
        return f"{data}.{sig}"

    def verify(self, token: str) -> Optional[dict]:
        """Verify token signature, expiry, and revocation status.

        Tries the kid from the token payload first, then falls back to
        all known keys (for legacy tokens without kid).
        """
        try:
            parts = token.rsplit(".", 1)
            if len(parts) != 2:
                return None
            data, sig = parts
            # Decode payload to get kid hint (without verifying sig yet)
            padded = data + "=" * (-len(data) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
            # Always try all keys to prevent kid-based timing oracle
            keys_to_try = list(self._keys.values())
            verified = False
            for secret in keys_to_try:
                expected = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
                if hmac.compare_digest(sig, expected):
                    verified = True
                    break
            if not verified:
                return None
            if payload.get("exp", 0) < time.time():
                return None
            jti = payload.get("jti")
            uid = payload.get("uid")
            iat = payload.get("iat", 0)
            if jti and self._is_revoked(jti):
                return None
            # Also check per-user bulk revocation (revoke_all_for_user)
            if uid and self._is_user_revoked(uid, iat):
                return None
            return payload  # type: ignore[no-any-return]
        except Exception as e:  # noqa: broad-except
            return None

    def revoke(self, token: str) -> bool:
        """Revoke a token by jti. Requires valid HMAC signature (even if expired)
        to prevent revocation-table poisoning via forged payloads."""
        try:
            # Try normal verify first (catches valid + non-expired)
            payload = self.verify(token)
            if payload is None:
                # Token may be expired but still have valid signature.
                # Verify signature manually before trusting the jti.
                parts = token.rsplit(".", 1)
                if len(parts) != 2:
                    return False
                data, sig = parts
                padded = data + "=" * (-len(data) % 4)
                try:
                    payload = json.loads(base64.urlsafe_b64decode(padded))
                except Exception:
                    return False
                # Verify HMAC signature — reject forged tokens entirely
                keys_to_try = list(self._keys.values())
                valid_sig = any(
                    hmac.compare_digest(sig, hmac.new(k, data.encode(), hashlib.sha256).hexdigest())
                    for k in keys_to_try
                )
                if not valid_sig:
                    return False  # Forged token — do NOT insert into revocation table
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if not jti:
                return False  # Legacy token without jti
            # Cap exp to prevent far-future bloat (max 90 days)
            exp = min(exp, time.time() + 90 * 86400)
            with self._revoked_lock:
                conn = _get_auth_db(AUTH_DB)
                conn.execute(
                    "INSERT OR IGNORE INTO revoked_tokens (jti, revoked_at, expires_at) VALUES (?, ?, ?)",
                    (jti, time.time(), exp),
                )
                conn.commit()
                # Invalidate LRU cache so revocation takes effect immediately
                try:
                    self._is_revoked_cached.cache_clear()
                except AttributeError:
                    pass
            return True
        except Exception:
            return False

    def revoke_all_for_user(self, user_id: int) -> None:
        """Invalidate ALL tokens for a user by recording a per-user revocation timestamp.

        Any token issued before this timestamp will be rejected by _is_revoked().
        This is O(1) regardless of how many tokens the user has.
        """
        try:
            with self._revoked_lock:
                conn = _get_auth_db(AUTH_DB)
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS user_revocations (
                        user_id INTEGER PRIMARY KEY,
                        revoked_after REAL NOT NULL
                    )"""
                )
                conn.execute(
                    "INSERT OR REPLACE INTO user_revocations (user_id, revoked_after) VALUES (?, ?)",
                    (user_id, time.time()),
                )
                conn.commit()
                # conn.close()  # omitted: thread-local connection
            log.info(f"[AUTH] All tokens revoked for user_id={user_id}")
        except Exception as e:
            log.error(f"[AUTH] revoke_all_for_user failed: {e}")
            raise

    def _is_revoked(self, jti: str) -> bool:
        """Check if a specific jti has been revoked.

        H-3 fix: uses thread-local auth.db connection + short LRU cache to avoid
        opening a new sqlite3.connect() on every authenticated request.
        """
        # LRU cache key: (jti, bucket) where bucket changes every 5s.
        # This keeps revocation latency low while still reducing DB lookups.
        import os as _os
        if _os.environ.get("SALMALM_NO_JTI_CACHE"):
            return self._is_revoked_uncached(jti)
        bucket = int(time.time() / 5)
        return self._is_revoked_cached(jti, bucket)

    @functools.lru_cache(maxsize=2048)
    def _is_revoked_cached(self, jti: str, bucket: int) -> bool:
        return self._is_revoked_uncached(jti)

    def _is_revoked_uncached(self, jti: str) -> bool:
        try:
            conn = _get_auth_db(AUTH_DB)
            row = conn.execute("SELECT 1 FROM revoked_tokens WHERE jti=?", (jti,)).fetchone()
            return row is not None
        except Exception:
            return False

    def _is_user_revoked(self, user_id: int, token_iat: float) -> bool:
        """Check if token was issued before a bulk user-revocation event.

        H-3 fix: uses thread-local auth.db connection.
        """
        try:
            conn = _get_auth_db(AUTH_DB)
            # user_revocations table may not exist on old DBs — treat as not revoked
            row = conn.execute(
                "SELECT revoked_after FROM user_revocations WHERE user_id=?", (user_id,)
            ).fetchone()
            if row and token_iat <= row[0]:
                # Use <= to cover same-second edge case:
                # token issued at the exact moment of revocation is also invalid.
                return True  # Token issued at or before revocation event
        except Exception:
            pass
        return False

    def cleanup_expired(self) -> int:
        """Remove revocation entries for tokens that have expired anyway."""
        try:
            conn = _get_auth_db(AUTH_DB)
            cursor = conn.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (time.time(),))
            conn.commit()
            deleted = cursor.rowcount
            # Invalidate the LRU cache after bulk cleanup so stale hits are evicted
            self._is_revoked_cached.cache_clear()
            return deleted
        except Exception as e:  # noqa: broad-except
            return 0


# ── Rate Limiter (Token Bucket) ─────────────────────────────


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: float = 0) -> None:
        """Init  ."""
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after:.0f}s")


class RateLimiter:
    """Token bucket rate limiter per key (user_id or IP)."""

    def __init__(self) -> None:
        """Init  ."""
        self._buckets: Dict[str, dict] = {}
        self._lock = threading.Lock()
        # Default limits
        self._limits = {
            "admin": {"rate": 60, "per": 60, "burst": 100},  # 60 req/min
            "user": {"rate": 30, "per": 60, "burst": 50},  # 30 req/min
            "readonly": {"rate": 10, "per": 60, "burst": 20},  # 10 req/min
            "anonymous": {"rate": 5, "per": 60, "burst": 10},  # 5 req/min
            "ip": {"rate": 120, "per": 60, "burst": 200},  # 120 req/min per IP
        }

    _last_cleanup = 0.0

    def check(self, key: str, role: str = "anonymous") -> bool:
        """Check rate limit. Raises RateLimitExceeded if exceeded."""
        with self._lock:
            limit = self._limits.get(role, self._limits["anonymous"])
            now = time.time()

            # Auto-cleanup stale buckets every 10 minutes
            if now - self._last_cleanup > 600:
                stale = [k for k, v in self._buckets.items() if now - v["last_refill"] > 3600]
                for k in stale:
                    del self._buckets[k]
                self._last_cleanup = now

            # Hard cap: prevent memory exhaustion from IP flooding
            if key not in self._buckets:
                if len(self._buckets) >= 50000:
                    # Emergency eviction: remove oldest 10%
                    oldest = sorted(self._buckets.items(), key=lambda x: x[1]["last_refill"])[:5000]
                    for k, _ in oldest:
                        del self._buckets[k]
                self._buckets[key] = {
                    "tokens": limit["burst"],
                    "last_refill": now,
                }

            bucket = self._buckets[key]
            # Refill tokens
            elapsed = now - bucket["last_refill"]
            refill = elapsed * (limit["rate"] / limit["per"])
            bucket["tokens"] = min(limit["burst"], bucket["tokens"] + refill)
            bucket["last_refill"] = now

            if bucket["tokens"] < 1:
                retry_after = (1 - bucket["tokens"]) / (limit["rate"] / limit["per"])
                raise RateLimitExceeded(retry_after)

            bucket["tokens"] -= 1
            return True

    def get_remaining(self, key: str) -> int:
        """Get remaining requests allowed in the current rate limit window."""
        with self._lock:
            bucket = self._buckets.get(key)
            return int(bucket["tokens"]) if bucket else -1

    def cleanup(self) -> None:
        """Remove stale buckets (>1h inactive)."""
        with self._lock:
            now = time.time()
            stale = [k for k, v in self._buckets.items() if now - v["last_refill"] > 3600]
            for k in stale:
                del self._buckets[k]


# ── LLM-specific Rate Limiter ───────────────────────────────


class LLMRateLimiter(RateLimiter):
    """Tighter token bucket for LLM-triggering endpoints (/api/chat, /api/agent/task).

    LLM calls consume external API credits; a single user can cause significant
    cost within seconds. These limits are intentionally lower than the global
    rate limiter.
    """

    def __init__(self) -> None:
        """Init  ."""
        super().__init__()
        self._limits = {
            "admin":     {"rate": 30,  "per": 60, "burst": 40},   # 30 req/min (< global 60)
            "user":      {"rate": 20,  "per": 60, "burst": 25},   # 20 req/min (< global 30)
            "readonly":  {"rate": 3,   "per": 60, "burst": 5},    # 3 req/min  (< global 10)
            "anonymous": {"rate": 2,   "per": 60, "burst": 5},    # 2 req/min  (< global 5)
            "ip":        {"rate": 10,  "per": 60, "burst": 15},   # 10 req/min (< global 120)
        }


# ── IP Ban List ─────────────────────────────────────────────


class IPBanList:
    """Auto-ban IPs that repeatedly exceed rate limits.

    Tracks violation counts per IP in a sliding window. After
    ``ban_threshold`` violations, the IP is blocked for ``ban_duration``
    seconds. State is persisted to ``auth.db`` so bans survive restarts.
    """

    _DB_TABLE = """
        CREATE TABLE IF NOT EXISTS ip_bans (
            ip          TEXT PRIMARY KEY,
            violations  INTEGER NOT NULL DEFAULT 0,
            first_at    REAL    NOT NULL,
            banned_until REAL   NOT NULL DEFAULT 0
        )
    """

    def __init__(self, ban_threshold: int = 10, ban_duration: int = 3600) -> None:
        """Init  ."""
        # ip -> {"count": int, "first_at": float, "last_at": float, "banned_until": float}
        self._records: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._ban_threshold = ban_threshold  # violations before ban
        self._ban_duration = ban_duration    # seconds to ban (default 1 h)
        self._init_db()
        self._load_from_db()
        self._start_cleanup_thread()

    def _start_cleanup_thread(self) -> None:
        """Spawn a daemon thread that evicts expired ban records every 30 min."""
        def _loop():
            while True:
                time.sleep(1800)
                try:
                    self.cleanup()
                except Exception:
                    pass
        t = threading.Thread(target=_loop, daemon=True, name="IPBanList-cleanup")
        t.start()

    def _get_conn(self):
        """Return thread-local auth DB connection (reuses _get_auth_db)."""
        conn = _get_auth_db(AUTH_DB)
        conn.execute(self._DB_TABLE)
        conn.commit()
        return conn

    def _init_db(self) -> None:
        """Ensure ip_bans table exists."""
        try:
            conn = self._get_conn()
        except Exception as _e:
            log.warning("[BAN] DB init failed: %s", _e)

    def _load_from_db(self) -> None:
        """Load active bans from DB into memory on startup."""
        try:
            conn = self._get_conn()
            now = time.time()
            rows = conn.execute(
                "SELECT ip, violations, first_at, banned_until FROM ip_bans WHERE banned_until > ?",
                (now,),
            ).fetchall()
            # conn.close()  # thread-local: do not close
            with self._lock:
                for ip, violations, first_at, banned_until in rows:
                    self._records[ip] = {
                        "count": violations,
                        "first_at": first_at,
                        "banned_until": banned_until,
                    }
            if rows:
                log.info("[BAN] Loaded %d active ban(s) from DB", len(rows))
        except Exception as _e:
            log.warning("[BAN] DB load failed: %s", _e)

    _persist_pool = None  # lazy ThreadPoolExecutor

    def _persist(self, ip: str, rec: dict, *, sync: bool = False) -> None:
        """Upsert a single record to DB.

        Uses a 2-worker ThreadPoolExecutor by default to prevent thread
        explosion under IP flooding.  Pass sync=True to write immediately
        (used when callers need guaranteed durability before returning).
        """
        rec_copy = dict(rec)  # snapshot under caller's lock before releasing

        def _write():
            try:
                conn = self._get_conn()
                conn.execute(
                    "INSERT OR REPLACE INTO ip_bans (ip, violations, first_at, banned_until) VALUES (?,?,?,?)",
                    (ip, rec_copy["count"], rec_copy["first_at"], rec_copy["banned_until"]),
                )
                conn.commit()
            except Exception as _e:
                log.debug("[BAN] DB persist failed: %s", _e)

        if sync:
            _write()
            return

        if IPBanList._persist_pool is None:
            from concurrent.futures import ThreadPoolExecutor
            IPBanList._persist_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ipban")
        try:
            IPBanList._persist_pool.submit(_write)
        except RuntimeError:
            # Pool shut down — fire-and-forget thread as last resort
            threading.Thread(target=_write, daemon=True, name="ipban-persist-fallback").start()

    def is_banned(self, ip: str) -> "tuple[bool, int]":
        """Return (is_banned, seconds_remaining). Pure read — no side effects."""
        with self._lock:
            rec = self._records.get(ip)
            if not rec:
                return False, 0
            now = time.time()
            if rec["banned_until"] > now:
                return True, int(rec["banned_until"] - now)
            return False, 0

    def record_violation(self, ip: str) -> bool:
        """Record one rate-limit violation for *ip*.

        Returns True if the IP is now banned (either newly or already).
        """
        with self._lock:
            now = time.time()
            if ip not in self._records:
                self._records[ip] = {
                    "count": 0, "first_at": now,
                    "last_at": now, "banned_until": 0.0,
                }

            rec = self._records[ip]

            # Already banned — just return
            if rec["banned_until"] > now:
                return True

            # Reset sliding window after 1 h of *no new violations*
            # (use last_at, not first_at — otherwise 9 violations/hour loop beats the ban)
            if now - rec.get("last_at", rec["first_at"]) > 3600:
                rec["count"] = 0
                rec["first_at"] = now

            rec["last_at"] = now
            rec["count"] += 1

            if rec["count"] >= self._ban_threshold:
                rec["banned_until"] = now + self._ban_duration
                log.warning(
                    "[BAN] IP %s auto-banned for %ds after %d violations",
                    ip, self._ban_duration, rec["count"],
                )
                self._persist(ip, rec, sync=True)
                return True

            self._persist(ip, rec)
            return False

    def unban(self, ip: str) -> None:
        """Manually lift a ban (admin use)."""
        with self._lock:
            self._records.pop(ip, None)   # remove entirely — no lingering violation count
        # Drain pending async persists so they don't re-insert after DELETE
        if IPBanList._persist_pool is not None:
            IPBanList._persist_pool.shutdown(wait=True)
            IPBanList._persist_pool = None
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM ip_bans WHERE ip = ?", (ip,))
            conn.commit()
        except Exception as _e:
            log.debug("[BAN] unban DB delete failed: %s", _e)
        log.info("[BAN] IP %s manually unbanned", ip)

    def list_banned(self) -> list:
        """Return list of currently banned IPs with remaining seconds."""
        now = time.time()
        with self._lock:
            return [
                {"ip": ip, "remaining": int(rec["banned_until"] - now)}
                for ip, rec in self._records.items()
                if rec["banned_until"] > now
            ]

    def cleanup(self) -> None:
        """Evict expired records from memory and DB."""
        with self._lock:
            now = time.time()
            expired = [
                ip for ip, rec in self._records.items()
                if rec["banned_until"] < now and now - rec["first_at"] > 7200
            ]
            for ip in expired:
                del self._records[ip]
        try:
            _t = time.time()
            conn = self._get_conn()
            conn.execute("DELETE FROM ip_bans WHERE banned_until < ? AND first_at < ?",
                         (_t, _t - 7200))
            conn.commit()
            # conn.close()  # thread-local: do not close
        except Exception as _e:
            log.debug("[BAN] cleanup DB failed: %s", _e)


# ── Daily Token Quota ────────────────────────────────────────


class DailyQuotaExceeded(Exception):
    """Raised when a user exceeds their daily token quota."""

    def __init__(self, used: int, limit: int) -> None:
        """Init  ."""
        self.used = used
        self.limit = limit
        super().__init__(f"Daily token quota exceeded: {used}/{limit}")


class DailyQuotaManager:
    """Per-user daily token quota enforced across all LLM calls.

    Limits are role-based (tokens = input + output combined):
      - admin:     unlimited (-1)
      - user:      500 000 tokens / day
      - readonly:  100 000 tokens / day
      - anonymous:  50 000 tokens / day

    Override via SALMALM_DAILY_QUOTA_USER / SALMALM_DAILY_QUOTA_ANON env vars.
    """

    _DB_TABLE = """
        CREATE TABLE IF NOT EXISTS daily_quota (
            user_id TEXT    NOT NULL,
            date    TEXT    NOT NULL,
            tokens  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )
    """

    # Default daily token limits per role (-1 = unlimited)
    _ROLE_LIMITS: Dict[str, int] = {
        "admin":     -1,
        "user":      500_000,
        "readonly":  100_000,
        "anonymous":  50_000,
    }

    def __init__(self) -> None:
        """Init  ."""
        self._lock = threading.Lock()
        self._cache: Dict[str, int] = {}   # "user_id:date" -> token count (in-memory write-through)
        # Make an instance-level copy so env-var overrides don't bleed into the class
        self._ROLE_LIMITS = dict(self.__class__._ROLE_LIMITS)
        self._init_db()
        # Allow env-var override
        import os as _os
        _u = int(_os.environ.get("SALMALM_DAILY_QUOTA_USER", 0))
        _a = int(_os.environ.get("SALMALM_DAILY_QUOTA_ANON", 0))
        if _u > 0:
            self._ROLE_LIMITS["user"] = _u
        if _a > 0:
            self._ROLE_LIMITS["anonymous"] = _a

    def _get_conn(self):
        """Return thread-local auth DB connection (reuses _get_auth_db)."""
        conn = _get_auth_db(AUTH_DB)
        conn.execute(self._DB_TABLE)
        conn.commit()
        return conn

    def _init_db(self) -> None:
        try:
            conn = self._get_conn()
        except Exception as _e:
            log.warning("[QUOTA] DB init failed: %s", _e)

    def _today(self) -> str:
        """Return today's date string in UTC (YYYY-MM-DD)."""
        import datetime
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    def get_usage(self, user_id: str) -> int:
        """Return today's token count for *user_id*."""
        today = self._today()   # capture once — avoids day-boundary cache/DB mismatch
        key = f"{user_id}:{today}"
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT tokens FROM daily_quota WHERE user_id=? AND date=?",
                (user_id, today),
            ).fetchone()
            # conn.close()  # thread-local: do not close
            val = row[0] if row else 0
        except Exception:
            val = 0
        with self._lock:
            self._cache[key] = val
        return val

    def limit_for(self, role: str) -> int:
        """Return the daily token limit for *role*. -1 = unlimited."""
        return self._ROLE_LIMITS.get(role, self._ROLE_LIMITS["anonymous"])

    def check(self, user_id: str, role: str) -> None:
        """Raise DailyQuotaExceeded if *user_id* is over their daily limit."""
        limit = self.limit_for(role)
        if limit < 0:
            return   # unlimited
        used = self.get_usage(user_id)
        if used >= limit:
            raise DailyQuotaExceeded(used, limit)

    def add_usage(self, user_id: str, tokens: int) -> None:
        """Increment today's token counter for *user_id*."""
        if tokens <= 0:
            return
        today = self._today()
        key = f"{user_id}:{today}"
        with self._lock:
            self._cache[key] = self._cache.get(key, 0) + tokens
            # Prune stale date keys to prevent unbounded cache growth.
            # Keys with a different date suffix are yesterday (or older) — evict them.
            if len(self._cache) > 200:
                stale = [k for k in self._cache if not k.endswith(f":{today}")]
                for k in stale:
                    del self._cache[k]
        try:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO daily_quota (user_id, date, tokens) VALUES (?,?,?)
                   ON CONFLICT(user_id, date) DO UPDATE SET tokens = tokens + excluded.tokens""",
                (user_id, today, tokens),
            )
            conn.commit()
            # conn.close()  # thread-local: do not close
        except Exception as _e:
            log.debug("[QUOTA] DB add_usage failed: %s", _e)

    def get_all_today(self) -> List[dict]:
        """Admin view — all users' today usage."""
        today = self._today()
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT user_id, tokens FROM daily_quota WHERE date=? ORDER BY tokens DESC",
                (today,),
            ).fetchall()
            # conn.close()  # thread-local: do not close
            return [{"user_id": uid, "tokens": t} for uid, t in rows]
        except Exception:
            return []

    def cleanup_old(self, keep_days: int = 30) -> None:
        """Delete quota records older than *keep_days* days."""
        import datetime
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=keep_days)).strftime("%Y-%m-%d")
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM daily_quota WHERE date < ?", (cutoff,))
            conn.commit()
            # conn.close()  # thread-local: do not close
        except Exception as _e:
            log.debug("[QUOTA] cleanup failed: %s", _e)


# ── User Database ───────────────────────────────────────────


class AuthManager:
    """Multi-user authentication with SQLite backend."""

    ROLES = ("admin", "user", "readonly")

    def __init__(self) -> None:
        """Init  ."""
        self._token_mgr = TokenManager()
        self._lock = threading.Lock()
        self._lockout_duration = 300  # 5 min lockout
        self._max_attempts = 5
        self._initialized = False

    def _ensure_db(self):
        """Ensure DB is initialized. Double-checked locking prevents TOCTOU race."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:  # second check under lock
                return
            self._ensure_db_locked()

    def _ensure_db_locked(self):
        """Called while holding self._lock. Creates tables and default admin."""
        conn = _get_auth_db(AUTH_DB)
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL,
            password_salt BLOB NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            api_key TEXT UNIQUE,
            created_at TEXT NOT NULL,
            last_login TEXT,
            enabled INTEGER NOT NULL DEFAULT 1
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            ip_address TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            attempted_at REAL NOT NULL,
            ip_address TEXT
        )""")
        conn.execute("""CREATE INDEX IF NOT EXISTS idx_login_attempts_user
            ON login_attempts (username, attempted_at)""")
        conn.commit()

        # Create default admin if no users exist (random password)
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            default_pw = base64.urlsafe_b64encode(os.urandom(18)).decode().rstrip("=")
            _, raw_api_key = self._create_user_db(conn, "admin", default_pw, "admin")
            # SECURITY: Never log passwords to file — console only via stderr
            # Write the initial password to a 0o600 file instead of stderr/logs.
            # Logging the password to stderr risks exposure via journald, container
            # log collectors, or log aggregators — a one-time file is safer.
            try:
                _pw_file = AUTH_DB.parent / ".initial_admin_password"
                _pw_file.write_text(
                    f"username: admin\npassword: {default_pw}\n"
                    f"(delete this file after first login)\n",
                    encoding="utf-8",
                )
                _pw_file.chmod(0o600)
                log.warning(
                    "[USER] Default admin created — password written to %s (mode 0600). "
                    "Delete the file after first login.",
                    _pw_file,
                )
            except Exception as _pw_err:
                # Fallback to stderr only if we cannot write the file
                import sys as _sys
                print(  # noqa: T201
                    f"\n{'=' * 50}\n"
                    f"[USER] Default admin created\n"
                    f"   Username: admin\n"
                    f"   Password: {default_pw}\n"
                    f"[WARN]  Save this — it won't be shown again!\n"
                    f"{'=' * 50}",
                    file=_sys.stderr,
                )
                log.warning("[USER] Could not write initial_admin_password file: %s", _pw_err)
            log.info("[USER] Default admin user created")
        # conn.close() — omitted: thread-local connection, auto-recycled by _get_auth_db()
        self._initialized = True

    def _has_users(self) -> bool:
        """Return True if at least one user exists in the database."""
        try:
            conn = _get_auth_db(AUTH_DB)
            row = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
            return row is not None
        except Exception:
            return False

    # Static HMAC secret for API key hashing.  Using a server-side secret
    # prevents offline dictionary attacks even if the DB is leaked:
    # an attacker needs both the DB rows AND this secret to brute-force keys.
    # Falls back to a deterministic seed so existing hashes remain valid if the
    # env var is unset (backwards compat).  Set SALMALM_API_KEY_SECRET in prod.
    _API_KEY_SECRET: Optional[bytes] = None

    @classmethod
    def _get_api_key_secret(cls) -> bytes:
        if cls._API_KEY_SECRET is None:
            raw = os.environ.get("SALMALM_API_KEY_SECRET", "")
            if raw:
                cls._API_KEY_SECRET = raw.encode()
            else:
                # Derive a per-installation secret from the vault file path.
                # Not ideal but better than bare SHA-256.
                seed = str(AUTH_DB.parent.resolve()).encode()
                cls._API_KEY_SECRET = hashlib.sha256(seed).digest()
        return cls._API_KEY_SECRET

    @classmethod
    def _hash_api_key(cls, api_key: str) -> str:
        """Hash API key for storage using HMAC-SHA256 with a server-side secret.

        Compared to bare SHA-256, this prevents offline dictionary attacks
        even when the database is exfiltrated — the attacker also needs the
        secret. Set SALMALM_API_KEY_SECRET env var to a random 32-byte value
        in production.
        """
        return hmac.new(cls._get_api_key_secret(), api_key.encode(), hashlib.sha256).hexdigest()

    def _create_user_db(self, conn, username: str, password: str, role: str) -> tuple:
        """Create user, return (lastrowid, raw_api_key). Raw key is shown once only."""
        pw_hash, salt = _hash_password(password)
        api_key = f"sk_{base64.urlsafe_b64encode(os.urandom(24)).decode().rstrip('=')}"
        api_key_hash = self._hash_api_key(api_key)
        from datetime import datetime

        now = datetime.now(KST).isoformat()
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, password_salt, role, api_key, created_at) VALUES (?,?,?,?,?,?)",
            (username, pw_hash, salt, role, api_key_hash, now),
        )
        conn.commit()
        return cursor.lastrowid, api_key

    def create_user(self, username: str, password: str, role: str = "user") -> dict:
        """Create a new user. Returns user info."""
        self._ensure_db()
        if role not in self.ROLES:
            from salmalm.core.exceptions import AuthError

            raise AuthError(f"Invalid role: {role}. Must be one of {self.ROLES}")
        if len(password) < 8:
            from salmalm.core.exceptions import AuthError

            raise AuthError("Password must be at least 8 characters")

        conn = _get_auth_db(AUTH_DB)
        try:
            uid, raw_api_key = self._create_user_db(conn, username, password, role)
            # Return raw API key only at creation time — it's hashed in DB
            return {
                "id": uid,
                "username": username,
                "role": role,
                "api_key": raw_api_key,
            }
        except sqlite3.IntegrityError:
            raise ValueError(f"Username already exists: {username}")

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """Authenticate user. Returns user dict or None."""
        self._ensure_db()

        # Check lockout (DB-persisted)
        if self._is_locked_out(username):
            log.warning(f"[LOCK] Account locked: {username}")
            return None

        # Thread-local connection reuse for the entire authenticate sequence
        conn = _get_auth_db(AUTH_DB)
        row = conn.execute(
            "SELECT id, username, password_hash, password_salt, role, api_key, enabled FROM users WHERE username=?",
            (username,),
        ).fetchone()

        if not row or not row[6]:  # Not found or disabled
            _verify_password(password, _DUMMY_HASH, _DUMMY_SALT)  # timing equalization
            self._record_attempt(username)
            return None

        if not _verify_password(password, row[2], row[3]):
            self._record_attempt(username)
            return None

        from datetime import datetime
        # Success — clear attempts + update last_login in one commit
        conn.execute("DELETE FROM login_attempts WHERE username=?", (username,))
        conn.execute(
            "UPDATE users SET last_login=? WHERE id=?",
            (datetime.now(KST).isoformat(), row[0]),
        )
        conn.commit()
        return {"id": row[0], "username": row[1], "role": row[4]}

    def authenticate_api_key(self, api_key: str) -> Optional[dict]:
        """Authenticate via API key (constant-time hash comparison)."""
        self._ensure_db()
        key_hash = self._hash_api_key(api_key)
        conn = _get_auth_db(AUTH_DB)
        row = conn.execute(
            "SELECT id, username, role, enabled FROM users WHERE api_key=? AND enabled=1",
            (key_hash,),
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "role": row[2]}

    def _record_attempt(self, username: str, ip: str = ""):
        """Record a failed login attempt in DB (survives restart)."""
        try:
            conn = _get_auth_db(AUTH_DB)
            conn.execute(
                "INSERT INTO login_attempts (username, attempted_at, ip_address) VALUES (?, ?, ?)",
                (username, time.time(), ip),
            )
            # Cleanup: remove attempts older than lockout window
            cutoff = time.time() - self._lockout_duration
            conn.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (cutoff,))
            conn.commit()
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")

    def _is_locked_out(self, username: str) -> bool:
        """Check if username is locked out (DB-persisted, survives restart)."""
        try:
            conn = _get_auth_db(AUTH_DB)
            cutoff = time.time() - self._lockout_duration
            row = conn.execute(
                "SELECT COUNT(*) FROM login_attempts WHERE username=? AND attempted_at>?",
                (username, cutoff),
            ).fetchone()
            # conn.close()  # omitted: thread-local connection
            return (row[0] if row else 0) >= self._max_attempts
        except Exception as e:  # noqa: broad-except
            log.warning("[AUTH] DB unavailable in lockout check — failing closed for %s: %s", username, e)
            return True  # fail CLOSED: deny login when we can't verify lockout state

    _MAX_TOKEN_LIFETIME = 30 * 86400  # 30 days absolute max

    def create_token(self, user: dict, expires_in: int = 86400) -> str:
        """Create auth token for authenticated user."""
        expires_in = min(expires_in, self._MAX_TOKEN_LIFETIME)
        return self._token_mgr.create(
            {
                "uid": user["id"],
                "usr": user["username"],
                "role": user["role"],
            },
            expires_in=expires_in,
        )

    def verify_token(self, token: str) -> Optional[dict]:
        """Verify auth token. Checks signature, expiry, revocation, AND user existence.
        A token for a deleted/disabled user is rejected even if signature is valid.
        """
        payload = self._token_mgr.verify(token)
        if payload is None:
            return None
        uid = payload.get("uid")
        if uid is None:
            log.warning("[AUTH] Rejected legacy token with no uid")
            return None
        try:
            conn = _get_auth_db(AUTH_DB)
            row = conn.execute(
                "SELECT id, username, role, enabled FROM users WHERE id=? AND enabled=1", (uid,)
            ).fetchone()
            # conn.close()  # omitted: thread-local connection
            if not row:
                log.debug(f"[AUTH] Token rejected: user_id={uid} not found or disabled")
                return None
        except Exception as _db_err:
            # DB read failed: fail CLOSED (deny access) rather than fail open.
            # A transient DB error is operationally painful but far safer than
            # granting access to potentially revoked or disabled accounts.
            log.warning("[AUTH] DB unavailable during token verification — denying access: %s", _db_err)
            return None
        return payload

    def revoke_token(self, token: str) -> bool:
        """Revoke a token (logout). Returns True on success."""
        return self._token_mgr.revoke(token)

    def list_users(self) -> List[dict]:
        """List all users (admin only)."""
        self._ensure_db()
        conn = _get_auth_db(AUTH_DB)
        rows = conn.execute("SELECT id, username, role, created_at, last_login, enabled FROM users").fetchall()
        # conn.close()  # omitted: thread-local connection
        return [
            {
                "id": r[0],
                "username": r[1],
                "role": r[2],
                "created_at": r[3],
                "last_login": r[4],
                "enabled": bool(r[5]),
            }
            for r in rows
        ]

    def delete_user(self, username: str) -> bool:
        """Delete a user account by username."""
        self._ensure_db()
        conn = _get_auth_db(AUTH_DB)
        cursor = conn.execute("DELETE FROM users WHERE username=? AND role != ?", (username, "admin"))
        conn.commit()
        deleted = cursor.rowcount > 0
        # conn.close()  # omitted: thread-local connection
        return deleted

    def change_password(self, username: str, new_password: str) -> bool:
        """Change a user password. Returns True on success."""
        if len(new_password) < 8:
            from salmalm.core.exceptions import AuthError

            raise AuthError("Password must be at least 8 characters")
        self._ensure_db()
        pw_hash, salt = _hash_password(new_password)
        conn = _get_auth_db(AUTH_DB)
        cursor = conn.execute(
            "UPDATE users SET password_hash=?, password_salt=? WHERE username=?",
            (pw_hash, salt, username),
        )
        conn.commit()
        ok = cursor.rowcount > 0
        if ok:
            # Revoke ALL existing tokens — stolen tokens must be invalidated immediately
            user_row = conn.execute(
                "SELECT id FROM users WHERE username=?", (username,)
            ).fetchone()
            if user_row:
                self._token_mgr.revoke_all_for_user(user_row[0])
        # conn.close()  # omitted: thread-local connection
        return ok

    def has_permission(self, user: dict, action: str) -> bool:
        """Check if user has permission for action."""
        role = user.get("role", "readonly")
        permissions = {
            "admin": {"chat", "tools", "config", "users", "exec", "files", "admin"},
            "user": {"chat", "tools", "files"},
            "readonly": {"chat"},
        }
        return action in permissions.get(role, set())


# ── Request authentication middleware ────────────────────────


def normalize_principal(user: Optional[dict]) -> Optional[dict]:
    """Normalize auth principal schema.

    JWT tokens produce  {uid, usr, role, jti, ...}
    API key auth produces {id, username, role}

    Both are unified into {id, username, role, jti} so every downstream
    handler can safely access user["id"] and user["username"] regardless
    of the auth method used.
    """
    if not user:
        return None
    return {
        "id": user.get("id") or user.get("uid"),
        "username": user.get("username") or user.get("usr"),
        "role": user.get("role", "anonymous"),
        "jti": user.get("jti"),
    }


def extract_auth(headers: dict) -> Optional[dict]:
    """Extract and normalize user from request headers (Bearer token or API key)."""
    # Normalize dict to lowercase keys for reliable lookup
    if isinstance(headers, dict):
        headers = {k.lower(): v for k, v in headers.items()}
    auth_header = headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return normalize_principal(auth_manager.verify_token(token))
    if auth_header.startswith("ApiKey "):
        api_key = auth_header[7:]
        return normalize_principal(auth_manager.authenticate_api_key(api_key))
    # Check X-Session-Token header (used by frontend JS)
    session_token = headers.get("x-session-token", "")
    if session_token:
        return normalize_principal(auth_manager.verify_token(session_token))
    # Check X-API-Key header
    api_key = headers.get("x-api-key", "")
    if api_key:
        return normalize_principal(auth_manager.authenticate_api_key(api_key))
    return None


# ── Module instances ─────────────────────────────────────────

auth_manager = AuthManager()
rate_limiter = RateLimiter()
llm_rate_limiter = LLMRateLimiter()
ip_ban_list = IPBanList(ban_threshold=10, ban_duration=3600)
daily_quota = DailyQuotaManager()
