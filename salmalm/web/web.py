"""SalmAlm Web UI — HTML + WebHandler."""

import warnings

warnings.filterwarnings("ignore", category=SyntaxWarning, module="web")
import asyncio
import http.server
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
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
from salmalm.core import get_usage_report, router, audit_log
from salmalm.web.auth import auth_manager, rate_limiter, extract_auth, RateLimitExceeded
from salmalm.utils.logging_ext import request_logger, set_correlation_id
from salmalm.web import templates as _tmpl

# Google OAuth CSRF state tokens {state: timestamp}
_google_oauth_pending_states: dict = {}

# ============================================================


class WebHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for web UI and API."""

    def log_message(self, format, *args):
        """Suppress default HTTP request logging."""
        pass  # Suppress default logging

    # Allowed origins for CORS (same-host only)
    _ALLOWED_ORIGINS = {
        "http://127.0.0.1:18800",
        "http://localhost:18800",
        "http://127.0.0.1:18801",
        "http://localhost:18801",
        "https://127.0.0.1:18800",
        "https://localhost:18800",
    }

    def _cors(self):
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

    def _security_headers(self):
        """Add security headers to all responses.

        CSP defaults to nonce-based script-src (strict mode).
        Set SALMALM_CSP_COMPAT=1 to fall back to 'unsafe-inline' for compatibility.
        """
        self._csp_nonce = secrets.token_urlsafe(16)

        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
        # CSP: unsafe-inline by default (setup/unlock templates use inline scripts).
        # Set SALMALM_CSP_STRICT=1 to use nonce-based script-src instead.
        if os.environ.get("SALMALM_CSP_STRICT"):
            script_src = f"'self' 'nonce-{self._csp_nonce}'"
        else:
            script_src = "'self' 'unsafe-inline'"
        self.send_header(
            "Content-Security-Policy",
            f"default-src 'self'; "
            f"script-src {script_src}; "
            f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
            f"img-src 'self' data: blob:; "
            f"connect-src 'self' ws://127.0.0.1:* ws://localhost:* wss://127.0.0.1:* wss://localhost:*; "
            f"font-src 'self' data: https://fonts.gstatic.com; "
            f"object-src 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'",
        )

    def _html(self, content: str):
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
        "/api/auth/login",
        "/api/users/register",
        "/api/onboarding",
        "/api/onboarding/preferences",
        "/api/setup",
        "/docs",
        "/api/google/callback",
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

    def _check_rate_limit(self) -> bool:
        """Check rate limit. Returns True if OK, sends 429 if exceeded."""
        ip = self._get_client_ip()
        user = extract_auth(dict(self.headers))
        # Loopback admin bypass: only when server is bound to 127.0.0.1 (not 0.0.0.0)
        _bind = os.environ.get("SALMALM_BIND", "127.0.0.1")
        if (
            not user
            and ip in ("127.0.0.1", "::1", "localhost")
            and vault.is_unlocked
            and _bind in ("127.0.0.1", "::1", "localhost")
        ):
            user = {"username": "local", "role": "admin"}
        role = user.get("role", "anonymous") if user else "anonymous"
        key = user.get("username", ip) if user else ip
        try:
            rate_limiter.check(key, role)
            return True
        except RateLimitExceeded as e:
            self.send_response(429)
            self.send_header("Retry-After", str(int(e.retry_after)))
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Rate limit exceeded", "retry_after": e.retry_after}).encode())
            return False

    def do_PUT(self):
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

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS")
        self.end_headers()

    def do_GET(self):
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
            request_logger.log_request(
                "GET",
                self.path.split("?")[0],
                ip=self._get_client_ip(),
                duration_ms=duration,
            )

    def _needs_onboarding(self) -> bool:
        """Check if first-run onboarding is needed (no API keys or Ollama configured)."""
        if not vault.is_unlocked:
            return False
        providers = [
            "anthropic_api_key",
            "openai_api_key",
            "xai_api_key",
            "google_api_key",
        ]
        has_api_key = any(vault.get(k) for k in providers)
        has_ollama = bool(vault.get("ollama_url") or vault.get("ollama_api_key"))
        return not (has_api_key or has_ollama)

    def _auto_unlock_localhost(self):
        """Auto-unlock vault for localhost connections.

        Priority: OS keychain → env var (deprecated) → empty password → prompt.
        """
        if vault.is_unlocked:
            return True
        ip = self._get_client_ip()
        if ip not in ("127.0.0.1", "::1", "localhost"):
            return False
        # 1. Try OS keychain first (most secure)
        if vault.try_keychain_unlock():
            return True
        # 1b. Try .vault_auto file (WSL/no-keychain fallback)
        try:
            _pw_hint_file = VAULT_FILE.parent / ".vault_auto"  # noqa: F405
            if _pw_hint_file.exists():
                _hint = _pw_hint_file.read_text(encoding="utf-8").strip()
                if _hint:
                    import base64

                    _auto_pw = base64.b64decode(_hint).decode()
                else:
                    _auto_pw = ""
                if vault.unlock(_auto_pw, save_to_keychain=True):
                    return True
        except Exception:
            pass
        pw = os.environ.get("SALMALM_VAULT_PW", "")
        if pw:
            import warnings

            warnings.warn(
                "SALMALM_VAULT_PW env var is deprecated and will be removed in v0.20. "
                "Use OS keychain instead: vault password is auto-saved on first unlock.",
                FutureWarning,
                stacklevel=2,
            )
        if VAULT_FILE.exists():  # noqa: F405
            # Check if this is a no-crypto marker file
            try:
                marker = VAULT_FILE.read_bytes()  # noqa: F405
                if b"no_crypto" in marker:
                    vault._data = {}
                    vault._password = ""
                    vault._salt = b"\x00" * 16
                    return True
            except Exception:
                pass
            # 2. Try env password (deprecated), then empty password
            try:
                if pw and vault.unlock(pw, save_to_keychain=True):
                    return True
                if vault.unlock(""):
                    return True  # No-password vault
            except RuntimeError:
                log.warning("Vault unlock failed (cryptography not installed?)")
                return False
            if not pw:
                return False  # Has password but no env var — show unlock screen
            return False
        elif pw:
            try:
                vault.create(pw)
                return True
            except RuntimeError:
                log.warning("Vault create failed (cryptography not installed?)")
                return False
        # No vault file, no env var → first run, handled by _needs_first_run
        return True

    def _needs_first_run(self) -> bool:
        """True if vault file doesn't exist and no env password — brand new install."""
        return not VAULT_FILE.exists() and not os.environ.get("SALMALM_VAULT_PW", "")  # noqa: F405

    # ── Extracted GET handlers ────────────────────────────────

    def _get_uptime(self):
        from salmalm.features.sla import uptime_monitor

        self._json(uptime_monitor.get_stats())

    def _get_latency(self):
        from salmalm.features.sla import latency_tracker

        self._json(latency_tracker.get_stats())

    def _get_sla(self):
        from salmalm.features.sla import uptime_monitor, latency_tracker, watchdog, sla_config

        self._json(
            {
                "uptime": uptime_monitor.get_stats(),
                "latency": latency_tracker.get_stats(),
                "health": watchdog.get_last_report(),
                "config": sla_config.get_all(),
            }
        )

    def _get_sla_config(self):
        from salmalm.features.sla import sla_config

        self._json(sla_config.get_all())

    def _get_nodes(self):
        from salmalm.features.nodes import node_manager

        self._json({"nodes": node_manager.list_nodes()})

    def _get_gateway_nodes(self):
        from salmalm.features.nodes import gateway

        self._json({"nodes": gateway.list_nodes()})

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
        except Exception:
            pass
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
        except Exception:
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

    def _get_status(self):
        channels = {}
        if vault.is_unlocked:
            channels["telegram"] = bool(vault.get("telegram_token"))
            channels["discord"] = bool(vault.get("discord_token"))
        self._json(
            {
                "app": APP_NAME,
                "version": VERSION,  # noqa: F405
                "unlocked": vault.is_unlocked,
                "usage": get_usage_report(),
                "model": router.force_model or "auto",
                "channels": channels,
            }
        )

    def _get_metrics(self):
        from salmalm.core import _metrics

        usage = get_usage_report()
        _metrics["total_cost"] = usage.get("total_cost", 0.0)
        merged = {**request_logger.get_metrics(), **_metrics}
        self._json(merged)

    def _get_cert(self):
        from salmalm.utils.tls import get_cert_info

        self._json(get_cert_info())

    def _get_ws_status(self):
        from salmalm.web.ws import ws_server

        self._json(
            {
                "running": ws_server._running,
                "clients": ws_server.client_count,
                "port": ws_server.port,
            }
        )

    def _get_usage_daily(self):
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import usage_tracker

        self._json({"report": usage_tracker.daily_report()})

    def _get_usage_monthly(self):
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import usage_tracker

        self._json({"report": usage_tracker.monthly_report()})

    def _get_usage_models(self):
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import usage_tracker

        self._json({"breakdown": usage_tracker.model_breakdown()})

    def _get_groups(self):
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import session_groups

        self._json({"groups": session_groups.list_groups()})

    def _get_models(self):
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import model_detector

        force = "?force" in self.path
        models = model_detector.detect_all(force=force)
        self._json({"models": models, "count": len(models)})

    def _get_llm_router_providers(self):
        if not self._require_auth("user"):
            return
        from salmalm.core.llm_router import (
            PROVIDERS,
            is_provider_available,
            list_available_models,
            llm_router,
        )

        providers = []
        for name, cfg in PROVIDERS.items():
            if name == "ollama":
                # Fetch real models from local endpoint instead of hardcoded list
                try:
                    from salmalm.features.model_detect import model_detector

                    detected = model_detector.detect_all(force=True)
                    local_models = [
                        {"name": m["name"], "full": m["id"]} for m in detected if m.get("provider") == "ollama"
                    ]
                except Exception:
                    local_models = [{"name": m, "full": f"ollama/{m}"} for m in cfg["models"]]
                providers.append(
                    {
                        "name": name,
                        "available": is_provider_available(name) or bool(local_models),
                        "env_key": "",
                        "models": local_models or [{"name": m, "full": f"ollama/{m}"} for m in cfg["models"]],
                    }
                )
            else:
                providers.append(
                    {
                        "name": name,
                        "available": is_provider_available(name),
                        "env_key": cfg.get("env_key", ""),
                        "models": [{"name": m, "full": f"{name}/{m}"} for m in cfg["models"]],
                    }
                )
        # Check session-level override (more accurate than global router state)
        _cur = llm_router.current_model
        try:
            _sid = self.headers.get("X-Session-Id") or "web"
            from salmalm.core import get_session as _gs_prov

            _s = _gs_prov(_sid)
            _override = getattr(_s, "model_override", None)
            if _override is not None and _override != "auto":
                _cur = _override
            elif _override == "auto":
                _cur = "auto"
        except Exception:
            pass
        self._json(
            {
                "providers": providers,
                "current_model": _cur,
                "all_models": list_available_models(),
            }
        )

    def _get_llm_router_current(self):
        if not self._require_auth("user"):
            return
        from salmalm.core.llm_router import llm_router

        self._json({"current_model": llm_router.current_model})

    def _get_api_onboarding(self):
        """GET /api/onboarding — return onboarding status."""
        needs = self._needs_onboarding() if vault.is_unlocked else False
        self._json({"needs_onboarding": needs, "vault_unlocked": vault.is_unlocked})

    def _get_soul(self):
        if not self._require_auth("user"):
            return
        from salmalm.core.prompt import get_user_soul, USER_SOUL_FILE

        self._json({"content": get_user_soul(), "path": str(USER_SOUL_FILE)})

    def _get_routing(self):
        if not self._require_auth("user"):
            return
        from salmalm.core.engine import get_routing_config

        config = get_routing_config()
        # Validate: strip models whose provider has no key
        _provider_key_map = {
            "anthropic": "anthropic_api_key",
            "openai": "openai_api_key",
            "xai": "xai_api_key",
            "google": "google_api_key",
            "openrouter": "openrouter_api_key",
        }
        for tier in ("simple", "moderate", "complex"):
            model = config.get(tier, "")
            if not model or model == "auto":
                continue
            provider = model.split("/")[0] if "/" in model else ""
            key_name = _provider_key_map.get(provider)
            if key_name and not vault.get(key_name):
                config[tier] = ""  # Reset to auto default
        self._json({"config": config, "available_models": MODELS})

    def _get_failover(self):
        if not self._require_auth("user"):
            return
        from salmalm.core.engine import get_failover_config, _load_cooldowns

        self._json({"config": get_failover_config(), "cooldowns": _load_cooldowns()})

    def _get_memory_files(self):
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

    def _get_cron(self):
        if not self._require_auth("user"):
            return
        from salmalm.core import _llm_cron

        self._json({"jobs": _llm_cron.list_jobs() if _llm_cron else []})

    def _get_mcp(self):
        if not self._require_auth("user"):
            return
        from salmalm.features.mcp import mcp_manager

        servers = mcp_manager.list_servers()
        all_tools = mcp_manager.get_all_tools()
        self._json({"servers": servers, "total_tools": len(all_tools)})

    def _get_rag(self):
        if not self._require_auth("user"):
            return
        from salmalm.features.rag import rag_engine

        self._json(rag_engine.get_stats())

    def _get_personas(self):
        from salmalm.core.prompt import list_personas, get_active_persona

        session_id = self.headers.get("X-Session-Id", "web")
        personas = list_personas()
        active = get_active_persona(session_id)
        self._json({"personas": personas, "active": active})

    def _get_thoughts(self):
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
        from salmalm.features.thoughts import thought_stream

        self._json(thought_stream.stats())

    def _get_features(self):
        cats = [
            {
                "id": "core",
                "icon": "🤖",
                "title": "Core AI",
                "title_kr": "핵심 AI",
                "features": [
                    {
                        "name": "Multi-model Routing",
                        "name_kr": "멀티 모델 라우팅",
                        "desc": "Auto-routes to haiku/sonnet/opus based on complexity",
                        "desc_kr": "복잡도에 따라 haiku/sonnet/opus 자동 선택",
                        "command": "/model",
                    },
                    {
                        "name": "Extended Thinking",
                        "name_kr": "확장 사고",
                        "desc": "Deep reasoning for complex tasks",
                        "desc_kr": "복잡한 작업을 위한 심층 추론",
                        "command": "/thinking on",
                    },
                    {
                        "name": "Context Compaction",
                        "name_kr": "컨텍스트 압축",
                        "desc": "Auto-summarize long sessions",
                        "desc_kr": "긴 세션 자동 요약",
                        "command": "/compact",
                    },
                    {
                        "name": "Prompt Caching",
                        "name_kr": "프롬프트 캐싱",
                        "desc": "Anthropic cache for cost savings",
                        "desc_kr": "Anthropic 캐시로 비용 절감",
                        "command": "/context",
                    },
                    {
                        "name": "Self-Evolving Prompt",
                        "name_kr": "자가 진화 프롬프트",
                        "desc": "AI learns your preferences over time",
                        "desc_kr": "대화할수록 선호도 자동 학습",
                        "command": "/evolve status",
                    },
                    {
                        "name": "Mood-Aware Response",
                        "name_kr": "기분 감지 응답",
                        "desc": "Adjusts tone based on your emotion",
                        "desc_kr": "감정에 따라 톤 자동 조절",
                        "command": "/mood on",
                    },
                    {
                        "name": "A/B Split Response",
                        "name_kr": "A/B 분할 응답",
                        "desc": "Two perspectives on one question",
                        "desc_kr": "하나의 질문에 두 관점 동시 응답",
                        "command": "/split",
                    },
                ],
            },
            {
                "id": "tools",
                "icon": "🔧",
                "title": "Tools",
                "title_kr": "도구",
                "features": [
                    {
                        "name": "Web Search",
                        "name_kr": "웹 검색",
                        "desc": "Search the internet",
                        "desc_kr": "인터넷 검색",
                    },
                    {
                        "name": "Code Execution",
                        "name_kr": "코드 실행",
                        "desc": "Run code with sandbox protection",
                        "desc_kr": "샌드박스 보호 하에 코드 실행",
                        "command": "/bash",
                    },
                    {
                        "name": "File Operations",
                        "name_kr": "파일 작업",
                        "desc": "Read, write, edit files",
                        "desc_kr": "파일 읽기/쓰기/편집",
                    },
                    {
                        "name": "Browser Automation",
                        "name_kr": "브라우저 자동화",
                        "desc": "Control Chrome via CDP",
                        "desc_kr": "Chrome DevTools Protocol 제어",
                        "command": "/screen",
                    },
                    {
                        "name": "Image Vision",
                        "name_kr": "이미지 분석",
                        "desc": "Analyze images with AI",
                        "desc_kr": "AI로 이미지 분석",
                    },
                    {
                        "name": "TTS / STT",
                        "name_kr": "음성 입출력",
                        "desc": "Text-to-speech and speech-to-text",
                        "desc_kr": "텍스트↔음성 변환",
                    },
                    {
                        "name": "PDF Extraction",
                        "name_kr": "PDF 추출",
                        "desc": "Extract text from PDFs",
                        "desc_kr": "PDF에서 텍스트 추출",
                    },
                ],
            },
            {
                "id": "personal",
                "icon": "👤",
                "title": "Personal Assistant",
                "title_kr": "개인 비서",
                "features": [
                    {
                        "name": "Daily Briefing",
                        "name_kr": "데일리 브리핑",
                        "desc": "Morning/evening digest",
                        "desc_kr": "아침/저녁 종합 브리핑",
                        "command": "/life",
                    },
                    {
                        "name": "Smart Reminders",
                        "name_kr": "스마트 리마인더",
                        "desc": "Natural language time parsing",
                        "desc_kr": "자연어 시간 파싱",
                    },
                    {
                        "name": "Expense Tracker",
                        "name_kr": "가계부",
                        "desc": "Track spending by category",
                        "desc_kr": "카테고리별 지출 추적",
                    },
                    {
                        "name": "Pomodoro Timer",
                        "name_kr": "포모도로 타이머",
                        "desc": "25min focus sessions",
                        "desc_kr": "25분 집중 세션",
                    },
                    {
                        "name": "Notes & Links",
                        "name_kr": "메모 & 링크",
                        "desc": "Save and search notes/links",
                        "desc_kr": "메모와 링크 저장/검색",
                    },
                    {
                        "name": "Routines",
                        "name_kr": "루틴",
                        "desc": "Daily habit tracking",
                        "desc_kr": "일일 습관 추적",
                    },
                    {
                        "name": "Google Calendar",
                        "name_kr": "구글 캘린더",
                        "desc": "View, add, delete events",
                        "desc_kr": "일정 보기/추가/삭제",
                    },
                    {
                        "name": "Gmail",
                        "name_kr": "지메일",
                        "desc": "Read, send, search emails",
                        "desc_kr": "이메일 읽기/보내기/검색",
                    },
                    {
                        "name": "Life Dashboard",
                        "name_kr": "인생 대시보드",
                        "desc": "All-in-one life overview",
                        "desc_kr": "원페이지 인생 현황판",
                        "command": "/life",
                    },
                ],
            },
            {
                "id": "unique",
                "icon": "✨",
                "title": "Unique Features",
                "title_kr": "독자 기능",
                "features": [
                    {
                        "name": "Thought Stream",
                        "name_kr": "생각 스트림",
                        "desc": "Quick thought timeline with tags",
                        "desc_kr": "해시태그 기반 생각 타임라인",
                        "command": "/think",
                    },
                    {
                        "name": "Time Capsule",
                        "name_kr": "타임캡슐",
                        "desc": "Messages to your future self",
                        "desc_kr": "미래의 나에게 보내는 메시지",
                        "command": "/capsule",
                    },
                    {
                        "name": "Dead Man's Switch",
                        "name_kr": "데드맨 스위치",
                        "desc": "Emergency actions on inactivity",
                        "desc_kr": "비활동 시 긴급 조치",
                        "command": "/deadman",
                    },
                    {
                        "name": "Shadow Mode",
                        "name_kr": "분신술",
                        "desc": "AI replies in your style when away",
                        "desc_kr": "부재 시 내 말투로 대리 응답",
                        "command": "/shadow on",
                    },
                    {
                        "name": "Encrypted Vault",
                        "name_kr": "비밀 금고",
                        "desc": "Double-encrypted private chat",
                        "desc_kr": "이중 암호화 비밀 대화",
                        "command": "/vault open",
                    },
                    {
                        "name": "Agent-to-Agent",
                        "name_kr": "AI간 통신",
                        "desc": "Negotiate with other SalmAlm instances",
                        "desc_kr": "다른 SalmAlm과 자동 협상",
                        "command": "/a2a",
                    },
                ],
            },
            {
                "id": "infra",
                "icon": "⚙️",
                "title": "Infrastructure",
                "title_kr": "인프라",
                "features": [
                    {
                        "name": "Workflow Engine",
                        "name_kr": "워크플로우 엔진",
                        "desc": "Multi-step automation pipelines",
                        "desc_kr": "다단계 자동화 파이프라인",
                        "command": "/workflow",
                    },
                    {
                        "name": "MCP Marketplace",
                        "name_kr": "MCP 마켓",
                        "desc": "One-click MCP server install",
                        "desc_kr": "MCP 서버 원클릭 설치",
                        "command": "/mcp catalog",
                    },
                    {
                        "name": "Plugin System",
                        "name_kr": "플러그인",
                        "desc": "Extend with custom plugins",
                        "desc_kr": "커스텀 플러그인으로 확장",
                    },
                    {
                        "name": "Multi-Agent",
                        "name_kr": "다중 에이전트",
                        "desc": "Isolated sub-agents for parallel work",
                        "desc_kr": "병렬 작업용 격리 서브에이전트",
                        "command": "/subagents",
                    },
                    {
                        "name": "Sandboxing",
                        "name_kr": "샌드박싱",
                        "desc": "Docker/subprocess isolation",
                        "desc_kr": "Docker/subprocess 격리 실행",
                    },
                    {
                        "name": "OAuth Auth",
                        "name_kr": "OAuth 인증",
                        "desc": "Anthropic/OpenAI subscription auth",
                        "desc_kr": "API 키 없이 구독 인증",
                        "command": "/oauth",
                    },
                    {
                        "name": "Prompt Caching",
                        "name_kr": "프롬프트 캐싱",
                        "desc": "Reduce API costs with caching",
                        "desc_kr": "캐싱으로 API 비용 절감",
                        "command": "/context",
                    },
                ],
            },
            {
                "id": "channels",
                "icon": "📱",
                "title": "Channels",
                "title_kr": "채널",
                "features": [
                    {
                        "name": "Web UI",
                        "name_kr": "웹 UI",
                        "desc": "Full-featured web interface",
                        "desc_kr": "풀기능 웹 인터페이스",
                    },
                    {
                        "name": "Telegram",
                        "name_kr": "텔레그램",
                        "desc": "Bot with topics, reactions, groups",
                        "desc_kr": "토픽/반응/그룹 지원 봇",
                    },
                    {
                        "name": "Discord",
                        "name_kr": "디스코드",
                        "desc": "Bot with threads and reactions",
                        "desc_kr": "스레드/반응 지원 봇",
                    },
                    {
                        "name": "Slack",
                        "name_kr": "슬랙",
                        "desc": "Event API + Web API",
                        "desc_kr": "Event API + Web API",
                    },
                    {
                        "name": "PWA",
                        "name_kr": "PWA",
                        "desc": "Install as desktop/mobile app",
                        "desc_kr": "데스크톱/모바일 앱 설치",
                    },
                ],
            },
            {
                "id": "commands",
                "icon": "⌨️",
                "title": "Commands",
                "title_kr": "명령어",
                "features": [
                    {"name": "/help", "desc": "Show help", "desc_kr": "도움말"},
                    {
                        "name": "/status",
                        "desc": "Session status",
                        "desc_kr": "세션 상태",
                    },
                    {"name": "/model", "desc": "Switch model", "desc_kr": "모델 전환"},
                    {
                        "name": "/compact",
                        "desc": "Compress context",
                        "desc_kr": "컨텍스트 압축",
                    },
                    {
                        "name": "/context",
                        "desc": "Token breakdown",
                        "desc_kr": "토큰 분석",
                    },
                    {
                        "name": "/usage",
                        "desc": "Token/cost tracking",
                        "desc_kr": "토큰/비용 추적",
                    },
                    {
                        "name": "/think",
                        "desc": "Record a thought / set thinking level",
                        "desc_kr": "생각 기록 / 사고 레벨",
                    },
                    {
                        "name": "/persona",
                        "desc": "Switch persona",
                        "desc_kr": "페르소나 전환",
                    },
                    {
                        "name": "/branch",
                        "desc": "Branch conversation",
                        "desc_kr": "대화 분기",
                    },
                    {
                        "name": "/rollback",
                        "desc": "Rollback messages",
                        "desc_kr": "메시지 롤백",
                    },
                ],
            },
        ]
        self._json({"categories": cats})

    def _get_tools_list(self):
        tools = []
        try:
            from salmalm.tools.tool_registry import _HANDLERS, _ensure_modules

            _ensure_modules()
            for name in sorted(_HANDLERS.keys()):
                tools.append({"name": name, "description": ""})
        except Exception:
            pass
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
            except Exception:
                tools = [
                    {"name": "web_search", "description": "Search the web"},
                    {"name": "bash", "description": "Execute shell commands"},
                    {"name": "file_read", "description": "Read files"},
                    {"name": "file_write", "description": "Write files"},
                    {"name": "browser", "description": "Browser automation"},
                ]
        self._json({"tools": tools, "count": len(tools)})

    def _get_commands(self):
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

    # ── GET Route Table (exact path → method) ──
    _GET_ROUTES = {
        "/api/uptime": "_get_uptime",
        "/api/latency": "_get_latency",
        "/api/sla": "_get_sla",
        "/api/sla/config": "_get_sla_config",
        "/api/nodes": "_get_nodes",
        "/api/gateway/nodes": "_get_gateway_nodes",
        "/api/status": "_get_status",
        "/api/debug": "_get_debug",
        "/api/queue": "_get_queue",
        "/api/metrics": "_get_metrics",
        "/api/cert": "_get_cert",
        "/api/ws/status": "_get_ws_status",
        "/api/usage/daily": "_get_usage_daily",
        "/api/usage/monthly": "_get_usage_monthly",
        "/api/usage/models": "_get_usage_models",
        "/api/groups": "_get_groups",
        "/api/models": "_get_models",
        "/api/llm-router/providers": "_get_llm_router_providers",
        "/api/llm-router/current": "_get_llm_router_current",
        "/api/soul": "_get_soul",
        "/api/onboarding": "_get_api_onboarding",
        "/api/routing": "_get_routing",
        "/api/failover": "_get_failover",
        "/api/cron": "_get_cron",
        "/api/memory/files": "_get_memory_files",
        "/api/mcp": "_get_mcp",
        "/api/rag": "_get_rag",
        "/api/personas": "_get_personas",
        "/api/thoughts": "_get_thoughts",
        "/api/thoughts/stats": "_get_thoughts_stats",
        "/api/features": "_get_features",
        "/api/engine/settings": "_get_api_engine_settings",
        "/api/tools/list": "_get_tools_list",
        "/api/commands": "_get_commands",
        "/setup": "_get_setup",
        "/api/sessions": "_get_api_sessions",
        "/api/notifications": "_get_api_notifications",
        "/api/presence": "_get_api_presence",
        "/api/channels": "_get_api_channels",
        "/api/dashboard": "_get_api_dashboard",
        "/api/plugins": "_get_api_plugins",
        "/api/agents": "_get_api_agents",
        "/api/hooks": "_get_api_hooks",
        "/api/security/report": "_get_api_security_report",
        "/api/health/providers": "_get_api_health_providers",
        "/api/bookmarks": "_get_api_bookmarks",
        "/api/paste/detect": "_get_api_paste_detect",
        "/api/health": "_get_api_health",
        "/api/check-update": "_get_api_check_update",
        "/api/update/check": "_get_api_update_check",
        "/api/auth/users": "_get_api_auth_users",
        "/api/users": "_get_api_users",
        "/api/users/quota": "_get_api_users_quota",
        "/api/users/settings": "_get_api_users_settings",
        "/api/tenant/config": "_get_api_tenant_config",
        "/api/google/auth": "_get_api_google_auth",
        "/manifest.json": "_get_manifest_json",
        "/sw.js": "_get_sw_js",
        "/static/app.js": "_get_static_app_js",
        "/dashboard": "_get_dashboard",
        "/docs": "_get_docs",
    }

    def _get_setup(self):
        # Allow re-running the setup wizard anytime
        self._html(_tmpl.ONBOARDING_HTML)

    def _get_api_sessions(self):
        _auth_user = self._require_auth("user")
        if not _auth_user:
            return
        from salmalm.core import _get_db

        conn = _get_db()
        # User-scoped session list (user_id=0 or NULL = legacy/local = show all)
        _uid = _auth_user.get("id", 0)
        if _uid and _uid > 0:
            rows = conn.execute(
                "SELECT session_id, updated_at, title, parent_session_id FROM session_store "
                "WHERE user_id=? OR user_id IS NULL ORDER BY updated_at DESC",
                (_uid,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT session_id, updated_at, title, parent_session_id FROM session_store ORDER BY updated_at DESC"
            ).fetchall()
        sessions = []
        for r in rows:
            sid = r[0]
            stored_title = r[2] if len(r) > 2 else ""
            parent_sid = r[3] if len(r) > 3 else None
            if stored_title:
                title = stored_title
                msg_count = 0
            else:
                try:
                    msgs = json.loads(
                        conn.execute(
                            "SELECT messages FROM session_store WHERE session_id=?",
                            (sid,),
                        ).fetchone()[0]
                    )
                    title = ""
                    for m in msgs:
                        if m.get("role") == "user" and isinstance(m.get("content"), str):
                            title = m["content"][:60]
                            break
                    msg_count = len([m for m in msgs if m.get("role") in ("user", "assistant")])
                except Exception:
                    title = sid
                    msg_count = 0
            entry = {
                "id": sid,
                "title": title or sid,
                "updated_at": r[1],
                "messages": msg_count,
            }
            if parent_sid:
                entry["parent_session_id"] = parent_sid
            sessions.append(entry)
        self._json({"sessions": sessions})

    def _get_api_notifications(self):
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
        if not self._require_auth("user"):
            return
        from salmalm.channels.channel_router import channel_router

        self._json(
            {
                "channels": channel_router.list_channels(),
            }
        )

    def _get_api_dashboard(self):
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
        except Exception:
            pass
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

    def _get_api_plugins(self):
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
        if not self._require_auth("admin"):
            return
        from salmalm.security import security_auditor

        self._json(security_auditor.audit())

    def _get_api_health_providers(self):
        # Provider health check — Open WebUI style (프로바이더 상태 확인)
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import provider_health

        force = "?force" in self.path or "force=1" in self.path
        self._json(provider_health.check_all(force=force))

    def _get_api_bookmarks(self):
        # Message bookmarks — LobeChat style (메시지 북마크)
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
        from salmalm.core.health import get_health_report

        report = get_health_report()
        status_code = 200 if report.get("status") == "healthy" else 503
        self._json(report, status=status_code)

    def _get_api_check_update(self):
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

    def _get_api_update_check(self):
        # Alias for /api/check-update
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

    def _get_api_auth_users(self):
        user = extract_auth(dict(self.headers))
        if not user or user.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
        else:
            self._json({"users": auth_manager.list_users()})

    def _get_api_users(self):
        # Admin: full user list with stats (멀티테넌트 사용자 관리)
        user = extract_auth(dict(self.headers))
        if not user:
            ip = self._get_client_ip()
            if ip in ("127.0.0.1", "::1", "localhost") and vault.is_unlocked:
                user = {"username": "local", "role": "admin", "id": 0}
        if not user or user.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
        else:
            from salmalm.features.users import user_manager

            self._json(
                {
                    "users": user_manager.get_all_users_with_stats(),
                    "multi_tenant": user_manager.multi_tenant_enabled,
                    "registration_mode": user_manager.get_registration_mode(),
                }
            )

    def _get_api_users_quota(self):
        # Get own quota (사용량 확인)
        user = extract_auth(dict(self.headers))
        if not user:
            self._json({"error": "Authentication required"}, 401)
        else:
            from salmalm.features.users import user_manager

            uid = user.get("uid") or user.get("id", 0)
            quota = user_manager.get_quota(uid)
            self._json({"quota": quota})

    def _get_api_users_settings(self):
        # Get own settings
        user = extract_auth(dict(self.headers))
        if not user:
            self._json({"error": "Authentication required"}, 401)
        else:
            from salmalm.features.users import user_manager

            uid = user.get("uid") or user.get("id", 0)
            settings = user_manager.get_user_settings(uid)
            self._json({"settings": settings})

    def _get_api_tenant_config(self):
        # Admin: get multi-tenant config
        user = extract_auth(dict(self.headers))
        if not user or user.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
        else:
            from salmalm.features.users import user_manager

            self._json(
                {
                    "multi_tenant": user_manager.multi_tenant_enabled,
                    "registration_mode": user_manager.get_registration_mode(),
                    "telegram_allowlist": user_manager.get_telegram_allowlist_mode(),
                }
            )

    def _get_api_google_auth(self):
        if not self._require_auth("user"):
            return
        client_id = vault.get("google_client_id") or ""
        if not client_id:
            self._json(
                {"error": "Set google_client_id in vault first (Settings > Vault)"},
                400,
            )
            return
        import urllib.parse

        port = self.server.server_address[1]
        redirect_uri = f"http://localhost:{port}/api/google/callback"
        # CSRF protection: generate and store state token
        state = secrets.token_urlsafe(32)
        _google_oauth_pending_states[state] = time.time()
        params = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/calendar",
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
        )
        url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def _get_manifest_json(self):
        manifest = {
            "name": "SalmAlm — Personal AI Gateway",
            "short_name": "SalmAlm",
            "description": "Your personal AI gateway. 43 tools, 6 providers, zero dependencies.",
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

    def _get_sw_js(self):
        # Return self-uninstalling SW — clears old caches and unregisters itself
        sw_js = """self.addEventListener("install",()=>self.skipWaiting());
self.addEventListener("activate",e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.map(k=>caches.delete(k)))).then(()=>self.registration.unregister()))});"""
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/javascript")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.end_headers()
        self.wfile.write(sw_js.encode())

    def _get_static_app_js(self):
        """Serve extracted main application JavaScript."""
        js_path = Path(__file__).parent.parent / "static" / "app.js"
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

    def _get_dashboard(self):
        if not self._require_auth("user"):
            return
        self._html(_tmpl.DASHBOARD_HTML)

    def _get_docs(self):
        from salmalm.features.docs import generate_api_docs_html

        self._html(generate_api_docs_html())

    def _do_get_inner(self):
        # Route table dispatch for simple API endpoints
        _clean_path = self.path.split("?")[0]
        _handler_name = self._GET_ROUTES.get(_clean_path)
        if _handler_name:
            # Centralized auth gate: all /api/ routes require auth unless public
            if _clean_path.startswith("/api/") and _clean_path not in self._PUBLIC_PATHS:
                if not self._require_auth("user"):
                    return
            return getattr(self, _handler_name)()
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

        elif self.path.startswith("/api/search"):
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

        elif self.path.startswith("/api/sessions/") and "/export" in self.path:
            if not self._require_auth("user"):
                return
            import urllib.parse

            m = re.match(r"^/api/sessions/([^/]+)/export", self.path)
            if not m:
                self._json({"error": "Invalid path"}, 400)
                return
            sid = m.group(1)
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            fmt = params.get("format", ["json"])[0]
            from salmalm.core import _get_db

            conn = _get_db()
            row = conn.execute(
                "SELECT messages, updated_at FROM session_store WHERE session_id=?",
                (sid,),
            ).fetchone()
            if not row:
                self._json({"error": "Session not found"}, 404)
                return
            msgs = json.loads(row[0])
            updated_at = row[1]
            if fmt == "md":
                lines = [
                    "# SalmAlm Chat Export",
                    "Session: {sid}",
                    "Date: {updated_at}",
                    "",
                ]
                for msg in msgs:
                    role = msg.get("role", "")
                    if role == "system":
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(
                            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
                        )
                    icon = "## 👤 User" if role == "user" else "## 😈 Assistant"
                    lines.append(icon)
                    lines.append(str(content))
                    lines.append("")
                    lines.append("---")
                    lines.append("")
                body = "\n".join(lines).encode("utf-8")
                fname = f"salmalm_{sid}_{updated_at[:10]}.md"
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                self.wfile.write(body)
            else:
                export_data = {
                    "session_id": sid,
                    "updated_at": updated_at,
                    "messages": msgs,
                }
                body = json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8")
                fname = f"salmalm_{sid}_{updated_at[:10]}.json"
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                self.wfile.write(body)
            return

        elif self.path.startswith("/api/rag/search"):
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
        elif self.path.startswith("/api/audit"):
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

        elif self.path.startswith("/api/sessions/") and "/summary" in self.path:
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
        elif self.path.startswith("/api/sessions/") and "/alternatives" in self.path:
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

        elif self.path.startswith("/api/logs"):
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

        elif self.path.startswith("/api/memory/read?"):
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

        elif self.path.startswith("/api/google/callback"):
            import urllib.parse

            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [""])[0]
            state = params.get("state", [""])[0]
            error = params.get("error", [""])[0]
            # CSRF: validate state token
            if not state or state not in _google_oauth_pending_states:
                self._html(
                    '<html><body><h2>Invalid OAuth State</h2>'
                    "<p>CSRF protection: state token missing or invalid.</p>"
                    '<p><a href="/">Back</a></p></body></html>'
                )
                return
            issued_at = _google_oauth_pending_states.pop(state)
            # Expire states older than 10 minutes
            if time.time() - issued_at > 600:
                self._html(
                    '<html><body><h2>OAuth State Expired</h2>'
                    '<p>Please try again.</p><p><a href="/">Back</a></p></body></html>'
                )
                return
            # Cleanup stale states (older than 15 min)
            cutoff = time.time() - 900
            stale = [k for k, v in _google_oauth_pending_states.items() if v < cutoff]
            for k in stale:
                _google_oauth_pending_states.pop(k, None)
            if error:
                self._html(
                    f'<html><body><h2>Google OAuth Error</h2><p>{error}</p><p><a href="/">Back</a></p></body></html>'
                )
                return
            if not code:
                self._html('<html><body><h2>No code received</h2><p><a href="/">Back</a></p></body></html>')
                return
            client_id = vault.get("google_client_id") or ""
            client_secret = vault.get("google_client_secret") or ""
            port = self.server.server_address[1]
            redirect_uri = f"http://localhost:{port}/api/google/callback"
            try:
                data = json.dumps(
                    {
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    }
                ).encode()
                req = urllib.request.Request(
                    "https://oauth2.googleapis.com/token",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read())
                access_token = result.get("access_token", "")
                refresh_token = result.get("refresh_token", "")
                if refresh_token:
                    vault.set("google_refresh_token", refresh_token)
                if access_token:
                    vault.set("google_access_token", access_token)
                scopes = result.get("scope", "")
                self._html(f"""<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;text-align:center">
                    <h2 style="color:#22c55e">\\u2705 Google Connected!</h2>
                    <p>Refresh token saved to vault.</p>
                    <p style="font-size:0.85em;color:#666">Scopes: {scopes}</p>
                    <p><a href="/" style="color:#6366f1">\\u2190 Back to SalmAlm</a></p>
                    </body></html>""")
                log.info(f"[OK] Google OAuth2 connected (scopes: {scopes})")
            except Exception as e:
                log.error(f"Google OAuth2 token exchange failed: {e}")
                self._html(f"""<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;text-align:center">
                    <h2 style="color:#ef4444">\\u274c Token Exchange Failed</h2>
                    <p>{str(e)[:200]}</p>
                    <p><a href="/" style="color:#6366f1">\\u2190 Back</a></p>
                    </body></html>""")
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

        elif self.path.startswith("/api/agent/export"):
            # Vault export requires admin role
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            inc_vault = qs.get("vault", ["0"])[0] == "1"
            _min_role = "admin" if inc_vault else "user"
            _export_user = self._require_auth(_min_role)
            if not _export_user:
                return
            inc_sessions = qs.get("sessions", ["1"])[0] == "1"
            inc_data = qs.get("data", ["1"])[0] == "1"
            import zipfile
            import io
            import json as _json
            import datetime

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                # Soul / personality
                soul_path = DATA_DIR / "soul.md"
                if soul_path.exists():
                    zf.writestr("soul.md", soul_path.read_text(encoding="utf-8"))
                # Memory files
                from salmalm.constants import MEMORY_DIR as _mem_dir

                if _mem_dir.exists():
                    for f in _mem_dir.glob("*"):
                        if f.is_file():
                            zf.writestr(f"memory/{f.name}", f.read_text(encoding="utf-8"))
                # Also include memory.md from DATA_DIR
                mem_md = DATA_DIR / "memory.md"
                if mem_md.exists():
                    zf.writestr("memory.md", mem_md.read_text(encoding="utf-8"))
                # Config
                config_path = DATA_DIR / "config.json"
                if config_path.exists():
                    zf.writestr("config.json", config_path.read_text(encoding="utf-8"))
                routing_path = Path.home() / ".salmalm" / "routing.json"
                if routing_path.exists():
                    zf.writestr("routing.json", routing_path.read_text(encoding="utf-8"))
                # Sessions
                if inc_sessions:
                    from salmalm.core import _get_db

                    conn = _get_db()
                    _export_uid = _export_user.get("id", 0)
                    if _export_uid and _export_uid > 0:
                        rows = conn.execute(
                            "SELECT session_id, messages, title FROM session_store WHERE user_id=? OR user_id IS NULL",
                            (_export_uid,),
                        ).fetchall()
                    else:
                        rows = conn.execute("SELECT session_id, messages, title FROM session_store").fetchall()
                    sessions = []
                    for r in rows:
                        sessions.append(
                            {
                                "id": r[0],
                                "data": r[1],
                                "title": r[2] if len(r) > 2 else "",
                            }
                        )
                    zf.writestr(
                        "sessions.json",
                        _json.dumps(sessions, ensure_ascii=False, indent=2),
                    )
                # Data (notes, expenses, habits, etc.)
                if inc_data:
                    for name in (
                        "notes.json",
                        "expenses.json",
                        "habits.json",
                        "journal.json",
                        "dashboard.json",
                    ):
                        p = DATA_DIR / name
                        if p.exists():
                            zf.writestr(f"data/{name}", p.read_text(encoding="utf-8"))
                # Vault (API keys) — only if explicitly requested
                if inc_vault:
                    from salmalm.security.crypto import vault as _vault_mod

                    if _vault_mod.is_unlocked:
                        keys = {}
                        # Use internal vault key names (lowercase)
                        for k in _vault_mod.keys():
                            v = _vault_mod.get(k)
                            if v:
                                keys[k] = v
                        if keys:
                            zf.writestr("vault_keys.json", _json.dumps(keys, indent=2))
                # Manifest
                zf.writestr(
                    "manifest.json",
                    _json.dumps(
                        {
                            "version": VERSION,
                            "exported_at": datetime.datetime.now().isoformat(),
                            "includes": {
                                "sessions": inc_sessions,
                                "data": inc_data,
                                "vault": inc_vault,
                            },
                        },
                        indent=2,
                    ),
                )
            buf.seek(0)
            data = buf.getvalue()
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="salmalm-export-{ts}.zip"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        elif self.path.startswith("/uploads/"):
            # Serve uploaded files (images, audio) — basename-only to prevent traversal
            fname = Path(self.path.split("/uploads/", 1)[-1]).name
            if not fname:
                self.send_error(400)
                return
            upload_dir = (WORKSPACE_DIR / "uploads").resolve()  # noqa: F405
            fpath = (upload_dir / fname).resolve()
            if not fpath.is_relative_to(upload_dir) or not fpath.exists():
                self.send_error(404)
                return
            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".mp3": "audio/mpeg",
                ".wav": "audio/wav",
                ".ogg": "audio/ogg",
            }
            ext = fpath.suffix.lower()
            mime = mime_map.get(ext, "application/octet-stream")
            # ETag caching for static uploads
            stat = fpath.stat()
            etag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(stat.st_size))
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(fpath.read_bytes())
        else:
            self.send_error(404)

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

    def do_POST(self):
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
            print(f"[ERROR] POST {self.path}: {e}", flush=True)
            try:
                self._json({"error": f"Internal error: {str(e)[:200]}"}, 500)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass  # Client already gone
        finally:
            duration = (time.time() - _start) * 1000
            request_logger.log_request("POST", self.path, ip=self._get_client_ip(), duration_ms=duration)

    # Max POST body size: 10MB
    _MAX_POST_SIZE = 10 * 1024 * 1024

    def _post_api_users_register(self):
        body = self._body
        # Register new user (admin or open registration)
        from salmalm.features.users import user_manager

        requester = extract_auth(dict(self.headers))
        reg_mode = user_manager.get_registration_mode()
        if reg_mode == "admin_only":
            if not requester or requester.get("role") != "admin":
                self._json(
                    {"error": "Admin access required for registration / 관리자만 등록 가능"},
                    403,
                )
                return
        try:
            user = auth_manager.create_user(
                body.get("username", ""),
                body.get("password", ""),
                body.get("role", "user"),
            )
            user_manager.ensure_quota(user["id"])
            self._json({"ok": True, "user": user})
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        return

    def _post_api_users_delete(self):
        body = self._body
        requester = extract_auth(dict(self.headers))
        if not requester or requester.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
            return
        uid = body.get("user_id")
        username = body.get("username", "")
        if username:
            ok = auth_manager.delete_user(username)
        elif uid:
            from salmalm.features.users import user_manager

            u = user_manager.get_user_by_id(uid)
            ok = auth_manager.delete_user(u["username"]) if u else False
        else:
            self._json({"error": "user_id or username required"}, 400)
            return
        self._json({"ok": ok})
        return

    def _post_api_users_toggle(self):
        body = self._body
        # Enable/disable user (admin only)
        requester = extract_auth(dict(self.headers))
        if not requester or requester.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
            return
        from salmalm.features.users import user_manager

        uid = body.get("user_id")
        enabled = body.get("enabled", True)
        if not uid:
            self._json({"error": "user_id required"}, 400)
            return
        ok = user_manager.toggle_user(uid, enabled)
        self._json({"ok": ok})
        return

    def _post_api_users_quota_set(self):
        body = self._body
        # Set user quota (admin only)
        requester = extract_auth(dict(self.headers))
        if not requester or requester.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
            return
        from salmalm.features.users import user_manager

        uid = body.get("user_id")
        if not uid:
            self._json({"error": "user_id required"}, 400)
            return
        user_manager.set_quota(
            uid,
            daily_limit=body.get("daily_limit"),
            monthly_limit=body.get("monthly_limit"),
        )
        self._json({"ok": True, "quota": user_manager.get_quota(uid)})
        return

    def _post_api_users_settings(self):
        body = self._body
        # Update own settings
        user = extract_auth(dict(self.headers))
        if not user:
            self._json({"error": "Authentication required"}, 401)
            return
        from salmalm.features.users import user_manager

        uid = user.get("uid") or user.get("id", 0)
        allowed_keys = ("model_preference", "persona", "tts_enabled", "tts_voice")
        updates = {k: v for k, v in body.items() if k in allowed_keys}
        if updates:
            user_manager.set_user_settings(uid, **updates)
        self._json({"ok": True, "settings": user_manager.get_user_settings(uid)})
        return

    def _post_api_tenant_config(self):
        body = self._body
        # Admin: update multi-tenant config
        requester = extract_auth(dict(self.headers))
        if not requester or requester.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
            return
        from salmalm.features.users import user_manager

        if "multi_tenant" in body:
            user_manager.enable_multi_tenant(body["multi_tenant"])
        if "registration_mode" in body:
            user_manager.set_registration_mode(body["registration_mode"])
        if "telegram_allowlist" in body:
            user_manager.set_telegram_allowlist_mode(body["telegram_allowlist"])
        self._json({"ok": True})
        return

    def _post_api_auth_login(self):
        body = self._body
        username = body.get("username", "")
        password = body.get("password", "")
        user = auth_manager.authenticate(username, password)
        if user:
            token = auth_manager.create_token(user)
            audit_log(
                "auth_success",
                f"user={username}",
                detail_dict={"username": username, "ip": self._get_client_ip()},
            )
            self._json({"ok": True, "token": token, "user": user})
        else:
            audit_log(
                "auth_failure",
                f"user={username}",
                detail_dict={"username": username, "ip": self._get_client_ip()},
            )
            self._json({"error": "Invalid credentials"}, 401)
        return

    def _post_api_auth_register(self):
        body = self._body
        requester = extract_auth(dict(self.headers))
        if not requester or requester.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
            return
        try:
            user = auth_manager.create_user(
                body.get("username", ""),
                body.get("password", ""),
                body.get("role", "user"),
            )
            self._json({"ok": True, "user": user})
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        return

    def _post_api_setup(self):
        body = self._body
        # First-run setup — create vault with or without password
        if VAULT_FILE.exists():  # noqa: F405
            self._json({"error": "Already set up"}, 400)
            return
        use_pw = body.get("use_password", False)
        pw = body.get("password", "")
        if use_pw:
            if len(pw) < 4:
                self._json({"error": "Password must be at least 4 characters"}, 400)
                return
        try:
            _vault_pw = pw if use_pw else ""
            vault.create(_vault_pw)
            # Auto-unlock vault after creation so API keys can be saved immediately
            vault.unlock(_vault_pw, save_to_keychain=True)
            # Save password hint file for auto-unlock on restart (WSL lacks keychain)
            try:
                _pw_hint_file = VAULT_FILE.parent / ".vault_auto"  # noqa: F405
                if not use_pw:
                    _pw_hint_file.write_text("", encoding="utf-8")
                else:
                    # Store obfuscated pw for auto-unlock (local machine only)
                    import base64

                    _pw_hint_file.write_text(base64.b64encode(_vault_pw.encode()).decode(), encoding="utf-8")
                _pw_hint_file.chmod(0o600)
            except Exception:
                pass
            audit_log("setup", f"vault created {'with' if use_pw else 'without'} password")
        except RuntimeError:
            # cryptography not installed and fallback not enabled —
            # proceed without vault; create a marker file so setup doesn't loop
            log.warning("[SETUP] Vault unavailable (no cryptography). Proceeding without encryption.")
            audit_log("setup", "vault skipped — no cryptography package")
            vault._data = {}
            vault._password = ""
            vault._salt = b"\x00" * 16
            # Write a marker so _needs_first_run() returns False next time
            try:
                VAULT_FILE.parent.mkdir(parents=True, exist_ok=True)  # noqa: F405
                VAULT_FILE.write_bytes(b'{"no_crypto": true}')  # noqa: F405
            except Exception:
                pass
        self._json({"ok": True})
        return

    def _post_api_do_update(self):
        if not self._require_auth("admin"):
            return
        if self._get_client_ip() not in ("127.0.0.1", "::1", "localhost"):
            self._json({"error": "Update only allowed from localhost"}, 403)
            return
        try:
            import subprocess
            import sys

            # Try pipx first (common install method), fallback to pip
            import shutil

            _use_pipx = shutil.which("pipx") is not None
            if _use_pipx:
                _update_cmd = ["pipx", "install", "salmalm", "--force"]
            else:
                _update_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", "salmalm"]
            result = subprocess.run(
                _update_cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                # Get installed version
                ver_result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "from salmalm.constants import VERSION; print(VERSION)",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                new_ver = ver_result.stdout.strip() or "?"
                audit_log("update", f"upgraded to v{new_ver}")
                self._json({"ok": True, "version": new_ver, "output": result.stdout[-200:]})
            else:
                self._json({"ok": False, "error": result.stderr[-200:]})
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:200]})
        return

    def _post_api_restart(self):
        if not self._require_auth("admin"):
            return
        if self._get_client_ip() not in ("127.0.0.1", "::1", "localhost"):
            self._json({"error": "Restart only allowed from localhost"}, 403)
            return
        import sys

        audit_log("restart", "user-initiated restart")
        self._json({"ok": True, "message": "Restarting..."})
        # Graceful restart: flush response, then replace process after a short delay
        import threading
        import sys as _sys

        def _do_restart():
            import time

            time.sleep(0.5)  # Let HTTP response flush
            os.execv(_sys.executable, [_sys.executable] + _sys.argv)

        threading.Thread(target=_do_restart, daemon=True).start()
        return

    def _post_api_update(self):
        # Alias for /api/do-update with WebSocket progress
        if not self._require_auth("admin"):
            return
        if self._get_client_ip() not in ("127.0.0.1", "::1", "localhost"):
            self._json({"error": "Update only allowed from localhost"}, 403)
            return
        try:
            import subprocess

            # Broadcast update start via WebSocket
            try:
                from salmalm.web.ws import ws_server
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(ws_server.broadcast({"type": "update_status", "status": "installing"}))
            except Exception:
                pass
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "--no-cache-dir",
                    "salmalm",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                ver_result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "from salmalm.constants import VERSION; print(VERSION)",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                new_ver = ver_result.stdout.strip() or "?"
                audit_log("update", f"upgraded to v{new_ver}")
                self._json({"ok": True, "version": new_ver, "output": result.stdout[-200:]})
            else:
                self._json({"ok": False, "error": result.stderr[-200:]})
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:200]})
        return

    def _post_api_persona_switch(self):
        body = self._body
        session_id = body.get("session_id", self.headers.get("X-Session-Id", "web"))
        name = body.get("name", "")
        if not name:
            self._json({"error": "name required"}, 400)
            return
        from salmalm.core.prompt import switch_persona

        content = switch_persona(session_id, name)
        if content is None:
            self._json({"error": f'Persona "{name}" not found'}, 404)
            return
        self._json({"ok": True, "name": name, "content": content})
        return

    def _post_api_persona_create(self):
        body = self._body
        name = body.get("name", "")
        content = body.get("content", "")
        if not name or not content:
            self._json({"error": "name and content required"}, 400)
            return
        from salmalm.core.prompt import create_persona

        ok = create_persona(name, content)
        if ok:
            self._json({"ok": True})
        else:
            self._json({"error": "Invalid persona name"}, 400)
        return

    def _post_api_persona_delete(self):
        body = self._body
        name = body.get("name", "")
        if not name:
            self._json({"error": "name required"}, 400)
            return
        from salmalm.core.prompt import delete_persona

        ok = delete_persona(name)
        if ok:
            self._json({"ok": True})
        else:
            self._json({"error": "Cannot delete built-in persona or not found"}, 400)
        return

    def _post_api_test_key(self):
        body = self._body
        provider = body.get("provider", "")
        from salmalm.core.llm import _http_post

        tests = {
            "anthropic": lambda: _http_post(
                "https://api.anthropic.com/v1/messages",
                {
                    "x-api-key": vault.get("anthropic_api_key") or "",
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                {
                    "model": TEST_MODELS["anthropic"],
                    "max_tokens": 10,  # noqa: F405
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=15,
            ),
            "openai": lambda: _http_post(
                "https://api.openai.com/v1/chat/completions",
                {
                    "Authorization": "Bearer " + (vault.get("openai_api_key") or ""),
                    "Content-Type": "application/json",
                },
                {
                    "model": TEST_MODELS["openai"],
                    "max_tokens": 10,  # noqa: F405
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=15,
            ),
            "xai": lambda: _http_post(
                "https://api.x.ai/v1/chat/completions",
                {
                    "Authorization": "Bearer " + (vault.get("xai_api_key") or ""),
                    "Content-Type": "application/json",
                },
                {
                    "model": TEST_MODELS["xai"],
                    "max_tokens": 10,  # noqa: F405
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=15,
            ),
            "google": lambda: (
                lambda k: __import__("urllib.request", fromlist=["urlopen"]).urlopen(
                    __import__("urllib.request", fromlist=["Request"]).Request(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{TEST_MODELS['google']}:generateContent?key={k}",  # noqa: F405
                        data=json.dumps({"contents": [{"parts": [{"text": "ping"}]}]}).encode(),
                        headers={"Content-Type": "application/json"},
                    ),
                    timeout=15,
                )
            )(vault.get("google_api_key") or ""),
        }
        if provider not in tests:
            self._json({"ok": False, "result": f"❌ Unknown provider: {provider}"})
            return
        key = vault.get(f"{provider}_api_key") if provider != "google" else vault.get("google_api_key")
        if not key:
            self._json({"ok": False, "result": f"❌ {provider} API key not found in vault"})
            return
        try:
            tests[provider]()
            self._json({"ok": True, "result": f"✅ {provider} API connection successful!"})
        except Exception as e:
            self._json(
                {
                    "ok": False,
                    "result": f"❌ {provider} Test failed: {str(e)[:120]}",
                }
            )
        return

    def _post_api_unlock(self):
        body = self._body
        password = body.get("password", "")
        if VAULT_FILE.exists():  # noqa: F405
            ok = vault.unlock(password, save_to_keychain=True)
        else:
            vault.create(password, save_to_keychain=True)
            ok = True
        if ok:
            audit_log("unlock", "vault unlocked")
            token = secrets.token_hex(32)
            self._json({"ok": True, "token": token})
        else:
            audit_log("unlock_fail", "wrong password")
            self._json({"ok": False, "error": "Wrong password"}, 401)

    def _post_api_stt(self):
        body = self._body
        if not self._require_auth("user"):
            return
        audio_b64 = body.get("audio_base64", "")
        lang = body.get("language", "ko")
        if not audio_b64:
            self._json({"error": "No audio data"}, 400)
            return
        try:
            from salmalm.tools.tool_handlers import execute_tool

            result = execute_tool("stt", {"audio_base64": audio_b64, "language": lang})  # type: ignore[assignment]
            text = result.replace("🎤 Transcription:\n", "") if isinstance(result, str) else ""
            self._json({"ok": True, "text": text})
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)

    def _post_api_agent_sync(self):
        body = self._body
        if not self._require_auth("user"):
            return
        action = body.get("action", "export")
        if action == "export":
            import json as _json

            export_data = {}
            # Quick sync: lightweight JSON export (no ZIP)
            soul_path = DATA_DIR / "soul.md"
            if soul_path.exists():
                export_data["soul"] = soul_path.read_text(encoding="utf-8")
            config_path = DATA_DIR / "config.json"
            if config_path.exists():
                export_data["config"] = _json.loads(config_path.read_text(encoding="utf-8"))
            routing_path = Path.home() / ".salmalm" / "routing.json"
            if routing_path.exists():
                export_data["routing"] = _json.loads(routing_path.read_text(encoding="utf-8"))
            memory_dir = BASE_DIR / "memory"
            if memory_dir.exists():
                export_data["memory"] = {}
                for f in memory_dir.glob("*"):
                    if f.is_file():
                        export_data["memory"][f.name] = f.read_text(encoding="utf-8")
            self._json({"ok": True, "data": export_data})
        else:
            self._json({"ok": False, "error": "Unknown action"}, 400)

    def _post_api_agent_import_preview(self):
        if not self._require_auth("user"):
            return
        # Read multipart file
        import zipfile
        import io
        import json as _json

        content_type = self.headers.get("Content-Type", "")
        if "multipart" not in content_type:
            self._json({"ok": False, "error": "Expected multipart upload"}, 400)
            return
        content_length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(content_length)
        # Find ZIP in multipart
        boundary = content_type.split("boundary=")[1].encode() if "boundary=" in content_type else b""
        parts = raw.split(b"--" + boundary)
        zip_data = None
        for part in parts:
            if b"filename=" in part:
                body_start = part.find(b"\r\n\r\n")
                if body_start > 0:
                    zip_data = part[body_start + 4 :]
                    if zip_data.endswith(b"\r\n"):
                        zip_data = zip_data[:-2]
                    break
        if not zip_data:
            self._json({"ok": False, "error": "No ZIP file found"}, 400)
            return
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_data))
            manifest = _json.loads(zf.read("manifest.json")) if "manifest.json" in zf.namelist() else {}
            preview = {
                "files": zf.namelist(),
                "manifest": manifest,
                "size": len(zip_data),
            }
            self._json({"ok": True, "preview": preview})
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 400)

    def _post_api_queue_mode(self):
        body = self._body
        from salmalm.features.queue import set_queue_mode

        mode = body.get("mode", "collect")
        session_id = body.get("session_id", "web")
        try:
            result = set_queue_mode(session_id, mode)
            self._json({"ok": True, "message": result})
        except ValueError as e:
            self._json({"ok": False, "error": str(e)}, 400)

    def _post_api_cron_add(self):
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core import _llm_cron

        if not _llm_cron:
            self._json({"ok": False, "error": "Cron not available"}, 500)
            return
        name = body.get("name", "untitled")
        interval = int(body.get("interval", 3600))
        prompt = body.get("prompt", "")
        run_at = body.get("run_at", "")  # HH:MM or ISO datetime
        if not prompt:
            self._json({"ok": False, "error": "Prompt required"}, 400)
            return
        if run_at:
            # "Run at" mode: daily alarm at specific time
            if len(run_at) <= 5:  # HH:MM format → daily
                schedule = {
                    "kind": "cron",
                    "expr": f"{run_at.split(':')[1]} {run_at.split(':')[0]} * * *",
                }
            else:  # ISO datetime → one-shot
                schedule = {"kind": "at", "time": run_at}
        else:
            schedule = {"kind": "every", "seconds": interval}
        job = _llm_cron.add_job(name, schedule, prompt)
        self._json({"ok": True, "job": job})

    def _post_api_cron_delete(self):
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core import _llm_cron

        job_id = body.get("id", "")
        if _llm_cron and _llm_cron.remove_job(job_id):
            self._json({"ok": True})
        else:
            self._json({"ok": False, "error": "Job not found"}, 404)

    def _post_api_cron_toggle(self):
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core import _llm_cron

        job_id = body.get("id", "")
        if _llm_cron:
            for j in _llm_cron.jobs:
                if j["id"] == job_id:
                    j["enabled"] = not j["enabled"]
                    _llm_cron.save_jobs()
                    self._json({"ok": True, "enabled": j["enabled"]})
                    return
        self._json({"ok": False, "error": "Job not found"}, 404)

    def _post_api_sessions_create(self):
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        if not sid:
            self._json({"ok": False, "error": "Missing session_id"}, 400)
            return
        from salmalm.core import _get_db

        conn = _get_db()
        try:
            conn.execute(
                'INSERT OR IGNORE INTO session_store (session_id, messages, updated_at, title) VALUES (?, ?, datetime("now"), ?)',
                (sid, "[]", "New Chat"),
            )
            conn.commit()
        except Exception:
            pass
        self._json({"ok": True, "session_id": sid})

    def _post_api_sessions_import(self):
        """Import a chat session from JSON export."""
        body = self._body
        if not self._require_auth("user"):
            return
        messages = body.get("messages", [])
        title = body.get("title", "Imported Chat")
        if not messages or not isinstance(messages, list):
            self._json({"ok": False, "error": "messages array required"}, 400)
            return
        import uuid

        sid = f"imported_{uuid.uuid4().hex[:8]}"
        from salmalm.core import _get_db

        conn = _get_db()
        conn.execute(
            "INSERT OR REPLACE INTO session_store (session_id, messages, title, updated_at) VALUES (?, ?, ?, datetime('now'))",
            (sid, json.dumps(messages, ensure_ascii=False), title),
        )
        conn.commit()
        audit_log("session_import", sid, detail_dict={"title": title, "msg_count": len(messages)})
        self._json({"ok": True, "session_id": sid})

    def _post_api_sessions_delete(self):
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        if not sid:
            self._json({"ok": False, "error": "Missing session_id"}, 400)
            return
        from salmalm.core import _sessions, _get_db

        if sid in _sessions:
            del _sessions[sid]
        conn = _get_db()
        conn.execute("DELETE FROM session_store WHERE session_id=?", (sid,))
        conn.commit()
        audit_log("session_delete", sid, session_id=sid, detail_dict={"session_id": sid})
        self._json({"ok": True})

    def _post_api_soul(self):
        body = self._body
        if not self._require_auth("user"):
            return
        content = body.get("content", "")
        from salmalm.core.prompt import set_user_soul, reset_user_soul

        if content.strip():
            set_user_soul(content)
            self._json({"ok": True, "message": "SOUL.md saved"})
        else:
            reset_user_soul()
            self._json({"ok": True, "message": "SOUL.md reset to default"})
        return

    def _post_api_routing(self):
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core.engine import _save_routing_config, get_routing_config

        cfg = get_routing_config()
        for k in ("simple", "moderate", "complex"):
            if k in body and body[k]:
                cfg[k] = body[k]
        _save_routing_config(cfg)
        self._json({"ok": True, "config": cfg})
        return

    def _post_api_routing_optimize(self):
        """POST /api/routing/optimize — Auto-optimize routing based on available keys."""
        if not self._require_auth("user"):
            return
        from salmalm.core.model_selection import auto_optimize_and_save

        available_keys = []
        for key_name in ("anthropic_api_key", "openai_api_key", "xai_api_key", "google_api_key"):
            if vault.get(key_name):
                available_keys.append(key_name)
        if not available_keys:
            self._json({"ok": False, "error": "No API keys configured"}, 400)
            return
        config = auto_optimize_and_save(available_keys)
        # Build human-readable summary
        from salmalm.core.model_selection import _MODEL_COSTS

        summary = {}
        for tier, model in config.items():
            cost = _MODEL_COSTS.get(model, (0, 0))
            provider = model.split("/")[0] if "/" in model else "?"
            name = model.split("/")[-1] if "/" in model else model
            summary[tier] = {
                "model": model,
                "provider": provider,
                "name": name,
                "cost_input": cost[0],
                "cost_output": cost[1],
            }
        self._json({"ok": True, "config": config, "summary": summary, "keys_used": available_keys})

    def _post_api_failover(self):
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core.engine import save_failover_config, get_failover_config

        save_failover_config(body)
        self._json({"ok": True, "config": get_failover_config()})
        return

    def _post_api_sessions_rename(self):
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        title = body.get("title", "").strip()[:60]
        if not sid or not title:
            self._json({"ok": False, "error": "Missing session_id or title"}, 400)
            return
        from salmalm.core import _get_db

        conn = _get_db()
        conn.execute("UPDATE session_store SET title=? WHERE session_id=?", (title, sid))
        conn.commit()
        self._json({"ok": True})

    def _post_api_sessions_rollback(self):
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        count = int(body.get("count", 1))
        if not sid:
            self._json({"ok": False, "error": "Missing session_id"}, 400)
            return
        from salmalm.core import rollback_session

        result = rollback_session(sid, count)
        self._json(result)

    def _post_api_messages_edit(self):
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        idx = body.get("message_index")
        content = body.get("content", "")
        if not sid or idx is None or not content:
            self._json(
                {
                    "ok": False,
                    "error": "Missing session_id, message_index, or content",
                },
                400,
            )
            return
        from salmalm.core import edit_message

        result = edit_message(sid, int(idx), content)
        self._json(result)

    def _post_api_messages_delete(self):
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        idx = body.get("message_index")
        if not sid or idx is None:
            self._json({"ok": False, "error": "Missing session_id or message_index"}, 400)
            return
        from salmalm.core import delete_message

        result = delete_message(sid, int(idx))
        self._json(result)

    def _post_api_sessions_branch(self):
        body = self._body
        if not self._require_auth("user"):
            return
        sid = body.get("session_id", "")
        message_index = body.get("message_index")
        if not sid or message_index is None:
            self._json({"ok": False, "error": "Missing session_id or message_index"}, 400)
            return
        from salmalm.core import branch_session

        result = branch_session(sid, int(message_index))
        self._json(result)

    def _post_api_agents(self):
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.features.agents import agent_manager

        action = body.get("action", "")
        if action == "create":
            result = agent_manager.create(body.get("id", ""), body.get("display_name", ""))
            self._json({"ok": "✅" in result, "message": result})
        elif action == "delete":
            result = agent_manager.delete(body.get("id", ""))
            self._json({"ok": True, "message": result})
        elif action == "bind":
            result = agent_manager.bind(body.get("chat_key", ""), body.get("agent_id", ""))
            self._json({"ok": True, "message": result})
        elif action == "switch":
            result = agent_manager.switch(body.get("chat_key", ""), body.get("agent_id", ""))
            self._json({"ok": True, "message": result})
        else:
            self._json({"error": "Unknown action. Use: create, delete, bind, switch"}, 400)

    def _post_api_hooks(self):
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.features.hooks import hook_manager

        action = body.get("action", "")
        if action == "add":
            result = hook_manager.add_hook(body.get("event", ""), body.get("command", ""))
            self._json({"ok": True, "message": result})
        elif action == "remove":
            result = hook_manager.remove_hook(body.get("event", ""), body.get("index", 0))
            self._json({"ok": True, "message": result})
        elif action == "test":
            result = hook_manager.test_hook(body.get("event", ""))
            self._json({"ok": True, "message": result})
        elif action == "reload":
            hook_manager.reload()
            self._json({"ok": True, "message": "🔄 Hooks reloaded"})
        else:
            self._json({"error": "Unknown action"}, 400)

    def _post_api_plugins_manage(self):
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.features.plugin_manager import plugin_manager

        action = body.get("action", "")
        if action == "reload":
            result = plugin_manager.reload_all()
            self._json({"ok": True, "message": result})
        elif action == "enable":
            result = plugin_manager.enable(body.get("name", ""))
            self._json({"ok": True, "message": result})
        elif action == "disable":
            result = plugin_manager.disable(body.get("name", ""))
            self._json({"ok": True, "message": result})
        else:
            self._json({"error": "Unknown action"}, 400)

    def _post_api_chat(self):
        """Handle /api/chat and /api/chat/stream — main conversation endpoint."""
        from salmalm.core.engine import process_message

        body = self._body
        self._auto_unlock_localhost()
        if not vault.is_unlocked:
            self._json({"error": "Vault locked"}, 403)
            return
        message = body.get("message", "")
        session_id = body.get("session", "web")
        image_b64 = body.get("image_base64")
        image_mime = body.get("image_mime", "image/png")
        ui_lang = body.get("lang", "")
        use_stream = self.path.endswith("/stream")

        if use_stream:
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            def send_sse(event, data):
                try:
                    payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    self.wfile.write(payload.encode())
                    self.wfile.flush()
                except Exception:
                    pass

            send_sse("status", {"text": "🤔 Thinking..."})
            tool_count = [0]

            def on_tool_sse(name, args):
                tool_count[0] += 1
                send_sse("tool", {"name": name, "args": str(args)[:200], "count": tool_count[0]})
                send_sse("status", {"text": f"🔧 Running {name}..."})

            streamed_text = [""]

            def on_token_sse(event):
                try:
                    etype = event.get("type", "")
                    if etype == "text_delta":
                        text = event.get("text", "")
                        if text:
                            streamed_text[0] += text
                            send_sse("chunk", {"text": text, "streaming": True})
                    elif etype == "thinking_delta":
                        send_sse("thinking", {"text": event.get("text", "")})
                    elif etype == "tool_use_start":
                        tool_count[0] += 1
                        send_sse("status", {"text": f"🔧 Running {event.get('name', 'tool')}..."})
                        send_sse("tool", {"name": event.get("name", ""), "count": tool_count[0]})
                    elif etype == "error":
                        send_sse("error", {"text": event.get("error", "")})
                except Exception:
                    pass

            try:
                loop = asyncio.new_event_loop()
                # Pass session-level model override to engine
                from salmalm.core import get_session as _gs_pre

                _sess_pre = _gs_pre(session_id)
                _model_ov = getattr(_sess_pre, "model_override", None)
                if _model_ov == "auto":
                    _model_ov = None
                response = loop.run_until_complete(
                    process_message(
                        session_id,
                        message,
                        model_override=_model_ov,
                        image_data=(image_b64, image_mime) if image_b64 else None,
                        on_tool=on_tool_sse,
                        on_token=on_token_sse,
                        lang=ui_lang,
                    )
                )
                loop.close()
            except Exception as e:
                log.error(f"SSE process_message error: {e}")
                response = f"❌ Internal error: {type(e).__name__}"
            from salmalm.core import get_session as _gs2

            _sess2 = _gs2(session_id)
            try:
                from salmalm.tools.tools_ui import pop_pending_commands

                for cmd in pop_pending_commands():
                    send_sse("ui_cmd", cmd)
            except Exception:
                pass
            send_sse(
                "done",
                {
                    "response": response,
                    "model": getattr(_sess2, "last_model", router.force_model or "auto"),
                    "complexity": getattr(_sess2, "last_complexity", "auto"),
                },
            )
            try:
                self.wfile.write(b"event: close\ndata: {}\n\n")
                self.wfile.flush()
            except Exception:
                pass
        else:
            try:
                loop = asyncio.new_event_loop()
                # Pass session-level model override to engine
                from salmalm.core import get_session as _gs_pre2

                _sess_pre2 = _gs_pre2(session_id)
                _model_ov2 = getattr(_sess_pre2, "model_override", None)
                if _model_ov2 == "auto":
                    _model_ov2 = None
                response = loop.run_until_complete(
                    process_message(
                        session_id,
                        message,
                        model_override=_model_ov2,
                        image_data=(image_b64, image_mime) if image_b64 else None,
                        lang=ui_lang,
                    )
                )
                loop.close()
            except Exception as e:
                log.error(f"Chat process_message error: {e}")
                response = f"❌ Internal error: {type(e).__name__}"
            from salmalm.core import get_session as _gs

            _sess = _gs(session_id)
            self._json(
                {
                    "response": response,
                    "model": getattr(_sess, "last_model", router.force_model or "auto"),
                    "complexity": getattr(_sess, "last_complexity", "auto"),
                }
            )

    def _post_api_model_switch(self):
        """Handle /api/llm-router/switch and /api/model/switch."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core.llm_router import llm_router

        model = body.get("model", "")
        if not model:
            self._json({"error": "model required"}, 400)
            return
        msg = llm_router.switch_model(model)
        # Also update session-level override so auto-routing respects UI selection
        sid = self.headers.get("X-Session-Id") or body.get("session") or "web"
        try:
            from salmalm.core import get_session as _gs_switch

            _s = _gs_switch(sid)
            _s.model_override = None if model == "auto" else model
        except Exception:
            pass
        # Return the effective model (session override takes precedence)
        _effective = model if model else llm_router.current_model
        self._json({"ok": "✅" in msg, "message": msg, "current_model": _effective})

    def _post_api_test_provider(self):
        """Handle /api/llm-router/test-key and /api/test-provider."""
        body = self._body
        if not self._require_auth("user"):
            return
        provider = body.get("provider", "")
        api_key = body.get("api_key", "")
        if not provider or not api_key:
            self._json({"error": "provider and api_key required"}, 400)
            return
        from salmalm.core.llm_router import PROVIDERS

        prov_cfg = PROVIDERS.get(provider)
        if not prov_cfg:
            self._json({"ok": False, "message": f"Unknown provider: {provider}"})
            return
        env_key = prov_cfg.get("env_key", "")
        if env_key:
            old_val = os.environ.get(env_key)
            os.environ[env_key] = api_key
        try:
            import urllib.request
            import urllib.error

            if provider == "anthropic":
                url = f"{prov_cfg['base_url']}/messages"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(
                        {
                            "model": TEST_MODELS["anthropic"],
                            "max_tokens": 1,  # noqa: E128
                            "messages": [{"role": "user", "content": "hi"}],
                        }
                    ).encode(),
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    method="POST",
                )
            elif provider == "ollama":
                url = f"{prov_cfg['base_url']}/api/tags"
                req = urllib.request.Request(url)
            else:
                url = f"{prov_cfg['base_url']}/models"
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
            urllib.request.urlopen(req, timeout=10)
            self._json({"ok": True, "message": f"✅ {provider} key is valid"})
        except urllib.error.HTTPError as e:
            self._json({"ok": False, "message": f"❌ HTTP {e.code}: Invalid key"})
        except Exception as e:
            self._json({"ok": False, "message": f"❌ Connection failed: {e}"})
        finally:
            if env_key:
                if old_val is not None:
                    os.environ[env_key] = old_val
                elif env_key in os.environ:
                    del os.environ[env_key]

    def _post_api_thoughts_search(self):
        """Handle /api/thoughts/search."""
        body = self._body
        from salmalm.features.thoughts import thought_stream

        q = body.get("q", body.get("query", ""))
        if not q:
            self._json({"error": "query required"}, 400)
            return
        results = thought_stream.search(q)
        self._json({"thoughts": results})

    def _post_api_chat_abort(self):
        body = self._body
        # Abort generation — LibreChat style (생성 중지)
        if not self._require_auth("user"):
            return
        session_id = body.get("session", body.get("session_id", "web"))
        from salmalm.features.edge_cases import abort_controller

        abort_controller.set_abort(session_id)
        self._json({"ok": True, "message": "Abort signal sent / 중단 신호 전송됨"})
        return

    def _post_api_chat_regenerate(self):
        body = self._body
        # Regenerate response — LibreChat style (응답 재생성)
        if not self._require_auth("user"):
            return
        session_id = body.get("session_id", "web")
        message_index = body.get("message_index")
        if message_index is None:
            self._json({"error": "Missing message_index"}, 400)
            return
        from salmalm.features.edge_cases import conversation_fork

        try:
            loop = asyncio.new_event_loop()
            response = loop.run_until_complete(conversation_fork.regenerate(session_id, int(message_index)))
            loop.close()
            if response:
                self._json({"ok": True, "response": response})
            else:
                self._json({"ok": False, "error": "Could not regenerate"}, 400)
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:200]}, 500)
        return

    def _post_api_chat_compare(self):
        body = self._body
        # Compare models — BIG-AGI style (응답 비교)
        if not self._require_auth("user"):
            return
        message = body.get("message", "")
        models = body.get("models", [])
        session_id = body.get("session_id", "web")
        if not message:
            self._json({"error": "Missing message"}, 400)
            return
        from salmalm.features.edge_cases import compare_models

        try:
            loop = asyncio.new_event_loop()
            results = loop.run_until_complete(compare_models(session_id, message, models or None))
            loop.close()
            self._json({"ok": True, "results": results})
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:200]}, 500)
        return

    def _post_api_alternatives_switch(self):
        body = self._body
        # Switch alternative — LibreChat style (대안 전환)
        if not self._require_auth("user"):
            return
        session_id = body.get("session_id", "")
        message_index = body.get("message_index")
        alt_id = body.get("alt_id")
        if not all([session_id, message_index is not None, alt_id]):
            self._json({"error": "Missing parameters"}, 400)
            return
        from salmalm.features.edge_cases import conversation_fork

        content = conversation_fork.switch_alternative(session_id, int(message_index), int(alt_id))
        if content:
            # Update session messages
            from salmalm.core import get_session

            session = get_session(session_id)
            ua = [(i, m) for i, m in enumerate(session.messages) if m.get("role") in ("user", "assistant")]
            if int(message_index) < len(ua):
                real_idx = ua[int(message_index)][0]
                session.messages[real_idx] = {
                    "role": "assistant",
                    "content": content,
                }
                session._persist()
            self._json({"ok": True, "content": content})
        else:
            self._json({"ok": False, "error": "Alternative not found"}, 404)
        return

    def _post_api_bookmarks(self):
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

    def _post_api_groups(self):
        body = self._body
        # Session group CRUD — LobeChat style (그룹 관리)
        if not self._require_auth("user"):
            return
        action = body.get("action", "create")
        from salmalm.features.edge_cases import session_groups

        if action == "create":
            name = body.get("name", "").strip()
            if not name:
                self._json({"error": "Missing name"}, 400)
                return
            result = session_groups.create_group(name, body.get("color", "#6366f1"))
            self._json(result)
        elif action == "update":
            gid = body.get("id")
            if not gid:
                self._json({"error": "Missing id"}, 400)
                return
            kwargs = {k: v for k, v in body.items() if k in ("name", "color", "sort_order", "collapsed")}
            ok = session_groups.update_group(int(gid), **kwargs)
            self._json({"ok": ok})
        elif action == "delete":
            gid = body.get("id")
            if not gid:
                self._json({"error": "Missing id"}, 400)
                return
            ok = session_groups.delete_group(int(gid))
            self._json({"ok": ok})
        elif action == "move":
            sid = body.get("session_id", "")
            gid = body.get("group_id")
            ok = session_groups.move_session(sid, int(gid) if gid else None)
            self._json({"ok": ok})
        else:
            self._json({"error": "Unknown action"}, 400)
        return

    def _post_api_paste_detect(self):
        body = self._body
        # Smart paste detection — BIG-AGI style (스마트 붙여넣기 감지)
        if not self._require_auth("user"):
            return
        text = body.get("text", "")
        if not text:
            self._json({"error": "Missing text"}, 400)
            return
        from salmalm.features.edge_cases import detect_paste_type

        self._json(detect_paste_type(text))
        return

    def _post_api_vault(self):
        body = self._body
        if not vault.is_unlocked:
            self._json({"error": "Vault locked"}, 403)
            return
        # Vault ops require admin
        user = extract_auth(dict(self.headers))
        ip = self._get_client_ip()
        if not user and ip not in ("127.0.0.1", "::1", "localhost"):
            self._json({"error": "Admin access required"}, 403)
            return
        action = body.get("action")
        if action == "set":
            key = body.get("key")
            value = body.get("value")
            if not key:
                self._json({"error": "key required"}, 400)
                return
            try:
                vault.set(key, value)
                self._json({"ok": True})
            except Exception as e:
                self._json({"error": f"Vault error: {type(e).__name__}: {e}"}, 500)
        elif action == "get":
            key = body.get("key")
            if not key:
                self._json({"error": "key required"}, 400)
                return
            val = vault.get(key)
            self._json({"value": val})
        elif action == "keys":
            self._json({"keys": vault.keys()})
        elif action == "delete":
            key = body.get("key")
            if not key:
                self._json({"error": "key required"}, 400)
                return
            vault.delete(key)
            self._json({"ok": True})
        elif action == "change_password":
            old_pw = body.get("old_password", "")
            new_pw = body.get("new_password", "")
            if new_pw and len(new_pw) < 4:
                self._json({"error": "Password must be at least 4 characters"}, 400)
            elif vault.change_password(old_pw, new_pw):
                audit_log("vault", "master password changed")
                self._json({"ok": True})
            else:
                self._json({"error": "Current password is incorrect"}, 403)
        else:
            self._json({"error": "Unknown action"}, 400)

    def _post_api_upload(self):
        length = self._content_length
        if not vault.is_unlocked:
            self._json({"error": "Vault locked"}, 403)
            return
        # Parse multipart form data
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._json({"error": "multipart required"}, 400)
            return
        try:
            raw = self.rfile.read(length)
            # Parse multipart using stdlib email.parser (robust edge-case handling)
            import email.parser
            import email.policy

            header_bytes = f"Content-Type: {content_type}\r\n\r\n".encode()
            msg = email.parser.BytesParser(policy=email.policy.compat32).parsebytes(header_bytes + raw)
            for part in msg.walk():
                fname_raw = part.get_filename()
                if not fname_raw:
                    continue
                fname = Path(fname_raw).name  # basename only (prevent path traversal)
                # Reject suspicious filenames
                if not fname or ".." in fname or not re.match(r"^[\w.\- ]+$", fname):
                    self._json({"error": "Invalid filename"}, 400)
                    return
                # Validate file type (Open WebUI style)
                from salmalm.features.edge_cases import validate_upload

                ok, err = validate_upload(fname, len(part.get_payload(decode=True) or b""))
                if not ok:
                    self._json({"error": err}, 400)
                    return
                file_data = part.get_payload(decode=True)
                if not file_data:
                    continue
                # Size limit: 50MB
                if len(file_data) > 50 * 1024 * 1024:
                    self._json({"error": "File too large (max 50MB)"}, 413)
                    return
                # Save
                save_dir = WORKSPACE_DIR / "uploads"  # noqa: F405
                save_dir.mkdir(exist_ok=True)
                save_path = save_dir / fname
                save_path.write_bytes(file_data)  # type: ignore[arg-type]
                size_kb = len(file_data) / 1024
                is_image = any(
                    fname.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
                )
                is_text = any(
                    fname.lower().endswith(ext)
                    for ext in (
                        ".txt",
                        ".md",
                        ".py",
                        ".js",
                        ".json",
                        ".csv",
                        ".log",
                        ".html",
                        ".css",
                        ".sh",
                        ".bat",
                        ".yaml",
                        ".yml",
                        ".xml",
                        ".sql",
                    )
                )
                is_pdf = fname.lower().endswith(".pdf")
                info = f"[{'🖼️ Image' if is_image else '📎 File'} uploaded: uploads/{fname} ({size_kb:.1f}KB)]"
                if is_pdf:
                    # PDF text extraction (Open WebUI style)
                    try:
                        from salmalm.features.edge_cases import process_uploaded_file

                        info = process_uploaded_file(fname, file_data)
                    except Exception:
                        info += "\n[PDF text extraction failed]"
                elif is_text:
                    try:
                        from salmalm.features.edge_cases import process_uploaded_file

                        info = process_uploaded_file(fname, file_data)
                    except Exception:
                        preview = file_data.decode("utf-8", errors="replace")[:3000]  # type: ignore[union-attr]
                        info += f"\n[File content]\n{preview}"
                log.info(f"[SEND] Web upload: {fname} ({size_kb:.1f}KB)")
                audit_log("web_upload", fname)
                resp = {
                    "ok": True,
                    "filename": fname,
                    "size": len(file_data),
                    "info": info,
                    "is_image": is_image,
                }
                if is_image:
                    import base64

                    ext = fname.rsplit(".", 1)[-1].lower()
                    mime = {
                        "png": "image/png",
                        "jpg": "image/jpeg",
                        "jpeg": "image/jpeg",
                        "gif": "image/gif",
                        "webp": "image/webp",
                        "bmp": "image/bmp",
                    }.get(ext, "image/png")
                    resp["image_base64"] = base64.b64encode(file_data).decode()  # type: ignore[arg-type]
                    resp["image_mime"] = mime
                self._json(resp)
                return
            self._json({"error": "No file found"}, 400)
        except Exception as e:
            log.error(f"Upload error: {e}")
            self._json({"error": str(e)[:200]}, 500)
            return

    def _post_api_onboarding(self):
        try:
            return self._post_api_onboarding_inner()
        except Exception as e:
            log.exception(f"[ONBOARDING] Unhandled error: {e}")
            self._json({"error": f"Internal error: {str(e)[:200]}"}, 500)

    def _post_api_onboarding_inner(self):
        body = self._body
        if not vault.is_unlocked:
            # Fresh install: auto-create vault with empty password
            try:
                from salmalm.security.crypto import VAULT_FILE

                if not VAULT_FILE.exists():
                    vault.create("", save_to_keychain=False)
                else:
                    vault.unlock("")
            except Exception:
                pass
            if not vault.is_unlocked:
                self._json({"error": "Vault locked"}, 403)
                return
        # Save all provided API keys + Ollama URL
        saved = []
        for key in (
            "anthropic_api_key",
            "openai_api_key",
            "xai_api_key",
            "google_api_key",
            "brave_api_key",
        ):
            val = body.get(key, "").strip()
            if val:
                vault.set(key, val)
                saved.append(key.replace("_api_key", ""))
        dc_token = body.get("discord_token", "").strip()
        if dc_token:
            vault.set("discord_token", dc_token)
            saved.append("discord")
        ollama_url = body.get("ollama_url", "").strip()
        if ollama_url:
            vault.set("ollama_url", ollama_url)
            saved.append("ollama")
        ollama_key = body.get("ollama_api_key", "").strip()
        if ollama_key:
            vault.set("ollama_api_key", ollama_key)
            saved.append("ollama_key")
        # Test all provided keys
        from salmalm.core.llm import _http_post  # noqa: F811

        test_results = []
        if body.get("anthropic_api_key"):
            try:
                _http_post(
                    "https://api.anthropic.com/v1/messages",
                    {
                        "x-api-key": body["anthropic_api_key"],
                        "content-type": "application/json",
                        "anthropic-version": "2023-06-01",
                    },
                    {
                        "model": TEST_MODELS["anthropic"],
                        "max_tokens": 10,  # noqa: F405
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                    timeout=15,
                )
                test_results.append("✅ Anthropic OK")
            except Exception as e:
                test_results.append(f"⚠️ Anthropic: {str(e)[:80]}")
        if body.get("openai_api_key"):
            try:
                _http_post(
                    "https://api.openai.com/v1/chat/completions",
                    {
                        "Authorization": f"Bearer {body['openai_api_key']}",
                        "Content-Type": "application/json",
                    },
                    {
                        "model": TEST_MODELS["openai"],
                        "max_tokens": 10,  # noqa: F405
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                    timeout=15,
                )
                test_results.append("✅ OpenAI OK")
            except Exception as e:
                test_results.append(f"⚠️ OpenAI: {str(e)[:80]}")
        if body.get("xai_api_key"):
            try:
                _http_post(
                    "https://api.x.ai/v1/chat/completions",
                    {
                        "Authorization": f"Bearer {body['xai_api_key']}",
                        "Content-Type": "application/json",
                    },
                    {
                        "model": TEST_MODELS["xai"],
                        "max_tokens": 10,  # noqa: F405
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                    timeout=15,
                )
                test_results.append("✅ xAI OK")
            except Exception as e:
                test_results.append(f"⚠️ xAI: {str(e)[:80]}")
        if body.get("google_api_key"):
            try:
                import urllib.request

                gk = body["google_api_key"]
                req = urllib.request.Request(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{TEST_MODELS['google']}:generateContent?key={gk}",  # noqa: F405
                    data=json.dumps({"contents": [{"parts": [{"text": "ping"}]}]}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=15)
                test_results.append("✅ Google OK")
            except Exception as e:
                test_results.append(f"⚠️ Google: {str(e)[:80]}")
        audit_log("onboarding", f"keys: {', '.join(saved)}")
        # Auto-optimize routing based on available keys
        routing_config = {}
        try:
            from salmalm.core.model_selection import auto_optimize_and_save

            available_keys = []
            for key_name in ("anthropic_api_key", "openai_api_key", "xai_api_key", "google_api_key"):
                if vault.get(key_name):
                    available_keys.append(key_name)
            if available_keys:
                routing_config = auto_optimize_and_save(available_keys)
                log.info(f"[ONBOARDING] Auto-optimized routing: {routing_config}")
        except Exception as e:
            log.warning(f"[ONBOARDING] Auto-routing failed (ignored): {e}")
        test_result = " | ".join(test_results) if test_results else "Keys saved."
        self._json({"ok": True, "saved": saved, "test_result": test_result, "routing": routing_config})
        return

    def _post_api_onboarding_preferences(self):
        body = self._body
        # Save model + persona preferences from setup wizard
        model = body.get("model", "auto")
        persona = body.get("persona", "expert")
        if model and model != "auto":
            vault.set("default_model", model)
        # Write SOUL.md persona template
        persona_templates = {
            "expert": "# SOUL.md\n\nYou are a professional AI expert. Be precise, detail-oriented, and thorough in your responses. Use technical language when appropriate and always provide well-structured answers.",
            "friend": "# SOUL.md\n\nYou are a friendly and warm conversational partner. Be casual, use humor when appropriate, and make the user feel comfortable. Keep things light and engaging while still being helpful.",
            "assistant": "# SOUL.md\n\nYou are an efficient personal assistant. Be concise, task-focused, and proactive. Prioritize actionable information and minimize unnecessary verbosity.",
        }
        template = persona_templates.get(persona, persona_templates["expert"])
        try:
            soul_path = os.path.join(str(DATA_DIR), "SOUL.md")
            if not os.path.exists(soul_path):
                os.makedirs(os.path.dirname(soul_path), exist_ok=True)
                with open(soul_path, "w", encoding="utf-8") as f:
                    f.write(template)
        except Exception:
            pass
        audit_log("onboarding", f"preferences: model={model}, persona={persona}")
        self._json({"ok": True})
        return

    def _post_api_config_telegram(self):
        body = self._body
        if not vault.is_unlocked:
            self._json({"error": "Vault locked"}, 403)
            return
        vault.set("telegram_token", body.get("token", ""))
        vault.set("telegram_owner_id", body.get("owner_id", ""))
        self._json({"ok": True, "message": "Telegram config saved. Restart required."})

    def _post_api_gateway_register(self):
        body = self._body
        from salmalm.features.nodes import gateway

        node_id = body.get("node_id", "")
        url = body.get("url", "")
        if not node_id or not url:
            self._json({"error": "node_id and url required"}, 400)
            return
        result = gateway.register(  # type: ignore[assignment]
            node_id,
            url,
            token=body.get("token", ""),
            capabilities=body.get("capabilities"),
            name=body.get("name", ""),
        )
        self._json(result)  # type: ignore[arg-type]

    def _post_api_gateway_heartbeat(self):
        body = self._body
        from salmalm.features.nodes import gateway

        node_id = body.get("node_id", "")
        self._json(gateway.heartbeat(node_id))

    def _post_api_gateway_unregister(self):
        body = self._body
        from salmalm.features.nodes import gateway

        node_id = body.get("node_id", "")
        self._json(gateway.unregister(node_id))

    def _post_api_gateway_dispatch(self):
        body = self._body
        from salmalm.features.nodes import gateway

        node_id = body.get("node_id", "")
        tool = body.get("tool", "")
        args = body.get("args", {})
        if node_id:
            result = gateway.dispatch(node_id, tool, args)  # type: ignore[assignment]
        else:
            result = gateway.dispatch_auto(tool, args)  # type: ignore[assignment]
            if result is None:
                result = {"error": "No available node for this tool"}
        self._json(result)  # type: ignore[arg-type]

    def _post_webhook_slack(self):
        body = self._body
        # Slack Event API webhook
        from salmalm.channels.slack_bot import slack_bot

        if not slack_bot.bot_token:
            self._json({"error": "Slack not configured"}, 503)
            return
        # Verify request
        ts = self.headers.get("X-Slack-Request-Timestamp", "")
        sig = self.headers.get("X-Slack-Signature", "")
        raw_body = json.dumps(body).encode() if isinstance(body, dict) else b""
        if not slack_bot.verify_request(ts, sig, raw_body):
            self._json({"error": "Invalid signature"}, 403)
            return
        result = slack_bot.handle_event(body)
        if result:
            self._json(result)
        else:
            self._json({"ok": True})

    def _post_api_presence(self):
        body = self._body
        # Register/heartbeat presence
        instance_id = body.get("instanceId", "")
        if not instance_id:
            self._json({"error": "instanceId required"}, 400)
            return
        from salmalm.features.presence import presence_manager

        entry = presence_manager.register(
            instance_id,
            host=body.get("host", ""),
            ip=self._get_client_ip(),
            mode=body.get("mode", "web"),
            user_agent=body.get("userAgent", ""),
        )
        self._json({"ok": True, "state": entry.state})

    def _post_webhook_telegram(self):
        body = self._body
        # Telegram webhook endpoint
        from salmalm.channels.telegram import telegram_bot

        if not telegram_bot.token:
            self._json({"error": "Telegram not configured"}, 503)
            return
        # Verify secret token
        secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if telegram_bot._webhook_secret and not telegram_bot.verify_webhook_request(secret):
            log.warning("[BLOCK] Telegram webhook: invalid secret token")
            self._json({"error": "Forbidden"}, 403)
            return
        try:
            update = body
            # Run async handler in event loop
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(telegram_bot.handle_webhook_update(update))
                else:
                    loop.run_until_complete(telegram_bot.handle_webhook_update(update))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(telegram_bot.handle_webhook_update(update))
                loop.close()
            self._json({"ok": True})
        except Exception as e:
            log.error(f"Webhook handler error: {e}")
            self._json({"ok": True})  # Always return 200 to Telegram

    def _post_api_sla_config(self):
        body = self._body
        # Update SLA config (SLA 설정 업데이트)
        if not self._require_auth("admin"):
            return
        from salmalm.features.sla import sla_config

        sla_config.update(body)
        self._json({"ok": True, "config": sla_config.get_all()})

    def _post_api_node_execute(self):
        body = self._body
        # Node endpoint: execute a tool locally (called by gateway)
        from salmalm.tools.tool_handlers import execute_tool

        tool = body.get("tool", "")
        args = body.get("args", {})
        if not tool:
            self._json({"error": "tool name required"}, 400)
            return
        try:
            result = execute_tool(tool, args)  # type: ignore[assignment]
            self._json({"ok": True, "result": result[:50000]})  # type: ignore[index]
        except Exception as e:
            self._json({"error": str(e)[:500]}, 500)

    def _get_api_engine_settings(self):
        """GET /api/engine/settings — return current engine optimization toggles."""
        import os
        from salmalm.constants import COMPACTION_THRESHOLD

        self._json(
            {
                "dynamic_tools": os.environ.get("SALMALM_ALL_TOOLS", "0") != "1",
                "planning": os.environ.get("SALMALM_PLANNING", "0") == "1",
                "reflection": os.environ.get("SALMALM_REFLECT", "0") == "1",
                "compaction_threshold": COMPACTION_THRESHOLD,
                "cost_cap": os.environ.get("SALMALM_COST_CAP", ""),
                "max_tool_iterations": int(os.environ.get("SALMALM_MAX_TOOL_ITER", "15")),
                "cache_ttl": int(os.environ.get("SALMALM_CACHE_TTL", "3600")),
                "batch_api": os.environ.get("SALMALM_BATCH_API", "0") == "1",
                "file_presummary": os.environ.get("SALMALM_FILE_PRESUMMARY", "0") == "1",
                "early_stop": os.environ.get("SALMALM_EARLY_STOP", "0") == "1",
            }
        )

    def _post_api_engine_settings(self):
        """POST /api/engine/settings — toggle engine optimization settings."""
        import os
        import salmalm.constants as _const

        body = self._body
        if "dynamic_tools" in body:
            os.environ["SALMALM_ALL_TOOLS"] = "0" if body["dynamic_tools"] else "1"
        if "planning" in body:
            os.environ["SALMALM_PLANNING"] = "1" if body["planning"] else "0"
        if "reflection" in body:
            os.environ["SALMALM_REFLECT"] = "1" if body["reflection"] else "0"
        if "compaction_threshold" in body:
            try:
                val = int(body["compaction_threshold"])
                if 10000 <= val <= 200000:
                    _const.COMPACTION_THRESHOLD = val
            except (ValueError, TypeError):
                pass
        if "max_tool_iterations" in body:
            try:
                val = int(body["max_tool_iterations"])
                if 3 <= val <= 999:
                    os.environ["SALMALM_MAX_TOOL_ITER"] = str(val)
            except (ValueError, TypeError):
                pass
        if "cache_ttl" in body:
            try:
                val = int(body["cache_ttl"])
                if 0 <= val <= 86400:
                    os.environ["SALMALM_CACHE_TTL"] = str(val)
                    _const.CACHE_TTL = val
            except (ValueError, TypeError):
                pass
        if "batch_api" in body:
            os.environ["SALMALM_BATCH_API"] = "1" if body["batch_api"] else "0"
        if "file_presummary" in body:
            os.environ["SALMALM_FILE_PRESUMMARY"] = "1" if body["file_presummary"] else "0"
        if "early_stop" in body:
            os.environ["SALMALM_EARLY_STOP"] = "1" if body["early_stop"] else "0"
        if "cost_cap" in body:
            cap = str(body["cost_cap"]).strip()
            if cap:
                os.environ["SALMALM_COST_CAP"] = cap
            elif "SALMALM_COST_CAP" in os.environ:
                del os.environ["SALMALM_COST_CAP"]
        self._json({"ok": True})

    def _post_api_thoughts(self):
        body = self._body
        from salmalm.features.thoughts import thought_stream

        content = body.get("content", "").strip()
        if not content:
            self._json({"error": "content required"}, 400)
            return
        mood = body.get("mood", "neutral")
        tid = thought_stream.add(content, mood=mood)
        self._json({"ok": True, "id": tid})

    _POST_ROUTES = {
        "/api/users/register": "_post_api_users_register",
        "/api/users/delete": "_post_api_users_delete",
        "/api/users/toggle": "_post_api_users_toggle",
        "/api/users/quota/set": "_post_api_users_quota_set",
        "/api/users/settings": "_post_api_users_settings",
        "/api/tenant/config": "_post_api_tenant_config",
        "/api/auth/login": "_post_api_auth_login",
        "/api/auth/register": "_post_api_auth_register",
        "/api/setup": "_post_api_setup",
        "/api/do-update": "_post_api_do_update",
        "/api/restart": "_post_api_restart",
        "/api/update": "_post_api_update",
        "/api/persona/switch": "_post_api_persona_switch",
        "/api/persona/create": "_post_api_persona_create",
        "/api/persona/delete": "_post_api_persona_delete",
        "/api/test-key": "_post_api_test_key",
        "/api/unlock": "_post_api_unlock",
        "/api/stt": "_post_api_stt",
        "/api/agent/sync": "_post_api_agent_sync",
        "/api/agent/import/preview": "_post_api_agent_import_preview",
        "/api/queue/mode": "_post_api_queue_mode",
        "/api/cron/add": "_post_api_cron_add",
        "/api/cron/delete": "_post_api_cron_delete",
        "/api/cron/toggle": "_post_api_cron_toggle",
        "/api/sessions/create": "_post_api_sessions_create",
        "/api/sessions/delete": "_post_api_sessions_delete",
        "/api/sessions/import": "_post_api_sessions_import",
        "/api/soul": "_post_api_soul",
        "/api/routing": "_post_api_routing",
        "/api/routing/optimize": "_post_api_routing_optimize",
        "/api/failover": "_post_api_failover",
        "/api/sessions/rename": "_post_api_sessions_rename",
        "/api/sessions/rollback": "_post_api_sessions_rollback",
        "/api/messages/edit": "_post_api_messages_edit",
        "/api/messages/delete": "_post_api_messages_delete",
        "/api/sessions/branch": "_post_api_sessions_branch",
        "/api/agents": "_post_api_agents",
        "/api/hooks": "_post_api_hooks",
        "/api/plugins/manage": "_post_api_plugins_manage",
        "/api/chat/abort": "_post_api_chat_abort",
        "/api/chat/regenerate": "_post_api_chat_regenerate",
        "/api/chat/compare": "_post_api_chat_compare",
        "/api/alternatives/switch": "_post_api_alternatives_switch",
        "/api/bookmarks": "_post_api_bookmarks",
        "/api/groups": "_post_api_groups",
        "/api/paste/detect": "_post_api_paste_detect",
        "/api/vault": "_post_api_vault",
        "/api/upload": "_post_api_upload",
        "/api/onboarding": "_post_api_onboarding",
        "/api/onboarding/preferences": "_post_api_onboarding_preferences",
        "/api/config/telegram": "_post_api_config_telegram",
        "/api/gateway/register": "_post_api_gateway_register",
        "/api/gateway/heartbeat": "_post_api_gateway_heartbeat",
        "/api/gateway/unregister": "_post_api_gateway_unregister",
        "/api/gateway/dispatch": "_post_api_gateway_dispatch",
        "/webhook/slack": "_post_webhook_slack",
        "/api/presence": "_post_api_presence",
        "/webhook/telegram": "_post_webhook_telegram",
        "/api/sla/config": "_post_api_sla_config",
        "/api/node/execute": "_post_api_node_execute",
        "/api/thoughts": "_post_api_thoughts",
        "/api/engine/settings": "_post_api_engine_settings",
    }

    def _do_post_inner(self):
        from salmalm.core.engine import process_message  # noqa: F401

        length = int(self.headers.get("Content-Length", 0))

        # Request size limit
        if length > self._MAX_POST_SIZE:
            self._json(
                {"error": f"Request too large ({length} bytes). Max: {self._MAX_POST_SIZE} bytes."},
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
