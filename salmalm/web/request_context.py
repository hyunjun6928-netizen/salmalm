"""RequestContext — bridges FastAPI Request to WebHandler-style interface.

Allows existing Mixin methods (which use self._json, self._require_auth, etc.)
to run unchanged under FastAPI, via asyncio.to_thread().
"""
from __future__ import annotations

import io
import json
import os
from http.server import BaseHTTPRequestHandler
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response


class RequestContext(BaseHTTPRequestHandler):
    """Thin shim: wraps FastAPI Request as a BaseHTTPRequestHandler-compatible object."""

    def __init__(self, fastapi_request: Request, body_bytes: bytes = b""):
        # Skip BaseHTTPRequestHandler.__init__ (it calls handle() immediately)
        self.fastapi_request = fastapi_request
        self._body_bytes = body_bytes
        self.path = str(fastapi_request.url.path)
        if fastapi_request.url.query:
            self.path += "?" + fastapi_request.url.query
        self.headers = fastapi_request.headers  # type: ignore[assignment]
        self.command = fastapi_request.method
        self.rfile = io.BytesIO(body_bytes)
        self._response: Response | None = None
        self._response_started = False
        # Fake wfile (never used in FastAPI path)
        self.wfile = io.BytesIO()
        self.server = type("_S", (), {"server_address": ("", 0)})()
        # client_address used by _require_auth fallback
        client_ip = (
            fastapi_request.client.host if fastapi_request.client else "127.0.0.1"
        )
        self.client_address = (client_ip, 0)

    # ── Response helpers ───────────────────────────────────────────────────

    def _json(self, data: Any, status: int = 200) -> None:
        self._response = JSONResponse(content=data, status_code=status)

    def _html(self, content: str, status: int = 200) -> None:
        self._response = HTMLResponse(content=content, status_code=status)

    def _require_auth(self, min_role: str = "user") -> Optional[dict]:
        """Auth check using existing auth module, mirroring WebHandler._require_auth."""
        from salmalm.web.auth import auth_manager, extract_auth
        from salmalm.security.crypto import vault

        path = self.path.split("?")[0]

        # Check PUBLIC_PATHS if available via class attribute
        public_paths = getattr(self.__class__, "_PUBLIC_PATHS", set())
        if path in public_paths:
            return {"username": "public", "role": "public", "id": 0}

        user = extract_auth(dict(self.fastapi_request.headers))
        if user:
            role_rank = {"admin": 3, "user": 2, "readonly": 1}
            if role_rank.get(user.get("role", ""), 0) >= role_rank.get(min_role, 2):
                return user
            self._json({"error": "Insufficient permissions"}, 403)
            return None

        # Loopback fallback
        ip = self.client_address[0]
        bind = os.environ.get("SALMALM_BIND", "127.0.0.1")
        if bind in ("127.0.0.1", "localhost", "::1"):
            if ip in ("127.0.0.1", "::1", "localhost") and vault.is_unlocked:
                return {"username": "local", "role": "admin", "id": 0}

        self._json({"error": "Authentication required"}, 401)
        return None

    def _get_client_ip(self) -> str:
        return self.client_address[0]

    # ── Stub methods BaseHTTPRequestHandler needs ─────────────────────────
    def log_message(self, *a, **kw): pass
    def send_response(self, code, *a): pass
    def send_header(self, k, v): pass
    def end_headers(self): pass
    def handle(self): pass

    # ── Body helpers ──────────────────────────────────────────────────────
    def _read_body(self) -> bytes:
        return self._body_bytes

    def _json_body(self) -> dict:
        try:
            return json.loads(self._body_bytes or b"{}")
        except Exception:
            return {}
