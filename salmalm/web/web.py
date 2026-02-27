"""SalmAlm Web UI — HTML + WebHandler."""

import warnings

warnings.filterwarnings("ignore", category=SyntaxWarning, module="web")
import http.server
import json
import os
import re
import sys
import time
from typing import Optional

from salmalm.constants import (  # noqa: F401
    APP_NAME,
    AUDIT_DB,
    BASE_DIR,
    DATA_DIR,
    MODELS,
    TEST_MODELS,
    VAULT_FILE,
    VERSION,
    WORKSPACE_DIR,
)
from salmalm.security.crypto import vault, log
from salmalm.web.auth import extract_auth
from salmalm.utils.logging_ext import request_logger, set_correlation_id
from salmalm.web import templates as _tmpl
from salmalm.web.routes.web_auth import WebAuthMixin
from salmalm.web.routes.web_chat import WebChatMixin
from salmalm.web.routes.web_cron import WebCronMixin
from salmalm.web.routes.web_engine import WebEngineMixin
from salmalm.web.routes.web_gateway import WebGatewayMixin
from salmalm.web.routes.web_model import WebModelMixin
from salmalm.web.routes.web_sessions import WebSessionsMixin
from salmalm.web.routes.web_setup import WebSetupMixin
from salmalm.web.routes.web_users import WebUsersMixin
from salmalm.web.routes.web_features import WebFeaturesMixin
from salmalm.web.routes.web_files import WebFilesMixin
from salmalm.web.routes.web_system import SystemMixin as WebSystemMixin
from salmalm.web.routes.web_manage import ManageMixin as WebManageMixin
from salmalm.web.routes.web_content import ContentMixin as WebContentMixin
from salmalm.web.routes.web_agents import AgentsMixin

# Google OAuth CSRF state tokens {state: timestamp}
_google_oauth_pending_states: dict = {}

# ============================================================


class WebHandler(
    WebAuthMixin,
    WebChatMixin,
    WebCronMixin,
    WebEngineMixin,
    WebGatewayMixin,
    WebModelMixin,
    WebSessionsMixin,
    WebSetupMixin,
    WebUsersMixin,
    WebFeaturesMixin,
    WebFilesMixin,
    WebSystemMixin,
    WebManageMixin,
    WebContentMixin,
    AgentsMixin,
    http.server.BaseHTTPRequestHandler,
):
    """HTTP handler for web UI and API."""

    def log_message(self, format: str, *args) -> None:
        """Suppress default HTTP stderr logging — requests logged via salmalm logger in each handler."""
        pass

    # Track last HTTP status code for metrics instrumentation
    _last_status: int = 200

    def send_response(self, code, message=None):
        """Override to capture status code for metrics."""
        self._last_status = code
        super().send_response(code, message)

    # Allowed origins for CORS (same-host only, dynamic port)
    @staticmethod
    def _build_allowed_origins():
        """Build allowed origins from configured port."""
        _port = int(os.environ.get("SALMALM_PORT", 18800))
        _ws_port = int(os.environ.get("SALMALM_WS_PORT", 18801))
        origins = set()
        for scheme in ("http", "https"):
            for host in ("127.0.0.1", "localhost"):
                origins.add(f"{scheme}://{host}:{_port}")
                origins.add(f"{scheme}://{host}:{_ws_port}")
        return origins

    _ALLOWED_ORIGINS = None  # lazily built

    def _cors(self):
        """Cors."""
        if self._ALLOWED_ORIGINS is None:
            WebHandler._ALLOWED_ORIGINS = WebHandler._build_allowed_origins()
        origin = self.headers.get("Origin", "")
        if origin in self._ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        # No Origin header (same-origin requests, curl, etc) → no CORS headers needed
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key, X-Requested-With")

    def _maybe_gzip(self, body: bytes) -> bytes:
        """Compress body if client accepts gzip and body is large enough."""
        if len(body) < 1024:
            return body
        ae = self.headers.get("Accept-Encoding", "")
        if "gzip" not in ae:
            return body
        import gzip as _gzip

        compressed = _gzip.compress(body, compresslevel=1)  # fast compression, minimal CPU
        if len(compressed) < len(body):
            self.send_header("Content-Encoding", "gzip")
            return compressed
        return body

    def _json(self, data: dict, status=200):
        """Json."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self._security_headers()
        body = self._maybe_gzip(body)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Per-request CSP nonce (generated fresh each time)
    _csp_nonce: str = ""

    def _html(self, content: str):
        """Html."""
        body_raw = content
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self._security_headers()
        # Inject CSP nonce into inline <script> tags (after _security_headers generates nonce)
        if self._csp_nonce and "<script>" in body_raw:
            body_raw = body_raw.replace("<script>", f'<script nonce="{self._csp_nonce}">')
        body = body_raw.encode("utf-8")
        body = self._maybe_gzip(body)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Public endpoints (no auth required)
    _PUBLIC_PATHS = {
        "/",
        "/index.html",
        "/api/status",
        "/api/health",
        "/api/unlock",
        "/api/auto-unlock",
        "/api/auth/login",
        "/api/users/register",
        "/api/onboarding",
        "/api/onboarding/preferences",
        "/api/setup",
        "/docs",
        "/api/google/callback",
        "/api/google/auth",
        "/webhook/telegram",
        "/webhook/slack",
        "/api/check-update",
    }

    def _require_auth(self, min_role: str = "user") -> Optional[dict]:
        """Check auth for protected endpoints. Returns user dict or sends 401 and returns None.
        If vault is locked, also rejects (403)."""
        path = self.path.split("?")[0]
        if path in self._PUBLIC_PATHS:
            return {
                "username": "public",
                "role": "public",
                "id": 0,
            }  # skip auth for public endpoints

        # Try token/api-key auth first
        user = extract_auth(dict(self.headers))
        if user:
            role_rank = {"admin": 3, "user": 2, "readonly": 1}
            if role_rank.get(user.get("role", ""), 0) >= role_rank.get(min_role, 2):
                return user
            self._json({"error": "Insufficient permissions"}, 403)
            return None

        # Fallback: if request is from loopback AND vault is unlocked, allow (single-user local mode)
        # Disabled when binding to 0.0.0.0 (external exposure) for safety
        ip = self._get_client_ip()
        bind = os.environ.get("SALMALM_BIND", "127.0.0.1")
        if bind in ("127.0.0.1", "localhost", "::1"):
            if ip in ("127.0.0.1", "::1", "localhost") and vault.is_unlocked:
                return {"username": "local", "role": "admin", "id": 0}

        self._json({"error": "Authentication required"}, 401)
        return None

    # Trusted proxy subnets — only accept X-Forwarded-For from these
    _TRUSTED_PROXY_NETS = (
        "127.",
        "::1",
        "10.",
        "172.16.",
        "172.17.",
        "172.18.",
        "172.19.",
        "172.2",
        "172.30.",
        "172.31.",
        "192.168.",
    )

    def _get_client_ip(self) -> str:
        """Get client IP. Only trusts X-Forwarded-For if:
        1. SALMALM_TRUST_PROXY is set, AND
        2. The actual socket peer is from a trusted proxy subnet (private/loopback).
        This prevents XFF spoofing from untrusted sources.
        """
        remote_addr = self.client_address[0] if self.client_address else "?"
        if os.environ.get("SALMALM_TRUST_PROXY"):
            # Only trust XFF if the direct connection is from a trusted proxy
            is_trusted = any(remote_addr.startswith(net) for net in self._TRUSTED_PROXY_NETS)
            if is_trusted:
                xff = self.headers.get("X-Forwarded-For")
                if xff:
                    return xff.split(",")[0].strip()
        return remote_addr

    def do_PUT(self) -> None:
        """Handle HTTP PUT requests."""
        _start = time.time()
        import uuid

        set_correlation_id(str(uuid.uuid4())[:8])
        if self.path.startswith("/api/") and not self._check_origin():
            return
        if self.path.startswith("/api/") and not self._check_rate_limit():
            return
        try:
            self._do_put_inner()
        except Exception as e:
            log.error(f"PUT {self.path} error: {e}")
            self._json({"error": "Internal server error"}, 500)
        finally:
            duration = (time.time() - _start) * 1000
            request_logger.log_request(
                "PUT",
                self.path.split("?")[0],
                ip=self._get_client_ip(),
                duration_ms=duration,
            )

    def _do_put_inner(self):
        """Do put inner."""
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        # PUT /api/sessions/{id}/title
        m = re.match(r"^/api/sessions/([^/]+)/title$", self.path)
        if m:
            if not self._require_auth("user"):
                return
            sid = m.group(1)
            title = body.get("title", "").strip()[:60]
            if not title:
                self._json({"ok": False, "error": "Missing title"}, 400)
                return
            from salmalm.core import _get_db

            conn = _get_db()
            conn.execute("UPDATE session_store SET title=? WHERE session_id=?", (title, sid))
            conn.commit()
            self._json({"ok": True})
            return
        self._json({"error": "Not found"}, 404)

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle HTTP GET requests."""
        _start = time.time()
        import uuid

        set_correlation_id(str(uuid.uuid4())[:8])

        if self.path.startswith("/api/") and not self._check_rate_limit():
            return

        try:
            self._do_get_inner()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            log.error(f"GET {self.path} error: {e}")
            try:
                self._json({"error": "Internal server error"}, 500)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
        finally:
            duration = (time.time() - _start) * 1000
            _clean = self.path.split("?")[0]
            request_logger.log_request(
                "GET",
                _clean,
                ip=self._get_client_ip(),
                duration_ms=duration,
            )
            try:
                from salmalm.monitoring.metrics import requests_total, request_duration
                requests_total.inc(method="GET", path=_clean, status=str(self._last_status))
                request_duration.observe(duration / 1000.0, method="GET")
            except Exception:
                pass

    # ── GET Route Table (exact path → method) ──
    _GET_ROUTES: dict = {}
    for _mixin_cls in [
        WebAuthMixin, WebChatMixin, WebCronMixin, WebEngineMixin, WebGatewayMixin, WebModelMixin, WebSessionsMixin, WebSetupMixin, WebUsersMixin, WebFeaturesMixin, WebFilesMixin, WebSystemMixin, WebManageMixin, WebContentMixin, AgentsMixin,
    ]:
        _GET_ROUTES.update(getattr(_mixin_cls, 'GET_ROUTES', {}))
    _GET_ROUTES.update({
        "/api/notifications": "_get_api_notifications",
        "/api/presence": "_get_api_presence",
        "/api/channels": "_get_api_channels",
        "/api/plugins": "_get_api_plugins",
        "/api/agents": "_get_api_agents",
        "/api/hooks": "_get_api_hooks",
        "/api/security/report": "_get_api_security_report",
        "/api/security/bans": "_get_api_security_bans",
        "/api/quota/usage": "_get_api_quota_usage",
        "/api/quota/my": "_get_api_quota_my",
        "/api/bookmarks": "_get_api_bookmarks",
        "/api/paste/detect": "_get_api_paste_detect",
        "/api/health": "_get_api_health",
        "/api/check-update": "_get_api_check_update",
        "/sw.js": "_get_sw_js",
        "/dashboard": "_get_dashboard",
        "/docs": "_get_docs",
    })


    def _get_api_notifications(self):
        """Get api notifications."""
        if not self._require_auth("user"):
            return
        from salmalm.core import _sessions

        web_session = _sessions.get("web")
        notifications = []
        if web_session and hasattr(web_session, "_notifications"):
            notifications = web_session._notifications
            web_session._notifications = []  # clear after read
        self._json({"notifications": notifications})

    def _get_api_presence(self):
        """Get api presence."""
        if not self._require_auth("user"):
            return
        from salmalm.features.presence import presence_manager

        self._json(
            {
                "clients": presence_manager.list_all(),
                "counts": presence_manager.count_by_state(),
                "total": presence_manager.count(),
            }
        )

    def _get_api_channels(self):
        """Get api channels."""
        if not self._require_auth("user"):
            return
        from salmalm.channels.channel_router import channel_router

        self._json(
            {
                "channels": channel_router.list_channels(),
            }
        )

    def _get_api_plugins(self):
        """Get api plugins."""
        if not self._require_auth("user"):
            return
        from salmalm.core import PluginLoader

        legacy_tools = PluginLoader.get_all_tools()
        legacy = [{"name": n, "tools": len(p["tools"]), "path": p["path"]} for n, p in PluginLoader._plugins.items()]
        from salmalm.features.plugin_manager import plugin_manager

        new_plugins = plugin_manager.list_plugins()
        self._json(
            {
                "plugins": legacy,
                "total_tools": len(legacy_tools),
                "directory_plugins": new_plugins,
                "directory_total_tools": len(plugin_manager.get_all_tools()),
            }
        )

    def _get_api_agents(self):
        """Get api agents."""
        if not self._require_auth("user"):
            return
        from salmalm.features.agents import agent_manager

        self._json(
            {
                "agents": agent_manager.list_agents(),
                "bindings": agent_manager.list_bindings(),
            }
        )

    def _get_api_hooks(self):
        """Get api hooks."""
        if not self._require_auth("user"):
            return
        from salmalm.features.hooks import hook_manager, VALID_EVENTS

        self._json(
            {
                "hooks": hook_manager.list_hooks(),
                "valid_events": list(VALID_EVENTS),
            }
        )

    def _get_api_security_report(self):
        """Get api security report."""
        if not self._require_auth("admin"):
            return
        from salmalm.security import security_auditor

        self._json(security_auditor.audit())

    def _get_api_security_bans(self):
        """List currently banned IPs. Admin only."""
        if not self._require_auth("admin"):
            return
        from salmalm.web.auth import ip_ban_list
        self._json({"bans": ip_ban_list.list_banned()})

    def _get_api_quota_usage(self):
        """Admin: view all users' daily token usage for today."""
        if not self._require_auth("admin"):
            return
        from salmalm.web.auth import daily_quota
        self._json({"date": daily_quota._today(), "usage": daily_quota.get_all_today()})

    def _get_api_quota_my(self):
        """User: view own daily token usage and limit."""
        if not self._require_auth("user"):
            return
        from salmalm.web.auth import daily_quota, extract_auth
        user = extract_auth({k.lower(): v for k, v in self.headers.items()})
        uid = str(user["id"]) if user else "anonymous"
        role = user.get("role", "anonymous") if user else "anonymous"
        used = daily_quota.get_usage(uid)
        limit = daily_quota.limit_for(role)
        self._json({
            "date": daily_quota._today(),
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used) if limit >= 0 else -1,
            "unlimited": limit < 0,
        })

    def _post_api_security_unban(self):
        """Manually lift an IP ban. Admin only.

        Body: {"ip": "1.2.3.4"}
        """
        if not self._require_auth("admin"):
            return
        import json as _json
        try:
            body = _json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
            ip = body.get("ip", "").strip()
        except Exception:
            self._json({"error": "Invalid JSON body"}, 400)
            return
        if not ip:
            self._json({"error": "Missing 'ip' field"}, 400)
            return
        from salmalm.web.auth import ip_ban_list
        ip_ban_list.unban(ip)
        self._json({"ok": True, "ip": ip, "message": f"IP {ip} unbanned"})

    def _get_api_bookmarks(self):
        # Message bookmarks — LobeChat style (메시지 북마크)
        """Get api bookmarks."""
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import bookmark_manager
        import urllib.parse

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        sid = params.get("session_id", [None])[0]
        if sid:
            self._json({"bookmarks": bookmark_manager.list_session(sid)})
        else:
            self._json({"bookmarks": bookmark_manager.list_all()})

    def _get_api_paste_detect(self):
        # Smart paste detection — BIG-AGI style (스마트 붙여넣기)
        # GET version reads from query param
        """Get api paste detect."""
        if not self._require_auth("user"):
            return
        import urllib.parse

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        text = params.get("text", [""])[0]
        if text:
            from salmalm.features.edge_cases import detect_paste_type

            self._json(detect_paste_type(text))
        else:
            self._json({"error": "Missing text parameter"}, 400)

    def _get_api_health(self):
        # K8s readiness/liveness probe compatible: 200=healthy, 503=unhealthy
        """Get api health."""
        from salmalm.core.health import get_health_report

        report = get_health_report()
        status_code = 200 if report.get("status") == "healthy" else 503
        self._json(report, status=status_code)

    def _get_api_check_update(self):
        """Get api check update."""
        try:
            import urllib.request

            resp = urllib.request.urlopen("https://pypi.org/pypi/salmalm/json", timeout=10)
            data = json.loads(resp.read().decode())
            latest = data.get("info", {}).get("version", VERSION)  # noqa: F405
            is_exe = getattr(sys, "frozen", False)
            result = {"current": VERSION, "latest": latest, "exe": is_exe}  # noqa: F405
            if is_exe:
                result["download_url"] = "https://github.com/hyunjun6928-netizen/salmalm/releases/latest"
            self._json(result)
        except Exception as e:
            self._json({"current": VERSION, "latest": None, "error": str(e)[:100]})  # noqa: F405

    def _get_sw_js(self):
        """Service worker — PWA offline cache + install support."""
        from salmalm.constants import VERSION

        sw_js = f"""const CACHE='salmalm-v{VERSION}';
const PRECACHE=['/','/static/app.js','/static/style.css','/manifest.json'];
self.addEventListener('install',e=>{{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(PRECACHE.map(u=>u.trim()))).then(()=>self.skipWaiting()))}});
self.addEventListener('activate',e=>{{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))}});
self.addEventListener('fetch',e=>{{
  if(e.request.method!=='GET')return;
  const u=new URL(e.request.url);
  if(u.pathname.startsWith('/api/')||u.pathname.startsWith('/ws'))return;
  e.respondWith(fetch(e.request).then(r=>{{
    if(r.ok){{const c=r.clone();caches.open(CACHE).then(ca=>ca.put(e.request,c))}}
    return r;
  }}).catch(()=>caches.match(e.request)))
}});"""
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/javascript")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.end_headers()
        self.wfile.write(sw_js.encode())

    def _get_dashboard(self):
        """Get dashboard."""
        if not self._require_auth("user"):
            return
        self._html(_tmpl.DASHBOARD_HTML)

    def _get_docs(self):
        """Get docs."""
        from salmalm.features.docs import generate_api_docs_html

        self._html(generate_api_docs_html())

    def _do_get_inner(self):
        # Route table dispatch for simple API endpoints
        """Do get inner."""
        _clean_path = self.path.split("?")[0]
        _handler_name = self._GET_ROUTES.get(_clean_path)
        if _handler_name:
            # Centralized auth gate: all /api/ routes require auth unless public
            if _clean_path.startswith("/api/") and _clean_path not in self._PUBLIC_PATHS:
                if not self._require_auth("user"):
                    return
            return getattr(self, _handler_name)()
        # Prefix-based route dispatch
        for _prefix, _method, _extra in self._GET_PREFIX_ROUTES:
            if self.path.startswith(_prefix):
                if _extra and _extra not in self.path:
                    continue
                if _clean_path.startswith("/api/") and _clean_path not in self._PUBLIC_PATHS:
                    if not self._require_auth("user"):
                        return
                return getattr(self, _method)()
        if self.path == "/" or self.path == "/index.html":
            if self._needs_first_run():
                self._html(_tmpl.SETUP_HTML)
                return
            self._auto_unlock_localhost()
            if not vault.is_unlocked:
                self._html(_tmpl.UNLOCK_HTML)
            elif self._needs_onboarding():
                self._html(_tmpl.ONBOARDING_HTML)
            else:
                self._html(_tmpl.WEB_HTML)

        elif self.path in ("/icon-192.svg", "/icon-512.svg"):
            size = 192 if "192" in self.path else 512
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">
<rect width="{size}" height="{size}" rx="{size // 6}" fill="#6366f1"/>
<text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-size="{size // 2}">😈</text>
</svg>'''
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "image/svg+xml")
            self.end_headers()
            self.wfile.write(svg.encode())

        else:
            self.send_error(404)

    def do_POST(self) -> None:
        """Handle HTTP POST requests."""
        _start = time.time()
        import uuid

        set_correlation_id(str(uuid.uuid4())[:8])

        # CSRF protection: block cross-origin POST requests
        if self.path.startswith("/api/") and not self._check_origin():
            return

        if self.path.startswith("/api/") and not self._check_rate_limit():
            return

        try:
            self._do_post_inner()
        except (BrokenPipeError, ConnectionResetError):
            pass  # Client disconnected — nothing to send
        except Exception as e:
            import traceback

            err_detail = traceback.format_exc()
            log.error(f"POST {self.path} error: {e}\n{err_detail}")
            try:
                self._json({"error": f"Internal error: {str(e)[:200]}"}, 500)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass  # Client already gone
        finally:
            duration = (time.time() - _start) * 1000
            _post_path = self.path.split("?")[0]
            request_logger.log_request("POST", _post_path, ip=self._get_client_ip(), duration_ms=duration)
            try:
                from salmalm.monitoring.metrics import requests_total, request_duration
                requests_total.inc(method="POST", path=_post_path, status=str(self._last_status))
                request_duration.observe(duration / 1000.0, method="POST")
            except Exception:
                pass

    # Max POST body size: 10MB
    _MAX_POST_SIZE = 10 * 1024 * 1024

    _POST_ROUTES: dict = {}
    for _mixin_cls in [
        WebAuthMixin, WebChatMixin, WebCronMixin, WebEngineMixin, WebGatewayMixin, WebModelMixin, WebSessionsMixin, WebSetupMixin, WebUsersMixin, WebFeaturesMixin, WebFilesMixin, WebSystemMixin, WebManageMixin, WebContentMixin, AgentsMixin,
    ]:
        _POST_ROUTES.update(getattr(_mixin_cls, 'POST_ROUTES', {}))
    _POST_ROUTES.update({
        "/api/security/unban": "_post_api_security_unban",
    })


    def _do_post_inner(self):
        """Do post inner."""
        from salmalm.core.engine import process_message  # noqa: F401

        length = int(self.headers.get("Content-Length", 0))

        # Request size limit: uploads get 50 MB, everything else 10 MB
        _upload_max = 50 * 1024 * 1024
        _effective_max = _upload_max if self.path == "/api/upload" else self._MAX_POST_SIZE
        if length > _effective_max:
            self._json(
                {"error": f"Request too large ({length} bytes). Max: {_effective_max} bytes."},
                413,
            )
            return

        # Don't parse multipart as JSON
        if self.path == "/api/upload":
            body = {}  # type: ignore[var-annotated]
        else:
            # Content-Type validation for JSON endpoints
            ct = self.headers.get("Content-Type", "")
            if length > 0 and self.path.startswith("/api/") and "json" not in ct and "form" not in ct:
                self._json({"error": "Expected Content-Type: application/json"}, 400)
                return
            try:
                body = json.loads(self.rfile.read(length)) if length else {}
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                self._json({"error": f"Invalid JSON body: {e}"}, 400)
                return

        # Store parsed body for route handlers
        self._body = body
        self._content_length = length

        # Route table dispatch for POST endpoints
        _clean_post_path = self.path.split("?")[0]
        _post_handler = self._POST_ROUTES.get(_clean_post_path)
        if _post_handler:
            # Centralized auth gate: all /api/ POST routes require auth unless public
            if _clean_post_path.startswith("/api/") and _clean_post_path not in self._PUBLIC_PATHS:
                if not self._require_auth("user"):
                    return
            return getattr(self, _post_handler)()

        # ── Remaining POST routes (dispatch table above handles most) ──────
        if self.path in ("/api/chat", "/api/chat/stream"):
            return self._post_api_chat()
        elif self.path in ("/api/llm-router/switch", "/api/model/switch"):
            return self._post_api_model_switch()
        elif self.path in ("/api/llm-router/test-key", "/api/test-provider"):
            return self._post_api_test_provider()
        elif self.path.startswith("/api/thoughts/search"):
            return self._post_api_thoughts_search()
        else:
            self._json({"error": "Not found"}, 404)

    _GET_PREFIX_ROUTES: list = []
    for _mixin_cls in [
        WebAuthMixin, WebChatMixin, WebCronMixin, WebEngineMixin, WebGatewayMixin, WebModelMixin, WebSessionsMixin, WebSetupMixin, WebUsersMixin, WebFeaturesMixin, WebFilesMixin, WebSystemMixin, WebManageMixin, WebContentMixin, AgentsMixin,
    ]:
        _GET_PREFIX_ROUTES.extend(getattr(_mixin_cls, 'GET_PREFIX_ROUTES', []))

