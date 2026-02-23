"""SalmAlm Hooks System — 이벤트 훅 매니저 (Event Hook Manager).

특정 이벤트 발생 시 사용자 정의 스크립트/명령을 비동기 실행합니다.
Executes user-defined scripts/commands asynchronously on specific events.

Supported events:
  on_message, on_response, on_tool_call, on_error,
  on_session_create, on_startup, on_shutdown

Config: ~/.salmalm/hooks.json
"""

import json
import os
import subprocess
import threading
from typing import Dict, List, Optional

from salmalm.security.crypto import log
from salmalm.constants import DATA_DIR

HOOKS_FILE = DATA_DIR / "hooks.json"

# Valid event names
VALID_EVENTS = (
    "on_message",
    "on_response",
    "on_tool_call",
    "on_error",
    "on_session_create",
    "on_startup",
    "on_shutdown",
)


class HookManager:
    """Manages event hooks — loads config, fires hooks asynchronously."""

    def __init__(self) -> None:
        """Init  ."""
        self._hooks: Dict[str, List[str]] = {}
        self._plugin_hooks: Dict[str, List[callable]] = {}  # from plugins
        self.reload()

    def reload(self) -> None:
        """Reload hooks from ~/.salmalm/hooks.json."""
        self._hooks = {}
        try:
            if HOOKS_FILE.exists():
                data = json.loads(HOOKS_FILE.read_text(encoding="utf-8"))
                for event, cmds in data.items():
                    if event in VALID_EVENTS and isinstance(cmds, list):
                        self._hooks[event] = [c for c in cmds if isinstance(c, str)]
                log.info(
                    f"[HOOK] Loaded {sum(len(v) for v in self._hooks.values())} hooks for {len(self._hooks)} events"
                )
        except Exception as e:
            log.error(f"[HOOK] Failed to load hooks.json: {e}")

    def save(self) -> None:
        """Save current hooks config."""
        try:
            HOOKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            HOOKS_FILE.write_text(json.dumps(self._hooks, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.error(f"[HOOK] Failed to save hooks.json: {e}")

    def register_plugin_hook(self, event: str, callback: callable) -> None:
        """Register a plugin callback for an event."""
        if event not in VALID_EVENTS:
            return
        self._plugin_hooks.setdefault(event, []).append(callback)

    def unregister_plugin_hooks(self, callbacks: list) -> None:
        """Remove specific plugin callbacks."""
        for event in list(self._plugin_hooks.keys()):
            self._plugin_hooks[event] = [cb for cb in self._plugin_hooks[event] if cb not in callbacks]

    def fire(self, event: str, context: Optional[Dict] = None) -> None:
        """Fire an event — runs all registered hooks asynchronously (non-blocking).

        Context is passed via environment variables:
          SALMALM_EVENT, SALMALM_SESSION_ID, SALMALM_MESSAGE
        """
        if event not in VALID_EVENTS:
            return

        ctx = context or {}
        cmds = self._hooks.get(event, [])
        plugin_cbs = self._plugin_hooks.get(event, [])

        if not cmds and not plugin_cbs:
            return

        env = {
            **os.environ,
            "SALMALM_EVENT": event,
            "SALMALM_SESSION_ID": str(ctx.get("session_id", "")),
            "SALMALM_MESSAGE": str(ctx.get("message", ""))[:4096],
        }

        # Fire shell commands in background threads
        for cmd in cmds:
            t = threading.Thread(target=self._run_cmd, args=(cmd, env, event), daemon=True, name=f"hook-{event}")
            t.start()

        # Fire plugin callbacks in background threads
        for cb in plugin_cbs:
            t = threading.Thread(
                target=self._run_callback, args=(cb, event, ctx), daemon=True, name=f"hook-plugin-{event}"
            )
            t.start()

    @staticmethod
    def _run_cmd(cmd: str, env: dict, event: str):
        """Execute a hook command (runs in background thread)."""
        try:
            import shlex

            result = subprocess.run(shlex.split(cmd), env=env, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                log.warning(f"[HOOK] {event} command failed (rc={result.returncode}): {result.stderr[:200]}")
            else:
                log.info(f"[HOOK] {event} command ok: {cmd[:60]}")
        except subprocess.TimeoutExpired:
            log.warning(f"[HOOK] {event} command timed out: {cmd[:60]}")
        except Exception as e:
            log.error(f"[HOOK] {event} command error: {e}")

    @staticmethod
    def _run_callback(cb: callable, event: str, ctx: dict):
        """Execute a plugin hook callback."""
        try:
            cb(event, ctx)
        except Exception as e:
            log.error(f"[HOOK] Plugin callback error for {event}: {e}")

    def list_hooks(self) -> Dict[str, List[str]]:
        """Return all configured hooks."""
        result = {}
        for event in VALID_EVENTS:
            cmds = self._hooks.get(event, [])
            plugin_count = len(self._plugin_hooks.get(event, []))
            if cmds or plugin_count:
                result[event] = {
                    "commands": cmds,
                    "plugin_callbacks": plugin_count,
                }
        return result

    def test_hook(self, event: str) -> str:
        """Test-fire a hook event with dummy context."""
        if event not in VALID_EVENTS:
            return f"❌ Invalid event: {event}. Valid: {', '.join(VALID_EVENTS)}"
        cmds = self._hooks.get(event, [])
        plugin_cbs = self._plugin_hooks.get(event, [])
        if not cmds and not plugin_cbs:
            return f"⚠️ No hooks registered for {event}"
        self.fire(event, {"session_id": "test", "message": "Hook test fired"})
        return f"✅ Fired {event}: {len(cmds)} commands, {len(plugin_cbs)} plugin callbacks"

    def add_hook(self, event: str, command: str) -> str:
        """Add a command to an event hook."""
        if event not in VALID_EVENTS:
            return f"❌ Invalid event: {event}"
        self._hooks.setdefault(event, []).append(command)
        self.save()
        return f"✅ Added hook for {event}: {command[:60]}"

    def remove_hook(self, event: str, index: int) -> str:
        """Remove a hook command by event and index."""
        cmds = self._hooks.get(event, [])
        if index < 0 or index >= len(cmds):
            return f"❌ Invalid index {index} for {event}"
        removed = cmds.pop(index)
        self.save()
        return f"🗑️ Removed hook for {event}: {removed[:60]}"


# Singleton instance
hook_manager = HookManager()
