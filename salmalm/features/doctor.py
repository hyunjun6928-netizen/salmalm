"""SalmAlm Doctor — self-diagnosis and repair tool.

자가 진단 + 수복 도구.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import shutil
import time
from datetime import timezone, timedelta
from pathlib import Path
from typing import List
from salmalm.constants import DATA_DIR

KST = timezone(timedelta(hours=9))

_SALMALM_DIR = DATA_DIR


def _status(ok: bool, msg: str, fixable: bool = False, issue_id: str = "") -> dict:
    """Status."""
    return {
        "status": "ok" if ok else "issue",
        "message": msg,
        "fixable": fixable,
        "issue_id": issue_id,
    }


class Doctor:
    """SalmAlm 자가 진단 + 수복 도구."""

    def check_python_version(self) -> dict:
        """Python 버전 확인 (3.9+ 필수)."""
        import sys
        v = sys.version_info
        if v >= (3, 9):
            return _status(True, f"Python {v.major}.{v.minor}.{v.micro}")
        return _status(False, f"Python {v.major}.{v.minor} — 3.9+ required")

    def check_crypto(self) -> dict:
        """cryptography 패키지 설치 여부."""
        try:
            from salmalm.security.crypto import HAS_CRYPTO
            if HAS_CRYPTO:
                return _status(True, "Vault: AES-256-GCM (cryptography installed)")
            return _status(False, "⚠️ Vault: HMAC-CTR fallback (weaker). Run: pip install salmalm[crypto]")
        except Exception as e:
            return _status(False, f"Vault check failed: {e}")

    def check_channels(self) -> dict:
        """Telegram/Discord 봇 토큰 유효성."""
        import urllib.request
        import urllib.error
        try:
            from salmalm.security.crypto import vault
        except Exception:
            return _status(True, "Channels: vault unavailable, skipped")

        results = []
        tg_token = vault.get("telegram_bot_token")
        if tg_token:
            try:
                req = urllib.request.Request(f"https://api.telegram.org/bot{tg_token}/getMe")
                resp = urllib.request.urlopen(req, timeout=5)
                data = json.loads(resp.read())
                bot_name = data.get("result", {}).get("username", "?")
                results.append(f"Telegram: ✅ @{bot_name}")
            except Exception:
                results.append("Telegram: ❌ invalid token")
        dc_token = vault.get("discord_bot_token")
        if dc_token:
            try:
                req = urllib.request.Request(
                    "https://discord.com/api/v10/users/@me",
                    headers={"Authorization": f"Bot {dc_token}"},
                )
                resp = urllib.request.urlopen(req, timeout=5)
                data = json.loads(resp.read())
                bot_name = data.get("username", "?")
                results.append(f"Discord: ✅ {bot_name}")
            except Exception:
                results.append("Discord: ❌ invalid token")
        if not results:
            return _status(True, "Channels: none configured")
        return _status("❌" not in " ".join(results), f"Channels: {'; '.join(results)}")

    def run_all(self, auto_fix: bool = False) -> List[dict]:
        """전체 진단 실행, 결과 리스트 반환."""
        checks = [
            self.check_python_version,
            self.check_crypto,
            self.check_config_integrity,
            self.check_database_integrity,
            self.check_session_integrity,
            self.check_api_keys,
            self.check_channels,
            self.check_port_availability,
            self.check_disk_space,
            self.check_permissions,
            self.check_oauth_expiry,
        ]
        results = []
        for check in checks:
            try:
                result = check()
            except Exception as e:
                result = _status(False, f"{check.__name__}: {e}")
            results.append(result)
            if auto_fix and result.get("fixable") and result.get("issue_id"):
                try:
                    self.repair(result["issue_id"])
                    result["auto_fixed"] = True
                except Exception:
                    result["auto_fixed"] = False
        return results

    def check_config_integrity(self) -> dict:
        """설정 파일 존재/유효성/권한 검사."""
        if not _SALMALM_DIR.exists():
            return _status(False, "Data directory missing", fixable=True, issue_id="missing_dir")
        config_files = list(_SALMALM_DIR.glob("*.json"))
        bad = []
        for cf in config_files:
            try:
                json.loads(cf.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                bad.append(f"{cf.name}: {e}")
        if bad:
            return _status(False, f"Invalid config files: {', '.join(bad)}", fixable=False, issue_id="bad_config")
        return _status(True, f"{len(config_files)} config files OK")

    def check_database_integrity(self) -> dict:
        """SQLite DB 무결성 (PRAGMA integrity_check)."""
        db_files = list(_SALMALM_DIR.glob("*.db")) + list(_SALMALM_DIR.glob("*.sqlite"))
        if not db_files:
            return _status(True, "No databases found")
        bad = []
        for db in db_files:
            try:
                conn = sqlite3.connect(str(db))
                result = conn.execute("PRAGMA integrity_check").fetchone()
                conn.close()
                if result[0] != "ok":
                    bad.append(f"{db.name}: {result[0]}")
            except Exception as e:
                bad.append(f"{db.name}: {e}")
        if bad:
            return _status(False, f"DB issues: {'; '.join(bad)}")
        return _status(True, f"{len(db_files)} databases OK")

    def check_session_integrity(self) -> dict:
        """세션 파일 존재/크기/손상 검사."""
        session_dir = _SALMALM_DIR / "sessions"
        if not session_dir.exists():
            return _status(True, "No session directory (OK)")
        files = list(session_dir.iterdir())
        bad = []
        for f in files:
            if f.suffix == ".json":
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        bad.append(f.name)
                except Exception:
                    bad.append(f.name)
            if f.stat().st_size == 0:
                bad.append(f"{f.name} (empty)")
        if bad:
            return _status(False, f"Bad sessions: {', '.join(bad)}", fixable=True, issue_id="bad_sessions")
        return _status(True, f"{len(files)} session files OK")

    def check_api_keys(self) -> dict:
        """API 키 설정 여부 + 실제 유효성 검증."""
        import urllib.request
        import urllib.error

        try:
            from salmalm.security.crypto import vault
        except Exception as e:
            return _status(False, f"Cannot load vault: {e}")

        providers = {
            "openai_api_key": ("https://api.openai.com/v1/models", "Bearer"),
            "anthropic_api_key": ("https://api.anthropic.com/v1/models", "x-api-key"),
            "google_api_key": (None, None),  # Google uses query param
            "xai_api_key": ("https://api.x.ai/v1/models", "Bearer"),
        }
        results = []
        for key_name, (url, auth_type) in providers.items():
            provider = key_name.replace("_api_key", "")
            key = os.environ.get(key_name.upper()) or vault.get(key_name)
            if not key:
                results.append(f"{provider}: ⚠️ no key")
                continue
            if not url:
                results.append(f"{provider}: ✅ key set")
                continue
            try:
                headers = {}
                if auth_type == "Bearer":
                    headers["Authorization"] = f"Bearer {key}"
                elif auth_type == "x-api-key":
                    headers["x-api-key"] = key
                    headers["anthropic-version"] = "2023-06-01"
                req = urllib.request.Request(url, headers=headers)
                urllib.request.urlopen(req, timeout=5)
                results.append(f"{provider}: ✅ valid")
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    results.append(f"{provider}: ❌ invalid key (401)")
                else:
                    results.append(f"{provider}: ⚠️ HTTP {e.code}")
            except Exception as e:
                results.append(f"{provider}: ⚠️ {str(e)[:40]}")

        valid = sum(1 for r in results if "✅" in r)
        invalid = sum(1 for r in results if "❌" in r)
        if invalid:
            return _status(False, f"API keys: {'; '.join(results)}")
        if valid == 0:
            return _status(False, "No API keys configured")
        return _status(True, f"API keys: {'; '.join(results)}")

    def check_port_availability(self) -> dict:
        """서버 포트 사용 가능 여부."""
        port = int(os.environ.get("SALMALM_PORT", "8080"))
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            result = s.connect_ex(("127.0.0.1", port))
            s.close()
            if result == 0:
                return _status(True, f"Port {port} is in use (server running)")
            return _status(True, f"Port {port} is available")
        except Exception as e:
            return _status(False, f"Port check failed: {e}")

    def check_disk_space(self) -> dict:
        """디스크 여유 공간."""
        usage = shutil.disk_usage(str(Path.home()))
        free_gb = usage.free / (1024**3)
        if free_gb < 1.0:
            return _status(False, f"Low disk: {free_gb:.1f}GB free", fixable=False)
        return _status(True, f"Disk OK: {free_gb:.1f}GB free")

    def check_permissions(self) -> dict:
        """설정 파일 권한 (600 권장)."""
        if not _SALMALM_DIR.exists():
            return _status(True, "No config directory")
        issues = []
        for f in _SALMALM_DIR.glob("*.json"):
            mode = f.stat().st_mode & 0o777
            if mode & 0o077:  # group/other can read
                issues.append(f"{f.name}: {oct(mode)}")
        if issues:
            return _status(False, f"Loose permissions: {', '.join(issues)}", fixable=True, issue_id="permissions")
        return _status(True, "File permissions OK")

    def check_oauth_expiry(self) -> dict:
        """OAuth 토큰 만료 임박 여부."""
        token_file = _SALMALM_DIR / "oauth_tokens.json"
        if not token_file.exists():
            return _status(True, "No OAuth tokens")
        try:
            tokens = json.loads(token_file.read_text(encoding="utf-8"))
            now = time.time()
            expiring = []
            for name, tok in tokens.items():
                exp = tok.get("expires_at", 0)
                if exp and exp - now < 3600:
                    expiring.append(name)
            if expiring:
                return _status(False, f"Tokens expiring soon: {', '.join(expiring)}", fixable=False)
            return _status(True, "OAuth tokens OK")
        except Exception as e:
            return _status(False, f"Cannot read tokens: {e}")

    def migrate_config(self) -> dict:
        """구 설정 → 신 설정 자동 마이그레이션."""
        try:
            from salmalm.config_manager import ConfigManager

            migrated = ConfigManager.migrate("channels")
            return _status(True, f"Migration {'applied' if migrated else 'not needed'}")
        except Exception as e:
            return _status(False, f"Migration failed: {e}")

    def repair(self, issue_id: str) -> bool:
        """특정 이슈 자동 수복."""
        if issue_id == "missing_dir":
            _SALMALM_DIR.mkdir(parents=True, exist_ok=True)
            return True
        elif issue_id == "permissions":
            for f in _SALMALM_DIR.glob("*.json"):
                f.chmod(0o600)
            return True
        elif issue_id == "bad_sessions":
            session_dir = _SALMALM_DIR / "sessions"
            if session_dir.exists():
                for f in session_dir.iterdir():
                    if f.stat().st_size == 0:
                        f.unlink()
            return True
        return False

    def format_report(self, results: List[dict] = None) -> str:
        """Format diagnosis results as human-readable text."""
        if results is None:
            results = self.run_all()
        lines = ["🏥 **SalmAlm Doctor Report**\n"]
        for r in results:
            icon = "✅" if r["status"] == "ok" else "❌"
            fix = " (🔧 fixable)" if r.get("fixable") else ""
            fixed = " ✨ auto-fixed" if r.get("auto_fixed") else ""
            lines.append(f"{icon} {r['message']}{fix}{fixed}")
        ok = sum(1 for r in results if r["status"] == "ok")
        total = len(results)
        lines.append(f"\n📊 {ok}/{total} checks passed")
        return "\n".join(lines)


# Singleton
doctor = Doctor()
