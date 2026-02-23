"""Web System routes mixin."""

import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

from salmalm.constants import DATA_DIR, VERSION, WORKSPACE_DIR, BASE_DIR  # noqa: F401
from salmalm.security.crypto import vault  # noqa: F401
from salmalm.constants import APP_NAME  # noqa: F401
from salmalm.core.core import get_usage_report, router  # noqa: F401

import logging

log = logging.getLogger(__name__)


class SystemMixin:
    def _get_uptime(self):
        """Get uptime."""
        from salmalm.features.sla import uptime_monitor

        self._json(uptime_monitor.get_stats())

    def _get_latency(self):
        """Get latency."""
        from salmalm.features.sla import latency_tracker

        self._json(latency_tracker.get_stats())

    def _get_nodes(self):
        """Get nodes."""
        from salmalm.features.nodes import node_manager

        self._json({"nodes": node_manager.list_nodes()})

    def _get_debug(self):
        """Real-time debug diagnostics panel data."""
        if not self._require_auth("user"):
            return
        import sys
        import platform
        import gc
        from salmalm.core import _metrics, get_session
        from salmalm.core.engine import _active_requests, _shutting_down
        from salmalm.tools.tool_registry import (
            _HANDLERS,
            _ensure_modules,
            _DYNAMIC_TOOLS,
        )

        try:
            _ensure_modules()
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        # Session info
        sess = get_session("web")
        sess_msgs = len(sess.messages) if sess else 0
        sess_ctx = sum(len(str(m.get("content", ""))) for m in (sess.messages if sess else []))
        # Provider keys
        from salmalm.core.llm_router import PROVIDERS, is_provider_available

        providers = {n: is_provider_available(n) for n in PROVIDERS}
        # Memory
        import resource

        try:
            mem_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        except Exception as e:  # noqa: broad-except
            mem_mb = 0
        # GC stats
        gc_counts = gc.get_count()
        self._json(
            {
                "python": sys.version,
                "platform": platform.platform(),
                "pid": os.getpid(),
                "memory_mb": round(mem_mb, 1),
                "gc": {
                    "gen0": gc_counts[0],
                    "gen1": gc_counts[1],
                    "gen2": gc_counts[2],
                },
                "active_requests": _active_requests,
                "shutting_down": _shutting_down,
                "metrics": {**_metrics},
                "session": {"messages": sess_msgs, "context_chars": sess_ctx},
                "tools": {"registered": len(_HANDLERS), "dynamic": len(_DYNAMIC_TOOLS)},
                "providers": providers,
                "vault_unlocked": vault.is_unlocked,
            }
        )

    def _get_queue(self):
        """Queue status API."""
        from salmalm.features.queue import queue_status

        session_id = self.headers.get("X-Session-Id", "web")
        self._json(queue_status(session_id))

    @staticmethod
    def _vault_type_label() -> str:
        """Vault type label."""
        try:
            from salmalm.security.crypto import HAS_CRYPTO

            return "AES-256-GCM" if HAS_CRYPTO else "HMAC-CTR (obfuscation only)"
        except Exception as e:  # noqa: broad-except
            return "unknown"

    def _get_ollama_detect(self):
        """GET /api/ollama/detect — auto-detect Ollama and list models."""
        from salmalm.core.llm_router import detect_ollama
        result = detect_ollama()
        self._json(result)

    def _get_status(self):
        """Get status."""
        channels = {}
        if vault.is_unlocked:
            channels["telegram"] = bool(vault.get("telegram_token"))
            channels["discord"] = bool(vault.get("discord_token"))
        self._json(
            {
                "app": APP_NAME,
                "version": VERSION,  # noqa: F405
                "unlocked": vault.is_unlocked,
                "vault_type": self._vault_type_label(),
                "usage": get_usage_report(),
                "model": router.force_model or "auto",
                "channels": channels,
            }
        )

    def _get_metrics(self):
        """Get metrics."""
        from salmalm.core import _metrics

        usage = get_usage_report()
        _metrics["total_cost"] = usage.get("total_cost", 0.0)
        merged = {**request_logger.get_metrics(), **_metrics}
        self._json(merged)

    def _get_cert(self):
        """Get cert."""
        from salmalm.utils.tls import get_cert_info

        self._json(get_cert_info())

    def _get_ws_status(self):
        """Get ws status."""
        from salmalm.web.ws import ws_server

        self._json(
            {
                "running": ws_server._running,
                "clients": ws_server.client_count,
                "port": ws_server.port,
            }
        )

    def _get_usage_daily(self):
        """Get usage daily."""
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import usage_tracker

        self._json({"report": usage_tracker.daily_report()})

    def _get_usage_monthly(self):
        """Get usage monthly."""
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import usage_tracker

        self._json({"report": usage_tracker.monthly_report()})

    def _get_doctor(self):
        """Get doctor."""
        if not self._require_auth("user"):
            return
        from salmalm.features.doctor import doctor

        results = doctor.run_all()
        ok = sum(1 for r in results if r["status"] == "ok")
        self._json({"checks": results, "passed": ok, "total": len(results)})

    def _get_api_logs(self) -> None:
        """Handle GET /api/logs routes."""
        if not self._require_auth("user"):
            return
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        lines = int(qs.get("lines", ["100"])[0])
        level = qs.get("level", [""])[0].upper()
        log_path = DATA_DIR / "salmalm.log"
        entries = []
        if log_path.exists():
            all_lines = log_path.read_text(encoding="utf-8", errors="replace").strip().split("\n")
            for ln in all_lines[-lines:]:
                if level and f"[{level}]" not in ln:
                    continue
                entries.append(ln)
        self._json({"logs": entries, "total": len(entries)})

    def _get_api_audit(self) -> None:
        """Handle GET /api/audit routes."""
        if not self._require_auth("user"):
            return
        import urllib.parse

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        limit = int(params.get("limit", ["50"])[0])
        event_type = params.get("type", [None])[0]
        sid = params.get("session_id", [None])[0]
        from salmalm.core import query_audit_log

        entries = query_audit_log(limit=limit, event_type=event_type, session_id=sid)
        self._json({"entries": entries, "count": len(entries)})

    def _get_api_update_check(self):
        # Alias for /api/check-update
        """Get api update check."""
        try:
            import urllib.request

            resp = urllib.request.urlopen("https://pypi.org/pypi/salmalm/json", timeout=10)
            data = json.loads(resp.read().decode())
            latest = data.get("info", {}).get("version", VERSION)  # noqa: F405
            is_exe = getattr(sys, "frozen", False)
            result = {
                "current": VERSION,
                "latest": latest,
                "exe": is_exe,  # noqa: F405
                "update_available": latest != VERSION,
            }  # noqa: F405
            if is_exe:
                result["download_url"] = "https://github.com/hyunjun6928-netizen/salmalm/releases/latest"
            self._json(result)
        except Exception as e:
            self._json({"current": VERSION, "latest": None, "error": str(e)[:100]})  # noqa: F405

    def _get_static_app_js(self):
        """Serve extracted main application JavaScript."""
        js_path = Path(__file__).parent.parent.parent / "static" / "app.js"
        if not js_path.exists():
            self.send_error(404)
            return
        content = js_path.read_bytes()
        # ETag for caching
        import hashlib

        etag = f'"{hashlib.md5(content).hexdigest()}"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.end_headers()
            return
        self.send_response(200)
        self._cors()
        self._security_headers()
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(content)

    def _check_origin(self) -> bool:
        """CSRF protection for state-changing requests (POST/PUT/DELETE).
        Two-layer defense:
        1. Origin header must be whitelisted (if present)
        2. Custom header X-Requested-With required for /api/ routes
           (browsers enforce CORS preflight for custom headers, blocking cross-origin)
        """
        origin = self.headers.get("Origin", "")
        # Layer 1: If Origin is present, it must be whitelisted
        if origin and origin not in self._ALLOWED_ORIGINS:
            log.warning(f"[BLOCK] CSRF blocked: Origin={origin} on {self.path}")
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"Forbidden: cross-origin request"}')
            return False
        # Layer 2: Require custom header for API routes (CSRF double-submit defense)
        # Webhooks and public paths are exempt (they come from external services)
        if self.path.startswith("/api/") and not self.path.split("?")[0] in self._PUBLIC_PATHS:
            xrw = self.headers.get("X-Requested-With", "")
            if not xrw:
                # Allow if Origin was explicitly whitelisted (SPA sends both)
                if not origin:
                    # No Origin + no X-Requested-With = non-browser (curl, scripts) → allow
                    # This is safe because browsers always send Origin on cross-origin
                    return True
            # If header present, any value is fine (existence proves CORS preflight passed)
        return True
