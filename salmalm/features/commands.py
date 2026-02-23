"""Extended slash command router (30+ commands).

stdlib-only. Extracts and extends the command dispatch from engine.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from salmalm.constants import DATA_DIR

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Command metadata
# ---------------------------------------------------------------------------

COMMAND_DEFS: Dict[str, str] = {
    # Debug / config
    "/debug": "Runtime-only config override (show|set|unset|reset)",
    "/config": "Disk config read/write (show|get|set|unset)",
    "/bash": "Execute host shell command (via exec approval)",
    "/restart": "Restart the server",
    # Channel
    "/dock": "Switch response channel (telegram|discord|slack|web)",
    "/activation": "Group chat activation mode (mention|always)",
    "/send": "Auto-response toggle (on|off)",
    # ACL
    "/allowlist": "Manage allowed users (list|add|remove <id>)",
    "/approve": "Exec approval prompt response (<id> allow-once|allow-always|deny)",
    # Model / thinking
    "/think": "Extended Thinking level (off|low|medium|high). Alias: /t",
    "/verbose": "Verbose output mode (on|full|off). Alias: /v",
    "/reasoning": "Show reasoning process (on|off|stream)",
    # Session
    "/new": "New session (optional model hint)",
    "/reset": "Reset current session",
    "/stop": "Stop current execution + active subagents",
    # Info
    "/whoami": "Show current user ID. Alias: /id",
    "/help": "Command help",
    "/commands": "Full command list",
    # Skill
    "/skill": "Run skill directly (<name> [input])",
    # OAuth
    "/oauth": "OAuth management (setup|status|revoke|refresh)",
    # Screen
    "/screen": "Screen capture & analysis (watch|history|search)",
    # MCP
    "/mcp": "MCP marketplace (install|list|catalog|remove|status|search)",
    # Existing (delegated back to engine)
    "/setup": "Re-run the setup wizard (opens in browser)",
    "/status": "Server/session status",
    "/compact": "Compact context",
    "/context": "Show context info",
    "/usage": "Usage stats",
    "/model": "Show/set model",
    "/queue": "Queue status",
    "/subagents": "Sub-agents (spawn|list|stop|steer|log|info|collect) / 서브에이전트",
    "/persona": "Persona management",
    "/branch": "Branch conversation",
    "/rollback": "Rollback to previous state",
    "/thinking": "Thinking mode info",
    "/vault": "Vault operations",
    "/shadow": "Shadow mode",
    "/deadman": "Dead man switch",
    "/capsule": "Time capsule",
    "/split": "Split response",
    "/workflow": "Workflow management",
    "/life": "Life dashboard",
    "/a2a": "Agent-to-agent",
    "/evolve": "Self-evolution",
    "/mood": "Mood info",
    "/clear": "Clear session",
}

# Aliases
ALIASES: Dict[str, str] = {
    "/t": "/think",
    "/v": "/verbose",
    "/id": "/whoami",
}

# Inline shortcuts — can fire even inside a larger message
INLINE_SHORTCUTS = {"/help", "/status", "/whoami", "/id", "/commands"}

# Directives — stripped from message, setting applied, rest sent to LLM
DIRECTIVE_COMMANDS = {"/think", "/t", "/verbose", "/v", "/model", "/reasoning"}

# Telegram-registerable commands (short list for setMyCommands)
TELEGRAM_COMMANDS: List[Tuple[str, str]] = [
    ("help", "Show command help"),
    ("status", "Server/session status"),
    ("think", "Set thinking level (off/low/medium/high)"),
    ("model", "Show or set model"),
    ("new", "Start new session"),
    ("reset", "Reset session"),
    ("stop", "Stop execution"),
    ("whoami", "Show your user ID"),
    ("commands", "List all commands"),
    ("screen", "Capture & analyze screen"),
    ("mcp", "MCP marketplace"),
    ("oauth", "OAuth management"),
    ("verbose", "Verbose mode (on/full/off)"),
    ("bash", "Run shell command"),
    ("config", "Config management"),
    ("debug", "Runtime debug settings"),
    ("dock", "Switch channel"),
    ("send", "Toggle auto-response"),
    ("allowlist", "Manage allowed users"),
    ("skill", "Run a skill"),
    ("brave", "Quick Brave web search"),
]

_CONFIG_DIR = DATA_DIR
_CONFIG_PATH = _CONFIG_DIR / "config.json"


def _ensure_config_dir():
    """Ensure config dir."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Runtime debug overrides (in-memory only)
# ---------------------------------------------------------------------------

_runtime_overrides: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# CommandRouter
# ---------------------------------------------------------------------------


class CommandRouter:
    """Central slash-command dispatcher."""

    def __init__(self, engine_dispatch=None) -> None:
        """
        Args:
            engine_dispatch: async callable(cmd, session, **kw) -> str|None
                Falls back to engine's _dispatch_slash_command for legacy cmds.
        """
        self._engine_dispatch = engine_dispatch
        self._handlers: Dict[str, Callable] = {}
        self._prefix_handlers: List[Tuple[str, Callable]] = []
        self._register_builtins()

    # -- registration helpers --

    def register(self, command: str, handler: Callable) -> None:
        """Register exact-match command."""
        self._handlers[command] = handler

    def register_prefix(self, prefix: str, handler: Callable) -> None:
        """Register prefix-match command."""
        self._prefix_handlers.append((prefix, handler))

    def _register_builtins(self):
        """Register builtins."""
        self._handlers["/help"] = self._cmd_help
        self._handlers["/commands"] = self._cmd_commands
        self._handlers["/whoami"] = self._cmd_whoami
        self._handlers["/id"] = self._cmd_whoami
        self._handlers["/setup"] = self._cmd_setup
        self._handlers["/restart"] = self._cmd_restart
        self._handlers["/reset"] = self._cmd_reset
        self._handlers["/stop"] = self._cmd_stop
        self._handlers["/new"] = self._cmd_new

        self._prefix_handlers.extend(
            [
                ("/debug", self._cmd_debug),
                ("/config", self._cmd_config),
                ("/bash ", self._cmd_bash),
                ("/dock", self._cmd_dock),
                ("/activation", self._cmd_activation),
                ("/send", self._cmd_send),
                ("/allowlist", self._cmd_allowlist),
                ("/approve", self._cmd_approve),
                ("/think", self._cmd_think),
                ("/t ", self._cmd_think),
                ("/verbose", self._cmd_verbose),
                ("/v ", self._cmd_verbose),
                ("/reasoning", self._cmd_reasoning),
                ("/new ", self._cmd_new),
                ("/skill", self._cmd_skill),
                ("/oauth", self._cmd_oauth),
                ("/screen", self._cmd_screen),
                ("/mcp", self._cmd_mcp),
                ("/brave", self._cmd_brave),
                ("/queue", self._cmd_queue),
            ]
        )

    # -- dispatch --

    async def dispatch(self, text: str, session=None, **kw) -> Optional[str]:
        """Dispatch a command string. Returns response or None."""
        cmd = self._normalize(text)
        if not cmd.startswith("/"):
            return None

        # Exact match
        handler = self._handlers.get(cmd)
        if handler:
            return await self._call(handler, cmd, session, **kw)

        # Prefix match (our extended commands)
        for prefix, handler in self._prefix_handlers:
            if cmd == prefix.rstrip() or cmd.startswith(prefix):
                return await self._call(handler, cmd, session, **kw)

        # Fallback to engine dispatch
        if self._engine_dispatch:
            result = self._engine_dispatch(text.strip(), session, **kw)
            if asyncio.iscoroutine(result):
                result = await result
            return result

        return None

    def parse_directives(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Extract directive commands from message text.

        Returns (remaining_text, directives_dict).
        """
        directives: Dict[str, str] = {}
        remaining = text
        # Sort longest-first so /think matches before /t
        sorted_directives = sorted(DIRECTIVE_COMMANDS, key=len, reverse=True)
        for d in sorted_directives:
            pattern = re.compile(
                rf"(?<!\w){re.escape(d)}(?!\w):?\s*(off|low|medium|high|on|full|stream|[\w/.-]+)",
                re.IGNORECASE,
            )
            m = pattern.search(remaining)
            if m:
                canonical = ALIASES.get(d, d)
                directives[canonical] = m.group(1).strip()
                remaining = remaining[: m.start()] + remaining[m.end() :]
        return remaining.strip(), directives

    def find_inline_shortcuts(self, text: str) -> List[str]:
        """Find inline shortcut commands within a message."""
        found = []
        for sc in INLINE_SHORTCUTS:
            if sc in text.split():
                found.append(sc)
        return found

    def get_completions(self) -> List[Dict[str, str]]:
        """Return command list for autocomplete / /api/commands."""
        result = []
        for cmd, desc in sorted(COMMAND_DEFS.items()):
            result.append({"command": cmd, "description": desc})
        return result

    # -- normalization --

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize command text: strip, handle colon syntax."""
        cmd = text.strip()
        # Allow /think: high → /think high
        cmd = re.sub(r"^(/\w+):\s*", r"\1 ", cmd)
        return cmd

    @staticmethod
    async def _call(handler, cmd, session, **kw):
        """Call."""
        result = handler(cmd, session, **kw)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    # -- built-in command handlers --

    @staticmethod
    def _cmd_help(cmd, session, **_):
        """Cmd help."""
        lines = ["**SalmAlm Commands**\n"]
        for c, desc in sorted(COMMAND_DEFS.items()):
            lines.append(f"`{c}` — {desc}")
        return "\n".join(lines)

    @staticmethod
    def _cmd_commands(cmd, session, **_):
        """Cmd commands."""
        cmds = sorted(COMMAND_DEFS.keys())
        return "**All commands:**\n" + " ".join(f"`{c}`" for c in cmds)

    @staticmethod
    def _cmd_whoami(cmd, session, **_) -> str:
        """Cmd whoami."""
        uid = getattr(session, "user_id", None) or "unknown"
        sid = getattr(session, "session_id", None) or "unknown"
        return f"👤 User: `{uid}`\nSession: `{sid}`"

    @staticmethod
    def _cmd_setup(cmd, session, **_) -> str:
        """Cmd setup."""
        from salmalm.constants import PORT
        return f"🔧 Setup Wizard: Open http://localhost:{PORT}/setup in your browser to re-run the setup wizard."

    @staticmethod
    def _cmd_restart(cmd, session, **_) -> str:
        """Cmd restart."""
        log.info("Restart requested via /restart")
        # Schedule restart after response (skip in test environments)
        import threading

        def _do_restart():
            """Do restart."""
            time.sleep(1)
            if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("SALMALM_NO_RESTART"):
                log.info("Restart suppressed (test/no-restart mode)")
                return
            os.execv(sys.executable, [sys.executable] + sys.argv)

        threading.Thread(target=_do_restart, daemon=True).start()
        return "🔄 Restarting server..."

    @staticmethod
    def _cmd_reset(cmd, session, **_) -> str:
        """Cmd reset."""
        if session and hasattr(session, "messages"):
            session.messages.clear()
        return "🗑️ Session reset."

    @staticmethod
    def _cmd_stop(cmd, session, **_) -> str:
        """Cmd stop."""
        return "🛑 Stop signal sent."

    @staticmethod
    def _cmd_new(cmd, session, **_):
        """Cmd new."""
        parts = cmd.split(maxsplit=1)
        model_hint = parts[1] if len(parts) > 1 else None
        if session and hasattr(session, "messages"):
            session.messages.clear()
        msg = "🆕 New session started."
        if model_hint:
            msg += f" Model hint: `{model_hint}`"
        return msg

    # -- debug --

    @staticmethod
    def _cmd_debug(cmd, session, **_) -> str:
        """Cmd debug."""
        parts = cmd.split()
        sub = parts[1] if len(parts) > 1 else "show"
        if sub == "show":
            if not _runtime_overrides:
                return "🔧 No runtime overrides set."
            lines = ["🔧 **Runtime overrides:**"]
            for k, v in _runtime_overrides.items():
                lines.append(f"  `{k}` = `{v}`")
            return "\n".join(lines)
        elif sub == "set" and len(parts) >= 4:
            key, val = parts[2], " ".join(parts[3:])
            _runtime_overrides[key] = val
            return f"✅ debug `{key}` = `{val}`"
        elif sub == "unset" and len(parts) >= 3:
            key = parts[2]
            _runtime_overrides.pop(key, None)
            return f"✅ debug `{key}` removed."
        elif sub == "reset":
            _runtime_overrides.clear()
            return "✅ All runtime overrides cleared."
        return "❓ Usage: /debug show|set <key> <val>|unset <key>|reset"

    # -- config --

    @staticmethod
    def _cmd_config(cmd, session, **_) -> str:
        """Cmd config."""
        parts = cmd.split()
        sub = parts[1] if len(parts) > 1 else "show"
        _ensure_config_dir()
        try:
            cfg = json.loads(_CONFIG_PATH.read_text()) if _CONFIG_PATH.exists() else {}
        except Exception as e:  # noqa: broad-except
            cfg = {}

        if sub == "show":
            if not cfg:
                return "⚙️ Config is empty."
            lines = ["⚙️ **Config:**"]
            for k, v in cfg.items():
                lines.append(f"  `{k}` = `{json.dumps(v)}`")
            return "\n".join(lines)
        elif sub == "get" and len(parts) >= 3:
            key = parts[2]
            val = cfg.get(key)
            if val is None:
                return f"⚙️ `{key}` not set."
            return f"⚙️ `{key}` = `{json.dumps(val)}`"
        elif sub == "set" and len(parts) >= 4:
            key = parts[2]
            raw = " ".join(parts[3:])
            try:
                val = json.loads(raw)
            except json.JSONDecodeError:
                val = raw
            cfg[key] = val
            _CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
            return f"✅ config `{key}` = `{json.dumps(val)}`"
        elif sub == "unset" and len(parts) >= 3:
            key = parts[2]
            cfg.pop(key, None)
            _CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
            return f"✅ config `{key}` removed."
        return "❓ Usage: /config show|get <key>|set <key> <val>|unset <key>"

    # -- bash --

    @staticmethod
    def _cmd_bash(cmd, session, **_) -> str:
        """Cmd bash."""
        shell_cmd = cmd[len("/bash ") :].strip()
        if not shell_cmd:
            return "❓ Usage: /bash <command>"
        try:
            from salmalm.security.exec_approvals import check_approval

            if not check_approval("bash", shell_cmd):
                return "🚫 Exec not approved. Use /approve to allow."
        except (ImportError, Exception):
            pass
        try:
            result = subprocess.run(shell_cmd, shell=True, capture_output=True, text=True, timeout=30)
            out = result.stdout or ""
            err = result.stderr or ""
            code = result.returncode
            resp = f"```\n{out}"
            if err:
                resp += f"\n[stderr]\n{err}"
            resp += f"\n```\nExit code: {code}"
            return resp
        except subprocess.TimeoutExpired:
            return "⏱️ Command timed out (30s limit)."
        except Exception as e:
            return f"❌ Error: {e}"

    # -- channel --

    @staticmethod
    def _cmd_dock(cmd, session, **_) -> str:
        """Cmd dock."""
        parts = cmd.split()
        channel = parts[1] if len(parts) > 1 else None
        valid = ("telegram", "discord", "slack", "web")
        if channel not in valid:
            return f"❓ Usage: /dock {'|'.join(valid)}"
        if session and hasattr(session, "response_channel"):
            session.response_channel = channel
        return f"📡 Response channel set to `{channel}`."

    @staticmethod
    def _cmd_activation(cmd, session, **_) -> str:
        """Cmd activation."""
        parts = cmd.split()
        mode = parts[1] if len(parts) > 1 else None
        if mode not in ("mention", "always"):
            return "❓ Usage: /activation mention|always"
        if session:
            session.__dict__["activation_mode"] = mode
        return f"🔔 Activation mode: `{mode}`"

    @staticmethod
    def _cmd_send(cmd, session, **_) -> str:
        """Cmd send."""
        parts = cmd.split()
        toggle = parts[1] if len(parts) > 1 else None
        if toggle not in ("on", "off"):
            return "❓ Usage: /send on|off"
        if session:
            session.__dict__["auto_send"] = toggle == "on"
        return f"📤 Auto-response: `{toggle}`"

    # -- ACL --

    @staticmethod
    def _cmd_allowlist(cmd, session, **_) -> str:
        """Cmd allowlist."""
        parts = cmd.split()
        sub = parts[1] if len(parts) > 1 else "list"
        _ensure_config_dir()
        al_path = _CONFIG_DIR / "allowlist.json"
        try:
            al = json.loads(al_path.read_text()) if al_path.exists() else []
        except Exception as e:  # noqa: broad-except
            al = []

        if sub == "list":
            if not al:
                return "📋 Allowlist is empty."
            return "📋 **Allowlist:**\n" + "\n".join(f"  • `{uid}`" for uid in al)
        elif sub == "add" and len(parts) >= 3:
            uid = parts[2]
            if uid not in al:
                al.append(uid)
                al_path.write_text(json.dumps(al))
            return f"✅ Added `{uid}` to allowlist."
        elif sub == "remove" and len(parts) >= 3:
            uid = parts[2]
            al = [x for x in al if x != uid]
            al_path.write_text(json.dumps(al))
            return f"✅ Removed `{uid}` from allowlist."
        return "❓ Usage: /allowlist list|add|remove <id>"

    @staticmethod
    def _cmd_approve(cmd, session, **_) -> str:
        """Cmd approve."""
        parts = cmd.split()
        if len(parts) < 3:
            return "❓ Usage: /approve <id> allow-once|allow-always|deny"
        target_id = parts[1]
        action = parts[2]
        if action not in ("allow-once", "allow-always", "deny"):
            return "❓ Action must be: allow-once|allow-always|deny"
        try:
            from salmalm.security.exec_approvals import set_approval

            set_approval(target_id, action)
        except (ImportError, Exception):
            pass
        return f"✅ Approval for `{target_id}`: `{action}`"

    # -- thinking / verbose --

    @staticmethod
    def _cmd_think(cmd, session, **_) -> str:
        """Cmd think."""
        parts = cmd.replace("/t ", "/think ").split()
        level = parts[1] if len(parts) > 1 else None
        valid = ("off", "low", "medium", "high", "xhigh")
        if level not in valid:
            return f"❓ Usage: /think {'|'.join(valid)}\n💡 low=4K, medium=10K, high=16K, xhigh=32K budget tokens"
        if session:
            if level == "off":
                session.thinking_enabled = False
                session.__dict__["thinking_level"] = "medium"
            else:
                session.thinking_enabled = True
                session.thinking_level = level
        _budgets = {"low": 4000, "medium": 10000, "high": 16000, "xhigh": 32000}
        return f"🧠 Thinking: `{level}`" + (" (OFF)" if level == "off" else f" (budget: {_budgets[level]}tok)")

    @staticmethod
    def _cmd_verbose(cmd, session, **_) -> str:
        """Cmd verbose."""
        parts = cmd.replace("/v ", "/verbose ").split()
        level = parts[1] if len(parts) > 1 else None
        if level not in ("on", "full", "off"):
            return "❓ Usage: /verbose on|full|off"
        if session:
            session.__dict__["verbose"] = level
        return f"📝 Verbose mode: `{level}`"

    @staticmethod
    def _cmd_reasoning(cmd, session, **_) -> str:
        """Cmd reasoning."""
        parts = cmd.split()
        mode = parts[1] if len(parts) > 1 else None
        if mode not in ("on", "off", "stream"):
            return "❓ Usage: /reasoning on|off|stream"
        if session:
            session.__dict__["reasoning"] = mode
        return f"💭 Reasoning: `{mode}`"

    # -- skill --

    @staticmethod
    def _cmd_skill(cmd, session, **_) -> str:
        """Cmd skill."""
        parts = cmd.split(maxsplit=2)
        if len(parts) < 2:
            return "❓ Usage: /skill <name> [input]"
        name = parts[1]
        inp = parts[2] if len(parts) > 2 else ""
        return f"🔧 Skill `{name}` invoked with: `{inp}`"

    # -- oauth (delegates to oauth module) --

    @staticmethod
    def _cmd_oauth(cmd, session, **_) -> str:
        """Cmd oauth."""
        parts = cmd.split()
        sub = parts[1] if len(parts) > 1 else "status"
        try:
            from salmalm.web.oauth import oauth_manager

            if sub == "setup":
                provider = parts[2] if len(parts) > 2 else "anthropic"
                return oauth_manager.setup(provider)
            elif sub == "status":
                return oauth_manager.status()
            elif sub == "revoke":
                return oauth_manager.revoke()
            elif sub == "refresh":
                return oauth_manager.refresh()
        except ImportError:
            return "❌ OAuth module not available."
        except Exception as e:
            return f"❌ OAuth error: {e}"
        return "❓ Usage: /oauth setup|status|revoke|refresh"

    # -- screen (delegates to screen_capture module) --

    @staticmethod
    def _cmd_screen(cmd, session, **_) -> str:
        """Cmd screen."""
        parts = cmd.split()
        sub = parts[1] if len(parts) > 1 else "capture"
        try:
            from salmalm.features.screen_capture import screen_manager

            if sub == "capture" or cmd.strip() == "/screen":
                return screen_manager.capture()
            elif sub == "watch":
                toggle = parts[2] if len(parts) > 2 else "on"
                return screen_manager.watch(toggle)
            elif sub == "history":
                n = int(parts[2]) if len(parts) > 2 else 5
                return screen_manager.history(n)
            elif sub == "search":
                query = " ".join(parts[2:])
                return screen_manager.search(query)
        except ImportError:
            return "❌ Screen capture module not available."
        except Exception as e:
            return f"❌ Screen error: {e}"
        return "❓ Usage: /screen [watch on|off|history N|search <query>]"

    # -- mcp (delegates to mcp_marketplace module) --

    @staticmethod
    def _cmd_mcp(cmd, session, **_) -> str:
        """Cmd mcp."""
        parts = cmd.split()
        sub = parts[1] if len(parts) > 1 else "status"
        try:
            from salmalm.features.mcp_marketplace import marketplace

            if sub == "install" and len(parts) >= 3:
                return marketplace.install(parts[2])
            elif sub == "list":
                return marketplace.list_installed()
            elif sub == "catalog":
                return marketplace.catalog()
            elif sub == "remove" and len(parts) >= 3:
                return marketplace.remove(parts[2])
            elif sub == "status":
                return marketplace.status()
            elif sub == "search":
                query = " ".join(parts[2:])
                return marketplace.search(query)
        except ImportError:
            return "❌ MCP marketplace module not available."
        except Exception as e:
            return f"❌ MCP error: {e}"
        return "❓ Usage: /mcp install|list|catalog|remove|status|search"

    def _cmd_brave(cmd, session, **_) -> str:
        """Quick Brave web search."""
        query = cmd[len("/brave") :].strip()
        if not query:
            return "❓ Usage: /brave <query>"
        try:
            from salmalm.tools.tools_brave import brave_web_search

            return brave_web_search({"query": query, "count": 5})
        except Exception as e:
            return f"❌ Brave search error: {e}"

    @staticmethod
    def _cmd_queue(cmd, session, **_) -> str:
        """Message queue management."""
        from salmalm.features.queue import get_queue, set_queue_mode, queue_status, QueueMode

        parts = cmd.split()
        sub = parts[1] if len(parts) > 1 else "status"
        sid = session.session_id if session else "default"

        if sub == "status":
            st = queue_status(sid)
            return (
                f"📨 **Queue Status**\n"
                f"• Mode: `{st['mode']}`\n"
                f"• Pending: {st['pending']}\n"
                f"• Backlog: {st['backlog']}\n"
                f"• Processing: {'🔄' if st['processing'] else '⏹️'}"
            )

        if sub in ("mode", "set") and len(parts) >= 3:
            mode = parts[2].lower()
            valid = [m.value for m in QueueMode]
            if mode not in valid:
                return f"❌ Invalid mode: `{mode}`\nValid: {', '.join(valid)}"
            result = set_queue_mode(sid, mode)
            return f"✅ {result}"

        if sub == "clear":
            q = get_queue(sid)
            q.clear()
            return "🗑️ Queue cleared"

        if sub == "modes":
            return (
                "📨 **Queue Modes**\n"
                "• `collect` — Queue all, process when done (default)\n"
                "• `steer` — Latest message replaces pending\n"
                "• `followup` — Queue as follow-up context\n"
                "• `steer-backlog` — Steer + keep history\n"
                "• `interrupt` — Cancel current, process new"
            )

        return (
            "📨 **Queue Commands**\n"
            "• `/queue` — Show status\n"
            "• `/queue mode <mode>` — Set mode\n"
            "• `/queue modes` — List available modes\n"
            "• `/queue clear` — Clear pending messages"
        )


# ---------------------------------------------------------------------------
# Telegram native command registration
# ---------------------------------------------------------------------------


def register_telegram_commands(bot_token: str) -> bool:
    """Register commands with Telegram's setMyCommands API."""
    import urllib.request

    url = f"https://api.telegram.org/bot{bot_token}/setMyCommands"
    commands = [{"command": c, "description": d} for c, d in TELEGRAM_COMMANDS]
    payload = json.dumps({"commands": commands}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("ok", False)
    except Exception as e:
        log.warning(f"Failed to register Telegram commands: {e}")
        return False


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_router: Optional[CommandRouter] = None


def get_router(engine_dispatch=None) -> CommandRouter:
    """Get router."""
    global _router
    if _router is None:
        _router = CommandRouter(engine_dispatch=engine_dispatch)
    return _router
