"""Web System routes mixin."""

import json
import os
from pathlib import Path

from salmalm.constants import DATA_DIR, VERSION, WORKSPACE_DIR, BASE_DIR  # noqa: F401
from salmalm.security.crypto import vault, log  # noqa: F401
from salmalm.constants import APP_NAME  # noqa: F401
from salmalm.core.core import get_usage_report, router as _core_router  # noqa: F401

import logging

log = logging.getLogger(__name__)


class SystemMixin:
    GET_ROUTES = {
        "/api/uptime": "_get_uptime",
        "/api/latency": "_get_latency",
        "/api/nodes": "_get_nodes",
        "/api/status": "_get_status",
        "/api/debug": "_get_debug",
        "/api/queue": "_get_queue",
        "/api/metrics": "_get_metrics",
        "/api/cert": "_get_cert",
        "/api/ws/status": "_get_ws_status",
        "/api/usage/daily": "_get_usage_daily",
        "/api/usage/monthly": "_get_usage_monthly",
        "/api/doctor": "_get_doctor",
        "/api/ollama/detect": "_get_ollama_detect",
        "/api/update/check": "_get_api_update_check",
        "/static/app.js": "_get_static_app_js",
    }
    GET_PREFIX_ROUTES = [
        ("/api/audit", "_get_api_audit", None),
        ("/api/logs", "_get_api_logs", None),
    ]

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
        from salmalm.core.engine_pipeline import _active_requests, _shutting_down
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
        # Include session-level model override if available
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(self.path).query)
        _sid = qs.get("session", ["web"])[0]
        # Session-level override takes absolute precedence (including "auto")
        _effective_model = "auto"
        try:
            from salmalm.core import get_session
            _sess = get_session(_sid)
            _ov = getattr(_sess, "model_override", None)
            if _ov and _ov != "auto":
                _effective_model = _ov  # specific model override on session
            elif _ov == "auto":
                _effective_model = "auto"  # user explicitly chose auto routing
            elif _ov is None and _core_router.force_model:
                _effective_model = _core_router.force_model  # no session pref → global fallback
        except Exception as e:
            log.debug(f"[STATUS] session model lookup failed: {e}")
            _effective_model = _core_router.force_model or "auto"
        self._json(
            {
                "app": APP_NAME,
                "version": VERSION,  # noqa: F405
                "unlocked": vault.is_unlocked,
                "vault_type": self._vault_type_label(),
                "usage": get_usage_report(),
                "model": _effective_model,
                "channels": channels,
            }
        )

    def _get_metrics(self):
        """Get metrics — Prometheus text format 0.0.4."""
        from salmalm.monitoring.metrics import metrics as prom_metrics

        body = prom_metrics.render_text().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self._cors()
        self._security_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
        try:
            limit = max(1, min(int(params.get("limit", ["50"])[0]), 500))
        except (TypeError, ValueError, IndexError):
            limit = 50
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

        etag = f'"{hashlib.md5(content, usedforsecurity=False).hexdigest()}"'
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
        if self._ALLOWED_ORIGINS is None:
            from salmalm.web.web import WebHandler
            WebHandler._ALLOWED_ORIGINS = WebHandler._build_allowed_origins()
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


# ── FastAPI router — true async handlers (no _dispatch) ──────────────────
import asyncio as _asyncio
import sys as _sys
from fastapi import APIRouter as _APIRouter, Request as _Request, Depends as _Depends, Query as _Query
from fastapi.responses import JSONResponse as _JSON, Response as _Response
from salmalm.web.fastapi_deps import require_auth as _auth, optional_auth as _optauth

router = _APIRouter()


@router.get("/api/uptime")
async def get_api_uptime():
    from salmalm.features.sla import uptime_monitor
    return _JSON(uptime_monitor.get_stats())


@router.get("/api/latency")
async def get_api_latency():
    from salmalm.features.sla import latency_tracker
    return _JSON(latency_tracker.get_stats())


@router.get("/api/nodes")
async def get_api_nodes(_u=_Depends(_auth)):
    from salmalm.features.nodes import node_manager
    return _JSON({"nodes": node_manager.list_nodes()})


@router.get("/api/status")
async def get_api_status(request: _Request, session: str = _Query("web")):
    from salmalm.core.core import get_usage_report, router as _cr
    from salmalm.security.crypto import vault
    channels = {}
    if vault.is_unlocked:
        channels["telegram"] = bool(vault.get("telegram_token"))
        channels["discord"] = bool(vault.get("discord_token"))
    _effective_model = "auto"
    try:
        from salmalm.core import get_session
        _sess = get_session(session)
        _ov = getattr(_sess, "model_override", None)
        if _ov and _ov != "auto":
            _effective_model = _ov
        elif _ov is None and _cr.force_model:
            _effective_model = _cr.force_model
    except Exception:
        pass
    from salmalm.security.crypto import HAS_CRYPTO
    vault_type = "AES-256-GCM" if HAS_CRYPTO else "HMAC-CTR (obfuscation only)"
    return _JSON({
        "app": APP_NAME, "version": VERSION,
        "unlocked": vault.is_unlocked, "vault_type": vault_type,
        "usage": get_usage_report(), "model": _effective_model,
        "channels": channels,
    })


@router.get("/api/debug")
async def get_api_debug(_u=_Depends(_auth)):
    import gc, platform
    from salmalm.core import _metrics, get_session
    from salmalm.core.engine_pipeline import _active_requests, _shutting_down
    from salmalm.tools.tool_registry import _HANDLERS, _ensure_modules, _DYNAMIC_TOOLS
    from salmalm.core.llm_router import PROVIDERS, is_provider_available
    from salmalm.security.crypto import vault
    try:
        _ensure_modules()
    except Exception:
        pass
    sess = get_session("web")
    sess_msgs = len(sess.messages) if sess else 0
    sess_ctx = sum(len(str(m.get("content", ""))) for m in (sess.messages if sess else []))
    providers = {n: is_provider_available(n) for n in PROVIDERS}
    import resource
    try:
        mem_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        mem_mb = 0
    gc_counts = gc.get_count()
    return _JSON({
        "python": _sys.version, "platform": platform.platform(),
        "pid": os.getpid(), "memory_mb": round(mem_mb, 1),
        "gc": {"gen0": gc_counts[0], "gen1": gc_counts[1], "gen2": gc_counts[2]},
        "active_requests": _active_requests, "shutting_down": _shutting_down,
        "metrics": {**_metrics},
        "session": {"messages": sess_msgs, "context_chars": sess_ctx},
        "tools": {"registered": len(_HANDLERS), "dynamic": len(_DYNAMIC_TOOLS)},
        "providers": providers, "vault_unlocked": vault.is_unlocked,
    })


@router.get("/api/queue")
async def get_api_queue(request: _Request, _u=_Depends(_auth)):
    from salmalm.features.queue import queue_status
    session_id = request.headers.get("x-session-id", "web")
    return _JSON(queue_status(session_id))


@router.get("/api/metrics")
async def get_api_metrics(_u=_Depends(_auth)):
    from salmalm.monitoring.metrics import metrics as _pm
    body = _pm.render_text().encode("utf-8")
    return _Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/api/cert")
async def get_api_cert(_u=_Depends(_auth)):
    from salmalm.utils.tls import get_cert_info
    return _JSON(get_cert_info())


@router.get("/api/ws/status")
async def get_api_ws_status(_u=_Depends(_auth)):
    from salmalm.web.ws import ws_server
    return _JSON({"running": ws_server._running, "clients": ws_server.client_count, "port": ws_server.port})


@router.get("/api/usage/daily")
async def get_api_usage_daily(_u=_Depends(_auth)):
    from salmalm.features.edge_cases import usage_tracker
    return _JSON({"report": usage_tracker.daily_report()})


@router.get("/api/usage/monthly")
async def get_api_usage_monthly(_u=_Depends(_auth)):
    from salmalm.features.edge_cases import usage_tracker
    return _JSON({"report": usage_tracker.monthly_report()})


@router.get("/api/doctor")
async def get_api_doctor(_u=_Depends(_auth)):
    from salmalm.features.doctor import doctor
    results = await _asyncio.to_thread(doctor.run_all)
    ok = sum(1 for r in results if r["status"] == "ok")
    return _JSON({"checks": results, "passed": ok, "total": len(results)})


@router.get("/api/ollama/detect")
async def get_api_ollama_detect():
    from salmalm.core.llm_router import detect_ollama
    result = await _asyncio.to_thread(detect_ollama)
    return _JSON(result)


@router.get("/api/update/check")
async def get_api_update_check():
    import urllib.request as _ur
    try:
        resp = await _asyncio.to_thread(lambda: _ur.urlopen("https://pypi.org/pypi/salmalm/json", timeout=10))
        import json as _j
        data = _j.loads(resp.read().decode())
        latest = data.get("info", {}).get("version", VERSION)
        result = {"current": VERSION, "latest": latest, "exe": getattr(_sys, "frozen", False),
                  "update_available": latest != VERSION}
    except Exception as e:
        result = {"current": VERSION, "latest": None, "error": str(e)[:100]}
    return _JSON(result)


@router.get("/static/app.js")
async def get_static_app_js(request: _Request):
    import hashlib
    js_path = Path(__file__).parent.parent.parent / "static" / "app.js"
    if not js_path.exists():
        return _Response(status_code=404)
    content = js_path.read_bytes()
    etag = f'"{hashlib.sha256(content).hexdigest()[:16]}"'
    if request.headers.get("if-none-match") == etag:
        return _Response(status_code=304)
    return _Response(content=content, media_type="application/javascript; charset=utf-8",
                     headers={"ETag": etag, "Cache-Control": "public, max-age=3600"})


@router.get("/api/audit")
async def get_api_audit(
    limit: int = _Query(50), type: str = _Query(None), session_id: str = _Query(None),
    _u=_Depends(_auth),
):
    from salmalm.core import query_audit_log
    entries = query_audit_log(limit=limit, event_type=type, session_id=session_id)
    return _JSON({"entries": entries, "count": len(entries)})


@router.get("/api/logs")
async def get_api_logs(lines: int = _Query(100), level: str = _Query(""), _u=_Depends(_auth)):
    log_path = DATA_DIR / "salmalm.log"
    entries = []
    if log_path.exists():
        all_lines = log_path.read_text(encoding="utf-8", errors="replace").strip().split("\n")
        lvl = level.upper()
        for ln in all_lines[-lines:]:
            if lvl and f"[{lvl}]" not in ln:
                continue
            entries.append(ln)
    return _JSON({"logs": entries, "total": len(entries)})

