"""SalmAlm agents — SubAgent, SkillLoader, PluginLoader."""
import asyncio, importlib, json, os, re, shutil, subprocess, threading, time
from datetime import datetime
from pathlib import Path

from .constants import WORKSPACE_DIR, BASE_DIR, KST
from .crypto import log


def _core():
    """Lazy import to avoid circular dependency."""
    from . import core
    return core


# ============================================================
class SubAgent:
    """Background task executor with notification on completion."""

    _agents: dict = {}  # id -> {task, status, result, thread, started, completed}
    _counter = 0
    _lock = threading.Lock()

    @classmethod
    def spawn(cls, task: str, model: str = None, notify_telegram: bool = True) -> str:
        """Spawn a background sub-agent. Returns agent ID."""
        with cls._lock:
            cls._counter += 1
            agent_id = f'sub-{cls._counter}'

        agent_info = {
            'id': agent_id, 'task': task, 'model': model,
            'status': 'running', 'result': None,
            'started': datetime.now(KST).isoformat(),
            'completed': None, 'notify_telegram': notify_telegram
        }

        def _run():
            try:
                # Create isolated session with its own event loop
                # (avoids cross-loop issues with main loop resources)
                session_id = f'subagent-{agent_id}'
                session = _core().get_session(session_id)
                from .engine import process_message
                result = asyncio.run(
                    process_message(session_id, task, model_override=model))
                agent_info['result'] = result
                agent_info['status'] = 'completed'
                agent_info['completed'] = datetime.now(KST).isoformat()
                log.info(f"🤖 Sub-agent {agent_id} completed: {len(result)} chars")

                # Notify via Telegram
                if agent_info['notify_telegram'] and _core()._tg_bot and _core()._tg_bot.token:
                    summary = result[:500] + ('...' if len(result) > 500 else '')
                    msg = f'🤖 **Sub-agent completed** [{agent_id}]\n\n📋 Task: {task[:100]}\n\n{summary}'
                    try:
                        _core()._tg_bot._api('sendMessage', {
                            'chat_id': _core()._tg_bot.owner_id,
                            'text': msg, 'parse_mode': 'Markdown'
                        })
                    except Exception as e:
                        log.warning(f"Sub-agent notification failed: {e}")

                # Clean up session after a while
                if session_id in _core()._sessions:
                    del _core()._sessions[session_id]

            except Exception as e:
                agent_info['result'] = f'❌ Sub-agent error: {e}'
                agent_info['status'] = 'error'
                agent_info['completed'] = datetime.now(KST).isoformat()
                log.error(f"Sub-agent {agent_id} error: {e}")

        t = threading.Thread(target=_run, daemon=True, name=f'subagent-{agent_id}')
        agent_info['thread'] = t
        cls._agents[agent_id] = agent_info
        t.start()
        log.info(f"🤖 Sub-agent {agent_id} spawned: {task[:80]}")
        return agent_id

    @classmethod
    def list_agents(cls) -> list:
        return [{'id': a['id'], 'task': a['task'][:60], 'status': a['status'],
                 'started': a['started'], 'completed': a['completed']}
                for a in cls._agents.values()]

    @classmethod
    def get_result(cls, agent_id: str) -> dict:
        agent = cls._agents.get(agent_id)
        if not agent:
            return {'error': f'Agent {agent_id} not found'}
        return {'id': agent['id'], 'task': agent['task'], 'status': agent['status'],
                'result': agent['result'], 'started': agent['started'],
                'completed': agent['completed']}

    @classmethod
    def send_message(cls, agent_id: str, message: str) -> str:
        """Send a follow-up message to a completed sub-agent's session."""
        agent = cls._agents.get(agent_id)
        if not agent:
            return f'❌ Agent {agent_id} not found'
        if agent['status'] == 'running':
            return f'⏳ Agent {agent_id} still running. Wait for completion first.'
        # Run in the agent's existing session
        session_id = f'subagent-{agent_id}'
        try:
            from .engine import process_message
            result = asyncio.run(process_message(session_id, message))
            agent['result'] = result  # Update with latest result
            return f'🤖 [{agent_id}] responded:\n\n{result[:3000]}'
        except Exception as e:
            return f'❌ Send failed: {str(e)[:200]}'


class SkillLoader:
    """Load skills from skills/ directory. Each skill = folder with SKILL.md."""

    _cache: dict = {}
    _last_scan = 0
    _defaults_installed = False

    @classmethod
    def _install_defaults(cls):
        """Copy bundled default skills to workspace on first run."""
        if cls._defaults_installed:
            return
        cls._defaults_installed = True
        skills_dir = WORKSPACE_DIR / 'skills'
        skills_dir.mkdir(exist_ok=True)
        import shutil
        pkg_dir = Path(__file__).parent / 'default_skills'
        if not pkg_dir.exists():
            return
        for src in pkg_dir.iterdir():
            if src.is_dir() and (src / 'SKILL.md').exists():
                dest = skills_dir / src.name
                if not dest.exists():
                    shutil.copytree(str(src), str(dest))
                    log.info(f"📚 Default skill installed: {src.name}")

    @classmethod
    def scan(cls) -> list:
        """Scan skills directory, return list of available skills."""
        cls._install_defaults()
        now = time.time()
        if cls._cache and now - cls._last_scan < 120:
            return list(cls._cache.values())

        skills_dir = WORKSPACE_DIR / 'skills'
        if not skills_dir.exists():
            skills_dir.mkdir(exist_ok=True)
            return []

        cls._cache = {}
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / 'SKILL.md'
            if not skill_md.exists():
                continue
            try:
                content = skill_md.read_text(encoding='utf-8', errors='replace')
                # Extract metadata from first few lines
                lines = content.splitlines()
                name = skill_dir.name
                description = ''
                for line in lines[:10]:
                    if line.startswith('# '):
                        name = line[2:].strip()
                    elif line.startswith('> ') or (line.strip() and not line.startswith('#')):
                        description = line.lstrip('> ').strip()
                        break
                cls._cache[skill_dir.name] = {
                    'name': name, 'dir_name': skill_dir.name,
                    'description': description,
                    'path': str(skill_md), 'size': len(content)
                }
            except Exception:
                continue

        cls._last_scan = now
        log.info(f"📚 Skills scanned: {len(cls._cache)} found")
        return list(cls._cache.values())

    @classmethod
    def load(cls, skill_name: str) -> str:
        """Load a skill's SKILL.md content."""
        cls.scan()
        skill = cls._cache.get(skill_name)
        if not skill:
            return None
        try:
            return Path(skill['path']).read_text(encoding='utf-8', errors='replace')
        except Exception:
            return None

    @classmethod
    def match(cls, user_message: str) -> str:
        """Auto-detect which skill matches the user's request. Returns skill content or None."""
        skills = cls.scan()
        if not skills:
            return None
        msg = user_message.lower()
        best_match = None
        best_score = 0
        for skill in skills:
            desc = skill['description'].lower()
            name = skill['name'].lower()
            # Simple keyword matching against skill description
            desc_words = set(re.findall(r'[\w가-힣]+', desc + ' ' + name))
            msg_words = set(re.findall(r'[\w가-힣]+', msg))
            overlap = len(desc_words & msg_words)
            if overlap > best_score:
                best_score = overlap
                best_match = skill
        if best_score >= 2:  # At least 2 keyword matches
            content = cls.load(best_match['dir_name'])
            if content:
                log.info(f"📚 Skill matched: {best_match['name']} (score={best_score})")
                return content
        return None

    @classmethod
    def install(cls, url: str) -> str:
        """Install a skill from a Git URL or GitHub shorthand (user/repo)."""
        import shutil
        skills_dir = WORKSPACE_DIR / 'skills'
        skills_dir.mkdir(exist_ok=True)

        # Support GitHub shorthand: user/repo or user/repo/path
        if not url.startswith('http'):
            parts = url.strip('/').split('/')
            if len(parts) >= 2:
                url = f'https://github.com/{parts[0]}/{parts[1]}.git'

        # Extract repo name for directory
        repo_name = url.rstrip('/').rstrip('.git').split('/')[-1]
        target = skills_dir / repo_name

        if target.exists():
            # Update existing
            result = subprocess.run(['git', '-C', str(target), 'pull'],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                cls._cache.clear()
                cls._last_scan = 0
                return f'📚 Skill updated: {repo_name}\n{result.stdout.strip()}'
            return f'❌ Git pull failed: {result.stderr[:200]}'

        # Fresh clone
        result = subprocess.run(['git', 'clone', '--depth=1', url, str(target)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return f'❌ Git clone failed: {result.stderr[:200]}'

        # Verify SKILL.md exists
        if not (target / 'SKILL.md').exists():
            # Check subdirectories (monorepo with multiple skills)
            found = list(target.glob('*/SKILL.md'))
            if found:
                # Move each skill subfolder to skills/
                installed = []
                for skill_md in found:
                    skill_dir = skill_md.parent
                    dest = skills_dir / skill_dir.name
                    if not dest.exists():
                        shutil.move(str(skill_dir), str(dest))
                        installed.append(skill_dir.name)
                shutil.rmtree(str(target), ignore_errors=True)
                cls._cache.clear()
                cls._last_scan = 0
                return f'📚 Installed {len(installed)} skills: {", ".join(installed)}'
            else:
                shutil.rmtree(str(target), ignore_errors=True)
                return '❌ No SKILL.md found in repository'

        cls._cache.clear()
        cls._last_scan = 0
        return f'📚 Skill installed: {repo_name}'

    @classmethod
    def uninstall(cls, skill_name: str) -> str:
        """Remove a skill directory."""
        import shutil
        target = WORKSPACE_DIR / 'skills' / skill_name
        if not target.exists():
            return f'❌ Skill not found: {skill_name}'
        shutil.rmtree(str(target), ignore_errors=True)
        cls._cache.pop(skill_name, None)
        return f'🗑️ Skill removed: {skill_name}'


# ============================================================
class PluginLoader:
    """Discover and load tool plugins from plugins/*.py files."""

    _plugins: dict = {}  # name -> {module, tools}

    @classmethod
    def scan(cls) -> int:
        """Scan plugins/ directory and load all .py files as tool providers."""
        plugins_dir = BASE_DIR / 'plugins'
        if not plugins_dir.exists():
            plugins_dir.mkdir(exist_ok=True)
            # Create example plugin
            example = plugins_dir / '_example_plugin.py'
            if not example.exists():
                example.write_text('''"""
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
''', encoding='utf-8')
            return 0

        count = 0
        for py_file in sorted(plugins_dir.glob('*.py')):
            if py_file.name.startswith('_'):
                continue  # Skip _example and __init__
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    f'salmalm_plugin_{py_file.stem}', py_file)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                tools = getattr(mod, 'TOOLS', [])
                execute_fn = getattr(mod, 'execute', None)
                if tools and execute_fn:
                    cls._plugins[py_file.stem] = {
                        'module': mod, 'tools': tools,
                        'execute': execute_fn, 'path': str(py_file)
                    }
                    count += len(tools)
                    log.info(f"🔌 Plugin loaded: {py_file.stem} ({len(tools)} tools)")
            except Exception as e:
                log.error(f"Plugin load error ({py_file.name}): {e}")

        log.info(f"🔌 Plugins: {len(cls._plugins)} loaded, {count} tools total")
        return count

    @classmethod
    def get_all_tools(cls) -> list:
        """Return all tool definitions from all plugins."""
        tools = []
        for plugin in cls._plugins.values():
            tools.extend(plugin['tools'])
        return tools

    @classmethod
    def execute(cls, tool_name: str, args: dict) -> str:
        """Execute a plugin tool by name."""
        for plugin in cls._plugins.values():
            tool_names = [t['name'] for t in plugin['tools']]
            if tool_name in tool_names:
                return plugin['execute'](tool_name, args)
        return None  # Not a plugin tool

    @classmethod
    def reload(cls) -> int:
        """Reload all plugins."""
        cls._plugins = {}
        return cls.scan()


# Global telegram bot reference (set during startup)
_llm_cron = None

