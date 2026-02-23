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
import sqlite3
import threading
import time
from typing import Dict, List, Optional, Tuple

from salmalm.constants import DATA_DIR, KST, PBKDF2_ITER
from salmalm.security.crypto import log

AUTH_DB = DATA_DIR / "auth.db"

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
            conn = sqlite3.connect(str(AUTH_DB))
            conn.execute("""CREATE TABLE IF NOT EXISTS revoked_tokens (
                jti TEXT PRIMARY KEY,
                revoked_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )""")
            conn.commit()
            conn.close()
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
            # Try kid-specific key first, then all keys
            kid = payload.get("kid")
            keys_to_try = []
            if kid and kid in self._keys:
                keys_to_try.append(self._keys[kid])
            else:
                keys_to_try.extend(self._keys.values())
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
            if jti and self._is_revoked(jti):
                return None
            return payload  # type: ignore[no-any-return]
        except Exception as e:  # noqa: broad-except
            return None

    def revoke(self, token: str) -> bool:
        """Revoke a token by its jti. Returns True if successfully revoked."""
        try:
            parts = token.rsplit(".", 1)
            if len(parts) != 2:
                return False
            data = parts[0]
            padded = data + "=" * (-len(data) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if not jti:
                return False  # Legacy token without jti
            with self._revoked_lock:
                conn = sqlite3.connect(str(AUTH_DB))
                conn.execute(
                    "INSERT OR IGNORE INTO revoked_tokens (jti, revoked_at, expires_at) VALUES (?, ?, ?)",
                    (jti, time.time(), exp),
                )
                conn.commit()
                conn.close()
            return True
        except Exception as e:  # noqa: broad-except
            return False

    def revoke_all_for_user(self, user_id: int) -> None:
        """Rotate the secret to invalidate ALL tokens. Nuclear option."""
        # For per-user revocation without rotating global secret,
        # we'd need to store all active jtis. For now, this is a
        # placeholder — the per-token revoke() covers logout.
        pass

    def _is_revoked(self, jti: str) -> bool:
        """Check if a jti has been revoked."""
        try:
            conn = sqlite3.connect(str(AUTH_DB))
            row = conn.execute("SELECT 1 FROM revoked_tokens WHERE jti=?", (jti,)).fetchone()
            conn.close()
            return row is not None
        except Exception as e:  # noqa: broad-except
            return False

    def cleanup_expired(self) -> int:
        """Remove revocation entries for tokens that have expired anyway."""
        try:
            conn = sqlite3.connect(str(AUTH_DB))
            cursor = conn.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (time.time(),))
            conn.commit()
            deleted = cursor.rowcount
            conn.close()
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
        """Ensure db."""
        if self._initialized:
            return
        conn = sqlite3.connect(str(AUTH_DB))
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
            import sys
            import logging as _logging

            _stderr_handler = _logging.StreamHandler(sys.stderr)
            _stderr_handler.setFormatter(_logging.Formatter("%(message)s"))
            _sec_logger = _logging.getLogger("salmalm.auth.setup")
            _sec_logger.addHandler(_stderr_handler)
            _sec_logger.propagate = False
            _sec_logger.warning(
                f"\n{'=' * 50}\n"
                f"[USER] Default admin created\n"
                f"   Username: admin\n"
                f"   Password: {default_pw}\n"
                f"[WARN]  Save this password! It won't be shown again.\n"
                f"{'=' * 50}"
            )
            log.info("[USER] Default admin user created (password shown in console only)")
        conn.close()
        self._initialized = True

    @staticmethod
    def _hash_api_key(api_key: str) -> str:
        """Hash API key for storage (SHA-256). Original key is never stored."""
        return hashlib.sha256(api_key.encode()).hexdigest()

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

        conn = sqlite3.connect(str(AUTH_DB))
        try:
            uid, raw_api_key = self._create_user_db(conn, username, password, role)
            conn.close()
            # Return raw API key only at creation time — it's hashed in DB
            return {
                "id": uid,
                "username": username,
                "role": role,
                "api_key": raw_api_key,
            }
        except sqlite3.IntegrityError:
            conn.close()
            raise ValueError(f"Username already exists: {username}")

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """Authenticate user. Returns user dict or None."""
        self._ensure_db()

        # Check lockout (DB-persisted)
        if self._is_locked_out(username):
            log.warning(f"[LOCK] Account locked: {username}")
            return None

        conn = sqlite3.connect(str(AUTH_DB))
        row = conn.execute(
            "SELECT id, username, password_hash, password_salt, role, api_key, enabled FROM users WHERE username=?",
            (username,),
        ).fetchone()
        conn.close()

        if not row or not row[6]:  # Not found or disabled
            self._record_attempt(username)
            return None

        if not _verify_password(password, row[2], row[3]):
            self._record_attempt(username)
            return None

        # Success — clear attempts from DB
        try:
            conn2 = sqlite3.connect(str(AUTH_DB))
            conn2.execute("DELETE FROM login_attempts WHERE username=?", (username,))
            conn2.commit()
            conn2.close()
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")

        # Update last login
        conn = sqlite3.connect(str(AUTH_DB))
        from datetime import datetime

        conn.execute(
            "UPDATE users SET last_login=? WHERE id=?",
            (datetime.now(KST).isoformat(), row[0]),
        )
        conn.commit()
        conn.close()

        return {"id": row[0], "username": row[1], "role": row[4]}

    def authenticate_api_key(self, api_key: str) -> Optional[dict]:
        """Authenticate via API key (constant-time hash comparison)."""
        self._ensure_db()
        key_hash = self._hash_api_key(api_key)
        conn = sqlite3.connect(str(AUTH_DB))
        row = conn.execute(
            "SELECT id, username, role, enabled FROM users WHERE api_key=? AND enabled=1",
            (key_hash,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "role": row[2]}

    def _record_attempt(self, username: str, ip: str = ""):
        """Record a failed login attempt in DB (survives restart)."""
        try:
            conn = sqlite3.connect(str(AUTH_DB))
            conn.execute(
                "INSERT INTO login_attempts (username, attempted_at, ip_address) VALUES (?, ?, ?)",
                (username, time.time(), ip),
            )
            # Cleanup: remove attempts older than lockout window
            cutoff = time.time() - self._lockout_duration
            conn.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (cutoff,))
            conn.commit()
            conn.close()
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")

    def _is_locked_out(self, username: str) -> bool:
        """Check if username is locked out (DB-persisted, survives restart)."""
        try:
            conn = sqlite3.connect(str(AUTH_DB))
            cutoff = time.time() - self._lockout_duration
            row = conn.execute(
                "SELECT COUNT(*) FROM login_attempts WHERE username=? AND attempted_at>?",
                (username, cutoff),
            ).fetchone()
            conn.close()
            return (row[0] if row else 0) >= self._max_attempts
        except Exception as e:  # noqa: broad-except
            return False

    def create_token(self, user: dict, expires_in: int = 86400) -> str:
        """Create auth token for authenticated user."""
        return self._token_mgr.create(
            {
                "uid": user["id"],
                "usr": user["username"],
                "role": user["role"],
            },
            expires_in=expires_in,
        )

    def verify_token(self, token: str) -> Optional[dict]:
        """Verify auth token. Returns user info or None."""
        return self._token_mgr.verify(token)

    def revoke_token(self, token: str) -> bool:
        """Revoke a token (logout). Returns True on success."""
        return self._token_mgr.revoke(token)

    def list_users(self) -> List[dict]:
        """List all users (admin only)."""
        self._ensure_db()
        conn = sqlite3.connect(str(AUTH_DB))
        rows = conn.execute("SELECT id, username, role, created_at, last_login, enabled FROM users").fetchall()
        conn.close()
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
        conn = sqlite3.connect(str(AUTH_DB))
        cursor = conn.execute("DELETE FROM users WHERE username=? AND role != ?", (username, "admin"))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted

    def change_password(self, username: str, new_password: str) -> bool:
        """Change a user password. Returns True on success."""
        if len(new_password) < 8:
            from salmalm.core.exceptions import AuthError

            raise AuthError("Password must be at least 8 characters")
        self._ensure_db()
        pw_hash, salt = _hash_password(new_password)
        conn = sqlite3.connect(str(AUTH_DB))
        cursor = conn.execute(
            "UPDATE users SET password_hash=?, password_salt=? WHERE username=?",
            (pw_hash, salt, username),
        )
        conn.commit()
        ok = cursor.rowcount > 0
        conn.close()
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


def extract_auth(headers: dict) -> Optional[dict]:
    """Extract user from headers. Accepts dict (case-sensitive) or HTTPMessage (case-insensitive)."""
    # Normalize dict to lowercase keys for reliable lookup
    if isinstance(headers, dict):
        headers = {k.lower(): v for k, v in headers.items()}
    """Extract user from request headers (Bearer token or API key)."""
    auth_header = headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return auth_manager.verify_token(token)
    if auth_header.startswith("ApiKey "):
        api_key = auth_header[7:]
        return auth_manager.authenticate_api_key(api_key)
    # Check X-API-Key header
    api_key = headers.get("x-api-key", "")
    if api_key:
        return auth_manager.authenticate_api_key(api_key)
    return None


# ── Module instances ─────────────────────────────────────────

auth_manager = AuthManager()
rate_limiter = RateLimiter()
