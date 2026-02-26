"""SalmAlm crypto — AES-256-GCM vault with HMAC-CTR fallback.

Password storage hierarchy (most secure → least secure):
  1. OS keychain (macOS Keychain / Windows Credential Manager / Linux Secret Service)
  2. User-entered master password (prompted each session)
  3. SALMALM_VAULT_KEY env var (deprecated — convenience only)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
from typing import Any, Dict, List, Optional

from salmalm.constants import VAULT_FILE, PBKDF2_ITER, VAULT_VERSION
from salmalm import log

# ── OS Keychain Integration ──
_KEYCHAIN_SERVICE = "salmalm"
_KEYCHAIN_ACCOUNT = "vault_master"

try:
    import keyring as _keyring  # noqa: F401
except (ImportError, Exception):
    _keyring = None

def _get_keyring():
    """Get keyring module. Uses sys.modules to support test patching."""
    import sys
    return sys.modules.get("keyring", _keyring)


def _keychain_get() -> Optional[str]:
    """Retrieve vault password from OS keychain. Returns None if unavailable."""
    try:
        kr = _get_keyring()
        if kr is None:
            return None
        pw = kr.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT)
        return pw
    except Exception as e:  # noqa: broad-except
        log.debug(f"[KEYCHAIN] get failed: {e}")
        return None


def _keychain_set(password: str) -> bool:
    """Store vault password in OS keychain. Returns True on success."""
    try:
        kr = _get_keyring()
        if kr is None:
            return False
        kr.set_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT, password)
        log.info("[OK] Vault password saved to OS keychain")
        return True
    except (ImportError, OSError, RuntimeError) as exc:
        log.debug(f"[WARN] Could not save to OS keychain: {exc}")
        return False


def _keychain_delete() -> bool:
    """Remove vault password from OS keychain."""
    try:
        kr = _get_keyring()
        if kr is None:
            return False
        kr.delete_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT)
        return True
    except Exception as e:  # noqa: broad-except
        log.debug(f"[KEYCHAIN] delete failed: {e}")
        return False


HAS_CRYPTO: bool = False
_ALLOW_FALLBACK: bool = (
    os.environ.get("SALMALM_VAULT_FALLBACK", "0") == "1"
)  # HMAC-CTR fallback when cryptography is missing (default OFF — matches SECURITY.md)
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes as crypto_hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    HAS_CRYPTO = True
    log.info("[OK] cryptography available -- AES-256-GCM enabled")
except ImportError:
    log.warning(
        "[WARN] cryptography not installed -- HMAC-CTR fallback enabled automatically. "
        "Install 'pip install salmalm[crypto]' for AES-256-GCM encryption."
    )


def _derive_key(password: str, salt: bytes, length: int = 32) -> bytes:
    """Derive encryption key using PBKDF2-HMAC-SHA256."""
    if HAS_CRYPTO:
        kdf = PBKDF2HMAC(
            algorithm=crypto_hashes.SHA256(),
            length=length,
            salt=salt,
            iterations=PBKDF2_ITER,
        )
        return kdf.derive(password.encode("utf-8"))
    else:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITER, dklen=length)


class Vault:
    """Encrypted key-value store for API keys and secrets.

    Supports two encryption backends:
      - AES-256-GCM (when `cryptography` is installed)
      - HMAC-CTR with random IV (pure stdlib fallback)
    """

    def __init__(self) -> None:
        """Init  ."""
        self._data: Dict[str, Any] = {}
        self._password: Optional[str] = None
        self._salt: Optional[bytes] = None
        self._lock = threading.RLock()  # Reentrant lock for thread-safe vault ops

    @property
    def is_unlocked(self) -> bool:
        """Whether the vault has been unlocked with a valid password."""
        return self._password is not None

    def create(self, password: str, save_to_keychain: bool = True, force: bool = False) -> None:
        """Create a new vault with the given master password.

        Args:
            force: If False (default), refuse to overwrite an existing vault file.
                   This prevents accidental data loss from stale create() calls.
        """
        if not HAS_CRYPTO and not _ALLOW_FALLBACK:
            raise RuntimeError("Vault disabled: install 'cryptography' or set SALMALM_VAULT_FALLBACK=1")
        with self._lock:
            if not force and VAULT_FILE.exists():
                raise RuntimeError(
                    "Vault already exists. Unlock it instead, or pass force=True to overwrite."
                )
            self._password = password
            self._salt = secrets.token_bytes(16)
            self._data = {}
            self._save()
        if save_to_keychain and password:
            _keychain_set(password)

    def try_keychain_unlock(self) -> bool:
        """Attempt to unlock vault using OS keychain. Returns True on success."""
        pw = _keychain_get()
        if pw is not None:
            if self.unlock(pw):
                log.info("[OK] Vault unlocked via OS keychain")
                return True
        return False

    def unlock(self, password: str, save_to_keychain: bool = False) -> bool:
        """Unlock an existing vault. Returns True on success."""
        with self._lock:
            if not VAULT_FILE.exists():
                return False
            raw: bytes = VAULT_FILE.read_bytes()
            if len(raw) < 17:
                return False
            version: bytes = raw[0:1]
            _tmp_salt: bytes = raw[1:17]   # local — NOT committed until success
            ciphertext: bytes = raw[17:]
            try:
                key = _derive_key(password, _tmp_salt)
                plaintext: bytes
                if version == b"\x03" and HAS_CRYPTO:
                    nonce, ct = ciphertext[:12], ciphertext[12:]
                    plaintext = AESGCM(key).decrypt(nonce, ct, None)
                elif version in (b"\x02", b"\x03"):
                    plaintext = self._unlock_hmac_ctr(password, ciphertext, _tmp_salt)
                else:
                    return False
                _tmp_data = json.loads(plaintext.decode("utf-8"))
                # ── commit atomically ONLY after full success ──────────────
                self._salt = _tmp_salt
                self._password = password
                self._data = _tmp_data
                if save_to_keychain and password:
                    _keychain_set(password)
                return True
            except json.JSONDecodeError as e:
                log.warning(f"[VAULT] Unlock failed: corrupted vault data: {e}")
                return False
            except ValueError as e:
                log.warning(f"[VAULT] Unlock failed: {e}")
                return False
            except Exception as e:  # noqa: broad-except
                log.warning(f"[VAULT] Unlock failed: {type(e).__name__}: {e}")
                return False

    def _unlock_hmac_ctr(self, password: str, ciphertext: bytes,
                         salt: Optional[bytes] = None) -> bytes:
        """Decrypt HMAC-CTR vault (new format with IV, legacy without).

        Format discrimination:
          new  : tag(32) | iv(16) | ct(N)  — HMAC covers (iv || ct)
          legacy: tag(32) | ct(N)           — HMAC covers ct only; no IV

        The two-attempt fallback is NOT an HMAC oracle: both attempts use the
        same hmac_key derived from the caller-supplied password.  An adversary
        without the password cannot make either HMAC comparison pass, so there
        is no exploitable oracle.  The fallback exists only for backward-compat
        with pre-IV vaults and is removed in the next major version.

        salt: explicit bytes (preferred); falls back to self._salt for compat.
        """
        _salt = salt if salt is not None else self._salt
        if _salt is None:
            raise ValueError("Salt must be provided")
        tag, rest = ciphertext[:32], ciphertext[32:]
        if len(rest) < 1:
            raise ValueError("Ciphertext too short")
        hmac_key = _derive_key(password, _salt + b"hmac", 32)

        # ── Attempt 1: new format (tag | iv | ct) ──────────────────────────
        if len(rest) >= 16:
            iv, ct = rest[:16], rest[16:]
            expected = hmac.new(hmac_key, iv + ct, hashlib.sha256).digest()
            if hmac.compare_digest(tag, expected):
                enc_key = _derive_key(password, _salt + b"enc" + iv, 32)
                return self._ctr_decrypt(enc_key, ct)

        # ── Attempt 2: legacy format (tag | ct, no IV) — backward compat ───
        # Only reached when new-format HMAC fails, indicating a pre-IV vault.
        log.debug("[VAULT] New-format HMAC mismatch — trying legacy (no-IV) format")
        ct = rest
        expected = hmac.new(hmac_key, ct, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("HMAC mismatch — wrong password or corrupted vault")
        enc_key = _derive_key(password, _salt + b"enc", 32)
        return self._ctr_decrypt(enc_key, ct)

    @staticmethod
    def _atomic_write(path, data: bytes) -> None:
        """Write *data* to *path* atomically: tmpfile → fsync → rename.

        Guarantees that *path* is never left in a partial state if the process
        crashes mid-write.  Uses a sibling temp file so rename() is same-device.
        """
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(parent))
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, str(path))   # atomic on POSIX; best-effort on Windows

    def _save(self) -> None:
        """Encrypt and write vault to disk.

        Must only be called while self._lock is held (create/unlock/set/delete/change_password
        all acquire the lock before calling _save).
        Writes an atomic backup (.vault.enc.bak) AFTER a successful save so we can
        recover from corruption on the next startup.
        """
        if self._password is None or self._salt is None:
            return
        VAULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        plaintext: bytes = json.dumps(self._data).encode("utf-8")
        _backup_file = VAULT_FILE.parent / (VAULT_FILE.name + ".bak")
        if HAS_CRYPTO:
            # AES-256-GCM: one PBKDF2 call
            key = _derive_key(self._password, self._salt)
            nonce = secrets.token_bytes(12)
            ct = AESGCM(key).encrypt(nonce, plaintext, None)
            new_bytes = VAULT_VERSION + self._salt + nonce + ct
        elif _ALLOW_FALLBACK:
            # HMAC-CTR: two PBKDF2 calls (enc_key + hmac_key).
            # Do NOT compute the base key — it is unused in this branch.
            iv = secrets.token_bytes(16)
            enc_key = _derive_key(self._password, self._salt + b"enc" + iv, 32)
            ct = self._ctr_encrypt(enc_key, plaintext)
            hmac_key = _derive_key(self._password, self._salt + b"hmac", 32)
            tag = hmac.new(hmac_key, iv + ct, hashlib.sha256).digest()
            new_bytes = b"\x02" + self._salt + tag + iv + ct
        else:
            raise RuntimeError("Vault disabled: install 'cryptography' or set SALMALM_VAULT_FALLBACK=1")

        self._atomic_write(VAULT_FILE, new_bytes)
        # Only update backup when vault is non-trivially large (has real keys)
        if len(new_bytes) > 100:
            try:
                self._atomic_write(_backup_file, new_bytes)
            except OSError:
                pass

    @staticmethod
    def _ctr_encrypt(key: bytes, data: bytes) -> bytes:
        """CTR-mode encryption using HMAC as block cipher."""
        out: bytearray = bytearray()
        ctr: int = 0
        for i in range(0, len(data), 32):
            block = hmac.new(key, ctr.to_bytes(8, "big"), hashlib.sha256).digest()
            chunk = data[i : i + 32]
            out.extend(b ^ k for b, k in zip(chunk, block[: len(chunk)]))
            ctr += 1
        return bytes(out)

    _ctr_decrypt = _ctr_encrypt  # CTR is symmetric

    # Map vault keys → env var names
    _ENV_MAP = {
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "openai_api_key": "OPENAI_API_KEY",
        "xai_api_key": "XAI_API_KEY",
        "google_api_key": "GOOGLE_API_KEY",
        "gemini_api_key": "GEMINI_API_KEY",
        "brave_api_key": "BRAVE_SEARCH_API_KEY",
        "openrouter_api_key": "OPENROUTER_API_KEY",
        "ollama_url": "OLLAMA_URL",
        "telegram_token": "TELEGRAM_TOKEN",
        "telegram_owner_id": "TELEGRAM_OWNER_ID",
        "discord_token": "DISCORD_TOKEN",
    }

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Get a stored value. Falls back to environment variable if not in vault."""
        val = self._data.get(key)
        if val is not None:
            return val
        # Fallback: check env var.  Log so the user knows which source is active.
        env_name = self._ENV_MAP.get(key, key.upper())
        env_val = os.environ.get(env_name)
        if env_val:
            log.debug("[VAULT] '%s' not in vault — using env var %s", key, env_name)
            return env_val
        return default

    def set(self, key: str, value: Any) -> None:
        """Store a value (triggers re-encryption)."""
        with self._lock:
            self._data[key] = value
            self._save()

    def delete(self, key: str) -> None:
        """Delete a key."""
        with self._lock:
            self._data.pop(key, None)
            self._save()

    def change_password(self, old_password: str, new_password: str) -> bool:
        """Change vault master password. Returns True on success."""
        with self._lock:
            if not self.is_unlocked:
                return False
            # Verify old password matches current (timing-safe comparison)
            if not hmac.compare_digest((self._password or "").encode("utf-8"), old_password.encode("utf-8")):
                return False
            # Re-encrypt with new password
            self._password = new_password
            self._salt = secrets.token_bytes(16)
            self._save()
            # Update keychain inside the lock: ensures vault and keychain are always
            # in sync.  If _keychain_set fails after _save succeeds the vault is still
            # usable via manual password entry — this is acceptable.
            _keychain_set(new_password)
        return True

    def keys(self) -> List[str]:
        """List all stored key names."""
        return list(self._data.keys())


vault = Vault()


# ── Fallback HMAC-CTR Encryption Notes ──
# Version byte in .vault.enc header:
#   b'\x03' = AES-256-GCM (requires `cryptography` package)
#   b'\x02' = HMAC-CTR fallback (stdlib only, NOT a standard AEAD)
#
# HMAC-CTR uses HMAC-SHA256 as a PRF to generate keystream blocks:
#   keystream[i] = HMAC(key, counter_i)  →  XOR with plaintext
# Integrity is via a separate HMAC tag over (IV || ciphertext).
#
# This is safe for personal/dev use but NOT a peer-reviewed construction.
# For production: install `cryptography` (AES-256-GCM).
