from __future__ import annotations

"""SalmAlm WebSocket server — RFC 6455 over asyncio, pure stdlib.

Provides real-time bidirectional communication:
  - Chat messages (user ↔ bot)
  - Streaming responses (token-by-token)
  - Session events (tool calls, status updates)
  - Heartbeat/ping-pong keepalive

Protocol:
  Client sends JSON: {"type": "message", "text": "...", "session": "web"}
  Server sends JSON: {"type": "chunk"|"done"|"tool"|"error"|"pong", ...}
"""


import asyncio
import base64
import hashlib
import json
import struct
import time
from typing import Dict, Optional

from salmalm.constants import VERSION
from salmalm.security.crypto import log

# WebSocket opcodes
OP_CONT = 0x0
OP_TEXT = 0x1
OP_BIN = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

WS_MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _safe_task(coro, *, name: str = "") -> asyncio.Task:
    """Create a task with error logging (prevents silent fire-and-forget failures)."""
    task = asyncio.create_task(coro, name=name or None)
    task.add_done_callback(
        lambda t: log.warning("[TASK] %s raised: %s", t.get_name(), t.exception())
        if not t.cancelled() and t.exception() is not None
        else None
    )
    return task


class WSClient:
    """Represents a single WebSocket connection."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: str = "web") -> None:
        """Init  ."""
        self.reader = reader
        self.writer = writer
        self.session_id = session_id
        self.connected = True
        self.created_at = time.time()
        self.last_ping = time.time()
        self._id = id(self)
        self._send_lock = asyncio.Lock()  # Serialize concurrent sends
        self._buffer: list = []  # Buffer messages during disconnect (max 50, TTL 120s)
        self._buffer_ts: float = 0.0  # Timestamp when buffering started

    async def send_json(self, data: dict) -> None:
        """Send a JSON message as a WebSocket text frame.

        Serializes concurrent sends to prevent frame interleaving.
        Buffers messages if disconnected.
        """
        if not self.connected:
            # Buffer for potential reconnection (max 50)
            import time as _time_ws
            now = _time_ws.monotonic()
            # Start TTL clock on first buffered message
            if not self._buffer:
                self._buffer_ts = now
            # Discard buffer if TTL (120s) exceeded — client won't reconnect in time
            if now - self._buffer_ts > 120.0:
                self._buffer.clear()
                self._buffer_ts = now
            if len(self._buffer) < 50:
                self._buffer.append(data)
            return
        try:
            async with self._send_lock:
                payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
                await self._send_frame(OP_TEXT, payload)
        except Exception as e:  # noqa: broad-except
            self.connected = False

    async def send_text(self, text: str) -> None:
        """Send a text message to a connected WebSocket client."""
        if not self.connected:
            return
        try:
            await self._send_frame(OP_TEXT, text.encode("utf-8"))
        except Exception as e:  # noqa: broad-except
            self.connected = False

    async def _send_frame(self, opcode: int, data: bytes):
        """Send a WebSocket frame (server→client, no masking)."""
        length = len(data)
        header = bytes([0x80 | opcode])
        if length < 126:
            header += bytes([length])
        elif length < 65536:
            header += bytes([126]) + struct.pack("!H", length)
        else:
            header += bytes([127]) + struct.pack("!Q", length)
        self.writer.write(header + data)
        await self.writer.drain()

    async def recv_frame(self) -> Optional[tuple]:
        """Read one WebSocket frame. Returns (opcode, payload) or None on close."""
        try:
            b0, b1 = await self.reader.readexactly(2)
            opcode = b0 & 0x0F
            masked = b1 & 0x80
            length = b1 & 0x7F

            if length == 126:
                data = await self.reader.readexactly(2)
                length = struct.unpack("!H", data)[0]
            elif length == 127:
                data = await self.reader.readexactly(8)
                length = struct.unpack("!Q", data)[0]

            if length > 1 * 1024 * 1024:  # 1MB limit (reject oversized frames)
                log.warning(f"[WS] Rejecting oversized frame: {length} bytes")
                return None

            mask_key = None
            if masked:
                mask_key = await self.reader.readexactly(4)

            payload = await self.reader.readexactly(length) if length > 0 else b""

            if mask_key:
                # Fast XOR unmask using 4-byte block expansion
                mask_int = int.from_bytes(mask_key, "big")
                full_blocks = len(payload) // 4
                remainder = len(payload) % 4
                arr = bytearray(len(payload))
                for j in range(full_blocks):
                    off = j * 4
                    block = int.from_bytes(payload[off:off + 4], "big") ^ mask_int
                    arr[off:off + 4] = block.to_bytes(4, "big")
                for j in range(remainder):
                    arr[full_blocks * 4 + j] = payload[full_blocks * 4 + j] ^ mask_key[j]
                payload = bytes(arr)

            return (opcode, payload)
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            return None

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Send close frame and close connection."""
        if self.connected:
            self.connected = False
            try:
                payload = struct.pack("!H", code) + reason.encode("utf-8")[:123]
                await self._send_frame(OP_CLOSE, payload)
                self.writer.close()
                try:
                    await self.writer.wait_closed()
                except Exception as e:  # noqa: broad-except
                    log.debug(f"Suppressed: {e}")
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")


class WebSocketServer:
    """Async WebSocket server that handles upgrade from raw TCP."""

    def __init__(self, host: str = "127.0.0.1", port: int = 18801) -> None:
        """Init  ."""
        self.host = host
        self.port = port
        self.clients: Dict[int, WSClient] = {}
        self._server: Optional[asyncio.AbstractServer] = None
        self._on_message = None  # callback: async (client, data) -> None
        self._on_connect = None  # callback: async (client) -> None
        self._on_disconnect = None  # callback: async (client) -> None
        self._running = False

    def on_message(self, fn):
        """Handle an incoming WebSocket message."""
        self._on_message = fn
        return fn

    def on_connect(self, fn):
        """Handle a new WebSocket client connection."""
        self._on_connect = fn
        return fn

    def on_disconnect(self, fn):
        """Handle a WebSocket client disconnection."""
        self._on_disconnect = fn
        return fn

    async def start(self) -> None:
        """Start listening for WebSocket connections."""
        self._running = True
        self._server = await asyncio.start_server(self._handle_connection, self.host, self.port)
        log.info(f"[FAST] WebSocket server: ws://{self.host}:{self.port}")
        _safe_task(self._keepalive_loop(), name="ws-keepalive")

    async def shutdown(self) -> None:
        """Graceful shutdown: notify clients with shutdown message, then close."""
        self._running = False
        # Send shutdown notification to all connected clients
        for client in list(self.clients.values()):
            try:
                await client.send_json({"type": "shutdown", "message": "Server is shutting down..."})
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
        # Brief pause so clients can process the message
        await asyncio.sleep(0.5)
        # Close all connections
        for client in list(self.clients.values()):
            await client.close(1001, "Server shutdown")
        self.clients.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        log.info("[SHUTDOWN] WebSocket server stopped")

    async def stop(self) -> None:
        """Stop the WebSocket server (alias for shutdown)."""
        await self.shutdown()

    async def broadcast(self, data: dict, session_id: Optional[str] = None) -> None:
        """Send to all connected clients (or filtered by session)."""
        for client in list(self.clients.values()):
            if session_id and client.session_id != session_id:
                continue
            await client.send_json(data)

    @property
    def client_count(self) -> int:
        """Get the number of connected WebSocket clients."""
        return len(self.clients)

    async def _resume_and_register(self, client, writer, headers: dict) -> None:
        """Resume buffered messages from prior connection and register presence."""
        session_id = client.session_id
        for old_id, old_client in list(self.clients.items()):
            if (
                old_id != client._id
                and old_client.session_id == session_id
                and not old_client.connected
                and old_client._buffer
            ):
                log.info(f"[WS] Resuming {len(old_client._buffer)} buffered messages for session={session_id}")
                for buffered_msg in old_client._buffer:
                    try:
                        await client.send_json(buffered_msg)
                    except Exception:
                        break
                old_client._buffer.clear()
                self.clients.pop(old_id, None)
        try:
            from salmalm.features.presence import presence_manager

            peer = writer.get_extra_info("peername")
            ip = peer[0] if peer else ""
            presence_manager.register(
                f"ws_{client._id}",
                ip=ip,
                mode="websocket",
                host=headers.get("host", ""),
                user_agent=headers.get("user-agent", ""),
            )
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")

    async def _cleanup_client(self, client, writer) -> None:
        """Clean up disconnected WebSocket client."""
        client.connected = False
        self.clients.pop(client._id, None)
        try:
            from salmalm.features.presence import presence_manager

            presence_manager.unregister(f"ws_{client._id}")
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")
        if self._on_disconnect:
            try:
                await self._on_disconnect(client)
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
        try:
            writer.close()
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")
        log.info(f"[FAST] WS client disconnected (total={len(self.clients)})")

    async def _handle_text_frame(self, client, payload: bytes) -> None:
        """Handle a WebSocket text frame (JSON message)."""
        text = payload.decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning(f"[WS] Invalid JSON from client {client._id}")
            await client.send_json({"type": "error", "error": "Invalid JSON format / 잘못된 JSON 형식"})
            return
        if data.get("type") == "abort":
            try:
                from salmalm.features.edge_cases import abort_controller

                sid = data.get("session", client.session_id)
                abort_controller.set_abort(sid)
                await client.send_json({"type": "aborted", "session": sid})
            except Exception as e:
                log.warning(f"WS abort error: {e}")
            return
        if self._on_message:
            try:
                await self._on_message(client, data)
            except Exception as e:
                log.error(f"WS message handler error: {e}")
                await client.send_json({"type": "error", "error": str(e)[:200]})

    async def _ws_handshake(self, reader, writer) -> Optional[dict]:
        """Perform WebSocket HTTP upgrade handshake. Returns headers dict or None on failure."""
        try:
            request_lines = []
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=10)
                if line in (b"\r\n", b"\n", b""):
                    break
                request_lines.append(line.decode("utf-8", errors="replace").strip())
        except (asyncio.TimeoutError, ConnectionError):
            writer.close()
            return None
        if not request_lines:
            writer.close()
            return None
        headers = {}
        for line in request_lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        # ── WebSocket Abuse Guard ────────────────────────────────────────────
        peer = writer.get_extra_info("peername")
        _ws_ip = peer[0] if peer else "unknown"

        # IP ban check
        try:
            from salmalm.web.auth import ip_ban_list, rate_limiter, RateLimitExceeded
            _banned, _ban_rem = ip_ban_list.is_banned(_ws_ip)
            if _banned:
                writer.write(
                    f"HTTP/1.1 429 Too Many Requests\r\n"
                    f"Retry-After: {_ban_rem}\r\n"
                    f"Content-Length: 0\r\n\r\n".encode()
                )
                await writer.drain()
                writer.close()
                return None
            # IP-level connection rate limit (reuses the global rate_limiter "ip" bucket)
            rate_limiter.check(f"ip:{_ws_ip}", "ip")
        except RateLimitExceeded as _e:
            ip_ban_list.record_violation(_ws_ip)
            _ra = int(_e.retry_after)
            writer.write(
                f"HTTP/1.1 429 Too Many Requests\r\n"
                f"Retry-After: {_ra}\r\n"
                f"Content-Length: 0\r\n\r\n".encode()
            )
            await writer.drain()
            writer.close()
            return None
        except Exception as _guard_err:
            log.debug("[WS] Abuse guard skipped: %s", _guard_err)
        # ── End WebSocket Abuse Guard ────────────────────────────────────────

        # Validate Origin
        origin = headers.get("origin", "")
        if origin:
            from urllib.parse import urlparse

            o = urlparse(origin)
            if o.hostname and o.hostname not in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
                log.warning("WS rejected: origin %s not in allowlist", origin)
                writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                writer.close()
                return None
        # Extract session from request line (GET /ws?session=xxx HTTP/1.1)
        if request_lines and "?session=" in request_lines[0]:
            try:
                headers["_session_id"] = request_lines[0].split("?session=")[1].split()[0].split("&")[0]
            except Exception as e:
                log.debug(f"[WS] session ID parse failed: {e}")
        ws_key = headers.get("sec-websocket-key", "")
        if not ws_key or "upgrade" not in headers.get("connection", "").lower():
            writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            return None
        accept_val = base64.b64encode(hashlib.sha1(ws_key.encode() + WS_MAGIC).digest()).decode()
        handshake = (
            "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept_val}\r\n"
            f"X-Server: SalmAlm/{VERSION}\r\n\r\n"
        )
        writer.write(handshake.encode())
        await writer.drain()
        return headers

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming TCP connection — perform WS upgrade, then message loop."""
        headers = await self._ws_handshake(reader, writer)
        if headers is None:
            return

        # Parse session from headers (set by handshake)
        session_id = headers.get("_session_id", "web")

        client = WSClient(reader, writer, session_id)
        self.clients[client._id] = client
        log.info(f"[FAST] WS client connected (session={session_id}, total={len(self.clients)})")

        await self._resume_and_register(client, writer, headers)

        if self._on_connect:
            try:
                await self._on_connect(client)
            except Exception as e:
                log.error(f"WS on_connect error: {e}")

        # Message loop
        try:
            while client.connected and self._running:
                frame = await asyncio.wait_for(client.recv_frame(), timeout=120)
                if frame is None:
                    break

                opcode, payload = frame

                if opcode == OP_TEXT:
                    client.last_ping = time.time()  # Any activity = alive
                    # Fire-and-forget so recv loop continues reading PONG frames
                    _safe_task(self._handle_text_frame(client, payload), name="ws-frame")
                elif opcode == OP_PING:
                    await client._send_frame(OP_PONG, payload)
                    client.last_ping = time.time()
                elif opcode == OP_PONG:
                    client.last_ping = time.time()
                elif opcode == OP_CLOSE:
                    break

        except asyncio.TimeoutError:
            log.info(f"WS client timeout (id={client._id})")
        except Exception as e:
            log.error(f"WS client error: {e}")
        finally:
            await self._cleanup_client(client, writer)

    async def _keepalive_loop(self):
        """Ping clients every 30s, drop dead ones."""
        while self._running:
            await asyncio.sleep(30)
            now = time.time()
            dead = []
            for cid, client in list(self.clients.items()):
                if now - client.last_ping > 180:  # 180s ping timeout (long tool chains)
                    dead.append(cid)
                else:
                    try:
                        await client._send_frame(OP_PING, b"")
                    except Exception as e:  # noqa: broad-except
                        dead.append(cid)
            for cid in dead:
                c = self.clients.get(cid)
                if c:
                    c.connected = False
                    if c._buffer:
                        # Keep in clients dict so _resume_and_register can find buffered messages
                        log.info(f"[FAST] WS client suspended (timeout, {len(c._buffer)} buffered)")
                    else:
                        self.clients.pop(cid, None)
                        log.info("[FAST] WS client dropped (timeout)")


# ── Streaming response helper ──────────────────────────────────


class StreamingResponse:
    """Helper to stream LLM response chunks to a WS client."""

    def __init__(self, client: WSClient, request_id: Optional[str] = None) -> None:
        """Init  ."""
        self.client = client
        self.request_id = request_id or str(int(time.time() * 1000))
        self._chunks: list = []

    async def send_chunk(self, text: str) -> None:
        """Send a text chunk (partial response)."""
        self._chunks.append(text)
        await self.client.send_json(
            {
                "type": "chunk",
                "text": text,
                "rid": self.request_id,
            }
        )

    async def send_tool_call(self, tool_name: str, tool_input: dict, result: Optional[str] = None) -> None:
        """Notify client about a tool call."""
        await self.client.send_json(
            {
                "type": "tool",
                "name": tool_name,
                "input": tool_input,
                "result": result[:500] if result else None,
                "rid": self.request_id,
            }
        )

    async def send_thinking(self, text: str) -> None:
        """Send thinking/reasoning chunk."""
        await self.client.send_json(
            {
                "type": "thinking",
                "text": text,
                "rid": self.request_id,
            }
        )

    async def send_done(self, full_text: Optional[str] = None) -> None:
        """Signal completion."""
        if full_text is None:
            full_text = "".join(self._chunks)
        await self.client.send_json(
            {
                "type": "done",
                "text": full_text,
                "rid": self.request_id,
            }
        )

    async def send_error(self, error: str) -> None:
        """Send an error message to a WebSocket client."""
        await self.client.send_json(
            {
                "type": "error",
                "error": error,
                "rid": self.request_id,
            }
        )


# ── Module-level server instance ──────────────────────────────

ws_server = WebSocketServer()


# ── ASGI WebSocket handler (FastAPI/Starlette) ─────────────────────────────

class WebSocketHandler:
    """Bridges FastAPI/Starlette WebSocket to the SalmAlm engine.

    Used by asgi.py when running under uvicorn — replaces the raw-TCP
    WebSocketServer for the /ws endpoint.
    """

    async def handle(self, ws) -> None:  # ws: fastapi.WebSocket
        """Handle the full lifecycle of a FastAPI WebSocket connection."""
        from salmalm.constants import VERSION
        import time as _time

        session_id = "web"
        if ws.client:
            session_id = f"web_{ws.client.host}"

        try:
            await ws.send_json({"type": "welcome", "version": VERSION, "session": session_id})
        except Exception:
            return

        try:
            while True:
                try:
                    data = await ws.receive_json()
                except Exception:
                    break

                msg_type = data.get("type", "message")
                if msg_type == "ping":
                    await ws.send_json({"type": "pong"})
                    continue
                if msg_type != "message":
                    continue

                text = data.get("text", "").strip()
                image_b64 = data.get("image")
                image_mime = data.get("image_mime", "image/png")
                sid = data.get("session") or session_id

                if not text and not image_b64:
                    await ws.send_json({"type": "error", "error": "Empty message"})
                    continue

                await ws.send_json({"type": "typing", "status": "typing"})
                _start = _time.time()

                async def on_tool(name: str, args) -> None:
                    try:
                        await ws.send_json({"type": "tool_call", "name": name, "input": args})
                    except Exception as _e:
                        log.debug("[WS] on_tool send failed: %s", _e)

                async def on_status(status_type, detail) -> None:
                    try:
                        await ws.send_json({"type": "typing", "status": status_type, "detail": detail})
                    except Exception as _e:
                        log.debug("[WS] on_status send failed: %s", _e)

                try:
                    from salmalm.core.engine import process_message
                    from salmalm.core import get_session as _gs

                    _sess = _gs(sid)
                    _model_ov = getattr(_sess, "model_override", None)
                    if _model_ov == "auto":
                        _model_ov = None
                    image_data = (image_b64, image_mime) if image_b64 else None
                    response = await process_message(
                        sid,
                        text or "",
                        image_data=image_data,
                        model_override=_model_ov,
                        on_tool=on_tool,
                        on_status=on_status,
                    )
                    _elapsed = _time.time() - _start
                    await ws.send_json({"type": "done", "text": response, "elapsed": round(_elapsed, 2)})
                except Exception as e:
                    await ws.send_json({"type": "error", "error": str(e)[:200]})
        except Exception as _e:
            log.debug("[WS] WebSocketHandler outer loop exception: %s", _e)
