"""Dead Man's Switch — triggers actions after prolonged user inactivity."""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from salmalm.constants import KST

DEADMAN_DIR = Path(os.path.expanduser("~/.salmalm"))
DEADMAN_CONFIG = DEADMAN_DIR / "deadman.json"
DEADMAN_STATE = DEADMAN_DIR / "deadman_state.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "inactivityDays": 3,
    "checkIntervalHours": 12,
    "actions": [
        {
            "type": "message",
            "target": "telegram:CHAT_ID",
            "content": "긴급: {user_name}이(가) {days}일간 응답이 없습니다."
        },
        {
            "type": "backup",
            "destination": "~/.salmalm/backup/deadman/"
        },
        {
            "type": "email",
            "to": "emergency@example.com",
            "subject": "Dead Man's Switch Activated"
        }
    ],
    "warningHours": 24,
    "confirmationRequired": True,
}


class DeadManSwitch:
    """Monitors user activity and triggers emergency actions on prolonged inactivity."""

    def __init__(self, config_path: Optional[Path] = None, state_path: Optional[Path] = None):
        self.config_path = config_path or DEADMAN_CONFIG
        self.state_path = state_path or DEADMAN_STATE
        self.config = self._load_config()
        self.state = self._load_state()

    # -- persistence ----------------------------------------------------------

    def _load_config(self) -> Dict[str, Any]:
        from salmalm.config_manager import ConfigManager
        if self.config_path != DEADMAN_CONFIG:
            # Custom path (e.g. tests) — use direct file I/O
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return dict(DEFAULT_CONFIG)
        return ConfigManager.load('deadman', defaults=DEFAULT_CONFIG)

    def _save_config(self) -> None:
        from salmalm.config_manager import ConfigManager
        if self.config_path != DEADMAN_CONFIG:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return
        ConfigManager.save('deadman', self.config)

    def _load_state(self) -> Dict[str, Any]:
        if self.state_path.exists():
            with open(self.state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "last_activity": time.time(),
            "warning_sent": False,
            "activated": False,
            "last_check": 0.0,
        }

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    # -- activity tracking ----------------------------------------------------

    def record_activity(self) -> None:
        """Record user activity (message or command)."""
        self.state["last_activity"] = time.time()
        self.state["warning_sent"] = False
        self.state["activated"] = False
        self._save_state()

    def reset(self) -> str:
        """Manually reset the timer."""
        self.record_activity()
        return "⏱️ Dead Man's Switch 타이머가 리셋되었습니다."

    # -- status ---------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Return current switch status."""
        enabled = self.config.get("enabled", False)
        last = self.state.get("last_activity", time.time())
        inactivity_secs = self.config.get("inactivityDays", 3) * 86400
        elapsed = time.time() - last
        remaining = max(0, inactivity_secs - elapsed)
        return {
            "enabled": enabled,
            "last_activity": datetime.fromtimestamp(last, tz=KST).isoformat(),
            "elapsed_hours": round(elapsed / 3600, 1),
            "remaining_hours": round(remaining / 3600, 1),
            "warning_sent": self.state.get("warning_sent", False),
            "activated": self.state.get("activated", False),
        }

    def format_status(self) -> str:
        s = self.status()
        state_str = "🟢 활성" if s["enabled"] else "⚪ 비활성"
        lines = [
            f"Dead Man's Switch: {state_str}",
            f"마지막 활동: {s['last_activity']}",
            f"경과: {s['elapsed_hours']}시간",
            f"남은 시간: {s['remaining_hours']}시간",
        ]
        if s["warning_sent"]:
            lines.append("⚠️ 경고 전송됨")
        if s["activated"]:
            lines.append("🚨 스위치 작동됨")
        return "\n".join(lines)

    # -- setup ----------------------------------------------------------------

    def setup(self, inactivity_days: int = 3, warning_hours: int = 24,
              actions: Optional[List[Dict]] = None,
              confirmation_required: bool = True) -> str:
        self.config["enabled"] = True
        self.config["inactivityDays"] = inactivity_days
        self.config["warningHours"] = warning_hours
        if actions is not None:
            self.config["actions"] = actions
        self.config["confirmationRequired"] = confirmation_required
        self._save_config()
        self.record_activity()
        return f"✅ Dead Man's Switch 설정 완료 (비활동 {inactivity_days}일, 경고 {warning_hours}시간 전)"

    def disable(self) -> str:
        self.config["enabled"] = False
        self._save_config()
        return "⏹️ Dead Man's Switch 비활성화됨."

    # -- check / heartbeat ----------------------------------------------------

    def check(self, send_fn=None, user_name: str = "사용자") -> Dict[str, Any]:
        """Periodic check — called from heartbeat.

        Returns dict with 'action' key: 'none', 'warning', 'activate'.
        send_fn(message: str) is used to send warning messages.
        """
        if not self.config.get("enabled", False):
            return {"action": "none", "reason": "disabled"}

        now = time.time()
        last = self.state.get("last_activity", now)
        inactivity_secs = self.config.get("inactivityDays", 3) * 86400
        warning_secs = self.config.get("warningHours", 24) * 3600
        elapsed = now - last

        # Already activated
        if self.state.get("activated", False):
            return {"action": "none", "reason": "already_activated"}

        # Time to activate?
        if elapsed >= inactivity_secs:
            return self._activate(user_name)

        # Time for warning?
        warning_threshold = inactivity_secs - warning_secs
        if elapsed >= warning_threshold and not self.state.get("warning_sent", False):
            return self._send_warning(send_fn)

        return {"action": "none", "reason": "within_threshold"}

    def confirm_alive(self) -> str:
        """User confirms they're alive after warning."""
        self.record_activity()
        return "✅ 확인되었습니다. 타이머가 리셋되었습니다."

    def _send_warning(self, send_fn=None) -> Dict[str, Any]:
        self.state["warning_sent"] = True
        self._save_state()
        msg = "⚠️ Dead Man's Switch: 아직 계신가요? `/deadman reset` 으로 확인해주세요."
        if send_fn:
            send_fn(msg)
        return {"action": "warning", "message": msg}

    def _activate(self, user_name: str = "사용자") -> Dict[str, Any]:
        self.state["activated"] = True
        self._save_state()
        results = []
        days = self.config.get("inactivityDays", 3)
        for action in self.config.get("actions", []):
            result = self._execute_action(action, user_name=user_name, days=days)
            results.append(result)
        return {"action": "activate", "results": results}

    def _execute_action(self, action: Dict, user_name: str = "사용자",
                        days: int = 3, dry_run: bool = False) -> Dict[str, Any]:
        atype = action.get("type", "unknown")
        if atype == "message":
            content = action.get("content", "").format(user_name=user_name, days=days)
            target = action.get("target", "")
            if dry_run:
                return {"type": "message", "target": target, "content": content, "dry_run": True}
            # In real implementation, dispatch to channel router
            return {"type": "message", "target": target, "content": content, "sent": True}
        elif atype == "backup":
            dest = os.path.expanduser(action.get("destination", "~/.salmalm/backup/deadman/"))
            if dry_run:
                return {"type": "backup", "destination": dest, "dry_run": True}
            return self._run_backup(dest)
        elif atype == "email":
            to = action.get("to", "")
            subject = action.get("subject", "Dead Man's Switch Activated")
            if dry_run:
                return {"type": "email", "to": to, "subject": subject, "dry_run": True}
            return {"type": "email", "to": to, "subject": subject, "sent": False,
                    "reason": "email sending not configured"}
        elif atype == "cleanup":
            paths = action.get("paths", [])
            if dry_run:
                return {"type": "cleanup", "paths": paths, "dry_run": True}
            return self._run_cleanup(paths)
        return {"type": atype, "error": "unknown action type"}

    def _run_backup(self, dest: str) -> Dict[str, Any]:
        dest_path = Path(dest)
        dest_path.mkdir(parents=True, exist_ok=True)
        src = Path(os.path.expanduser("~/.salmalm"))
        count = 0
        for f in src.glob("*.json"):
            shutil.copy2(f, dest_path / f.name)
            count += 1
        for f in src.glob("*.db"):
            shutil.copy2(f, dest_path / f.name)
            count += 1
        return {"type": "backup", "destination": dest, "files_copied": count}

    def _run_cleanup(self, paths: List[str]) -> Dict[str, Any]:
        removed = []
        for p in paths:
            fp = Path(os.path.expanduser(p))
            if fp.exists():
                if fp.is_dir():
                    shutil.rmtree(fp)
                else:
                    fp.unlink()
                removed.append(str(fp))
        return {"type": "cleanup", "removed": removed}

    # -- test -----------------------------------------------------------------

    def test(self, user_name: str = "사용자") -> List[Dict[str, Any]]:
        """Simulate activation without actually sending anything."""
        days = self.config.get("inactivityDays", 3)
        results = []
        for action in self.config.get("actions", []):
            result = self._execute_action(action, user_name=user_name, days=days, dry_run=True)
            results.append(result)
        return results

    # -- command dispatch -----------------------------------------------------

    def handle_command(self, args: str, send_fn=None, user_name: str = "사용자") -> str:
        """Handle /deadman subcommands."""
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "status"

        if sub == "setup":
            return self.setup()
        elif sub == "status":
            return self.format_status()
        elif sub == "test":
            results = self.test(user_name=user_name)
            lines = ["🧪 테스트 실행 결과 (dry run):"]
            for r in results:
                lines.append(f"  - {r['type']}: {r}")
            return "\n".join(lines)
        elif sub == "reset":
            return self.reset()
        elif sub == "off":
            return self.disable()
        else:
            return f"알 수 없는 명령: {sub}\n사용법: /deadman [setup|status|test|reset|off]"
