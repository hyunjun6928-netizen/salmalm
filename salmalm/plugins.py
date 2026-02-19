"""SalmAlm Plugin Architecture — 디렉토리 기반 플러그인 시스템.

Directory-based plugin system with dynamic tool registration and hook integration.

Plugin structure:
  ~/.salmalm/plugins/my_plugin/
    plugin.json    # metadata: name, version, description, tools, hooks
    __init__.py    # entry point

Config: ~/.salmalm/plugins.json (enabled/disabled state)
"""

import importlib.util
import json
import os
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

from .crypto import log

PLUGINS_DIR = Path.home() / '.salmalm' / 'plugins'
PLUGINS_STATE_FILE = Path.home() / '.salmalm' / 'plugins.json'


class PluginInfo:
    """Metadata and runtime state for a loaded plugin."""

    def __init__(self, name: str, path: Path, metadata: dict):
        self.name = name
        self.path = path
        self.metadata = metadata
        self.version = metadata.get('version', '0.0.0')
        self.description = metadata.get('description', '')
        self.enabled = True
        self.module = None
        self.tools: List[dict] = []  # tool definitions
        self.hook_callbacks: Dict[str, callable] = {}  # event -> callback
        self.error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'enabled': self.enabled,
            'path': str(self.path),
            'tools': [t.get('name', '?') for t in self.tools],
            'hooks': list(self.hook_callbacks.keys()),
            'error': self.error,
        }


class PluginManager:
    """Manages directory-based plugins with tool registration and hook integration."""

    def __init__(self):
        self._plugins: Dict[str, PluginInfo] = {}
        self._state: Dict[str, bool] = {}  # name -> enabled
        self._lock = threading.Lock()
        self._load_state()

    def _load_state(self):
        """Load enabled/disabled state from plugins.json."""
        try:
            if PLUGINS_STATE_FILE.exists():
                self._state = json.loads(PLUGINS_STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            self._state = {}

    def _save_state(self):
        """Save enabled/disabled state."""
        try:
            PLUGINS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            state = {name: p.enabled for name, p in self._plugins.items()}
            PLUGINS_STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')
        except Exception as e:
            log.error(f"[PLUGIN] Failed to save state: {e}")

    def scan_and_load(self):
        """Scan ~/.salmalm/plugins/ and load all valid plugins."""
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

        with self._lock:
            # Unregister old plugin hooks
            self._unregister_all_hooks()
            self._plugins.clear()

            for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
                if not plugin_dir.is_dir():
                    continue
                if plugin_dir.name.startswith('_') or plugin_dir.name.startswith('.'):
                    continue

                plugin_json = plugin_dir / 'plugin.json'
                init_py = plugin_dir / '__init__.py'

                if not plugin_json.exists():
                    continue

                try:
                    metadata = json.loads(plugin_json.read_text(encoding='utf-8'))
                except Exception as e:
                    log.error(f"[PLUGIN] Bad plugin.json in {plugin_dir.name}: {e}")
                    continue

                name = metadata.get('name', plugin_dir.name)
                info = PluginInfo(name, plugin_dir, metadata)

                # Check enabled state
                if name in self._state:
                    info.enabled = self._state[name]
                else:
                    info.enabled = True

                if not info.enabled:
                    self._plugins[name] = info
                    log.info(f"[PLUGIN] Skipped (disabled): {name}")
                    continue

                # Load module
                if init_py.exists():
                    try:
                        spec = importlib.util.spec_from_file_location(
                            f'salmalm_plugin_{name}', str(init_py),
                            submodule_search_locations=[str(plugin_dir)]
                        )
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        info.module = mod

                        # Extract tool definitions
                        tools = getattr(mod, 'TOOLS', [])
                        if isinstance(tools, list):
                            info.tools = tools

                        # Extract hook callbacks
                        hooks_config = metadata.get('hooks', {})
                        for event, func_name in hooks_config.items():
                            cb = getattr(mod, func_name, None)
                            if callable(cb):
                                info.hook_callbacks[event] = cb

                        log.info(f"[PLUGIN] Loaded: {name} v{info.version} "
                                 f"({len(info.tools)} tools, {len(info.hook_callbacks)} hooks)")

                    except Exception as e:
                        info.error = str(e)[:200]
                        log.error(f"[PLUGIN] Load error ({name}): {e}")

                self._plugins[name] = info

            # Register hooks
            self._register_all_hooks()

        total_tools = sum(len(p.tools) for p in self._plugins.values() if p.enabled)
        log.info(f"[PLUGIN] {len(self._plugins)} plugins scanned, {total_tools} tools total")
        return len(self._plugins)

    def _register_all_hooks(self):
        """Register all plugin hooks with the HookManager."""
        try:
            from .hooks import hook_manager
            for plugin in self._plugins.values():
                if not plugin.enabled:
                    continue
                for event, cb in plugin.hook_callbacks.items():
                    hook_manager.register_plugin_hook(event, cb)
        except Exception as e:
            log.error(f"[PLUGIN] Hook registration error: {e}")

    def _unregister_all_hooks(self):
        """Unregister all plugin hooks."""
        try:
            from .hooks import hook_manager
            all_cbs = []
            for plugin in self._plugins.values():
                all_cbs.extend(plugin.hook_callbacks.values())
            if all_cbs:
                hook_manager.unregister_plugin_hooks(all_cbs)
        except Exception:
            pass

    def get_all_tools(self) -> List[dict]:
        """Return all tool definitions from enabled plugins."""
        tools = []
        for plugin in self._plugins.values():
            if plugin.enabled and not plugin.error:
                tools.extend(plugin.tools)
        return tools

    def execute_tool(self, tool_name: str, args: dict) -> Optional[str]:
        """Execute a plugin tool by name. Returns None if not found."""
        for plugin in self._plugins.values():
            if not plugin.enabled or plugin.error or not plugin.module:
                continue
            tool_names = [t.get('name') for t in plugin.tools]
            if tool_name in tool_names:
                execute_fn = getattr(plugin.module, 'execute', None)
                if execute_fn:
                    return execute_fn(tool_name, args)
        return None

    def list_plugins(self) -> List[dict]:
        """Return list of all plugins with their status."""
        return [p.to_dict() for p in self._plugins.values()]

    def enable(self, name: str) -> str:
        """Enable a plugin."""
        plugin = self._plugins.get(name)
        if not plugin:
            return f'❌ Plugin not found: {name}'
        plugin.enabled = True
        self._save_state()
        self.scan_and_load()  # reload to activate
        return f'✅ Plugin enabled: {name}'

    def disable(self, name: str) -> str:
        """Disable a plugin."""
        plugin = self._plugins.get(name)
        if not plugin:
            return f'❌ Plugin not found: {name}'
        plugin.enabled = False
        self._save_state()
        self.scan_and_load()  # reload to deactivate
        return f'✅ Plugin disabled: {name}'

    def reload_all(self) -> str:
        """Reload all plugins."""
        count = self.scan_and_load()
        total_tools = sum(len(p.tools) for p in self._plugins.values() if p.enabled)
        return f'🔄 Reloaded {count} plugins ({total_tools} tools)'


# Singleton
plugin_manager = PluginManager()
