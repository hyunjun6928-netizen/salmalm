"""Utilities for wrapping WebHandler Mixin methods as FastAPI route handlers."""
from __future__ import annotations

import asyncio

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from .request_context import RequestContext


async def handle(request: Request, method_name: str, handler_cls) -> Response:
    """Run a Mixin method via RequestContext in a thread pool."""
    body = await request.body()
    ctx = RequestContext(request, body)

    # Propagate class-level attributes (PUBLIC_PATHS etc.) for _require_auth
    for attr in ("_PUBLIC_PATHS", "_TRUSTED_PROXY_NETS", "_MAX_POST_SIZE"):
        if hasattr(handler_cls, attr) and not hasattr(RequestContext, attr):
            setattr(RequestContext, attr, getattr(handler_cls, attr))

    bound = getattr(handler_cls, method_name)
    await asyncio.to_thread(bound, ctx)
    if ctx._response is not None:
        return ctx._response
    return JSONResponse({"error": "No response"}, status_code=500)
