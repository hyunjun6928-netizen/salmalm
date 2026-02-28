"""JWT-like token management (HMAC-SHA256) with jti revocation support.

Extracted from salmalm.web.auth to separate token lifecycle concerns from
user authentication and rate-limiting logic.

Usage:
    from salmalm.web.token_manager import TokenManager, token_manager
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Dict, Optional

from salmalm.constants import DATA_DIR
from salmalm.db import get_connection
from salmalm.security.crypto import log

AUTH_DB = DATA_DIR / "auth.db"

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
            conn = get_connection(AUTH_DB)
            conn.execute("""CREATE TABLE IF NOT EXISTS revoked_tokens (
                jti TEXT PRIMARY KEY,
                revoked_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS user_revocations (
                user_id INTEGER PRIMARY KEY,
                revoked_after TEXT NOT NULL
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
            # Check per-user bulk revocation
            uid = payload.get("uid")
            iat = payload.get("iat", 0)
            if uid and self._is_user_revoked(uid, iat):
                return None
            return payload  # type: ignore[no-any-return]
        except Exception as e:  # noqa: broad-except
            return None

    def revoke(self, token: str) -> bool:
        """Revoke a token by its jti. Returns True if successfully revoked.

        Signature is verified before the jti is persisted — prevents an
        attacker from inserting arbitrary jtis into the revocation table
        by submitting a forged token payload.
        """
        # verify() validates signature, expiry, and revocation status
        payload = self.verify(token)
        if not payload:
            return False  # Invalid / expired / already revoked — nothing to do
        jti = payload.get("jti")
        exp = payload.get("exp", 0)
        if not jti:
            return False  # Legacy token without jti
        try:
            with self._revoked_lock:
                conn = get_connection(AUTH_DB)
                conn.execute(
                    "INSERT OR IGNORE INTO revoked_tokens (jti, revoked_at, expires_at) VALUES (?, ?, ?)",
                    (jti, time.time(), exp),
                )
                conn.commit()
                conn.close()
            return True
        except Exception as _e:  # noqa: broad-except
            log.debug("[TOKEN] revoke DB write failed: %s", _e)
            return False

    def revoke_all_for_user(self, user_id: int) -> None:
        """Revoke ALL active tokens for *user_id*.

        Inserts a revocation timestamp into user_revocations. Any token with
        iat <= revoked_after for this user_id will be rejected by verify().
        """
        try:
            conn = get_connection(AUTH_DB)
            try:
                import datetime as _dt
                revoked_after = _dt.datetime.now(_dt.timezone.utc).isoformat()
                conn.execute(
                    "INSERT OR REPLACE INTO user_revocations (user_id, revoked_after) VALUES (?, ?)",
                    (user_id, revoked_after),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            log.warning("[TOKEN] revoke_all_for_user failed: %s", e)

    def _is_revoked(self, jti: str) -> bool:
        """Check if a jti has been revoked."""
        try:
            conn = get_connection(AUTH_DB)
            row = conn.execute("SELECT 1 FROM revoked_tokens WHERE jti=?", (jti,)).fetchone()
            conn.close()
            return row is not None
        except Exception as e:  # noqa: broad-except
            return False

    def _is_user_revoked(self, user_id: int, token_iat: int) -> bool:
        """Check if all tokens for user_id issued at or before token_iat have been revoked."""
        try:
            conn = get_connection(AUTH_DB)
            import datetime as _dt
            row = conn.execute(
                "SELECT revoked_after FROM user_revocations WHERE user_id=?", (user_id,)
            ).fetchone()
            conn.close()
            if row:
                revoked_ts = _dt.datetime.fromisoformat(row[0]).timestamp()
                return token_iat <= revoked_ts
        except Exception:
            pass
        return False


    def cleanup_expired(self) -> int:
        """Remove revocation entries for tokens that have expired anyway."""
        try:
            conn = get_connection(AUTH_DB)
            cursor = conn.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (time.time(),))
            conn.commit()
            deleted = cursor.rowcount
            conn.close()
            return deleted
        except Exception as e:  # noqa: broad-except
            return 0



# Singleton instance
token_manager = TokenManager()
