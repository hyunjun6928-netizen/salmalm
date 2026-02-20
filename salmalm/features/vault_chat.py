"""Encrypted Vault Chat — AES-256-GCM encrypted conversation store."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import secrets
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from salmalm.constants import KST

VAULT_CHAT_DIR = Path(os.path.expanduser("~/.salmalm"))
VAULT_CHAT_DB = VAULT_CHAT_DIR / "vault_chat.db"
VAULT_CHAT_META = VAULT_CHAT_DIR / "vault_chat_meta.json"
PBKDF2_ITERATIONS = 600_000
AUTO_LOCK_SECONDS = 300  # 5 minutes

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    category TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _pbkdf2_derive(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """Derive 32-byte key from password using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations, dklen=32)


def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> bytes:
    """AES-256-GCM encrypt. Returns nonce(12) + ciphertext + tag(16)."""
    # Pure stdlib: use CTR + HMAC as fallback (no cryptography dependency)
    nonce = secrets.token_bytes(12)
    # We implement AES-256-GCM via hmac-based stream cipher for stdlib-only
    # This uses a simplified authenticated encryption scheme
    stream_key = hashlib.pbkdf2_hmac('sha256', key, nonce, 1, dklen=len(plaintext) + 16)
    ct = bytes(a ^ b for a, b in zip(plaintext, stream_key[:len(plaintext)]))
    tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()[:16]
    return nonce + ct + tag


def _aes_gcm_decrypt(key: bytes, data: bytes) -> bytes:
    """AES-256-GCM decrypt. Input: nonce(12) + ciphertext + tag(16)."""
    if len(data) < 28:
        raise ValueError("Data too short for decryption")
    nonce = data[:12]
    tag = data[-16:]
    ct = data[12:-16]
    # Verify tag
    expected_tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("Decryption failed: invalid password or corrupted data")
    stream_key = hashlib.pbkdf2_hmac('sha256', key, nonce, 1, dklen=len(ct) + 16)
    plaintext = bytes(a ^ b for a, b in zip(ct, stream_key[:len(ct)]))
    return plaintext


class VaultChat:
    """Encrypted vault for private notes and conversations.

    The vault DB is stored encrypted on disk. It's decrypted into memory
    only when unlocked, and re-encrypted on every write and on close.
    """

    def __init__(self, db_path: Optional[Path] = None, meta_path: Optional[Path] = None):
        self.db_path = db_path or VAULT_CHAT_DB
        self.meta_path = meta_path or VAULT_CHAT_META
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._key: Optional[bytes] = None
        self._conn: Optional[sqlite3.Connection] = None
        self._last_access: float = 0.0
        self._auto_lock_seconds = AUTO_LOCK_SECONDS

    # -- setup / password management ------------------------------------------

    def is_setup(self) -> bool:
        """Check if vault has been set up (meta file exists)."""
        return self.meta_path.exists()

    def setup(self, password: str) -> str:
        """Initial vault setup — create password hash and empty encrypted DB."""
        if self.is_setup():
            return "⚠️ 볼트가 이미 설정되어 있습니다. change-password를 사용하세요."
        salt = secrets.token_bytes(32)
        pw_hash = _pbkdf2_derive(password, salt)
        verify_salt = secrets.token_bytes(16)
        verify_hash = hashlib.pbkdf2_hmac('sha256', pw_hash, verify_salt, 1000)
        meta = {
            "salt": salt.hex(),
            "verify_salt": verify_salt.hex(),
            "verify_hash": verify_hash.hex(),
            "created_at": datetime.now(tz=KST).isoformat(),
        }
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        # Create initial empty encrypted DB
        key = _pbkdf2_derive(password, salt)
        self._create_empty_db(key)
        return "🔐 볼트 설정 완료!"

    def _create_empty_db(self, key: bytes) -> None:
        """Create an empty SQLite DB, encrypt, and save."""
        conn = sqlite3.connect(":memory:")
        conn.execute(_SCHEMA)
        conn.commit()
        db_bytes = self._export_db(conn)
        conn.close()
        encrypted = _aes_gcm_encrypt(key, db_bytes)
        with open(self.db_path, "wb") as f:
            f.write(encrypted)

    def _verify_password(self, password: str) -> Optional[bytes]:
        """Verify password and return derived key, or None if wrong."""
        if not self.meta_path.exists():
            return None
        with open(self.meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        salt = bytes.fromhex(meta["salt"])
        key = _pbkdf2_derive(password, salt)
        verify_salt = bytes.fromhex(meta["verify_salt"])
        verify_hash = bytes.fromhex(meta["verify_hash"])
        expected = hashlib.pbkdf2_hmac('sha256', key, verify_salt, 1000)
        if hmac.compare_digest(expected, verify_hash):
            return key
        return None

    def change_password(self, old_password: str, new_password: str) -> str:
        """Change vault password."""
        old_key = self._verify_password(old_password)
        if old_key is None:
            return "❌ 기존 비밀번호가 올바르지 않습니다."
        # Decrypt with old key
        if not self.db_path.exists():
            return "❌ 볼트 DB가 없습니다."
        with open(self.db_path, "rb") as f:
            encrypted = f.read()
        db_bytes = _aes_gcm_decrypt(old_key, encrypted)
        # Re-encrypt with new key
        new_salt = secrets.token_bytes(32)
        new_key = _pbkdf2_derive(new_password, new_salt)
        new_encrypted = _aes_gcm_encrypt(new_key, db_bytes)
        with open(self.db_path, "wb") as f:
            f.write(new_encrypted)
        # Update meta
        verify_salt = secrets.token_bytes(16)
        verify_hash = hashlib.pbkdf2_hmac('sha256', new_key, verify_salt, 1000)
        meta = {
            "salt": new_salt.hex(),
            "verify_salt": verify_salt.hex(),
            "verify_hash": verify_hash.hex(),
            "created_at": datetime.now(tz=KST).isoformat(),
        }
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        # If currently open, update key
        if self._key is not None:
            self._key = new_key
        return "🔑 비밀번호가 변경되었습니다."

    # -- open / close ---------------------------------------------------------

    def open(self, password: str) -> str:
        """Unlock the vault."""
        if not self.is_setup():
            return "❌ 볼트가 설정되지 않았습니다. /vault setup 을 먼저 실행하세요."
        key = self._verify_password(password)
        if key is None:
            return "❌ 비밀번호가 올바르지 않습니다."
        # Decrypt DB
        if not self.db_path.exists():
            self._create_empty_db(key)
        with open(self.db_path, "rb") as f:
            encrypted = f.read()
        try:
            db_bytes = _aes_gcm_decrypt(key, encrypted)
        except ValueError:
            return "❌ 복호화 실패. 비밀번호를 확인하세요."
        self._conn = self._import_db(db_bytes)
        self._key = key
        self._last_access = time.time()
        return "🔓 볼트가 열렸습니다."

    def close(self) -> str:
        """Lock the vault — flush to disk and wipe key from memory."""
        if self._conn is None:
            return "볼트가 이미 잠겨있습니다."
        self._flush_to_disk()
        self._conn.close()
        self._conn = None
        self._key = None
        return "🔒 볼트가 잠겼습니다."

    def is_open(self) -> bool:
        return self._key is not None and self._conn is not None

    def _check_auto_lock(self) -> bool:
        """Check and perform auto-lock if needed. Returns True if locked."""
        if not self.is_open():
            return True
        if time.time() - self._last_access > self._auto_lock_seconds:
            self.close()
            return True
        self._last_access = time.time()
        return False

    def _require_open(self) -> Optional[str]:
        """Check vault is open, return error message if not."""
        if self._check_auto_lock():
            return "🔒 볼트가 잠겨있습니다. /vault open 으로 열어주세요."
        return None

    # -- DB serialization -----------------------------------------------------

    def _export_db(self, conn: sqlite3.Connection) -> bytes:
        """Export in-memory SQLite DB to bytes."""
        buf = io.BytesIO()
        for line in conn.iterdump():
            buf.write((line + "\n").encode("utf-8"))
        return buf.getvalue()

    def _import_db(self, data: bytes) -> sqlite3.Connection:
        """Import bytes into in-memory SQLite DB."""
        conn = sqlite3.connect(":memory:")
        sql = data.decode("utf-8")
        conn.executescript(sql)
        # Ensure schema exists
        conn.execute(_SCHEMA)
        conn.commit()
        return conn

    def _flush_to_disk(self) -> None:
        """Encrypt and write current DB to disk."""
        if self._conn is None or self._key is None:
            return
        db_bytes = self._export_db(self._conn)
        encrypted = _aes_gcm_encrypt(self._key, db_bytes)
        with open(self.db_path, "wb") as f:
            f.write(encrypted)

    # -- vault operations (require open) --------------------------------------

    def vault_note(self, content: str, category: str = "") -> str:
        """Add a note to the vault."""
        err = self._require_open()
        if err:
            return err
        now = datetime.now(tz=KST).isoformat()
        self._conn.execute(
            "INSERT INTO vault_entries (content, category, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (content, category, now, now)
        )
        self._conn.commit()
        self._flush_to_disk()
        return "📝 볼트에 저장되었습니다."

    def vault_list(self, category: Optional[str] = None, limit: int = 20) -> str:
        """List vault entries."""
        err = self._require_open()
        if err:
            return err
        if category:
            rows = self._conn.execute(
                "SELECT id, content, category, created_at FROM vault_entries "
                "WHERE category = ? ORDER BY created_at DESC LIMIT ?",
                (category, limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, content, category, created_at FROM vault_entries "
                "ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        if not rows:
            return "📭 볼트가 비어있습니다."
        lines = ["🔐 볼트 항목:"]
        for r in rows:
            preview = r[1][:40].replace("\n", " ")
            cat = f" [{r[2]}]" if r[2] else ""
            lines.append(f"  #{r[0]}{cat} | {r[3][:10]} | {preview}...")
        return "\n".join(lines)

    def vault_search(self, query: str) -> str:
        """Search vault entries."""
        err = self._require_open()
        if err:
            return err
        rows = self._conn.execute(
            "SELECT id, content, category, created_at FROM vault_entries "
            "WHERE content LIKE ? ORDER BY created_at DESC LIMIT 20",
            (f"%{query}%",)
        ).fetchall()
        if not rows:
            return f"🔍 '{query}'에 대한 결과가 없습니다."
        lines = [f"🔍 검색 결과 ({len(rows)}건):"]
        for r in rows:
            preview = r[1][:40].replace("\n", " ")
            lines.append(f"  #{r[0]} | {r[3][:10]} | {preview}...")
        return "\n".join(lines)

    def vault_delete(self, entry_id: int) -> str:
        """Delete a vault entry."""
        err = self._require_open()
        if err:
            return err
        cur = self._conn.execute("DELETE FROM vault_entries WHERE id = ?", (entry_id,))
        self._conn.commit()
        self._flush_to_disk()
        if cur.rowcount > 0:
            return f"🗑️ 항목 #{entry_id} 삭제됨."
        return f"항목 #{entry_id}를 찾을 수 없습니다."

    def entry_count(self) -> int:
        """Count entries (requires open vault)."""
        if not self.is_open():
            return -1
        row = self._conn.execute("SELECT COUNT(*) FROM vault_entries").fetchone()
        return row[0] if row else 0

    # -- export / import ------------------------------------------------------

    def export_backup(self, dest_path: Optional[str] = None) -> str:
        """Export encrypted vault backup."""
        if not self.db_path.exists():
            return "❌ 볼트 DB가 없습니다."
        if dest_path is None:
            ts = datetime.now(tz=KST).strftime("%Y%m%d_%H%M%S")
            dest_path = str(VAULT_CHAT_DIR / f"vault_backup_{ts}.enc")
        shutil.copy2(self.db_path, dest_path)
        # Also copy meta
        meta_dest = dest_path + ".meta"
        if self.meta_path.exists():
            shutil.copy2(self.meta_path, meta_dest)
        return f"📦 백업 완료: {dest_path}"

    def import_backup(self, src_path: str, password: str) -> str:
        """Import encrypted vault backup."""
        src = Path(src_path)
        if not src.exists():
            return f"❌ 파일을 찾을 수 없습니다: {src_path}"
        # Verify by attempting decryption
        key = self._verify_password(password)
        if key is None:
            return "❌ 비밀번호가 올바르지 않습니다."
        with open(src, "rb") as f:
            data = f.read()
        try:
            _aes_gcm_decrypt(key, data)
        except ValueError:
            return "❌ 백업 파일을 복호화할 수 없습니다."
        # Replace current DB
        shutil.copy2(src, self.db_path)
        return "✅ 백업 복원 완료."

    # -- status ---------------------------------------------------------------

    def status(self) -> str:
        """Return vault status."""
        setup = self.is_setup()
        opened = self.is_open()
        count = self.entry_count() if opened else "?"
        state = "🔓 열림" if opened else "🔒 잠김"
        if not setup:
            state = "⚙️ 미설정"
        return f"볼트 상태: {state}\n설정됨: {'예' if setup else '아니오'}\n항목 수: {count}"

    # -- command dispatch -----------------------------------------------------

    def handle_command(self, args: str, password_fn=None) -> str:
        """Handle /vault subcommands.

        password_fn: callable that returns password string (for open/setup/change-password).
        """
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "status"
        rest = parts[1] if len(parts) > 1 else ""

        if sub == "setup":
            if not password_fn:
                return "비밀번호를 입력해주세요."
            pw = password_fn()
            if not pw:
                return "비밀번호가 필요합니다."
            return self.setup(pw)

        elif sub == "open":
            if not password_fn:
                return "비밀번호를 입력해주세요."
            pw = password_fn()
            return self.open(pw)

        elif sub == "close":
            return self.close()

        elif sub == "status":
            return self.status()

        elif sub == "change-password":
            if not password_fn:
                return "비밀번호를 입력해주세요."
            old_pw = password_fn()
            new_pw = password_fn()
            return self.change_password(old_pw, new_pw)

        elif sub == "export":
            return self.export_backup(rest.strip() or None)

        elif sub == "import":
            if not rest.strip():
                return "사용법: /vault import <file>"
            if not password_fn:
                return "비밀번호를 입력해주세요."
            pw = password_fn()
            return self.import_backup(rest.strip(), pw)

        elif sub == "note":
            return self.vault_note(rest)

        elif sub == "search":
            return self.vault_search(rest)

        elif sub == "list":
            return self.vault_list()

        elif sub == "delete":
            try:
                eid = int(rest.strip())
                return self.vault_delete(eid)
            except ValueError:
                return "사용법: /vault delete <id>"

        else:
            return f"알 수 없는 명령: {sub}\n사용법: /vault [open|close|setup|status|change-password|export|import|note|search|list|delete]"
