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
from typing import Any, Dict, List, Optional

from salmalm.constants import VAULT_FILE, PBKDF2_ITER, VAULT_VERSION
from salmalm import log

# ── OS Keychain Integration ──
_KEYCHAIN_SERVICE = "salmalm"
_KEYCHAIN_ACCOUNT = "vault_master"


def _keychain_get() -> Optional[str]:
    """Retrieve vault password from OS keychain. Returns None if unavailable."""
    try:
        import keyring

        pw = keyring.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT)
        return pw
    except Exception as e:  # noqa: broad-except
        return None


def _keychain_set(password: str) -> bool:
    """Store vault password in OS keychain. Returns True on success."""
    try:
        import keyring

        keyring.set_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT, password)
        log.info("[OK] Vault password saved to OS keychain")
        return True
    except (ImportError, OSError, RuntimeError) as exc:
        log.debug(f"[WARN] Could not save to OS keychain: {exc}")
        return False


def _keychain_delete() -> bool:
    """Remove vault password from OS keychain."""
    try:
        import keyring

        keyring.delete_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT)
        return True
    except Exception as e:  # noqa: broad-except
        return False


HAS_CRYPTO: bool = False
_ALLOW_FALLBACK: bool = (
    os.environ.get("SALMALM_VAULT_FALLBACK", "1") == "1"
)  # Auto-fallback when cryptography is missing
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

    @property
    def is_unlocked(self) -> bool:
        """Whether the vault has been unlocked with a valid password."""
        return self._password is not None

    def create(self, password: str, save_to_keychain: bool = True) -> None:
        """Create a new vault with the given master password."""
        if not HAS_CRYPTO and not _ALLOW_FALLBACK:
            raise RuntimeError("Vault disabled: install 'cryptography' or set SALMALM_VAULT_FALLBACK=1")
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
        if not VAULT_FILE.exists():
            return False
        raw: bytes = VAULT_FILE.read_bytes()
        if len(raw) < 17:
            return False
        version: bytes = raw[0:1]
        self._salt = raw[1:17]
        ciphertext: bytes = raw[17:]
        self._password = password
        try:
            key = _derive_key(password, self._salt)
            plaintext: bytes
            if version == b"\x03" and HAS_CRYPTO:
                nonce, ct = ciphertext[:12], ciphertext[12:]
                plaintext = AESGCM(key).decrypt(nonce, ct, None)
            elif version in (b"\x02", b"\x03"):
                plaintext = self._unlock_hmac_ctr(password, ciphertext)
            else:
                return False
            self._data = json.loads(plaintext.decode("utf-8"))
            if save_to_keychain and password:
                _keychain_set(password)
            return True
        except Exception as e:  # noqa: broad-except
            self._password = None
            return False

    def _unlock_hmac_ctr(self, password: str, ciphertext: bytes) -> bytes:
        """Decrypt HMAC-CTR vault (new format with IV, legacy without)."""
        assert self._salt is not None, "Salt must be set before unlock"
        tag, rest = ciphertext[:32], ciphertext[32:]
        hmac_key = _derive_key(password, self._salt + b"hmac", 32)
        if len(rest) >= 16:
            iv, ct = rest[:16], rest[16:]
            expected = hmac.new(hmac_key, iv + ct, hashlib.sha256).digest()
            if hmac.compare_digest(tag, expected):
                enc_key = _derive_key(password, self._salt + b"enc" + iv, 32)
                return self._ctr_decrypt(enc_key, ct)
            # Legacy format (no IV)
            ct = rest
            expected = hmac.new(hmac_key, ct, hashlib.sha256).digest()
            if not hmac.compare_digest(tag, expected):
                raise ValueError("HMAC mismatch")
            enc_key = _derive_key(password, self._salt + b"enc", 32)
            return self._ctr_decrypt(enc_key, ct)
        raise ValueError("Ciphertext too short")

    def _save(self) -> None:
        """Encrypt and write vault to disk."""
        if self._password is None or self._salt is None:
            return
        VAULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        plaintext: bytes = json.dumps(self._data).encode("utf-8")
        key = _derive_key(self._password, self._salt)
        if HAS_CRYPTO:
            nonce = secrets.token_bytes(12)
            ct = AESGCM(key).encrypt(nonce, plaintext, None)
            VAULT_FILE.write_bytes(VAULT_VERSION + self._salt + nonce + ct)
            try:
                import os as _os

                _os.chmod(VAULT_FILE, 0o600)
            except OSError:
                pass
        elif _ALLOW_FALLBACK:
            iv = secrets.token_bytes(16)
            enc_key = _derive_key(self._password, self._salt + b"enc" + iv, 32)
            ct = self._ctr_encrypt(enc_key, plaintext)
            hmac_key = _derive_key(self._password, self._salt + b"hmac", 32)
            tag = hmac.new(hmac_key, iv + ct, hashlib.sha256).digest()
            VAULT_FILE.write_bytes(b"\x02" + self._salt + tag + iv + ct)
            try:
                import os as _os

                _os.chmod(VAULT_FILE, 0o600)
            except OSError:
                pass
        else:
            raise RuntimeError("Vault disabled: install 'cryptography' or set SALMALM_VAULT_FALLBACK=1")

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
        # Fallback: check env var
        env_name = self._ENV_MAP.get(key, key.upper())
        env_val = os.environ.get(env_name)
        if env_val:
            return env_val
        return default

    def set(self, key: str, value: Any) -> None:
        """Store a value (triggers re-encryption)."""
        self._data[key] = value
        self._save()

    def delete(self, key: str) -> None:
        """Delete a key."""
        self._data.pop(key, None)
        self._save()

    def change_password(self, old_password: str, new_password: str) -> bool:
        """Change vault master password. Returns True on success."""
        if not self.is_unlocked:
            return False
        # Verify old password matches current (timing-safe comparison)
        if not hmac.compare_digest((self._password or "").encode("utf-8"), old_password.encode("utf-8")):
            return False
        # Re-encrypt with new password
        self._password = new_password
        self._salt = secrets.token_bytes(16)
        self._save()
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
