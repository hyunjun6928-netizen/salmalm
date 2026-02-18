"""SalmAlm crypto — AES-256-GCM vault with HMAC-CTR fallback."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any, Dict, List, Optional

from .constants import VAULT_FILE, PBKDF2_ITER, VAULT_VERSION
from . import log

HAS_CRYPTO: bool = False
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes as crypto_hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
    log.info("✅ cryptography available — AES-256-GCM enabled")
except ImportError:
    log.warning("⚠️ cryptography not installed — falling back to HMAC-CTR")


def _derive_key(password: str, salt: bytes, length: int = 32) -> bytes:
    """Derive encryption key using PBKDF2-HMAC-SHA256."""
    if HAS_CRYPTO:
        kdf = PBKDF2HMAC(
            algorithm=crypto_hashes.SHA256(), length=length,
            salt=salt, iterations=PBKDF2_ITER
        )
        return kdf.derive(password.encode('utf-8'))
    else:
        return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                    salt, PBKDF2_ITER, dklen=length)


class Vault:
    """Encrypted key-value store for API keys and secrets.

    Supports two encryption backends:
      - AES-256-GCM (when `cryptography` is installed)
      - HMAC-CTR with random IV (pure stdlib fallback)
    """

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self._password: Optional[str] = None
        self._salt: Optional[bytes] = None

    @property
    def is_unlocked(self) -> bool:
        """Whether the vault has been unlocked with a valid password."""
        return self._password is not None

    def create(self, password: str) -> None:
        """Create a new vault with the given master password."""
        self._password = password
        self._salt = secrets.token_bytes(16)
        self._data = {}
        self._save()

    def unlock(self, password: str) -> bool:
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
            if version == b'\x03' and HAS_CRYPTO:
                nonce, ct = ciphertext[:12], ciphertext[12:]
                plaintext = AESGCM(key).decrypt(nonce, ct, None)
            elif version in (b'\x02', b'\x03'):
                plaintext = self._unlock_hmac_ctr(password, ciphertext)
            else:
                return False
            self._data = json.loads(plaintext.decode('utf-8'))
            return True
        except Exception:
            self._password = None
            return False

    def _unlock_hmac_ctr(self, password: str, ciphertext: bytes) -> bytes:
        """Decrypt HMAC-CTR vault (new format with IV, legacy without)."""
        tag, rest = ciphertext[:32], ciphertext[32:]
        hmac_key = _derive_key(password, self._salt + b'hmac', 32)
        if len(rest) >= 16:
            iv, ct = rest[:16], rest[16:]
            expected = hmac.new(hmac_key, iv + ct, hashlib.sha256).digest()
            if hmac.compare_digest(tag, expected):
                enc_key = _derive_key(password, self._salt + b'enc' + iv, 32)
                return self._ctr_decrypt(enc_key, ct)
            # Legacy format (no IV)
            ct = rest
            expected = hmac.new(hmac_key, ct, hashlib.sha256).digest()
            if not hmac.compare_digest(tag, expected):
                raise ValueError("HMAC mismatch")
            enc_key = _derive_key(password, self._salt + b'enc', 32)
            return self._ctr_decrypt(enc_key, ct)
        raise ValueError("Ciphertext too short")

    def _save(self) -> None:
        """Encrypt and write vault to disk."""
        if not self._password or self._salt is None:
            return
        plaintext: bytes = json.dumps(self._data).encode('utf-8')
        key = _derive_key(self._password, self._salt)
        if HAS_CRYPTO:
            nonce = secrets.token_bytes(12)
            ct = AESGCM(key).encrypt(nonce, plaintext, None)
            VAULT_FILE.write_bytes(VAULT_VERSION + self._salt + nonce + ct)
        else:
            iv = secrets.token_bytes(16)
            enc_key = _derive_key(self._password, self._salt + b'enc' + iv, 32)
            ct = self._ctr_encrypt(enc_key, plaintext)
            hmac_key = _derive_key(self._password, self._salt + b'hmac', 32)
            tag = hmac.new(hmac_key, iv + ct, hashlib.sha256).digest()
            VAULT_FILE.write_bytes(b'\x02' + self._salt + tag + iv + ct)

    @staticmethod
    def _ctr_encrypt(key: bytes, data: bytes) -> bytes:
        """CTR-mode encryption using HMAC as block cipher."""
        out: bytearray = bytearray()
        ctr: int = 0
        for i in range(0, len(data), 32):
            block = hmac.new(key, ctr.to_bytes(8, 'big'), hashlib.sha256).digest()
            chunk = data[i:i + 32]
            out.extend(b ^ k for b, k in zip(chunk, block[:len(chunk)]))
            ctr += 1
        return bytes(out)

    _ctr_decrypt = _ctr_encrypt  # CTR is symmetric

    def get(self, key: str, default: Any = None) -> Any:
        """Get a stored value."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Store a value (triggers re-encryption)."""
        self._data[key] = value
        self._save()

    def delete(self, key: str) -> None:
        """Delete a key."""
        self._data.pop(key, None)
        self._save()

    def keys(self) -> List[str]:
        """List all stored key names."""
        return list(self._data.keys())


vault = Vault()
