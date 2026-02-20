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
from salmalm.crypto import log

# WebSocket opcodes
OP_CONT = 0x0
OP_TEXT = 0x1
OP_BIN = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

WS_MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WSClient:
    """Represents a single WebSocket connection."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 session_id: str = "web"):
        self.reader = reader
        self.writer = writer
        self.session_id = session_id
        self.connected = True
        self.created_at = time.time()
        self.last_ping = time.time()
        self._id = id(self)
        self._send_lock = asyncio.Lock()  # Serialize concurrent sends
        self._buffer: list = []  # Buffer messages during disconnect

    async def send_json(self, data: dict):
        """Send a JSON message as a WebSocket text frame.

        Serializes concurrent sends to prevent frame interleaving.
        Buffers messages if disconnected.
        """
        if not self.connected:
            # Buffer for potential reconnection (max 50)
            if len(self._buffer) < 50:
                self._buffer.append(data)
            return
        try:
            async with self._send_lock:
                payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
                await self._send_frame(OP_TEXT, payload)
        except Exception:
            self.connected = False

    async def send_text(self, text: str):
        """Send a text message to a connected WebSocket client."""
        if not self.connected:
            return
        try:
            await self._send_frame(OP_TEXT, text.encode('utf-8'))
        except Exception:
            self.connected = False

    async def _send_frame(self, opcode: int, data: bytes):
        """Send a WebSocket frame (server→client, no masking)."""
        length = len(data)
        header = bytes([0x80 | opcode])
        if length < 126:
            header += bytes([length])
        elif length < 65536:
            header += bytes([126]) + struct.pack('!H', length)
        else:
            header += bytes([127]) + struct.pack('!Q', length)
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
                length = struct.unpack('!H', data)[0]
            elif length == 127:
                data = await self.reader.readexactly(8)
                length = struct.unpack('!Q', data)[0]

            if length > 1 * 1024 * 1024:  # 1MB limit (reject oversized frames)
                log.warning(f"[WS] Rejecting oversized frame: {length} bytes")
                return None

            mask_key = None
            if masked:
                mask_key = await self.reader.readexactly(4)

            payload = await self.reader.readexactly(length) if length > 0 else b''

            if mask_key:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            return (opcode, payload)
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            return None

    async def close(self, code: int = 1000, reason: str = ""):
        """Send close frame and close connection."""
        if self.connected:
            self.connected = False
            try:
                payload = struct.pack('!H', code) + reason.encode('utf-8')[:123]
                await self._send_frame(OP_CLOSE, payload)
                self.writer.close()
                try:
                    await self.writer.wait_closed()
                except Exception:
                    pass
            except Exception:
                pass


class WebSocketServer:
    """Async WebSocket server that handles upgrade from raw TCP."""

    def __init__(self, host: str = "127.0.0.1", port: int = 18801):
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

    async def start(self):
        """Start listening for WebSocket connections."""
        self._running = True
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port
        )
        log.info(f"[FAST] WebSocket server: ws://{self.host}:{self.port}")
        asyncio.create_task(self._keepalive_loop())

    async def shutdown(self):
        """Graceful shutdown: notify clients with shutdown message, then close."""
        self._running = False
        # Send shutdown notification to all connected clients
        for client in list(self.clients.values()):
            try:
                await client.send_json({"type": "shutdown",
                                        "message": "Server is shutting down..."})
            except Exception:
                pass
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

    async def stop(self):
        """Stop the WebSocket server (alias for shutdown)."""
        await self.shutdown()

    async def broadcast(self, data: dict, session_id: Optional[str] = None):
        """Send to all connected clients (or filtered by session)."""
        for client in list(self.clients.values()):
            if session_id and client.session_id != session_id:
                continue
            await client.send_json(data)

    @property
    def client_count(self) -> int:
        """Get the number of connected WebSocket clients."""
        return len(self.clients)

    async def _handle_connection(self, reader: asyncio.StreamReader,
                                 writer: asyncio.StreamWriter):
        """Handle incoming TCP connection — perform WS upgrade, then message loop."""
        # Read HTTP upgrade request
        try:
            request_lines = []
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=10)
                if line == b'\r\n' or line == b'\n' or not line:
                    break
                request_lines.append(line.decode('utf-8', errors='replace').strip())
        except (asyncio.TimeoutError, ConnectionError):
            writer.close()
            return

        if not request_lines:
            writer.close()
            return

        # Parse headers
        headers = {}
        for line in request_lines[1:]:  # type: ignore[assignment]
            if ':' in line:  # type: ignore[operator]
                k, v = line.split(':', 1)  # type: ignore[arg-type]
                headers[k.strip().lower()] = v.strip()

        # Validate WebSocket upgrade
        ws_key = headers.get('sec-websocket-key', '')  # type: ignore[call-overload]
        if not ws_key or 'upgrade' not in headers.get('connection', '').lower():  # type: ignore[call-overload]
            # Not a WS request — send 400
            response = b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n"
            writer.write(response)
            await writer.drain()
            writer.close()
            return

        # Perform handshake
        accept_val = base64.b64encode(
            hashlib.sha1(ws_key.encode() + WS_MAGIC).digest()
        ).decode()
        handshake = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_val}\r\n"
            f"X-Server: SalmAlm/{VERSION}\r\n"
            "\r\n"
        )
        writer.write(handshake.encode())
        await writer.drain()

        # Parse session from URL query if present
        # e.g., GET /ws?session=web HTTP/1.1
        session_id = "web"
        if request_lines:
            first_line = request_lines[0]
            if '?session=' in first_line:
                try:
                    session_id = first_line.split('?session=')[1].split()[0].split('&')[0]
                except Exception:
                    pass

        client = WSClient(reader, writer, session_id)
        self.clients[client._id] = client
        log.info(f"[FAST] WS client connected (session={session_id}, total={len(self.clients)})")

        # Auto-register presence
        try:
            from salmalm.presence import presence_manager
            peer = writer.get_extra_info('peername')
            ip = peer[0] if peer else ''
            presence_manager.register(
                f'ws_{client._id}', ip=ip, mode='websocket',
                host=headers.get('host', ''),
                user_agent=headers.get('user-agent', ''),
            )
        except Exception:
            pass

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
                    text = payload.decode('utf-8', errors='replace')
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        # Invalid JSON — send error but keep connection alive
                        log.warning(f"[WS] Invalid JSON from client {client._id}")
                        await client.send_json({
                            "type": "error",
                            "error": "Invalid JSON format / 잘못된 JSON 형식"
                        })
                        continue

                    # Abort handling — LibreChat style (생성 중지)
                    if data.get('type') == 'abort':
                        try:
                            from salmalm.edge_cases import abort_controller
                            sid = data.get('session', client.session_id)
                            abort_controller.set_abort(sid)
                            await client.send_json({'type': 'aborted', 'session': sid})
                        except Exception as e:
                            log.warning(f"WS abort error: {e}")
                        continue

                    if self._on_message:
                        try:
                            await self._on_message(client, data)
                        except Exception as e:
                            log.error(f"WS message handler error: {e}")
                            await client.send_json({
                                "type": "error",
                                "error": str(e)[:200]
                            })

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
            client.connected = False
            self.clients.pop(client._id, None)
            # Unregister presence
            try:
                from salmalm.presence import presence_manager
                presence_manager.unregister(f'ws_{client._id}')
            except Exception:
                pass
            if self._on_disconnect:
                try:
                    await self._on_disconnect(client)
                except Exception:
                    pass
            try:
                writer.close()
            except Exception:
                pass
            log.info(f"[FAST] WS client disconnected (total={len(self.clients)})")

    async def _keepalive_loop(self):
        """Ping clients every 30s, drop dead ones."""
        while self._running:
            await asyncio.sleep(30)
            now = time.time()
            dead = []
            for cid, client in list(self.clients.items()):
                if now - client.last_ping > 60:  # 60s ping timeout
                    dead.append(cid)
                else:
                    try:
                        await client._send_frame(OP_PING, b'')
                    except Exception:
                        dead.append(cid)
            for cid in dead:
                c = self.clients.pop(cid, None)
                if c:
                    c.connected = False
                    log.info("[FAST] WS client dropped (timeout)")


# ── Streaming response helper ──────────────────────────────────

class StreamingResponse:
    """Helper to stream LLM response chunks to a WS client."""

    def __init__(self, client: WSClient, request_id: Optional[str] = None):
        self.client = client
        self.request_id = request_id or str(int(time.time() * 1000))
        self._chunks: list = []

    async def send_chunk(self, text: str):
        """Send a text chunk (partial response)."""
        self._chunks.append(text)
        await self.client.send_json({
            "type": "chunk",
            "text": text,
            "rid": self.request_id,
        })

    async def send_tool_call(self, tool_name: str, tool_input: dict, result: Optional[str] = None):
        """Notify client about a tool call."""
        await self.client.send_json({
            "type": "tool",
            "name": tool_name,
            "input": tool_input,
            "result": result[:500] if result else None,
            "rid": self.request_id,
        })

    async def send_thinking(self, text: str):
        """Send thinking/reasoning chunk."""
        await self.client.send_json({
            "type": "thinking",
            "text": text,
            "rid": self.request_id,
        })

    async def send_done(self, full_text: Optional[str] = None):
        """Signal completion."""
        if full_text is None:
            full_text = ''.join(self._chunks)
        await self.client.send_json({
            "type": "done",
            "text": full_text,
            "rid": self.request_id,
        })

    async def send_error(self, error: str):
        """Send an error message to a WebSocket client."""
        await self.client.send_json({
            "type": "error",
            "error": error,
            "rid": self.request_id,
        })


# ── Module-level server instance ──────────────────────────────

ws_server = WebSocketServer()
