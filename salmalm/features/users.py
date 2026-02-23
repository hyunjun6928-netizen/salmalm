"""SalmAlm Users — Multi-tenant user management, quotas, per-user isolation.

Features:
  - User CRUD (create/list/delete/enable/disable)
  - Per-user quotas (daily/monthly cost limits)
  - Per-user vault (API keys per user, or shared admin keys)
  - Per-user settings (model, persona, routing)
  - Telegram chat_id ↔ user mapping
  - Quota reset (daily at 00:00, monthly on 1st)
  - Admin dashboard data

Usage:
  from salmalm.features.users import user_manager
  user_manager.create_user('alice', 'password123')
  user_manager.check_quota(user_id)  # raises QuotaExceeded
  user_manager.record_cost(user_id, 0.05)
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from salmalm.constants import BASE_DIR, KST, DATA_DIR
from salmalm.security.crypto import log

USERS_DB = BASE_DIR / "auth.db"  # Reuse auth.db for user tables
_USERS_DIR = DATA_DIR / "users"


class QuotaExceeded(Exception):
    """Raised when a user exceeds their daily or monthly cost quota."""

    def __init__(self, message: str = "사용량 한도를 초과했습니다 / Quota exceeded") -> None:
        super().__init__(message)
        self.message = message


class UserManager:
    """Multi-tenant user manager with quotas and data isolation."""

    _lock = threading.Lock()
    _initialized = False
    # Multi-tenant mode flag: False = legacy single-user mode (backward compat)
    _multi_tenant_enabled: Optional[bool] = None

    # Default quotas (USD)
    DEFAULT_DAILY_LIMIT = 5.0
    DEFAULT_MONTHLY_LIMIT = 50.0

    def _ensure_db(self):
        if self._initialized:
            return
        conn = sqlite3.connect(str(USERS_DB))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")

        # users table (created by auth.py, but ensure it exists here too)
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL DEFAULT x'',
            password_salt BLOB NOT NULL DEFAULT x'',
            role TEXT NOT NULL DEFAULT 'user',
            api_key TEXT UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_login TEXT,
            enabled INTEGER NOT NULL DEFAULT 1
        )""")

        # user_quotas table
        conn.execute("""CREATE TABLE IF NOT EXISTS user_quotas (
            user_id INTEGER PRIMARY KEY,
            daily_limit REAL NOT NULL DEFAULT 5.0,
            monthly_limit REAL NOT NULL DEFAULT 50.0,
            current_daily REAL NOT NULL DEFAULT 0.0,
            current_monthly REAL NOT NULL DEFAULT 0.0,
            last_daily_reset TEXT,
            last_monthly_reset TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )""")

        # user_settings table
        conn.execute("""CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            model_preference TEXT DEFAULT 'auto',
            persona TEXT DEFAULT 'default',
            routing_config TEXT DEFAULT '{}',
            tts_enabled INTEGER DEFAULT 0,
            tts_voice TEXT DEFAULT 'alloy',
            settings_json TEXT DEFAULT '{}',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )""")

        # telegram_users mapping table
        conn.execute("""CREATE TABLE IF NOT EXISTS telegram_users (
            chat_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            username TEXT,
            registered_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )""")

        # Add user_id column to session_store if not exists
        try:
            conn.execute("ALTER TABLE session_store ADD COLUMN user_id INTEGER DEFAULT NULL")
        except Exception:
            pass

        # Add user_id to usage_stats if not exists
        try:
            conn.execute("ALTER TABLE usage_stats ADD COLUMN user_id INTEGER DEFAULT NULL")
        except Exception:
            pass

        # multi_tenant_config table
        conn.execute("""CREATE TABLE IF NOT EXISTS multi_tenant_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")

        conn.commit()
        conn.close()
        self._initialized = True

    @property
    def multi_tenant_enabled(self) -> bool:
        """Check if multi-tenant mode is enabled."""
        if self._multi_tenant_enabled is not None:
            return self._multi_tenant_enabled
        self._ensure_db()
        try:
            conn = sqlite3.connect(str(USERS_DB))
            row = conn.execute("SELECT value FROM multi_tenant_config WHERE key='enabled'").fetchone()
            conn.close()
            self._multi_tenant_enabled = row and row[0] == "true"
        except Exception:
            self._multi_tenant_enabled = False
        return self._multi_tenant_enabled  # type: ignore

    def enable_multi_tenant(self, enabled: bool = True) -> None:
        """Enable or disable multi-tenant mode."""
        self._ensure_db()
        conn = sqlite3.connect(str(USERS_DB))
        conn.execute(
            "INSERT OR REPLACE INTO multi_tenant_config (key, value) VALUES ('enabled', ?)",
            ("true" if enabled else "false",),
        )
        conn.commit()
        conn.close()
        self._multi_tenant_enabled = enabled
        log.info(f"[TENANT] Multi-tenant mode: {'enabled' if enabled else 'disabled'}")

    def get_config(self, key: str, default: str = "") -> str:
        """Get a multi-tenant config value."""
        self._ensure_db()
        try:
            conn = sqlite3.connect(str(USERS_DB))
            row = conn.execute("SELECT value FROM multi_tenant_config WHERE key=?", (key,)).fetchone()
            conn.close()
            return row[0] if row else default
        except Exception:
            return default

    def set_config(self, key: str, value: str) -> None:
        """Set a multi-tenant config value."""
        self._ensure_db()
        conn = sqlite3.connect(str(USERS_DB))
        conn.execute("INSERT OR REPLACE INTO multi_tenant_config (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()

    # ── Quota Management ─────────────────────────────────────

    def ensure_quota(self, user_id: int) -> None:
        """Create quota record for user if it doesn't exist."""
        self._ensure_db()
        conn = sqlite3.connect(str(USERS_DB))
        existing = conn.execute("SELECT user_id FROM user_quotas WHERE user_id=?", (user_id,)).fetchone()
        if not existing:
            now = datetime.now(KST).isoformat()
            conn.execute(
                "INSERT INTO user_quotas (user_id, daily_limit, monthly_limit, current_daily, current_monthly, last_daily_reset, last_monthly_reset) VALUES (?,?,?,0,0,?,?)",
                (user_id, self.DEFAULT_DAILY_LIMIT, self.DEFAULT_MONTHLY_LIMIT, now, now),
            )
            conn.commit()
        conn.close()

    def check_quota(self, user_id: int) -> dict:
        """Check if user is within quota. Returns quota info.
        Raises QuotaExceeded if over limit."""
        if not self.multi_tenant_enabled:
            return {"ok": True, "unlimited": True}

        self._ensure_db()
        self._maybe_reset_quotas(user_id)
        conn = sqlite3.connect(str(USERS_DB))
        row = conn.execute(
            "SELECT daily_limit, monthly_limit, current_daily, current_monthly FROM user_quotas WHERE user_id=?",
            (user_id,),
        ).fetchone()
        conn.close()

        if not row:
            self.ensure_quota(user_id)
            return {
                "ok": True,
                "daily_remaining": self.DEFAULT_DAILY_LIMIT,
                "monthly_remaining": self.DEFAULT_MONTHLY_LIMIT,
            }

        daily_limit, monthly_limit, current_daily, current_monthly = row
        daily_remaining = daily_limit - current_daily
        monthly_remaining = monthly_limit - current_monthly

        if daily_remaining <= 0:
            raise QuotaExceeded(
                f"일일 사용량을 초과했습니다 (${current_daily:.2f}/${daily_limit:.2f}). "
                f"내일 리셋됩니다. / Daily quota exceeded."
            )
        if monthly_remaining <= 0:
            raise QuotaExceeded(
                f"월별 사용량을 초과했습니다 (${current_monthly:.2f}/${monthly_limit:.2f}). "
                f"다음 달에 리셋됩니다. / Monthly quota exceeded."
            )

        return {
            "ok": True,
            "daily_limit": daily_limit,
            "monthly_limit": monthly_limit,
            "current_daily": current_daily,
            "current_monthly": current_monthly,
            "daily_remaining": daily_remaining,
            "monthly_remaining": monthly_remaining,
        }

    def record_cost(self, user_id: int, cost: float) -> None:
        """Record cost against user quota."""
        if not self.multi_tenant_enabled or cost <= 0:
            return
        self._ensure_db()
        self.ensure_quota(user_id)
        conn = sqlite3.connect(str(USERS_DB))
        conn.execute(
            "UPDATE user_quotas SET current_daily = current_daily + ?, current_monthly = current_monthly + ? WHERE user_id=?",
            (cost, cost, user_id),
        )
        conn.commit()
        conn.close()

    def set_quota(self, user_id: int, daily_limit: Optional[float] = None, monthly_limit: Optional[float] = None) -> None:
        """Set quota limits for a user (admin only)."""
        self._ensure_db()
        self.ensure_quota(user_id)
        conn = sqlite3.connect(str(USERS_DB))
        if daily_limit is not None:
            conn.execute("UPDATE user_quotas SET daily_limit=? WHERE user_id=?", (daily_limit, user_id))
        if monthly_limit is not None:
            conn.execute("UPDATE user_quotas SET monthly_limit=? WHERE user_id=?", (monthly_limit, user_id))
        conn.commit()
        conn.close()

    def get_quota(self, user_id: int) -> dict:
        """Get quota info for a user."""
        self._ensure_db()
        self._maybe_reset_quotas(user_id)
        conn = sqlite3.connect(str(USERS_DB))
        row = conn.execute(
            "SELECT daily_limit, monthly_limit, current_daily, current_monthly FROM user_quotas WHERE user_id=?",
            (user_id,),
        ).fetchone()
        conn.close()
        if not row:
            return {
                "daily_limit": self.DEFAULT_DAILY_LIMIT,
                "monthly_limit": self.DEFAULT_MONTHLY_LIMIT,
                "current_daily": 0,
                "current_monthly": 0,
            }
        return {
            "daily_limit": row[0],
            "monthly_limit": row[1],
            "current_daily": row[2],
            "current_monthly": row[3],
            "daily_remaining": row[0] - row[2],
            "monthly_remaining": row[1] - row[3],
        }

    def _maybe_reset_quotas(self, user_id: int):
        """Reset daily/monthly quotas if due."""
        conn = sqlite3.connect(str(USERS_DB))
        row = conn.execute(
            "SELECT last_daily_reset, last_monthly_reset FROM user_quotas WHERE user_id=?", (user_id,)
        ).fetchone()
        if not row:
            conn.close()
            return

        now = datetime.now(KST)
        last_daily = row[0]
        last_monthly = row[1]
        updates = []

        # Daily reset: if last reset was not today
        if last_daily:
            try:
                last_dt = datetime.fromisoformat(last_daily)
                if last_dt.date() < now.date():
                    updates.append(("current_daily", 0))
                    updates.append(("last_daily_reset", now.isoformat()))
            except Exception:
                pass

        # Monthly reset: if last reset was in a previous month
        if last_monthly:
            try:
                last_dt = datetime.fromisoformat(last_monthly)
                if (last_dt.year, last_dt.month) < (now.year, now.month):
                    updates.append(("current_monthly", 0))
                    updates.append(("last_monthly_reset", now.isoformat()))
            except Exception:
                pass

        if updates:
            for col, val in updates:
                conn.execute(f"UPDATE user_quotas SET {col}=? WHERE user_id=?", (val, user_id))
            conn.commit()
            log.info(f"[QUOTA] Reset quotas for user {user_id}: {[u[0] for u in updates]}")
        conn.close()

    def reset_all_daily_quotas(self) -> None:
        """Reset all users' daily quotas. Called at midnight."""
        self._ensure_db()
        now = datetime.now(KST).isoformat()
        conn = sqlite3.connect(str(USERS_DB))
        count = conn.execute("UPDATE user_quotas SET current_daily=0, last_daily_reset=?", (now,)).rowcount
        conn.commit()
        conn.close()
        if count:
            log.info(f"[QUOTA] Daily quota reset for {count} users")

    def reset_all_monthly_quotas(self) -> None:
        """Reset all users' monthly quotas. Called on 1st of month."""
        self._ensure_db()
        now = datetime.now(KST).isoformat()
        conn = sqlite3.connect(str(USERS_DB))
        count = conn.execute("UPDATE user_quotas SET current_monthly=0, last_monthly_reset=?", (now,)).rowcount
        conn.commit()
        conn.close()
        if count:
            log.info(f"[QUOTA] Monthly quota reset for {count} users")

    # ── User Settings ────────────────────────────────────────

    def get_user_settings(self, user_id: int) -> dict:
        """Get per-user settings."""
        self._ensure_db()
        conn = sqlite3.connect(str(USERS_DB))
        row = conn.execute(
            "SELECT model_preference, persona, routing_config, tts_enabled, tts_voice, settings_json FROM user_settings WHERE user_id=?",
            (user_id,),
        ).fetchone()
        conn.close()
        if not row:
            return {
                "model_preference": "auto",
                "persona": "default",
                "routing_config": {},
                "tts_enabled": False,
                "tts_voice": "alloy",
                "extra": {},
            }
        try:
            routing = json.loads(row[2]) if row[2] else {}
        except Exception:
            routing = {}
        try:
            extra = json.loads(row[5]) if row[5] else {}
        except Exception:
            extra = {}
        return {
            "model_preference": row[0] or "auto",
            "persona": row[1] or "default",
            "routing_config": routing,
            "tts_enabled": bool(row[3]),
            "tts_voice": row[4] or "alloy",
            "extra": extra,
        }

    def set_user_settings(self, user_id: int, **kwargs) -> None:
        """Update per-user settings."""
        self._ensure_db()
        conn = sqlite3.connect(str(USERS_DB))
        # Ensure row exists
        conn.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
        for key, value in kwargs.items():
            if key == "routing_config":
                value = json.dumps(value, ensure_ascii=False)
            elif key == "extra":
                value = json.dumps(value, ensure_ascii=False)
                key = "settings_json"
            elif key == "tts_enabled":
                value = 1 if value else 0
            if key in ("model_preference", "persona", "routing_config", "tts_enabled", "tts_voice", "settings_json"):
                conn.execute(f"UPDATE user_settings SET {key}=? WHERE user_id=?", (value, user_id))
        conn.commit()
        conn.close()

    # ── Per-user Vault ───────────────────────────────────────

    def get_user_vault_dir(self, user_id: int) -> Path:
        """Get per-user vault directory."""
        d = _USERS_DIR / str(user_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_user_uploads_dir(self, user_id: int) -> Path:
        """Get per-user uploads directory."""
        from salmalm.constants import WORKSPACE_DIR

        d = WORKSPACE_DIR / "uploads" / str(user_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── Telegram Mapping ─────────────────────────────────────

    def get_user_by_telegram(self, chat_id: str) -> Optional[dict]:
        """Look up user by Telegram chat_id."""
        self._ensure_db()
        conn = sqlite3.connect(str(USERS_DB))
        row = conn.execute(
            """
            SELECT u.id, u.username, u.role, u.enabled, t.username as tg_username
            FROM telegram_users t
            JOIN users u ON t.user_id = u.id
            WHERE t.chat_id = ?
        """,
            (str(chat_id),),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "role": row[2], "enabled": bool(row[3]), "tg_username": row[4]}

    def link_telegram(self, chat_id: str, user_id: int, tg_username: str = "") -> None:
        """Link a Telegram chat_id to a user account."""
        self._ensure_db()
        now = datetime.now(KST).isoformat()
        conn = sqlite3.connect(str(USERS_DB))
        conn.execute(
            "INSERT OR REPLACE INTO telegram_users (chat_id, user_id, username, registered_at) VALUES (?,?,?,?)",
            (str(chat_id), user_id, tg_username, now),
        )
        conn.commit()
        conn.close()
        log.info(f"[TENANT] Telegram {chat_id} linked to user {user_id}")

    def unlink_telegram(self, chat_id: str) -> None:
        """Unlink a Telegram chat_id."""
        self._ensure_db()
        conn = sqlite3.connect(str(USERS_DB))
        conn.execute("DELETE FROM telegram_users WHERE chat_id=?", (str(chat_id),))
        conn.commit()
        conn.close()

    def register_telegram_user(self, chat_id: str, password: str, tg_username: str = "") -> dict:
        """Register a new user via Telegram.
        Creates user account + links telegram chat_id.
        Username = tg_username or 'tg_{chat_id}'.
        Returns {'ok': True, 'user': ...} or {'ok': False, 'error': ...}.
        """
        from salmalm.web.auth import auth_manager

        username = tg_username or f"tg_{chat_id}"
        # Check if chat_id already linked
        existing = self.get_user_by_telegram(chat_id)
        if existing:
            return {"ok": False, "error": f"이미 등록되었습니다 ({existing['username']}). / Already registered."}
        try:
            user = auth_manager.create_user(username, password, role="user")
            self.link_telegram(chat_id, user["id"], tg_username)
            self.ensure_quota(user["id"])
            return {"ok": True, "user": user}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    # ── Admin Dashboard Data ─────────────────────────────────

    def get_all_users_with_stats(self) -> List[dict]:
        """Get all users with usage stats for admin dashboard."""
        self._ensure_db()
        conn = sqlite3.connect(str(USERS_DB))

        users = []
        rows = conn.execute("""
            SELECT u.id, u.username, u.role, u.created_at, u.last_login, u.enabled
            FROM users u ORDER BY u.id
        """).fetchall()

        for r in rows:
            uid = r[0]
            # Get quota
            quota_row = conn.execute(
                "SELECT daily_limit, monthly_limit, current_daily, current_monthly FROM user_quotas WHERE user_id=?",
                (uid,),
            ).fetchone()

            # Get session count
            session_count = (
                conn.execute("SELECT COUNT(*) FROM session_store WHERE user_id=?", (uid,)).fetchone()[0] or 0
            )

            # Get total cost from usage_stats
            cost_row = conn.execute("SELECT SUM(cost) FROM usage_stats WHERE user_id=?", (uid,)).fetchone()
            total_cost = cost_row[0] if cost_row and cost_row[0] else 0

            # Get telegram link
            tg_row = conn.execute("SELECT chat_id FROM telegram_users WHERE user_id=?", (uid,)).fetchone()

            user_data = {
                "id": uid,
                "username": r[1],
                "role": r[2],
                "created_at": r[3],
                "last_login": r[4],
                "enabled": bool(r[5]),
                "session_count": session_count,
                "total_cost": total_cost,
                "telegram_linked": bool(tg_row),
            }
            if quota_row:
                user_data["quota"] = {
                    "daily_limit": quota_row[0],
                    "monthly_limit": quota_row[1],
                    "current_daily": quota_row[2],
                    "current_monthly": quota_row[3],
                }
            users.append(user_data)

        conn.close()
        return users

    def toggle_user(self, user_id: int, enabled: bool) -> bool:
        """Enable or disable a user account."""
        self._ensure_db()
        conn = sqlite3.connect(str(USERS_DB))
        cursor = conn.execute(
            "UPDATE users SET enabled=? WHERE id=? AND role != ?", (1 if enabled else 0, user_id, "admin")
        )
        conn.commit()
        ok = cursor.rowcount > 0
        conn.close()
        return ok

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        """Get user by ID."""
        self._ensure_db()
        conn = sqlite3.connect(str(USERS_DB))
        row = conn.execute("SELECT id, username, role, enabled FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "role": row[2], "enabled": bool(row[3])}

    def get_user_by_username(self, username: str) -> Optional[dict]:
        """Get user by username."""
        self._ensure_db()
        conn = sqlite3.connect(str(USERS_DB))
        row = conn.execute("SELECT id, username, role, enabled FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "role": row[2], "enabled": bool(row[3])}

    def get_registration_mode(self) -> str:
        """Get registration mode: 'open' or 'admin_only' (default)."""
        return self.get_config("registration_mode", "admin_only")

    def set_registration_mode(self, mode: str) -> None:
        """Set registration mode."""
        if mode not in ("open", "admin_only"):
            raise ValueError("Mode must be 'open' or 'admin_only'")
        self.set_config("registration_mode", mode)

    def get_telegram_allowlist_mode(self) -> bool:
        """Check if Telegram allowlist mode is enabled."""
        return self.get_config("telegram_allowlist", "false") == "true"

    def set_telegram_allowlist_mode(self, enabled: bool) -> None:
        """Enable/disable Telegram allowlist mode."""
        self.set_config("telegram_allowlist", "true" if enabled else "false")


# Module singleton
user_manager = UserManager()
