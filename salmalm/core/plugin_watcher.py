"""Plugin Hot-Reload — polling-based watcher for plugins/ directory.

Monitors ~/.salmalm/plugins/ for file changes and reloads only the affected plugin.
stdlib-only (polling, no watchdog dependency).
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Set

from salmalm.crypto import log
from salmalm.features.plugin_manager import PLUGINS_DIR, plugin_manager


class PluginWatcher:
    """Polling-based watcher for plugin hot-reload."""

    def __init__(self, interval: int = 3):
        self._interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._mtimes: Dict[str, float] = {}
        self._lock = threading.Lock()

    def start(self):
        """Start watching plugins/ directory in background."""
        if self._running:
            return
        self._running = True
        self._initial_scan()
        self._thread = threading.Thread(target=self._run, daemon=True, name='PluginWatcher')
        self._thread.start()
        log.info("[PLUGIN] Hot-reload watcher started")

    def stop(self):
        """Stop the watcher."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self._interval + 2)
        log.info("[PLUGIN] Hot-reload watcher stopped")

    @property
    def running(self) -> bool:
        return self._running

    def _initial_scan(self):
        """Build initial mtime map."""
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        for fpath in self._walk_plugins():
            try:
                self._mtimes[str(fpath)] = fpath.stat().st_mtime
            except OSError:
                pass

    def _run(self):
        while self._running:
            try:
                self._scan()
            except Exception as e:
                log.warning(f"[PLUGIN] Watcher scan error: {e}")
            time.sleep(self._interval)

    def _walk_plugins(self) -> list:
        """List all relevant files under plugins/ dir."""
        result = []
        if not PLUGINS_DIR.exists():
            return result
        exts = {'.py', '.json'}
        for plugin_dir in PLUGINS_DIR.iterdir():
            if not plugin_dir.is_dir() or plugin_dir.name.startswith(('.', '_')):
                continue
            for entry in plugin_dir.rglob('*'):
                if entry.is_file() and entry.suffix in exts:
                    result.append(entry)
        return result

    def _scan(self):
        """Check for changed files and reload affected plugins."""
        current_files: Set[str] = set()
        changed_plugins: Set[str] = set()

        for fpath in self._walk_plugins():
            key = str(fpath)
            current_files.add(key)
            try:
                mtime = fpath.stat().st_mtime
            except OSError:
                continue

            if key not in self._mtimes:
                # New file
                plugin_name = self._extract_plugin_name(fpath)
                if plugin_name:
                    changed_plugins.add(plugin_name)
                self._mtimes[key] = mtime
            elif mtime != self._mtimes[key]:
                # Modified file
                plugin_name = self._extract_plugin_name(fpath)
                if plugin_name:
                    changed_plugins.add(plugin_name)
                self._mtimes[key] = mtime

        # Deleted files
        deleted = set(self._mtimes.keys()) - current_files
        for key in deleted:
            plugin_name = self._extract_plugin_name(Path(key))
            if plugin_name:
                changed_plugins.add(plugin_name)
            del self._mtimes[key]

        # Reload changed plugins
        if changed_plugins:
            for name in changed_plugins:
                log.info(f"[PLUGIN] Hot-reload: {name} (file change detected)")
            self.reload_plugins(changed_plugins)

    def _extract_plugin_name(self, fpath: Path) -> Optional[str]:
        """Extract plugin directory name from a file path."""
        try:
            rel = fpath.relative_to(PLUGINS_DIR)
            return rel.parts[0] if rel.parts else None
        except (ValueError, IndexError):
            return None

    def reload_plugins(self, names: Optional[Set[str]] = None):
        """Reload specific plugins or all if names is None."""
        with self._lock:
            if names:
                # Targeted reload: unload→reload only specific plugins
                for name in names:
                    log.info(f"[PLUGIN] Reloading plugin: {name}")
                # Full scan_and_load handles unload+reload properly
                plugin_manager.scan_and_load()
                log.info(f"[PLUGIN] Hot-reloaded: {', '.join(names)}")
            else:
                plugin_manager.scan_and_load()
                log.info("[PLUGIN] All plugins reloaded")

    def reload_all(self) -> str:
        """Reload all plugins (for /plugins reload command)."""
        return plugin_manager.reload_all()


# Singleton
plugin_watcher = PluginWatcher()
