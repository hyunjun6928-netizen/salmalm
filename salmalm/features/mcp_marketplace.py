"""MCP Marketplace — catalog, install, manage MCP servers.

stdlib-only.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_CONFIG_DIR = Path.home() / '.salmalm'
_SERVERS_PATH = _CONFIG_DIR / 'mcp_servers.json'

# ---------------------------------------------------------------------------
# Built-in catalog
# ---------------------------------------------------------------------------

MCP_CATALOG: List[Dict[str, Any]] = [
    {
        'name': 'filesystem',
        'description': '파일 시스템 접근',
        'command': ['npx', '@modelcontextprotocol/server-filesystem', '{path}'],
        'env': {},
        'category': 'system',
        'params': {'path': 'Directory path to expose'},
    },
    {
        'name': 'github',
        'description': 'GitHub API',
        'command': ['npx', '@modelcontextprotocol/server-github'],
        'env': {'GITHUB_TOKEN': '{token}'},
        'category': 'dev',
        'params': {'token': 'GitHub personal access token'},
    },
    {
        'name': 'sqlite',
        'description': 'SQLite 데이터베이스',
        'command': ['npx', '@modelcontextprotocol/server-sqlite', '{db_path}'],
        'env': {},
        'category': 'data',
        'params': {'db_path': 'Path to SQLite database file'},
    },
    {
        'name': 'brave-search',
        'description': 'Brave 웹 검색',
        'command': ['npx', '@modelcontextprotocol/server-brave-search'],
        'env': {'BRAVE_API_KEY': '{key}'},
        'category': 'search',
        'params': {'key': 'Brave Search API key'},
    },
    {
        'name': 'puppeteer',
        'description': '브라우저 자동화',
        'command': ['npx', '@modelcontextprotocol/server-puppeteer'],
        'env': {},
        'category': 'browser',
        'params': {},
    },
    {
        'name': 'slack',
        'description': 'Slack 통합',
        'command': ['npx', '@modelcontextprotocol/server-slack'],
        'env': {'SLACK_BOT_TOKEN': '{token}'},
        'category': 'communication',
        'params': {'token': 'Slack bot token'},
    },
    {
        'name': 'google-maps',
        'description': 'Google Maps',
        'command': ['npx', '@modelcontextprotocol/server-google-maps'],
        'env': {'GOOGLE_MAPS_API_KEY': '{key}'},
        'category': 'maps',
        'params': {'key': 'Google Maps API key'},
    },
    {
        'name': 'memory',
        'description': '지식 그래프 메모리',
        'command': ['npx', '@modelcontextprotocol/server-memory'],
        'env': {},
        'category': 'memory',
        'params': {},
    },
    {
        'name': 'postgres',
        'description': 'PostgreSQL 데이터베이스',
        'command': ['npx', '@modelcontextprotocol/server-postgres', '{connection_string}'],
        'env': {},
        'category': 'data',
        'params': {'connection_string': 'PostgreSQL connection string'},
    },
    {
        'name': 'fetch',
        'description': '웹 페이지 가져오기',
        'command': ['npx', '@modelcontextprotocol/server-fetch'],
        'env': {},
        'category': 'web',
        'params': {},
    },
]


class MCPMarketplace:
    """Manage MCP server catalog, installation, and lifecycle."""

    def __init__(self):
        self._installed: Dict[str, Dict] = {}
        self._load()

    def _load(self):
        try:
            if _SERVERS_PATH.exists():
                self._installed = json.loads(_SERVERS_PATH.read_text())
        except Exception as e:
            log.warning(f'Failed to load MCP servers config: {e}')
            self._installed = {}

    def _save(self):
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _SERVERS_PATH.write_text(json.dumps(self._installed, indent=2, ensure_ascii=False))

    def _find_catalog_entry(self, name: str) -> Optional[Dict]:
        for entry in MCP_CATALOG:
            if entry['name'] == name:
                return entry
        return None

    def install(self, name: str, params: Optional[Dict[str, str]] = None) -> str:
        """Install an MCP server from catalog."""
        if name in self._installed:
            return f'ℹ️ `{name}` is already installed.'

        entry = self._find_catalog_entry(name)
        if not entry:
            return f'❌ `{name}` not found in catalog. Use `/mcp catalog` to see available servers.'

        # Build command with resolved params
        params = params or {}
        command = []
        for part in entry['command']:
            if part.startswith('{') and part.endswith('}'):
                param_name = part[1:-1]
                if param_name in params:
                    command.append(params[param_name])
                else:
                    # Needs user input
                    desc = entry.get('params', {}).get(param_name, param_name)
                    return f'⚠️ `{name}` requires parameter `{param_name}`: {desc}\n' \
                        f'Use: `/mcp install {name}` and set `{param_name}` in config.'
            else:
                command.append(part)

        # Build env with resolved params
        env = {}
        for k, v in entry.get('env', {}).items():
            if v.startswith('{') and v.endswith('}'):
                param_name = v[1:-1]
                if param_name in params:
                    env[k] = params[param_name]
                elif k in os.environ:
                    env[k] = os.environ[k]
                else:
                    desc = entry.get('params', {}).get(param_name, param_name)
                    return f'⚠️ `{name}` requires env `{k}`: {desc}\n' \
                        f'Set environment variable `{k}` or provide via params.'
            else:
                env[k] = v

        self._installed[name] = {
            'name': name,
            'description': entry['description'],
            'command': command,
            'env': env,
            'category': entry['category'],
            'installed_at': time.time(),
            'status': 'installed',
        }
        self._save()

        # Try to connect via MCPManager
        self._connect_server(name)

        return f'✅ `{name}` installed successfully ({entry["description"]}).'

    def _connect_server(self, name: str):
        """Attempt to connect installed server via MCPManager."""
        info = self._installed.get(name)
        if not info:
            return
        try:
            from salmalm.features.mcp import MCPManager
            mgr = MCPManager()
            mgr.add_server(name, info['command'], env=info.get('env'))
            info['status'] = 'connected'
            self._save()
        except Exception as e:
            log.warning(f'Failed to connect MCP server {name}: {e}')
            info['status'] = f'error: {e}'
            self._save()

    def remove(self, name: str) -> str:
        if name not in self._installed:
            return f'ℹ️ `{name}` is not installed.'
        try:
            from salmalm.features.mcp import MCPManager
            mgr = MCPManager()
            mgr.remove_server(name)
        except Exception:
            pass
        del self._installed[name]
        self._save()
        return f'🗑️ `{name}` removed.'

    def list_installed(self) -> str:
        if not self._installed:
            return '📦 No MCP servers installed. Use `/mcp catalog` to browse.'
        lines = ['📦 **Installed MCP servers:**']
        for name, info in self._installed.items():
            status = info.get('status', 'unknown')
            desc = info.get('description', '')
            lines.append(f'  • `{name}` — {desc} [{status}]')
        return '\n'.join(lines)

    def catalog(self) -> str:
        lines = ['📚 **MCP Server Catalog:**']
        by_cat: Dict[str, list] = {}
        for entry in MCP_CATALOG:
            cat = entry.get('category', 'other')
            by_cat.setdefault(cat, []).append(entry)
        for cat, entries in sorted(by_cat.items()):
            lines.append(f'\n**{cat.upper()}:**')
            for e in entries:
                installed = '✅' if e['name'] in self._installed else '  '
                lines.append(f'  {installed} `{e["name"]}` — {e["description"]}')
        lines.append('\nInstall: `/mcp install <name>`')
        return '\n'.join(lines)

    def status(self) -> str:
        total = len(self._installed)
        connected = sum(1 for i in self._installed.values() if i.get('status') == 'connected')
        lines = [f'🔌 **MCP Status:** {connected}/{total} connected']
        for name, info in self._installed.items():
            lines.append(f'  • `{name}`: {info.get("status", "unknown")}')
        return '\n'.join(lines)

    def search(self, query: str) -> str:
        if not query:
            return '❓ Usage: /mcp search <query>'
        query_lower = query.lower()
        matches = [
            e for e in MCP_CATALOG
            if query_lower in e['name'].lower()
            or query_lower in e.get('description', '').lower()
            or query_lower in e.get('category', '').lower()
        ]
        if not matches:
            return f'🔍 No MCP servers matching "{query}".'
        lines = [f'🔍 **{len(matches)} matches:**']
        for e in matches:
            installed = '✅' if e['name'] in self._installed else '  '
            lines.append(f'  {installed} `{e["name"]}` — {e["description"]}')
        return '\n'.join(lines)

    def auto_connect_all(self, retries: int = 3):
        """Connect all installed servers on startup."""
        for name in list(self._installed.keys()):
            for attempt in range(retries):
                try:
                    self._connect_server(name)
                    if self._installed[name].get('status') == 'connected':
                        break
                except Exception:
                    if attempt < retries - 1:
                        time.sleep(1)

    def get_catalog_json(self) -> List[Dict]:
        """Return catalog for /api/mcp/catalog."""
        result = []
        for e in MCP_CATALOG:
            result.append({
                'name': e['name'],
                'description': e['description'],
                'category': e.get('category', 'other'),
                'installed': e['name'] in self._installed,
                'params': e.get('params', {}),
            })
        return result

    def get_installed_json(self) -> List[Dict]:
        """Return installed list for /api/mcp/installed."""
        return [
            {
                'name': info['name'],
                'description': info.get('description', ''),
                'category': info.get('category', ''),
                'status': info.get('status', 'unknown'),
                'installed_at': info.get('installed_at', 0),
            }
            for info in self._installed.values()
        ]


# Singleton
marketplace = MCPMarketplace()
