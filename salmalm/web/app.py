"""salmalm/web/app.py — Real FastAPI application.

Replaces the single catch-all route in asgi.py with explicit FastAPI route
decorators for every endpoint registered in the WebHandler route tables.
The underlying dispatch still uses FastHandler (ASGI↔mixin bridge) so all
existing mixin handlers work unchanged; we only change *how* FastAPI sees
the routes (explicit paths vs. /{path:path} catch-all).

Import:
    from salmalm.web.app import app
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse

from salmalm.constants import VERSION
from salmalm.security.crypto import log
from salmalm.utils.logging_ext import request_logger, set_correlation_id
from salmalm.web.auth import (
    DailyQuotaExceeded,
    RateLimitExceeded,
    daily_quota,
    extract_auth,
    ip_ban_list,
    llm_rate_limiter,
    rate_limiter,
)
from salmalm.web.asgi import (
    FastHandler,
    _HTMLResp,
    _JSONResp,
    _RawResp,
    _SSEQueue,
    _cors_headers,
    _handle_sse_stream,
    _inject_mixin_methods,
)

# ── LLM-triggering paths (tighter rate limit) ─────────────────────────────
_LLM_PATHS: frozenset = frozenset(
    {
        "/api/chat",
        "/api/chat/stream",
        "/api/chat/abort",
        "/api/chat/regenerate",
        "/api/chat/compare",
        "/api/ask",
    }
)

# ── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(title="SalmAlm", version=VERSION, docs_url=None, redoc_url=None)

# ── Static files ─────────────────────────────────────────────────────────────
_static_dist = Path(__file__).parent.parent / "static" / "dist"
_static_dist.mkdir(parents=True, exist_ok=True)
app.mount("/static/dist", StaticFiles(directory=str(_static_dist)), name="static_dist")

# ── Handler class initialisation (done once, lazily) ─────────────────────────
_handler_initialised = False


def _ensure_handler() -> None:
    global _handler_initialised
    if _handler_initialised:
        return
    from salmalm.web.web import WebHandler  # local import to avoid circulars

    FastHandler._GET_ROUTES = WebHandler._GET_ROUTES
    FastHandler._POST_ROUTES = WebHandler._POST_ROUTES
    FastHandler._GET_PREFIX_ROUTES = WebHandler._GET_PREFIX_ROUTES
    FastHandler._PUBLIC_PATHS = WebHandler._PUBLIC_PATHS
    FastHandler._TRUSTED_PROXY_NETS = WebHandler._TRUSTED_PROXY_NETS
    FastHandler._MAX_POST_SIZE = WebHandler._MAX_POST_SIZE
    _inject_mixin_methods(FastHandler, WebHandler)
    _handler_initialised = True


# ── Abuse-guard middleware (extracted from asgi.catch_all) ────────────────────

async def _abuse_guard(request: Request) -> Response | None:
    """Return a Response if the request should be blocked, else None."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff and os.environ.get("SALMALM_TRUST_PROXY"):
        client_ip = xff.split(",")[0].strip()
    else:
        client_ip = (request.client.host if request.client else None) or "unknown"

    # 1. IP ban
    is_banned, ban_remaining = ip_ban_list.is_banned(client_ip)
    if is_banned:
        return JSONResponse(
            {"error": "Too many requests. IP temporarily blocked.", "retry_after": ban_remaining},
            status_code=429,
            headers={"Retry-After": str(ban_remaining)},
        )

    # 2. Extract auth for role-based limiting
    auth_headers = {k.lower(): v for k, v in request.headers.items()}
    auth_user = extract_auth(auth_headers)
    role = auth_user.get("role", "anonymous") if auth_user else "anonymous"
    uid_key = str(auth_user["id"]) if auth_user else f"ip:{client_ip}"

    # 3. Global IP rate limit
    try:
        rate_limiter.check(f"ip:{client_ip}", "ip")
    except RateLimitExceeded as e:
        ip_ban_list.record_violation(client_ip)
        ra = int(e.retry_after)
        return JSONResponse(
            {"error": "Rate limit exceeded", "retry_after": ra},
            status_code=429,
            headers={"Retry-After": str(ra)},
        )

    # 4. Per-user rate limit
    if auth_user:
        try:
            rate_limiter.check(uid_key, role)
        except RateLimitExceeded as e:
            ra = int(e.retry_after)
            return JSONResponse(
                {"error": "Rate limit exceeded", "retry_after": ra},
                status_code=429,
                headers={"Retry-After": str(ra), "X-RateLimit-Role": role},
            )

    # 5. LLM-path tighter quota
    req_path_base = request.url.path.split("?")[0]
    is_llm = req_path_base in _LLM_PATHS or req_path_base.startswith("/api/agent/task")
    if is_llm and request.method in ("POST", "PUT", "PATCH"):
        try:
            llm_rate_limiter.check(uid_key, role)
        except RateLimitExceeded as e:
            ip_ban_list.record_violation(client_ip)
            ra = int(e.retry_after)
            return JSONResponse(
                {"error": "LLM rate limit exceeded", "retry_after": ra},
                status_code=429,
                headers={"Retry-After": str(ra)},
            )
        try:
            daily_quota.check(uid_key, role)
        except DailyQuotaExceeded as e:
            return JSONResponse(
                {"error": "Daily token quota exceeded", "used": e.used, "limit": e.limit, "retry_after": "tomorrow"},
                status_code=429,
                headers={"X-Quota-Used": str(e.used), "X-Quota-Limit": str(e.limit)},
            )
    return None


# ── Core dispatcher (used by every route handler) ────────────────────────────

async def _dispatch(
    request: Request,
    method: str,
    method_name: str | None = None,
    body_bytes: bytes | None = None,
) -> Response:
    """Create FastHandler, call the appropriate mixin method, return a Response."""
    _ensure_handler()
    set_correlation_id(str(uuid.uuid4())[:8])
    _start = time.time()

    # Guard
    guard_resp = await _abuse_guard(request)
    if guard_resp is not None:
        return guard_resp

    # Body
    if body_bytes is None:
        if method in ("POST", "PUT", "PATCH"):
            body_bytes = await request.body()
        else:
            body_bytes = b""

    handler = FastHandler(request, body_bytes)
    req_path = handler.path.split("?")[0]

    try:
        # SSE streaming path
        if method == "POST" and req_path == "/api/chat/stream":
            return await _handle_sse_stream(handler)

        if method_name:
            getattr(handler, method_name)()
        elif method == "GET":
            handler._do_get_inner()
        elif method == "POST":
            handler._do_post_inner()
        elif method == "PUT":
            handler._do_put_inner()
        else:
            raise _JSONResp({"error": "Method not allowed"}, 405)

        # Redirect
        if handler._streaming and 300 <= handler._resp_status < 400:
            location = handler._resp_headers.get("location", "/")
            return RedirectResponse(url=location, status_code=handler._resp_status)

        # Raw streaming (non-SSE — e.g. SW.js)
        if handler._streaming and not handler._sse_queue._q.empty():
            chunks = []
            q = handler._sse_queue._q
            while not q.empty():
                chunk = q.get_nowait()
                if chunk is not None:
                    chunks.append(chunk)
            ct = handler._resp_headers.get("content-type", "application/octet-stream")
            return Response(
                b"".join(chunks),
                media_type=ct,
                status_code=handler._resp_status,
                headers=_cors_headers(request),
            )

        return JSONResponse({"error": "No response"}, status_code=500)

    except _JSONResp as e:
        return JSONResponse(e.data, status_code=e.status, headers=_cors_headers(request))
    except _HTMLResp as e:
        return HTMLResponse(e.content, status_code=e.status)
    except _RawResp as e:
        return Response(e.body, media_type=e.content_type, status_code=e.status)
    except (BrokenPipeError, ConnectionResetError):
        return Response(status_code=499)
    except Exception as e:
        import traceback
        log.error(f"[APP] {method} {req_path}: {e}\n{traceback.format_exc()}")
        return JSONResponse(
            {"error": f"Internal error: {str(e)[:200]}"},
            status_code=500,
            headers=_cors_headers(request),
        )
    finally:
        duration = (time.time() - _start) * 1000
        ip = handler.client_address[0] if body_bytes is not None or method == "GET" else "unknown"
        try:
            request_logger.log_request(method, req_path, ip=ip, duration_ms=duration)
        except Exception:
            pass


# ── Route factory helpers ─────────────────────────────────────────────────────

def _make_get_handler(method_name: str) -> Callable:
    async def _handler(request: Request) -> Response:
        return await _dispatch(request, "GET", method_name)
    _handler.__name__ = method_name
    return _handler


def _make_post_handler(method_name: str) -> Callable:
    async def _handler(request: Request) -> Response:
        return await _dispatch(request, "POST", method_name)
    _handler.__name__ = method_name
    return _handler


def _make_prefix_get_handler(method_name: str) -> Callable:
    async def _handler(request: Request) -> Response:
        return await _dispatch(request, "GET", method_name)
    _handler.__name__ = f"prefix_{method_name}"
    return _handler


# ── Register routes from route tables ────────────────────────────────────────
# We import WebHandler once at module load to retrieve route tables.
# This mirrors what create_asgi_app() does in asgi.py.
# Using a deferred approach via a startup event to avoid circular imports at
# module-level (web.py imports from app.py indirectly via bootstrap).

_routes_registered = False


def _register_all_routes() -> None:
    global _routes_registered
    if _routes_registered:
        return
    _routes_registered = True

    _ensure_handler()

    from salmalm.web.web import WebHandler

    # ── Explicit GET routes ───────────────────────────────────────────────
    for path, method_name in WebHandler._GET_ROUTES.items():
        app.add_api_route(
            path,
            _make_get_handler(method_name),
            methods=["GET"],
            include_in_schema=False,
        )

    # ── Explicit POST routes ──────────────────────────────────────────────
    for path, method_name in WebHandler._POST_ROUTES.items():
        app.add_api_route(
            path,
            _make_post_handler(method_name),
            methods=["POST"],
            include_in_schema=False,
        )

    # ── Prefix GET routes (path-param style) ─────────────────────────────
    # Each entry is (prefix, method_name, suffix_or_None).
    # We register as /{full_path:path} catch-all for these prefix patterns.
    # FastAPI route specificity: explicit routes above take priority.
    prefix_handlers: dict[str, str] = {}
    for prefix, method_name, _suffix in WebHandler._GET_PREFIX_ROUTES:
        prefix_handlers.setdefault(prefix, method_name)

    for prefix, method_name in prefix_handlers.items():
        clean = prefix.rstrip("/").rstrip("?")
        fp = f"{clean}/{{rest:path}}" if prefix.endswith("/") else f"{clean}"
        app.add_api_route(
            fp,
            _make_prefix_get_handler(method_name),
            methods=["GET"],
            include_in_schema=False,
        )

    # ── SSE streaming endpoint (special) ─────────────────────────────────
    @app.post("/api/chat/stream", include_in_schema=False)
    async def _chat_stream(request: Request) -> Response:
        guard_resp = await _abuse_guard(request)
        if guard_resp is not None:
            return guard_resp
        body_bytes = await request.body()
        _ensure_handler()
        handler = FastHandler(request, body_bytes)
        return await _handle_sse_stream(handler)

    # ── Extra routes defined directly on WebHandler (not in dicts) ───────

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    async def _root(request: Request) -> Response:
        return await _dispatch(request, "GET")

    @app.get("/icon-192.svg", include_in_schema=False)
    @app.get("/icon-512.svg", include_in_schema=False)
    async def _icons(request: Request) -> Response:
        return await _dispatch(request, "GET")

    @app.put("/api/sessions/{session_id}/title", include_in_schema=False)
    async def _put_session_title(request: Request, session_id: str) -> Response:
        return await _dispatch(request, "PUT")

    # ── CORS preflight ────────────────────────────────────────────────────
    @app.options("/{full_path:path}", include_in_schema=False)
    async def _options(request: Request, full_path: str = "") -> Response:
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS,PATCH",
                "Access-Control-Allow-Headers": (
                    "Content-Type,Authorization,X-API-Key,"
                    "X-Session-Token,X-Requested-With"
                ),
                "Access-Control-Max-Age": "86400",
            },
        )

    # ── Catch-all fallback (404 for unregistered paths) ───────────────────
    @app.api_route(
        "/{full_path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        include_in_schema=False,
    )
    async def _catch_all(request: Request, full_path: str = "") -> Response:
        return await _dispatch(request, request.method)


@app.on_event("startup")
async def _on_startup() -> None:  # noqa: D401
    _register_all_routes()


# Also register synchronously for tests that import app without running uvicorn
try:
    _register_all_routes()
except Exception:
    pass  # will be retried on startup event


# ── Include FastAPI routers from route modules ────────────────────────────────
def _include_route_routers() -> None:
    """Include APIRouter instances from all route modules into the app."""
    from salmalm.web.routes import (
        web_system,
        web_model,
        web_engine,
        web_gateway,
        web_cron,
        web_features,
        web_manage,
        web_content,
        web_files,
        web_auth,
        web_users,
        web_setup,
        web_sessions,
        web_agents,
        web_chat,
    )
    for mod in [
        web_system, web_model, web_engine, web_gateway, web_cron,
        web_features, web_manage, web_content, web_files,
        web_auth, web_users, web_setup, web_sessions, web_agents, web_chat,
    ]:
        if hasattr(mod, "router"):
            app.include_router(mod.router)


try:
    _include_route_routers()
except Exception:
    pass
