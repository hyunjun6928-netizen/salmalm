from .constants import VAULT_FILE, PBKDF2_ITER, VAULT_VERSION

from . import log

import json

import secrets

import hmac

import hashlib

HAS_CRYPTO = False
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes as crypto_hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
    log.info("✅ cryptography available — AES-256-GCM enabled")
except ImportError:
    log.warning("⚠️ cryptography not installed — falling back to HMAC-CTR")


def _derive_key(password: str, salt: bytes, length: int = 32) -> bytes:
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
    """Encrypted key-value store for API keys and secrets."""

    def __init__(self):
        self._data: dict = {}
        self._password: Optional[str] = None
        self._salt: Optional[bytes] = None

    def create(self, password: str):
        self._password = password
        self._salt = secrets.token_bytes(16)
        self._data = {}
        self._save()

    def unlock(self, password: str) -> bool:
        if not VAULT_FILE.exists():
            return False
        raw = VAULT_FILE.read_bytes()
        if len(raw) < 17:
            return False
        version = raw[0:1]
        self._salt = raw[1:17]
        ciphertext = raw[17:]
        self._password = password
        try:
            key = _derive_key(password, self._salt)
            if version == b'\x03' and HAS_CRYPTO:
                # AES-256-GCM
                nonce = ciphertext[:12]
                ct = ciphertext[12:]
                aesgcm = AESGCM(key)
                plaintext = aesgcm.decrypt(nonce, ct, None)
            elif version == b'\x02' or (version == b'\x03' and not HAS_CRYPTO):
                # HMAC-CTR fallback
                tag = ciphertext[:32]
                ct = ciphertext[32:]
                hmac_key = _derive_key(password, self._salt + b'hmac', 32)
                expected = hmac.new(hmac_key, ct, hashlib.sha256).digest()
                if not hmac.compare_digest(tag, expected):
                    return False
                enc_key = _derive_key(password, self._salt + b'enc', 32)
                plaintext = self._ctr_decrypt(enc_key, ct)
            else:
                return False
            self._data = json.loads(plaintext.decode('utf-8'))
            return True
        except Exception:
            self._password = None
            return False

    def _save(self):
        if not self._password or self._salt is None:
            return
        plaintext = json.dumps(self._data).encode('utf-8')
        key = _derive_key(self._password, self._salt)
        if HAS_CRYPTO:
            nonce = secrets.token_bytes(12)
            aesgcm = AESGCM(key)
            ct = aesgcm.encrypt(nonce, plaintext, None)
            VAULT_FILE.write_bytes(VAULT_VERSION + self._salt + nonce + ct)
        else:
            # HMAC-CTR
            enc_key = _derive_key(self._password, self._salt + b'enc', 32)
            ct = self._ctr_encrypt(enc_key, plaintext)
            hmac_key = _derive_key(self._password, self._salt + b'hmac', 32)
            tag = hmac.new(hmac_key, ct, hashlib.sha256).digest()
            VAULT_FILE.write_bytes(b'\x02' + self._salt + tag + ct)

    @staticmethod
    def _ctr_encrypt(key: bytes, data: bytes) -> bytes:
        out, ctr = bytearray(), 0
        for i in range(0, len(data), 32):
            block = hmac.new(key, ctr.to_bytes(8, 'big'), hashlib.sha256).digest()
            chunk = data[i:i+32]
            out.extend(b ^ k for b, k in zip(chunk, block[:len(chunk)]))
            ctr += 1
        return bytes(out)

    _ctr_decrypt = _ctr_encrypt  # symmetric

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self._save()

    def delete(self, key: str):
        self._data.pop(key, None)
        self._save()

    def keys(self):
        return list(self._data.keys())

    @property
    def is_unlocked(self):
        return self._password is not None


vault = Vault()
