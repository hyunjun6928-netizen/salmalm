"""WebSocket server — FastAPI/Starlette based (single port with HTTP).

Replaces the old asyncio.start_server (port 18801) implementation.
WebSocket is now served on the same port as HTTP (default 18800) via
FastAPI's @app.websocket("/ws") route.

Public API is 100% backward-compatible:
  ws_server.broadcast(data, session_id=None)
  ws_server.client_count
  ws_server._running
  ws_server.on_message(fn)
  ws_server.on_connect(fn)
  ws_server.on_disconnect(fn)
  ws_server.start() / ws_server.shutdown()  — no-ops (FastAPI owns lifecycle)
  StreamingResponse                          — interface unchanged
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable, Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

log = logging.getLogger(__name__)

# ── Legacy constants (kept for backward compatibility with tests/callers) ──
OP_CONT = 0x0
OP_TEXT = 0x1
OP_BIN = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA
WS_MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


# ── Connection manager ─────────────────────────────────────────────────────


class WSConnectionManager:
    """Tracks all active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}  # session_id → WebSocket
        self._all: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, session_id: str = "web") -> None:
        await ws.accept()
        async with self._lock:
            self._connections[session_id] = ws
            self._all.add(ws)

    async def disconnect(self, ws: WebSocket, session_id: str = "web") -> None:
        async with self._lock:
            self._connections.pop(session_id, None)
            self._all.discard(ws)

    async def send_json(self, ws: WebSocket, data: dict) -> None:
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_json(data)
        except Exception as e:
            log.debug(f"[WS] send_json failed: {e}")

    async def broadcast(self, data: dict, session_id: Optional[str] = None) -> None:
        if session_id and session_id in self._connections:
            await self.send_json(self._connections[session_id], data)
            return
        dead: Set[WebSocket] = set()
        for ws in list(self._all):
            try:
                await self.send_json(ws, data)
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                self._all -= dead


# ── Client adapter (presents old WSClient interface) ──────────────────────


class _WSClientAdapter:
    """Thin wrapper over Starlette WebSocket that mimics the old WSClient API."""

    def __init__(self, ws: WebSocket, session_id: str = "web") -> None:
        self._ws = ws
        self.session_id = session_id
        self.connected_at = time.time()
        self.connected = True  # legacy compat

    async def send_json(self, data: dict) -> None:
        try:
            await self._ws.send_json(data)
        except Exception as e:
            log.debug(f"[WS] send_json: {e}")

    async def send_text(self, text: str) -> None:
        try:
            await self._ws.send_text(text)
        except Exception as e:
            log.debug(f"[WS] send_text: {e}")

    async def close(self, code: int = 1000, reason: str = "") -> None:
        try:
            await self._ws.close(code=code)
        except Exception:
            pass


# ── Main server class (drop-in replacement) ───────────────────────────────


class WebSocketServer:
    """Drop-in replacement for the old asyncio-TCP WebSocketServer.

    The public API is identical; internally this delegates to FastAPI/Starlette
    so no separate port or server process is needed.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 18800) -> None:
        self._manager = WSConnectionManager()
        self._running = False
        self._message_handlers: list[Callable] = []
        self._connect_handlers: list[Callable] = []
        self._disconnect_handlers: list[Callable] = []
        self.port = port
        self.host = host

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def client_count(self) -> int:
        return len(self._manager._all)

    def on_message(self, fn: Callable) -> Callable:
        self._message_handlers.append(fn)
        return fn

    def on_connect(self, fn: Callable) -> Callable:
        self._connect_handlers.append(fn)
        return fn

    def on_disconnect(self, fn: Callable) -> Callable:
        self._disconnect_handlers.append(fn)
        return fn

    async def start(self) -> None:
        """No-op — FastAPI/uvicorn owns the server lifecycle."""
        self._running = True
        log.info(f"[WS] WebSocket ready at ws://{self.host}:{self.port}/ws")

    async def shutdown(self) -> None:
        self._running = False
        log.info("[WS] WebSocket server shutdown")

    async def stop(self) -> None:
        await self.shutdown()

    async def broadcast(self, data: dict, session_id: Optional[str] = None) -> None:
        await self._manager.broadcast(data, session_id)

    # ── FastAPI route handler ─────────────────────────────────────────────

    async def handle_connection(self, websocket: WebSocket) -> None:
        """Entry point called by @app.websocket('/ws')."""
        session_id = websocket.query_params.get("session", "web")
        client = _WSClientAdapter(websocket, session_id)

        await self._manager.connect(websocket, session_id)

        for handler in self._connect_handlers:
            try:
                result = handler(client)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                log.debug(f"[WS] on_connect error: {e}")

        try:
            while True:
                try:
                    text = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                except asyncio.TimeoutError:
                    try:
                        await websocket.send_json({"type": "ping"})
                    except Exception:
                        break
                    continue

                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = {"type": "text", "text": text}

                # Abort shortcut (keep parity with legacy handler)
                if data.get("type") == "abort":
                    try:
                        from salmalm.features.edge_cases import abort_controller
                        sid = data.get("session", session_id)
                        abort_controller.set_abort(sid)
                        await websocket.send_json({"type": "aborted", "session": sid})
                    except Exception as e:
                        log.warning(f"[WS] abort error: {e}")
                    continue

                for handler in self._message_handlers:
                    try:
                        result = handler(client, data)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        log.debug(f"[WS] on_message error: {e}")

        except WebSocketDisconnect:
            pass
        except Exception as e:
            log.debug(f"[WS] connection error: {e}")
        finally:
            await self._manager.disconnect(websocket, session_id)
            for handler in self._disconnect_handlers:
                try:
                    result = handler(client)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    log.debug(f"[WS] on_disconnect error: {e}")


# ── Streaming response helper ─────────────────────────────────────────────


class StreamingResponse:
    """Stream LLM responses over WebSocket. Interface unchanged from legacy."""

    def __init__(self, client: _WSClientAdapter, request_id: Optional[str] = None) -> None:
        self._client = client
        self.request_id = request_id or str(int(time.time() * 1000))
        self._request_id = self.request_id  # alias for internal use
        self._chunks: list[str] = []

    async def send_chunk(self, text: str) -> None:
        self._chunks.append(text)
        await self._client.send_json(
            {"type": "chunk", "text": text, "streaming": True, "rid": self._request_id}
        )

    async def send_tool_call(
        self, tool_name: str, tool_input: dict, result: Optional[str] = None
    ) -> None:
        await self._client.send_json(
            {
                "type": "tool",
                "name": tool_name,
                "input": tool_input,
                "result": result[:500] if result else None,
                "rid": self._request_id,
            }
        )

    async def send_thinking(self, text: str) -> None:
        await self._client.send_json(
            {"type": "thinking", "text": text, "rid": self._request_id}
        )

    async def send_done(self, full_text: Optional[str] = None) -> None:
        if full_text is None:
            full_text = "".join(self._chunks)
        await self._client.send_json(
            {"type": "done", "text": full_text, "rid": self._request_id}
        )

    async def send_error(self, error: str) -> None:
        await self._client.send_json(
            {"type": "error", "error": error, "rid": self._request_id}
        )

    async def send_status(self, text: str) -> None:
        await self._client.send_json(
            {"type": "status", "text": text, "rid": self._request_id}
        )


# ── Legacy WSClient shim (backward compat for tests / callers) ───────────


class WSClient(_WSClientAdapter):
    """Legacy class name kept for backward compatibility.

    Old signature: WSClient(reader, writer, session_id="web")
    The reader/writer args are accepted but ignored (no raw TCP anymore).
    """

    def __init__(self, reader, writer, session_id: str = "web") -> None:  # type: ignore[override]
        # Pass a sentinel; real WS is unused in compat mode
        super().__init__(ws=None, session_id=session_id)  # type: ignore[arg-type]
        self.reader = reader
        self.writer = writer
        self.created_at = time.time()
        self.last_ping = time.time()
        self._id = id(self)
        self._send_lock = asyncio.Lock()
        self._buffer: list = []
        self._buffer_ts: float = 0.0

    async def send_json(self, data: dict) -> None:  # type: ignore[override]
        # In compat/test mode there's no real websocket
        log.debug(f"[WSClient-compat] send_json: {data}")

    async def send_text(self, text: str) -> None:  # type: ignore[override]
        log.debug(f"[WSClient-compat] send_text: {text}")

    async def close(self, code: int = 1000, reason: str = "") -> None:  # type: ignore[override]
        self.connected = False


# ── Module-level singleton ────────────────────────────────────────────────

ws_server = WebSocketServer()
