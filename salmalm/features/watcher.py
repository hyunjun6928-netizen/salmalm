"""File Watcher + Auto-Index — polling-based file change detection with RAG re-indexing.

Monitors specified directories for file changes (created/modified/deleted)
using mtime polling. Triggers debounced RAG re-indexing on changes.
stdlib-only.
"""
import json
import os
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from salmalm import log

_WATCHER_CONFIG = Path.home() / '.salmalm' / 'watcher.json'

DEFAULT_EXTENSIONS = {'.md', '.txt', '.py', '.json', '.yaml', '.yml'}
DEFAULT_EXCLUDE = {'node_modules', '.git', '__pycache__', '.venv', 'venv'}


from salmalm.config_manager import ConfigManager

_WATCHER_DEFAULTS = {
    'enabled': True,
    'paths': [str(Path.home() / '.salmalm')],
    'extensions': list(DEFAULT_EXTENSIONS),
    'interval': 5,
    'debounceMs': 2000,
    'excludePatterns': list(DEFAULT_EXCLUDE),
}


def _load_config() -> dict:
    return ConfigManager.load('watcher', defaults=_WATCHER_DEFAULTS)


class FileWatcher:
    """Polling-based file watcher that detects created/modified/deleted files."""

    def __init__(self, paths: Optional[List[str]] = None, interval: int = 5,
                 extensions: Optional[Set[str]] = None,
                 exclude_patterns: Optional[Set[str]] = None,
                 on_change: Optional[Callable] = None):
        config = _load_config()
        self._paths = [Path(os.path.expanduser(p)) for p in (paths or config.get('paths', []))]
        self._interval = interval or config.get('interval', 5)
        self._extensions = extensions or set(config.get('extensions', DEFAULT_EXTENSIONS))
        self._exclude = exclude_patterns or set(config.get('excludePatterns', DEFAULT_EXCLUDE))
        self._on_change = on_change
        self._mtimes: Dict[str, float] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._debounce_timer: Optional[threading.Timer] = None
        self._debounce_ms = config.get('debounceMs', 2000)
        self._pending_changes: List[dict] = []
        self._lock = threading.Lock()

    def start(self):
        """Start watching in a background thread."""
        if self._running:
            return
        self._running = True
        # Initial scan to populate mtimes
        self._initial_scan()
        self._thread = threading.Thread(target=self._run, daemon=True, name='FileWatcher')
        self._thread.start()
        log.info('FileWatcher started')

    def stop(self):
        """Stop the watcher."""
        self._running = False
        if self._debounce_timer:
            self._debounce_timer.cancel()
        if self._thread:
            self._thread.join(timeout=self._interval + 2)
        log.info('FileWatcher stopped')

    @property
    def running(self) -> bool:
        return self._running

    def _run(self):
        while self._running:
            try:
                self._scan()
            except Exception as e:
                log.info(f'FileWatcher scan error: {e}')
            time.sleep(self._interval)

    def _initial_scan(self):
        """Build initial mtime map without triggering changes."""
        for path in self._paths:
            if not path.exists():
                continue
            for fpath in self._walk(path):
                key = str(fpath)
                try:
                    self._mtimes[key] = fpath.stat().st_mtime
                except OSError:
                    pass

    def _scan(self):
        """Compare current file mtimes with stored ones."""
        current_files: Set[str] = set()
        changes = []

        for path in self._paths:
            if not path.exists():
                continue
            for fpath in self._walk(path):
                key = str(fpath)
                current_files.add(key)
                try:
                    mtime = fpath.stat().st_mtime
                except OSError:
                    continue

                if key not in self._mtimes:
                    changes.append({'path': key, 'event': 'created'})
                    self._mtimes[key] = mtime
                elif mtime != self._mtimes[key]:
                    changes.append({'path': key, 'event': 'modified'})
                    self._mtimes[key] = mtime

        # Check for deleted files
        deleted = set(self._mtimes.keys()) - current_files
        for key in deleted:
            changes.append({'path': key, 'event': 'deleted'})
            del self._mtimes[key]

        if changes:
            self._handle_changes(changes)

    def _walk(self, root: Path):
        """Walk directory tree, yielding files matching extensions and not excluded."""
        try:
            for entry in os.scandir(str(root)):
                if entry.name in self._exclude:
                    continue
                if entry.is_dir(follow_symlinks=False):
                    yield from self._walk(Path(entry.path))
                elif entry.is_file():
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in self._extensions:
                        yield Path(entry.path)
        except PermissionError:
            pass

    def _handle_changes(self, changes: List[dict]):
        """Debounce changes and dispatch."""
        with self._lock:
            self._pending_changes.extend(changes)
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(
                self._debounce_ms / 1000.0, self._flush_changes
            )
            self._debounce_timer.start()

    def _flush_changes(self):
        """Flush pending changes to the callback."""
        with self._lock:
            changes = self._pending_changes[:]
            self._pending_changes.clear()

        if not changes:
            return

        # Bulk change detection
        BULK_THRESHOLD = 20
        is_bulk = len(changes) >= BULK_THRESHOLD

        for change in changes:
            try:
                if self._on_change:
                    self._on_change(change['path'], change['event'])
            except Exception as e:
                log.info(f'FileWatcher callback error: {e}')

    def get_watched_files(self) -> Dict[str, float]:
        """Return current tracked files and their mtimes."""
        return dict(self._mtimes)


# ── RAG Integration ──────────────────────────────────────────

class RAGFileWatcher(FileWatcher):
    """FileWatcher that triggers RAG re-indexing on file changes."""

    def __init__(self, rag_engine=None, **kwargs):
        self._rag = rag_engine
        super().__init__(on_change=self._on_file_change, **kwargs)

    def _on_file_change(self, path: str, event: str):
        if not self._rag:
            return
        try:
            if event == 'deleted':
                # Remove from index
                log.info(f'RAGFileWatcher: removing {path} from index')
                # RAG engine should support remove_file
                if hasattr(self._rag, 'remove_file'):
                    self._rag.remove_file(path)
            elif event in ('created', 'modified'):
                log.info(f'RAGFileWatcher: re-indexing {path}')
                fpath = Path(path)
                if fpath.exists() and hasattr(self._rag, 'index_file'):
                    label = fpath.name
                    self._rag.index_file(label, fpath)
        except Exception as e:
            log.info(f'RAGFileWatcher index error: {e}')
