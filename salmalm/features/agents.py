from typing import Optional

"""SalmAlm agents — SubAgent, SkillLoader, PluginLoader."""
import asyncio
import json
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from salmalm.constants import BASE_DIR, KST, DATA_DIR
from salmalm.security.crypto import log
from salmalm.features.agents_skills import SkillLoader  # noqa: F401

# Auto-archive delay (seconds after completion)
_ARCHIVE_DELAY_SEC = 3600  # 60 minutes


def _core():
    """Lazy import to avoid circular dependency."""
    from salmalm import core

    return core


def _load_tool_policy() -> dict:
    """Load subagent tool policy from config file."""
    policy_file = Path(__file__).resolve().parent.parent / "subagent_tool_policy.json"
    user_policy = DATA_DIR / "subagent_tool_policy.json"
    # User override takes priority
    for f in (user_policy, policy_file):
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
    return {"deny": [], "allow": []}


def _filter_tools_for_subagent(tools: list) -> list:
    """Filter tool definitions based on subagent tool policy. Deny overrides allow."""
    policy = _load_tool_policy()
    deny = set(policy.get("deny", []))
    allow = set(policy.get("allow", []))
    filtered = []
    for t in tools:
        name = t.get("name", "")
        if name in deny:
            continue
        if allow and name not in allow:
            continue
        filtered.append(t)
    return filtered


# ============================================================
class SubAgent:
    """Background task executor with notification on completion."""

    _agents: dict = {}  # id -> {task, status, result, thread, started, completed, ...}
    _counter = 0
    _lock = threading.Lock()
    _archive_timers: dict = {}  # id -> Timer
    MAX_CONCURRENT = 5  # Max concurrent sub-agents
    MAX_DEPTH = 2  # Max nesting depth (sub-agent spawning sub-agents)

    @classmethod
    def spawn(
        cls, task: str, model: Optional[str] = None, notify_telegram: bool = True, _depth: int = 0, label: str = ""
    ) -> str:
        """Spawn a background sub-agent. Returns agent ID."""
        if _depth >= cls.MAX_DEPTH:
            from salmalm.core.exceptions import SessionError

            raise SessionError(f"Sub-agent nesting depth limit ({cls.MAX_DEPTH}) reached")
        running = sum(1 for a in cls._agents.values() if a["status"] == "running")
        if running >= cls.MAX_CONCURRENT:
            from salmalm.core.exceptions import SessionError

            raise SessionError(f"Max concurrent sub-agents ({cls.MAX_CONCURRENT}) reached")
        with cls._lock:
            cls._counter += 1
            agent_id = f"sub-{cls._counter}"

        agent_info = {
            "id": agent_id,
            "task": task,
            "model": model,
            "label": label or task[:40],
            "status": "running",
            "result": None,
            "started": datetime.now(KST).isoformat(),
            "started_ts": time.time(),
            "completed": None,
            "completed_ts": None,
            "notify_telegram": notify_telegram,
            "transcript": [],  # full message log
            "token_usage": {"input": 0, "output": 0},
            "estimated_cost": 0.0,
            "archived": False,
        }

        def _run():
            """Run."""
            try:
                session_id = f"subagent-{agent_id}"
                session = _core().get_session(session_id)
                from salmalm.core.engine import process_message

                result = asyncio.run(process_message(session_id, task, model_override=model))
                agent_info["result"] = result
                agent_info["status"] = "completed"
                now = datetime.now(KST)
                agent_info["completed"] = now.isoformat()
                agent_info["completed_ts"] = time.time()
                runtime_s = agent_info["completed_ts"] - agent_info["started_ts"]

                # Collect transcript from session
                try:
                    agent_info["transcript"] = [
                        {
                            "role": m.get("role", "?"),
                            "content": m.get("content", "")[:500]
                            if isinstance(m.get("content"), str)
                            else str(m.get("content", ""))[:500],
                        }
                        for m in session.messages
                        if m.get("role") != "system"
                    ]
                except Exception as e:  # noqa: broad-except
                    log.debug(f"Suppressed: {e}")

                # Collect token usage from session metrics
                try:
                    from salmalm.features.edge_cases import usage_tracker  # noqa: F401

                    # Rough estimate from result length
                    out_tokens = len(result) // 3
                    in_tokens = len(task) // 3
                    agent_info["token_usage"] = {"input": in_tokens, "output": out_tokens}
                    model_name = (model or "sonnet").lower()
                    if "opus" in model_name:
                        cost = (in_tokens * 15 + out_tokens * 75) / 1_000_000
                    elif "haiku" in model_name:
                        cost = (in_tokens * 0.25 + out_tokens * 1.25) / 1_000_000
                    else:
                        cost = (in_tokens * 3 + out_tokens * 15) / 1_000_000
                    agent_info["estimated_cost"] = round(cost, 6)
                except Exception as e:  # noqa: broad-except
                    log.debug(f"Suppressed: {e}")

                log.info(f"[BOT] Sub-agent {agent_id} completed: {len(result)} chars, {runtime_s:.1f}s")

                # Build announce summary with stats
                summary = result[:500] + ("..." if len(result) > 500 else "")
                stats_line = (
                    f"⏱ {runtime_s:.1f}s | "
                    f"📊 in:{agent_info['token_usage']['input']} out:{agent_info['token_usage']['output']} | "
                    f"💰 ${agent_info['estimated_cost']:.4f}"
                )
                msg = f"🤖 **Sub-agent completed** [{agent_id}]\n📋 Task: {task[:100]}\n{stats_line}\n\n{summary}"

                # Notify via Telegram
                if agent_info["notify_telegram"] and _core()._tg_bot and _core()._tg_bot.token:
                    try:
                        _core()._tg_bot._api(
                            "sendMessage", {"chat_id": _core()._tg_bot.owner_id, "text": msg, "parse_mode": "Markdown"}
                        )
                    except Exception as e:
                        log.warning(f"Sub-agent notification failed: {e}")

                # Schedule auto-archive
                cls._schedule_archive(agent_id)

                # Clean up session after a while
                if session_id in _core()._sessions:
                    del _core()._sessions[session_id]

            except Exception as e:
                agent_info["result"] = f"❌ Sub-agent error: {e}"
                agent_info["status"] = "error"
                agent_info["completed"] = datetime.now(KST).isoformat()
                agent_info["completed_ts"] = time.time()
                log.error(f"Sub-agent {agent_id} error: {e}")
                cls._schedule_archive(agent_id)

        t = threading.Thread(target=_run, daemon=True, name=f"subagent-{agent_id}")
        agent_info["thread"] = t  # type: ignore[assignment]
        cls._agents[agent_id] = agent_info
        t.start()
        log.info(f"[BOT] Sub-agent {agent_id} spawned: {task[:80]}")
        return agent_id

    @classmethod
    def _schedule_archive(cls, agent_id: str):
        """Schedule auto-archive after _ARCHIVE_DELAY_SEC."""

        def _do_archive():
            """Do archive."""
            agent = cls._agents.get(agent_id)
            if agent and not agent.get("archived"):
                agent["archived"] = True
                # Rename conceptually — mark as archived
                agent["status"] = f"{agent['status']}.archived.{int(time.time())}"
                log.info(f"[BOT] Sub-agent {agent_id} auto-archived")
            cls._archive_timers.pop(agent_id, None)

        timer = threading.Timer(_ARCHIVE_DELAY_SEC, _do_archive)
        timer.daemon = True
        cls._archive_timers[agent_id] = timer
        timer.start()

    @classmethod
    def list_agents(cls) -> list:
        """List all sub-agents with their status, label, and runtime."""
        result = []
        now_ts = time.time()
        for a in cls._agents.values():
            if a.get("archived"):
                continue
            runtime = (a.get("completed_ts") or now_ts) - a["started_ts"]
            result.append(
                {
                    "id": a["id"],
                    "label": a.get("label", a["task"][:40]),
                    "task": a["task"][:60],
                    "status": a["status"],
                    "started": a["started"],
                    "completed": a["completed"],
                    "runtime_s": round(runtime, 1),
                    "token_usage": a.get("token_usage", {}),
                    "estimated_cost": a.get("estimated_cost", 0),
                }
            )
        return result

    @classmethod
    def stop_agent(cls, agent_id: str) -> str:
        """Stop a running sub-agent."""
        if agent_id == "all":
            stopped = []
            for aid, a in cls._agents.items():
                if a["status"] == "running":
                    a["status"] = "stopped"
                    a["completed"] = datetime.now(KST).isoformat()
                    a["completed_ts"] = time.time()
                    stopped.append(aid)
            return (
                f"⏹ Stopped {len(stopped)} sub-agents: {', '.join(stopped)}" if stopped else "⚠️ No running sub-agents"
            )

        # Support #N shorthand
        if agent_id.startswith("#"):
            try:
                idx = int(agent_id[1:]) - 1
                keys = list(cls._agents.keys())
                if 0 <= idx < len(keys):
                    agent_id = keys[idx]
            except ValueError:
                return f"❌ Invalid index: {agent_id}"

        agent = cls._agents.get(agent_id)
        if not agent:
            return f"❌ Agent {agent_id} not found"
        if agent["status"] != "running":
            return f"⚠️ Agent {agent_id} is not running (status: {agent['status']})"
        agent["status"] = "stopped"
        agent["completed"] = datetime.now(KST).isoformat()
        agent["completed_ts"] = time.time()
        return f"⏹ Stopped sub-agent {agent_id}"

    @classmethod
    def get_log(cls, agent_id: str, limit: int = 20) -> str:
        """Get sub-agent transcript."""
        # Support #N shorthand
        if agent_id.startswith("#"):
            try:
                idx = int(agent_id[1:]) - 1
                keys = list(cls._agents.keys())
                if 0 <= idx < len(keys):
                    agent_id = keys[idx]
            except ValueError:
                return f"❌ Invalid index: {agent_id}"

        agent = cls._agents.get(agent_id)
        if not agent:
            return f"❌ Agent {agent_id} not found"
        transcript = agent.get("transcript", [])
        if not transcript:
            if agent["result"]:
                return f"📜 [{agent_id}] Result:\n{agent['result'][:2000]}"
            return f"📜 [{agent_id}] No transcript available"
        lines = [f"📜 **Transcript** [{agent_id}] ({len(transcript)} messages, showing last {limit})\n"]
        for entry in transcript[-limit:]:
            role = entry.get("role", "?")
            content = entry.get("content", "")[:300]
            icon = {"user": "👤", "assistant": "🤖", "tool": "🔧"}.get(role, "❓")
            lines.append(f"{icon} **{role}**: {content}")
        return "\n".join(lines)

    @classmethod
    def get_info(cls, agent_id: str) -> str:
        """Get detailed metadata for a sub-agent."""
        # Support #N shorthand
        if agent_id.startswith("#"):
            try:
                idx = int(agent_id[1:]) - 1
                keys = list(cls._agents.keys())
                if 0 <= idx < len(keys):
                    agent_id = keys[idx]
            except ValueError:
                return f"❌ Invalid index: {agent_id}"

        agent = cls._agents.get(agent_id)
        if not agent:
            return f"❌ Agent {agent_id} not found"
        now_ts = time.time()
        runtime = (agent.get("completed_ts") or now_ts) - agent["started_ts"]
        usage = agent.get("token_usage", {})
        return (
            f"🤖 **Sub-agent Info** [{agent_id}]\n"
            f"📋 Label: {agent.get('label', '—')}\n"
            f"📝 Task: {agent['task'][:200]}\n"
            f"📊 Status: {agent['status']}\n"
            f"🕐 Started: {agent['started']}\n"
            f"✅ Completed: {agent.get('completed', '—')}\n"
            f"⏱ Runtime: {runtime:.1f}s\n"
            f"📊 Tokens: in={usage.get('input', 0)} out={usage.get('output', 0)}\n"
            f"💰 Est. cost: ${agent.get('estimated_cost', 0):.4f}\n"
            f"📜 Transcript: {len(agent.get('transcript', []))} messages\n"
            f"📦 Archived: {agent.get('archived', False)}\n"
            f"🤖 Model: {agent.get('model', 'auto')}"
        )

    @classmethod
    def get_result(cls, agent_id: str) -> dict:
        """Get the result of a completed sub-agent run."""
        agent = cls._agents.get(agent_id)
        if not agent:
            return {"error": f"Agent {agent_id} not found"}
        return {
            "id": agent["id"],
            "task": agent["task"],
            "status": agent["status"],
            "result": agent["result"],
            "started": agent["started"],
            "completed": agent["completed"],
        }

    @classmethod
    def send_message(cls, agent_id: str, message: str) -> str:
        """Send a follow-up message to a completed sub-agent's session."""
        agent = cls._agents.get(agent_id)
        if not agent:
            return f"❌ Agent {agent_id} not found"
        if agent["status"] == "running":
            return f"⏳ Agent {agent_id} still running. Wait for completion first."
        # Run in the agent's existing session
        session_id = f"subagent-{agent_id}"
        try:
            from salmalm.core.engine import process_message

            result = asyncio.run(process_message(session_id, message))
            agent["result"] = result  # Update with latest result
            return f"🤖 [{agent_id}] responded:\n\n{result[:3000]}"
        except Exception as e:
            return f"❌ Send failed: {str(e)[:200]}"


# ============================================================
class PluginLoader:
    """Discover and load tool plugins from plugins/*.py files."""

    _plugins: dict = {}  # name -> {module, tools}

    @classmethod
    def scan(cls) -> int:
        """Scan plugins/ directory and load all .py files as tool providers."""
        plugins_dir = BASE_DIR / "plugins"
        if not plugins_dir.exists():
            plugins_dir.mkdir(exist_ok=True)
            # Create example plugin
            example = plugins_dir / "_example_plugin.py"
            if not example.exists():
                example.write_text(
                    '''"""
Example Plugin — Drop .py files in plugins/ to auto-load tools.

Each plugin must define:
  TOOLS = [...]  # List of tool definition dicts
  def execute(name, args) -> str:  # Tool executor

Tool definition format:
  {'name': 'my_tool', 'description': '...', 'input_schema': {'type': 'object', 'properties': {...}, 'required': [...]}}
"""

TOOLS = [
    {
        'name': 'example_echo',
        'description': 'Echo back the input (example plugin).',
        'input_schema': {
            'type': 'object',
            'properties': {'text': {'type': 'string', 'description': 'Text to echo'}},
            'required': ['text']
        }
    }
]

def execute(name: str, args: dict) -> str:
    if name == 'example_echo':
        return f'🔊 Echo: {args.get("text", "")}'
    return f'Unknown tool: {name}'
''',
                    encoding="utf-8",
                )
            return 0

        count = 0
        for py_file in sorted(plugins_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue  # Skip _example and __init__
            try:
                import importlib.util

                spec = importlib.util.spec_from_file_location(f"salmalm_plugin_{py_file.stem}", py_file)
                mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
                spec.loader.exec_module(mod)  # type: ignore[union-attr]

                tools = getattr(mod, "TOOLS", [])
                execute_fn = getattr(mod, "execute", None)
                if tools and execute_fn:
                    cls._plugins[py_file.stem] = {
                        "module": mod,
                        "tools": tools,
                        "execute": execute_fn,
                        "path": str(py_file),
                    }
                    count += len(tools)
                    log.info(f"[CONN] Plugin loaded: {py_file.stem} ({len(tools)} tools)")
            except Exception as e:
                log.error(f"Plugin load error ({py_file.name}): {e}")

        log.info(f"[CONN] Plugins: {len(cls._plugins)} loaded, {count} tools total")
        return count

    @classmethod
    def get_all_tools(cls) -> list:
        """Return all tool definitions from all plugins."""
        tools = []
        for plugin in cls._plugins.values():
            tools.extend(plugin["tools"])
        return tools

    @classmethod
    def execute(cls, tool_name: str, args: dict) -> str:
        """Execute a plugin tool by name."""
        for plugin in cls._plugins.values():
            tool_names = [t["name"] for t in plugin["tools"]]
            if tool_name in tool_names:
                return plugin["execute"](tool_name, args)  # type: ignore[no-any-return]
        return None  # type: ignore[return-value]

    @classmethod
    def reload(cls) -> int:
        """Reload all plugins."""
        cls._plugins = {}
        return cls.scan()


# ============================================================
# Multi-Agent Routing (다중 에이전트 라우팅)
# ============================================================

AGENTS_DIR = DATA_DIR / "agents"
BINDINGS_FILE = AGENTS_DIR / "bindings.json"


class AgentConfig:
    """Configuration and paths for a single agent (에이전트 설정)."""

    def __init__(self, agent_id: str) -> None:
        """Init  ."""
        self.agent_id = agent_id
        self.base_dir = AGENTS_DIR / agent_id
        self.workspace_dir = self.base_dir / "workspace"
        self.sessions_dir = self.base_dir / "sessions"
        self.config_file = self.base_dir / "config.json"
        self._config: dict = {}
        self._load()

    def _load(self):
        """Load."""
        try:
            if self.config_file.exists():
                self._config = json.loads(self.config_file.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: broad-except
            self._config = {}

    def save(self) -> None:
        """Save."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(json.dumps(self._config, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.error(f"[AGENT] Config save error ({self.agent_id}): {e}")

    @property
    def display_name(self) -> str:
        """Display name."""
        return self._config.get("display_name", self.agent_id)

    @property
    def model(self) -> Optional[str]:
        """Model."""
        return self._config.get("model")

    @property
    def soul_file(self) -> Path:
        """Soul file."""
        return self.workspace_dir / "SOUL.md"

    @property
    def api_key(self) -> Optional[str]:
        """Api key."""
        return self._config.get("api_key")

    @property
    def allowed_tools(self) -> Optional[list]:
        """None means all tools allowed."""
        return self._config.get("allowed_tools")

    def to_dict(self) -> dict:
        """To dict."""
        return {
            "id": self.agent_id,
            "display_name": self.display_name,
            "model": self.model,
            "has_soul": self.soul_file.exists(),
            "workspace": str(self.workspace_dir),
            "allowed_tools": self.allowed_tools,
        }


class AgentManager:
    """Manages multiple agents with routing by Telegram chat/user.

    다중 에이전트 관리 — Telegram 채팅/사용자별 라우팅 지원.
    """

    def __init__(self) -> None:
        """Init  ."""
        self._agents: dict = {}  # agent_id -> AgentConfig
        self._bindings: dict = {}  # "telegram:chatid" -> agent_id
        self._lock = threading.Lock()
        self._ensure_main()
        self._load_bindings()

    def _ensure_main(self):
        """Ensure 'main' agent exists (기본 에이전트)."""
        main_dir = AGENTS_DIR / "main"
        if not main_dir.exists():
            main_dir.mkdir(parents=True, exist_ok=True)
            (main_dir / "workspace").mkdir(exist_ok=True)
            (main_dir / "sessions").mkdir(exist_ok=True)
            config = {"display_name": "Main", "model": None, "allowed_tools": None}
            (main_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        self._agents["main"] = AgentConfig("main")

    def _load_bindings(self):
        """Load chat→agent bindings from bindings.json."""
        try:
            if BINDINGS_FILE.exists():
                self._bindings = json.loads(BINDINGS_FILE.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: broad-except
            self._bindings = {}

    def _save_bindings(self):
        """Save bindings."""
        try:
            BINDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            BINDINGS_FILE.write_text(json.dumps(self._bindings, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.error(f"[AGENT] Bindings save error: {e}")

    def scan(self) -> None:
        """Scan agents directory and load all agent configs."""
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._agents.clear()
            for agent_dir in sorted(AGENTS_DIR.iterdir()):
                if not agent_dir.is_dir() or agent_dir.name.startswith("."):
                    continue
                if agent_dir.name == "bindings.json":
                    continue
                config_file = agent_dir / "config.json"
                if not config_file.exists():
                    continue
                self._agents[agent_dir.name] = AgentConfig(agent_dir.name)
            if "main" not in self._agents:
                self._ensure_main()
        log.info(f"[AGENT] Scanned {len(self._agents)} agents")

    def resolve(self, chat_key: str) -> str:
        """Resolve which agent handles a given chat key (e.g. 'telegram:12345').

        Returns agent_id (defaults to 'main').
        라우팅: 채팅 키에 해당하는 에이전트 ID 반환.
        """
        return self._bindings.get(chat_key, "main")

    def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        """Get agent config by ID."""
        if agent_id not in self._agents:
            self.scan()
        return self._agents.get(agent_id)

    def get_session_id(self, agent_id: str, base_session_id: str) -> str:
        """Get agent-scoped session ID.

        에이전트별 세션 ID 생성 (격리).
        """
        if agent_id == "main":
            return base_session_id  # backward compatible
        return f"{agent_id}:{base_session_id}"

    def create(self, agent_id: str, display_name: str = "", model: str = None) -> str:
        """Create a new agent. 새 에이전트 생성."""
        if not agent_id or not agent_id.replace("-", "").replace("_", "").isalnum():
            return "❌ Invalid agent ID (alphanumeric, hyphens, underscores only)"
        agent_dir = AGENTS_DIR / agent_id
        if agent_dir.exists():
            return f"❌ Agent already exists: {agent_id}"

        agent_dir.mkdir(parents=True)
        (agent_dir / "workspace").mkdir()
        (agent_dir / "sessions").mkdir()
        config = {
            "display_name": display_name or agent_id,
            "model": model,
            "allowed_tools": None,
        }
        (agent_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

        self._agents[agent_id] = AgentConfig(agent_id)
        log.info(f"[AGENT] Created agent: {agent_id}")
        return f"✅ Agent created: {agent_id}"

    def delete(self, agent_id: str) -> str:
        """Delete an agent (cannot delete 'main')."""
        if agent_id == "main":
            return "❌ Cannot delete the main agent"
        agent_dir = AGENTS_DIR / agent_id
        if not agent_dir.exists():
            return f"❌ Agent not found: {agent_id}"
        shutil.rmtree(str(agent_dir), ignore_errors=True)
        self._agents.pop(agent_id, None)
        # Remove bindings pointing to this agent
        self._bindings = {k: v for k, v in self._bindings.items() if v != agent_id}
        self._save_bindings()
        return f"🗑️ Agent deleted: {agent_id}"

    def bind(self, chat_key: str, agent_id: str) -> str:
        """Bind a chat to an agent. 채팅을 에이전트에 바인딩."""
        if agent_id not in self._agents:
            self.scan()
        if agent_id not in self._agents:
            return f"❌ Agent not found: {agent_id}"
        self._bindings[chat_key] = agent_id
        self._save_bindings()
        return f"✅ Bound {chat_key} → {agent_id}"

    def unbind(self, chat_key: str) -> str:
        """Remove a chat binding."""
        if chat_key in self._bindings:
            del self._bindings[chat_key]
            self._save_bindings()
            return f"✅ Unbound {chat_key} (will use main)"
        return f"⚠️ No binding found for {chat_key}"

    def list_agents(self) -> list:
        """List all agents. 전체 에이전트 목록."""
        self.scan()
        return [a.to_dict() for a in self._agents.values()]

    def list_bindings(self) -> dict:
        """Return all chat→agent bindings."""
        return dict(self._bindings)

    def switch(self, chat_key: str, agent_id: str) -> str:
        """Switch the agent for a chat. /agent switch 명령 처리."""
        return self.bind(chat_key, agent_id)


# Singleton
agent_manager = AgentManager()


# Global telegram bot reference (set during startup)
_llm_cron = None
