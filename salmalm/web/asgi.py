"""ASGI application — FastAPI + uvicorn transport layer.

Adapter pattern: FastHandler subclasses WebHandler but skips
BaseHTTPRequestHandler.__init__, overriding _json/_html/wfile so all
existing mixin route handlers work without modification.

SSE streaming: sync wfile.write() calls are bridged to an async
generator via a thread-safe queue, so uvicorn's event loop never blocks.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import queue
import time
from typing import AsyncIterator

from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from salmalm.security.crypto import log
from salmalm.utils.logging_ext import request_logger, set_correlation_id
from salmalm.web.auth import (
    rate_limiter, llm_rate_limiter, ip_ban_list,
    RateLimitExceeded, extract_auth,
)
import uuid

# LLM-triggering paths that get the tighter LLMRateLimiter bucket
_LLM_PATHS: frozenset = frozenset({
    "/api/chat",
    "/api/chat/stream",
    "/api/chat/abort",
    "/api/chat/regenerate",
    "/api/chat/compare",
    "/api/ask",
})


# ── Response signal exceptions ─────────────────────────────────────────────

class _JSONResp(BaseException):
    """Signals a JSON response — inherits BaseException so that
    'except Exception' blocks in mixin route handlers do NOT catch it.
    (e.g. try: do_work(); self._json(ok); except Exception: self._json(fail)
     would incorrectly treat the successful _json raise as a failure.)"""
    def __init__(self, data: dict, status: int = 200):
        self.data = data
        self.status = status


class _HTMLResp(BaseException):
    def __init__(self, content: str, status: int = 200):
        self.content = content
        self.status = status


class _RawResp(BaseException):
    """Raw bytes response (SVG, JS, etc.)."""
    def __init__(self, body: bytes, content_type: str, status: int = 200):
        self.body = body
        self.content_type = content_type
        self.status = status


# ── SSE queue bridge ────────────────────────────────────────────────────────

class _SSEQueue:
    """Bridges sync wfile.write() calls into an async StreamingResponse.

    The SSE handler thread calls write() synchronously.
    The async generate() coroutine polls the queue without blocking the event loop.
    """

    _SENTINEL = None

    def __init__(self) -> None:
        self._q: queue.SimpleQueue = queue.SimpleQueue()

    def write(self, data: bytes) -> int:
        self._q.put(data)
        return len(data)

    def flush(self) -> None:
        pass  # each write is immediately available

    def close(self) -> None:
        """Signal generator to stop."""
        self._q.put(self._SENTINEL)


# ── Case-insensitive header dict ────────────────────────────────────────────

class _CIHeaders(dict):
    """Case-insensitive header lookup (mirrors http.server.BaseHTTPRequestHandler.headers)."""

    def get(self, key, default=None):
        return super().get(key.lower(), super().get(key, default))

    def __getitem__(self, key):
        try:
            return super().__getitem__(key.lower())
        except KeyError:
            return super().__getitem__(key)

    def __contains__(self, key):
        return super().__contains__(key.lower()) or super().__contains__(key)


# ── FastHandler ─────────────────────────────────────────────────────────────

class FastHandler:
    """ASGI-compatible handler that mimics BaseHTTPRequestHandler interface.

    Subclasses all existing WebHandler mixin route classes so every route
    method (e.g. _get_api_status, _post_api_chat) works without modification.

    Key differences from WebHandler:
    - _json() raises _JSONResp instead of writing to wfile directly
    - _html() raises _HTMLResp
    - wfile delegates to _SSEQueue for SSE streaming
    - BaseHTTPRequestHandler.__init__ is never called
    """

    # ── Class-level route tables (copied from WebHandler at app creation) ──
    _GET_ROUTES: dict = {}
    _POST_ROUTES: dict = {}
    _GET_PREFIX_ROUTES: list = []
    _PUBLIC_PATHS: set = set()
    _TRUSTED_PROXY_NETS: tuple = ()
    _MAX_POST_SIZE: int = 10 * 1024 * 1024

    def __init__(self, starlette_request: Request, body_bytes: bytes = b"") -> None:
        # ── Replicate the attributes BaseHTTPRequestHandler would set ──
        self.path = starlette_request.url.path
        if starlette_request.url.query:
            self.path += "?" + starlette_request.url.query

        # Case-insensitive headers dict
        self.headers = _CIHeaders(
            {k.lower(): v for k, v in starlette_request.headers.items()}
        )
        self.command = starlette_request.method

        # Client address tuple (host, port)
        client = starlette_request.client
        self.client_address = (client.host if client else "127.0.0.1", 0)

        # Request body as file-like object (used by _do_post_inner)
        self.rfile = io.BytesIO(body_bytes)
        self._body_bytes = body_bytes
        self._body_parsed: dict | None = None
        self._content_length = len(body_bytes)

        # SSE streaming state
        self._sse_queue = _SSEQueue()
        self._streaming = False
        self._resp_status = 200
        self._resp_headers: dict = {}

        # Store original request for multipart/upload handling
        self._starlette_request = starlette_request

        # CSP nonce (no-op in ASGI mode)
        self._csp_nonce = ""

    # ── Body property (mirrors _do_post_inner's self._body = body) ──────────

    @property
    def _body(self) -> dict:
        if self._body_parsed is None:
            try:
                self._body_parsed = json.loads(self._body_bytes) if self._body_bytes else {}
            except Exception:
                self._body_parsed = {}
        return self._body_parsed

    @_body.setter
    def _body(self, value: dict) -> None:
        self._body_parsed = value

    # ── Response methods (raise exceptions instead of writing to socket) ────

    def _json(self, data: dict, status: int = 200) -> None:
        raise _JSONResp(data, status)

    def _html(self, content: str, status: int = 200) -> None:
        raise _HTMLResp(content, status)

    def _cors(self) -> None:
        """No-op — CORS handled by FastAPI middleware."""

    def _security_headers(self) -> None:
        """No-op — security headers added by middleware."""

    def _maybe_gzip(self, body: bytes) -> bytes:
        """No-op — uvicorn handles compression."""
        return body

    def send_error(self, code: int, message: str = "", *args) -> None:
        raise _JSONResp({"error": message or f"HTTP {code}"}, code)

    def log_message(self, *args) -> None:
        pass  # suppress http.server log

    def log_error(self, *args) -> None:
        pass

    # ── Raw streaming interface (for SSE) ───────────────────────────────────

    def send_response(self, status: int) -> None:
        self._streaming = True
        self._resp_status = status

    def send_header(self, key: str, value: str) -> None:
        self._resp_headers[key.lower()] = value

    def end_headers(self) -> None:
        pass  # headers finalised when StreamingResponse is built

    @property
    def wfile(self) -> _SSEQueue:
        return self._sse_queue

    # ── IP / auth helpers ────────────────────────────────────────────────────

    def _get_client_ip(self) -> str:
        remote_addr = self.client_address[0]
        if os.environ.get("SALMALM_TRUST_PROXY"):
            is_trusted = any(remote_addr.startswith(net) for net in self._TRUSTED_PROXY_NETS)
            if is_trusted:
                xff = self.headers.get("x-forwarded-for")
                if xff:
                    return xff.split(",")[0].strip()
        return remote_addr

    def _check_origin(self) -> bool:
        origin = self.headers.get("origin", "")
        if not origin:
            return True
        port = int(os.environ.get("SALMALM_PORT", 18800))
        allowed = {
            f"http://127.0.0.1:{port}", f"http://localhost:{port}",
            f"https://127.0.0.1:{port}", f"https://localhost:{port}",
        }
        return origin in allowed

    def _check_rate_limit(self) -> bool:
        return True  # delegate to middleware if needed


# ── ASGI App Factory ─────────────────────────────────────────────────────────

def create_asgi_app() -> FastAPI:
    """Build and return the FastAPI ASGI application."""
    from salmalm.web.web import WebHandler  # import here to avoid circular

    # Copy class-level attributes from WebHandler so FastHandler's dispatch works
    FastHandler._GET_ROUTES = WebHandler._GET_ROUTES
    FastHandler._POST_ROUTES = WebHandler._POST_ROUTES
    FastHandler._GET_PREFIX_ROUTES = WebHandler._GET_PREFIX_ROUTES
    FastHandler._PUBLIC_PATHS = WebHandler._PUBLIC_PATHS
    FastHandler._TRUSTED_PROXY_NETS = WebHandler._TRUSTED_PROXY_NETS
    FastHandler._MAX_POST_SIZE = WebHandler._MAX_POST_SIZE

    # Inject all mixin bases into FastHandler dynamically
    # FastHandler needs: all WebHandler mixins + WebHandler dispatch methods
    # We do this by copying __dict__ methods from WebHandler onto FastHandler
    _inject_mixin_methods(FastHandler, WebHandler)

    app = FastAPI(title="SalmAlm", docs_url=None, redoc_url=None)

    # ── Static files (React bundles, dist assets) ───────────────────────────
    _static_dist = Path(__file__).parent.parent / "static" / "dist"
    _static_dist.mkdir(parents=True, exist_ok=True)
    app.mount("/static/dist", StaticFiles(directory=str(_static_dist)), name="static_dist")

    # ── WebSocket note ──────────────────────────────────────────────────────
    # WebSocket runs as a separate asyncio TCP server on port 18801 (ws.py).
    # Clients connect directly to ws://host:18801 — no ASGI WS route needed.

    # ── HTTP catch-all ──────────────────────────────────────────────────────
    @app.api_route(
        "/{full_path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    )
    async def catch_all(request: Request, full_path: str = ""):
        set_correlation_id(str(uuid.uuid4())[:8])
        _start = time.time()
        method = request.method

        # CORS preflight
        if method == "OPTIONS":
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

        # ── Abuse Guard ──────────────────────────────────────────────────────
        # Resolve client IP (trust X-Forwarded-For only when proxy env is set)
        _xff = request.headers.get("x-forwarded-for", "")
        if _xff and os.environ.get("SALMALM_TRUST_PROXY"):
            _client_ip = _xff.split(",")[0].strip()
        else:
            _client_ip = (request.client.host if request.client else None) or "unknown"

        # 1. IP ban check — hard block before any further processing
        _is_banned, _ban_remaining = ip_ban_list.is_banned(_client_ip)
        if _is_banned:
            return JSONResponse(
                {"error": "Too many requests. IP temporarily blocked.",
                 "retry_after": _ban_remaining},
                status_code=429,
                headers={"Retry-After": str(_ban_remaining)},
            )

        # 2. Extract auth token for role-based limiting
        _auth_headers = {k.lower(): v for k, v in request.headers.items()}
        _auth_user = extract_auth(_auth_headers)
        _role = (_auth_user.get("role", "anonymous") if _auth_user else "anonymous")
        _uid_key = (str(_auth_user["id"]) if _auth_user else f"ip:{_client_ip}")

        # 3. Global IP-level rate limit (protects against unauthenticated flood)
        try:
            rate_limiter.check(f"ip:{_client_ip}", "ip")
        except RateLimitExceeded as _e:
            ip_ban_list.record_violation(_client_ip)
            _ra = int(_e.retry_after)
            return JSONResponse(
                {"error": "Rate limit exceeded", "retry_after": _ra},
                status_code=429,
                headers={"Retry-After": str(_ra)},
            )

        # 4. Per-user role-based rate limit
        if _auth_user:
            try:
                rate_limiter.check(_uid_key, _role)
            except RateLimitExceeded as _e:
                _ra = int(_e.retry_after)
                return JSONResponse(
                    {"error": "Rate limit exceeded", "retry_after": _ra},
                    status_code=429,
                    headers={
                        "Retry-After": str(_ra),
                        "X-RateLimit-Role": _role,
                    },
                )

        # 5. LLM-path tighter quota — cost-protection for chat/agent endpoints
        _req_path_base = request.url.path.split("?")[0]
        _is_llm_path = (
            _req_path_base in _LLM_PATHS
            or _req_path_base.startswith("/api/agent/task")
        )
        if _is_llm_path and method in ("POST", "PUT", "PATCH"):
            try:
                llm_rate_limiter.check(_uid_key, _role)
            except RateLimitExceeded as _e:
                ip_ban_list.record_violation(_client_ip)
                _ra = int(_e.retry_after)
                return JSONResponse(
                    {"error": "LLM rate limit exceeded", "retry_after": _ra},
                    status_code=429,
                    headers={"Retry-After": str(_ra)},
                )
        # ── End Abuse Guard ──────────────────────────────────────────────────

        # Read body for write methods
        body_bytes = b""
        if method in ("POST", "PUT", "PATCH"):
            content_length = int(request.headers.get("content-length", 0))
            # /api/upload allows up to 50 MB; all other endpoints cap at 10 MB
            _is_upload = request.url.path == "/api/upload"
            _max_body = 50 * 1024 * 1024 if _is_upload else 10 * 1024 * 1024
            if content_length > _max_body:
                return JSONResponse({"error": "Request too large"}, status_code=413)
            body_bytes = await request.body()

        handler = FastHandler(request, body_bytes)
        req_path = handler.path.split("?")[0]

        try:
            # ── SSE streaming path (must be caught before generic dispatch) ──
            if method == "POST" and req_path == "/api/chat/stream":
                return await _handle_sse_stream(handler)

            # ── Generic dispatch ─────────────────────────────────────────────
            if method == "GET":
                handler._do_get_inner()
            elif method == "POST":
                handler._do_post_inner()
            elif method == "PUT":
                handler._do_put_inner()
            else:
                raise _JSONResp({"error": "Method not allowed"}, 405)

            # ── Redirect response (302/301/307/308) ──────────────────────────
            if handler._streaming and 300 <= handler._resp_status < 400:
                location = handler._resp_headers.get("location", "/")
                from starlette.responses import RedirectResponse
                return RedirectResponse(url=location, status_code=handler._resp_status)

            # If handler returned normally (raw wfile writes for non-SSE streams like SW.js)
            if handler._streaming and not handler._sse_queue._q.empty():
                chunks = []
                q = handler._sse_queue._q
                while not q.empty():
                    chunk = q.get_nowait()
                    if chunk is not None:
                        chunks.append(chunk)
                ct = handler._resp_headers.get("content-type", "application/octet-stream")
                return Response(b"".join(chunks), media_type=ct,
                                status_code=handler._resp_status,
                                headers=_cors_headers(request))

            return JSONResponse({"error": "No response"}, status_code=500)

        except _JSONResp as e:
            return JSONResponse(e.data, status_code=e.status,
                                headers=_cors_headers(request))
        except _HTMLResp as e:
            return HTMLResponse(e.content, status_code=e.status)
        except _RawResp as e:
            return Response(e.body, media_type=e.content_type,
                            status_code=e.status)
        except (BrokenPipeError, ConnectionResetError):
            return Response(status_code=499)  # client disconnected
        except Exception as e:
            import traceback
            log.error(f"[ASGI] {method} {req_path}: {e}\n{traceback.format_exc()}")
            return JSONResponse({"error": f"Internal error: {str(e)[:200]}"},
                                status_code=500,
                                headers=_cors_headers(request))
        finally:
            duration = (time.time() - _start) * 1000
            ip = handler.client_address[0]
            request_logger.log_request(method, req_path, ip=ip, duration_ms=duration)

    return app


# ── SSE async bridge ─────────────────────────────────────────────────────────

async def _handle_sse_stream(handler: FastHandler) -> StreamingResponse:
    """Run SSE handler in thread-pool, yield chunks via async generator.

    The handler writes to handler.wfile (an _SSEQueue). The async generator
    reads from that queue without blocking uvicorn's event loop.
    """
    sse_q = handler.wfile  # ensure queue exists

    def _run_handler() -> None:
        try:
            handler._post_api_chat()
        except _JSONResp as resp_err:
            # _post_api_chat called self._json() for an early error (e.g. vault locked,
            # bad request). Convert to SSE error event.
            try:
                err_payload = f"event: error\ndata: {json.dumps(resp_err.data)}\n\n"
                sse_q.write(err_payload.encode())
            except Exception:
                pass
        except (_HTMLResp, _RawResp):
            pass  # Not expected from chat handler; just close the stream
        except Exception as e:
            log.error(f"[SSE] handler error: {e}")
            try:
                err_payload = f"event: error\ndata: {json.dumps({'text': str(e)[:200]})}\n\n"
                sse_q.write(err_payload.encode())
            except Exception:
                pass
        finally:
            sse_q.close()  # always signal end

    loop = asyncio.get_event_loop()
    thread_future = loop.run_in_executor(None, _run_handler)

    async def generate() -> AsyncIterator[bytes]:
        while True:
            try:
                # Poll queue in executor (non-blocking for event loop)
                chunk = await loop.run_in_executor(None, sse_q._q.get)
                if chunk is _SSEQueue._SENTINEL:
                    break
                yield chunk
            except Exception:
                break
        # Ensure thread finishes cleanly
        try:
            await asyncio.wait_for(thread_future, timeout=5.0)
        except asyncio.TimeoutError:
            pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx proxy buffering
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── Helper: inject mixin methods from WebHandler ─────────────────────────────

def _inject_mixin_methods(target_cls, source_cls) -> None:
    """Copy all methods from source_cls MRO (including source_cls itself,
    excluding BaseHTTPRequestHandler and object) into target_cls so all
    route handlers and dispatch methods are available on FastHandler.

    IMPORTANT: source_cls (WebHandler) is now included so that methods
    defined directly on it (_do_get_inner, _do_post_inner, _require_auth,
    _get_static_app_js, etc.) are copied in.  FastHandler's own override
    methods are protected by the exclusion list below.
    """
    import http.server
    import socketserver

    skip_bases = {
        http.server.BaseHTTPRequestHandler,
        socketserver.StreamRequestHandler,
        socketserver.BaseRequestHandler,
        object,
    }

    # Methods that FastHandler overrides — never overwrite these
    _protected = frozenset({
        "__init__", "_json", "_html", "_cors", "_security_headers",
        "_maybe_gzip", "send_response", "send_header", "end_headers",
        "send_error", "wfile", "_get_client_ip", "_check_origin",
        "_check_rate_limit", "log_message", "log_error",
    })

    for base in reversed(source_cls.__mro__):
        if base in skip_bases or base is target_cls:
            continue  # NOTE: source_cls (WebHandler) is intentionally included
        for name, val in base.__dict__.items():
            if name.startswith("__") and name not in ("__init__",):
                continue
            if name in _protected:
                continue  # keep FastHandler's own implementations
            # setattr always (later bases in reversed MRO override earlier ones,
            # matching normal Python MRO resolution order)
            setattr(target_cls, name, val)


# ── CORS helper ───────────────────────────────────────────────────────────────

def _cors_headers(request: Request) -> dict:
    origin = request.headers.get("origin", "")
    if not origin:
        return {}
    port = int(os.environ.get("SALMALM_PORT", 18800))
    allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    if origin in allowed:
        return {"Access-Control-Allow-Origin": origin}
    return {}
