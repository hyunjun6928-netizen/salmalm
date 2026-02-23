"""Web Content routes mixin."""

import json
import logging

from salmalm.constants import DATA_DIR, VERSION, WORKSPACE_DIR, MEMORY_DIR, BASE_DIR, AUDIT_DB  # noqa: F401
from salmalm.core.core import get_usage_report  # noqa: F401
from salmalm.security.crypto import vault, log as _log  # noqa: F401

log = logging.getLogger(__name__)


class ContentMixin:
    def _get_thoughts(self):
        """Get thoughts."""
        from salmalm.features.thoughts import thought_stream
        import urllib.parse as _up

        qs = _up.parse_qs(_up.urlparse(self.path).query)
        search_q = qs.get("q", [""])[0]
        if search_q:
            results = thought_stream.search(search_q)
        else:
            n = int(qs.get("limit", ["20"])[0])
            results = thought_stream.list_recent(n)
        self._json({"thoughts": results})

    def _get_thoughts_stats(self):
        """Get thoughts stats."""
        from salmalm.features.thoughts import thought_stream

        self._json(thought_stream.stats())

    def _get_tools_list(self):
        """Get tools list."""
        tools = []
        try:
            from salmalm.tools.tool_registry import _HANDLERS, _ensure_modules

            _ensure_modules()
            for name in sorted(_HANDLERS.keys()):
                tools.append({"name": name, "description": ""})
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        if not tools:
            # Fallback: list all known tools from INTENT_TOOLS
            try:
                from salmalm.core.engine import INTENT_TOOLS

                seen = set()
                for cat_tools in INTENT_TOOLS.values():
                    for t in cat_tools:
                        n = t.get("function", {}).get("name", "")
                        if n and n not in seen:
                            seen.add(n)
                            tools.append(
                                {
                                    "name": n,
                                    "description": t.get("function", {}).get("description", ""),
                                }
                            )
            except Exception as e:  # noqa: broad-except
                tools = [
                    {"name": "web_search", "description": "Search the web"},
                    {"name": "bash", "description": "Execute shell commands"},
                    {"name": "file_read", "description": "Read files"},
                    {"name": "file_write", "description": "Write files"},
                    {"name": "browser", "description": "Browser automation"},
                ]
        self._json({"tools": tools, "count": len(tools)})

    def _post_api_thoughts_search(self):
        """Handle /api/thoughts/search."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.features.thoughts import thought_stream

        q = body.get("q", body.get("query", ""))
        if not q:
            self._json({"error": "query required"}, 400)
            return
        results = thought_stream.search(q)
        self._json({"thoughts": results})

    def _post_api_bookmarks(self):
        """Post api bookmarks."""
        body = self._body
        # Add/remove bookmark — LobeChat style (북마크 추가/제거)
        if not self._require_auth("user"):
            return
        action = body.get("action", "add")
        session_id = body.get("session_id", "")
        message_index = body.get("message_index")
        if not session_id or message_index is None:
            self._json({"error": "Missing session_id or message_index"}, 400)
            return
        from salmalm.features.edge_cases import bookmark_manager

        if action == "add":
            ok = bookmark_manager.add(
                session_id,
                int(message_index),
                content_preview=body.get("preview", ""),
                note=body.get("note", ""),
                role=body.get("role", "assistant"),
            )
            self._json({"ok": ok})
        elif action == "remove":
            ok = bookmark_manager.remove(session_id, int(message_index))
            self._json({"ok": ok})
        else:
            self._json({"error": "Unknown action"}, 400)
        return

    def _post_api_thoughts(self):
        """Post api thoughts."""
        body = self._body
        from salmalm.features.thoughts import thought_stream

        content = body.get("content", "").strip()
        if not content:
            self._json({"error": "content required"}, 400)
            return
        mood = body.get("mood", "neutral")
        tid = thought_stream.add(content, mood=mood)
        self._json({"ok": True, "id": tid})

    def _get_personas(self):
        """Get personas."""
        from salmalm.core.prompt import list_personas, get_active_persona

        session_id = self.headers.get("X-Session-Id", "web")
        personas = list_personas()
        active = get_active_persona(session_id)
        self._json({"personas": personas, "active": active})

    def _get_memory_files(self):
        """Get memory files."""
        if not self._require_auth("user"):
            return
        mem_dir = BASE_DIR / "memory"
        files = []
        # Main memory file
        main_mem = DATA_DIR / "memory.json"
        if main_mem.exists():
            files.append(
                {
                    "name": "memory.json",
                    "size": main_mem.stat().st_size,
                    "path": "memory.json",
                }
            )
        # Memory directory files
        if mem_dir.exists():
            for f in sorted(mem_dir.iterdir(), reverse=True):
                if f.is_file() and f.suffix in (".json", ".md", ".txt"):
                    files.append(
                        {
                            "name": f.name,
                            "size": f.stat().st_size,
                            "path": f"memory/{f.name}",
                        }
                    )
        # Soul file
        soul = DATA_DIR / "soul.md"
        if soul.exists():
            files.append({"name": "soul.md", "size": soul.stat().st_size, "path": "soul.md"})
        self._json({"files": files})

    def _get_mcp(self):
        """Get mcp."""
        if not self._require_auth("user"):
            return
        from salmalm.features.mcp import mcp_manager

        servers = mcp_manager.list_servers()
        all_tools = mcp_manager.get_all_tools()
        self._json({"servers": servers, "total_tools": len(all_tools)})

    def _get_rag(self):
        """Get rag."""
        if not self._require_auth("user"):
            return
        from salmalm.features.rag import rag_engine

        self._json(rag_engine.get_stats())

    def _get_api_search(self) -> None:
        """Handle GET /api/search routes."""
        if not self._require_auth("user"):
            return
        import urllib.parse

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        query = params.get("q", [""])[0]
        if not query:
            self._json({"error": "Missing q parameter"}, 400)
            return
        lim = int(params.get("limit", ["20"])[0])
        from salmalm.core import search_messages

        results = search_messages(query, limit=lim)
        self._json({"query": query, "results": results, "count": len(results)})

    def _get_api_rag_search(self) -> None:
        """Handle GET /api/rag/search routes."""
        if not self._require_auth("user"):
            return
        from salmalm.features.rag import rag_engine
        import urllib.parse

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        query = params.get("q", [""])[0]
        if not query:
            self._json({"error": "Missing q parameter"}, 400)
        else:
            results = rag_engine.search(query, max_results=int(params.get("n", ["5"])[0]))
            self._json({"query": query, "results": results})

    def _get_api_memory_read(self) -> None:
        """Handle GET /api/memory/read? routes."""
        if not self._require_auth("user"):
            return
        import urllib.parse as _up

        qs = _up.parse_qs(_up.urlparse(self.path).query)
        fpath = qs.get("file", [""])[0]
        if not fpath or ".." in fpath:
            self._json({"error": "Invalid path"}, 400)
            return
        # P0-1: Block absolute paths and resolve to prevent path traversal
        from pathlib import PurePosixPath

        if PurePosixPath(fpath).is_absolute() or "\\" in fpath:
            self._json({"error": "Invalid path"}, 400)
            return
        full = (BASE_DIR / fpath).resolve()
        if not full.is_relative_to(BASE_DIR.resolve()):
            self._json({"error": "Path outside allowed directory"}, 403)
            return
        if not full.exists() or not full.is_file():
            self._json({"error": "File not found"}, 404)
            return
        try:
            content = full.read_text(encoding="utf-8")[:50000]
            self._json({"file": fpath, "content": content, "size": full.stat().st_size})
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _get_api_sessions_summary(self) -> None:
        """Handle GET /api/sessions/ routes."""
        # Conversation summary card — BIG-AGI style (대화 요약 카드)
        if not self._require_auth("user"):
            return
        m = re.match(r"^/api/sessions/([^/]+)/summary", self.path)
        if m:
            from salmalm.features.edge_cases import get_summary_card

            card = get_summary_card(m.group(1))
            self._json({"summary": card})
        else:
            self._json({"error": "Invalid path"}, 400)

    def _get_api_sessions_alternatives(self) -> None:
        """Handle GET /api/sessions/ routes."""
        # Conversation fork alternatives — LibreChat style (대화 포크)
        if not self._require_auth("user"):
            return
        m = re.match(r"^/api/sessions/([^/]+)/alternatives/(\d+)", self.path)
        if m:
            from salmalm.features.edge_cases import conversation_fork

            alts = conversation_fork.get_alternatives(m.group(1), int(m.group(2)))
            self._json({"alternatives": alts})
        else:
            self._json({"error": "Invalid path"}, 400)

    def _get_groups(self):
        """Get groups."""
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import session_groups

        self._json({"groups": session_groups.list_groups()})

    def _get_soul(self):
        """Get soul."""
        if not self._require_auth("user"):
            return
        from salmalm.core.prompt import get_user_soul, USER_SOUL_FILE

        self._json({"content": get_user_soul(), "path": str(USER_SOUL_FILE)})

    def _get_commands(self):
        """Get commands."""
        cmds = [
            {"name": "/help", "desc": "Show help"},
            {"name": "/status", "desc": "Session status"},
            {"name": "/model", "desc": "Switch model"},
            {"name": "/compact", "desc": "Compress context"},
            {"name": "/context", "desc": "Token breakdown"},
            {"name": "/usage", "desc": "Token/cost tracking"},
            {"name": "/think", "desc": "Record thought / thinking level"},
            {"name": "/persona", "desc": "Switch persona"},
            {"name": "/branch", "desc": "Branch conversation"},
            {"name": "/rollback", "desc": "Rollback messages"},
            {"name": "/life", "desc": "Life dashboard"},
            {"name": "/remind", "desc": "Set reminder"},
            {"name": "/expense", "desc": "Track expense"},
            {"name": "/pomodoro", "desc": "Pomodoro timer"},
            {"name": "/note", "desc": "Save note"},
            {"name": "/link", "desc": "Save link"},
            {"name": "/routine", "desc": "Manage routines"},
            {"name": "/shadow", "desc": "Shadow mode"},
            {"name": "/vault", "desc": "Encrypted vault"},
            {"name": "/capsule", "desc": "Time capsule"},
            {"name": "/deadman", "desc": "Dead man's switch"},
            {"name": "/a2a", "desc": "Agent-to-agent"},
            {"name": "/workflow", "desc": "Workflow engine"},
            {"name": "/mcp", "desc": "MCP management"},
            {"name": "/subagents", "desc": "Sub-agents"},
            {"name": "/oauth", "desc": "OAuth setup"},
            {"name": "/bash", "desc": "Run shell command"},
            {"name": "/screen", "desc": "Browser control"},
            {"name": "/evolve", "desc": "Evolving prompt"},
            {"name": "/mood", "desc": "Mood detection"},
            {"name": "/split", "desc": "A/B split response"},
        ]
        self._json({"commands": cmds, "count": len(cmds)})

    def _get_api_dashboard(self):
        """Get api dashboard."""
        if not self._require_auth("user"):
            return
        # Dashboard data: sessions, costs, tools, cron jobs
        from salmalm.core import _sessions, _llm_cron, PluginLoader, SubAgent  # type: ignore[attr-defined]

        sessions_info = [
            {
                "id": s.id,
                "messages": len(s.messages),
                "last_active": s.last_active,
                "created": s.created,
            }
            for s in _sessions.values()
        ]
        cron_jobs = _llm_cron.list_jobs() if _llm_cron else []
        plugins = [{"name": n, "tools": len(p["tools"])} for n, p in PluginLoader._plugins.items()]
        subagents = SubAgent.list_agents()
        usage = get_usage_report()
        # Cost by hour (from audit)
        cost_timeline = []
        try:
            import sqlite3 as _sq

            _conn = _sq.connect(str(AUDIT_DB))  # noqa: F405
            cur = _conn.execute(
                "SELECT substr(ts,1,13) as hour, COUNT(*) as cnt "
                "FROM audit_log WHERE event='tool_exec' "
                "GROUP BY hour ORDER BY hour DESC LIMIT 24"
            )
            cost_timeline = [{"hour": r[0], "count": r[1]} for r in cur.fetchall()]
            _conn.close()
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        self._json(
            {
                "sessions": sessions_info,
                "usage": usage,
                "cron_jobs": cron_jobs,
                "plugins": plugins,
                "subagents": subagents,
                "cost_timeline": cost_timeline,
            }
        )

    def _get_manifest_json(self):
        """Get manifest json."""
        manifest = {
            "name": "SalmAlm — Personal AI Gateway",
            "short_name": "SalmAlm",
            "description": "Your personal AI gateway. 67 tools, 6 providers, zero dependencies.",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0b0d14",
            "theme_color": "#6366f1",
            "orientation": "any",
            "categories": ["productivity", "utilities"],
            "icons": [
                {
                    "src": "/icon-192.svg",
                    "sizes": "192x192",
                    "type": "image/svg+xml",
                    "purpose": "any",
                },
                {
                    "src": "/icon-512.svg",
                    "sizes": "512x512",
                    "type": "image/svg+xml",
                    "purpose": "any maskable",
                },
            ],
        }
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/manifest+json")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(json.dumps(manifest).encode())
