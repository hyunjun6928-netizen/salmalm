"""SalmAlm Discord Bot — Pure stdlib Discord Gateway + HTTP API."""
from __future__ import annotations

import asyncio
import json
import hashlib
import hmac
import os
import struct
import ssl
import threading
import time
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, Callable

from . import log

API_BASE = 'https://discord.com/api/v10'


class DiscordBot:
    """Minimal Discord bot using Gateway WebSocket + REST API."""

    def __init__(self):
        self.token: Optional[str] = None
        self.owner_id: Optional[str] = None
        self._running = False
        self._heartbeat_interval = 41250
        self._seq: Optional[int] = None
        self._session_id: Optional[str] = None
        self._bot_user: Optional[Dict] = None
        self._on_message: Optional[Callable] = None
        self._ws = None

    def configure(self, token: str, owner_id: str = None):
        self.token = token
        self.owner_id = owner_id

    def on_message(self, func):
        """Decorator to register message handler."""
        self._on_message = func
        return func

    # ── REST API ──

    def _api(self, method: str, path: str, body: dict = None) -> dict:
        url = f'{API_BASE}{path}'
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header('Authorization', f'Bot {self.token}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('User-Agent', 'SalmAlm (github.com/hyunjun6928-netizen/salmalm, 0.8)')
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode('utf-8', errors='replace')
            log.error(f'Discord API {method} {path}: {e.code} {err[:200]}')
            return {}

    def send_message(self, channel_id: str, content: str, reply_to: str = None) -> dict:
        """Send a message to a channel."""
        body: Dict[str, Any] = {'content': content[:2000]}
        if reply_to:
            body['message_reference'] = {'message_id': reply_to}
        return self._api('POST', f'/channels/{channel_id}/messages', body)

    def send_typing(self, channel_id: str):
        """Send typing indicator."""
        self._api('POST', f'/channels/{channel_id}/typing')

    def add_reaction(self, channel_id: str, message_id: str, emoji: str):
        encoded = urllib.parse.quote(emoji)
        self._api('PUT', f'/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me')

    # ── Gateway WebSocket ──

    async def _gateway_connect(self):
        """Connect to Discord Gateway via raw SSL socket."""
        import socket

        # Get gateway URL
        gw = self._api('GET', '/gateway/bot')
        gateway_url = gw.get('url', 'wss://gateway.discord.gg')
        gateway_url += '/?v=10&encoding=json'

        # Parse URL
        host = gateway_url.split('//')[1].split('/')[0].split('?')[0]
        path = '/' + '/'.join(gateway_url.split('//')[1].split('/')[1:])

        # SSL connect
        ctx = ssl.create_default_context()
        sock = socket.create_connection((host, 443), timeout=30)
        self._ws_raw = ctx.wrap_socket(sock, server_hostname=host)

        # WebSocket handshake
        key = __import__('base64').b64encode(os.urandom(16)).decode()
        handshake = (
            f'GET {path} HTTP/1.1\r\n'
            f'Host: {host}\r\n'
            f'Upgrade: websocket\r\n'
            f'Connection: Upgrade\r\n'
            f'Sec-WebSocket-Key: {key}\r\n'
            f'Sec-WebSocket-Version: 13\r\n'
            f'\r\n'
        )
        self._ws_raw.sendall(handshake.encode())

        # Read handshake response
        resp = b''
        while b'\r\n\r\n' not in resp:
            resp += self._ws_raw.recv(4096)

        if b'101' not in resp.split(b'\r\n')[0]:
            raise ConnectionError(f'WebSocket handshake failed: {resp[:100]}')

        log.info('🎮 Discord Gateway connected')

    def _ws_send(self, data: dict):
        """Send a WebSocket frame (masked, as client)."""
        payload = json.dumps(data).encode()
        # Build frame: FIN + TEXT opcode
        frame = bytearray([0x81])
        length = len(payload)
        if length < 126:
            frame.append(0x80 | length)  # masked
        elif length < 65536:
            frame.append(0x80 | 126)
            frame.extend(struct.pack('>H', length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack('>Q', length))
        # Mask
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        self._ws_raw.sendall(frame)

    def _ws_recv(self) -> Optional[dict]:
        """Receive a WebSocket frame."""
        try:
            header = self._ws_raw.recv(2)
            if len(header) < 2:
                return None
            opcode = header[0] & 0x0F
            masked = header[1] & 0x80
            length = header[1] & 0x7F

            if length == 126:
                length = struct.unpack('>H', self._ws_raw.recv(2))[0]
            elif length == 127:
                length = struct.unpack('>Q', self._ws_raw.recv(8))[0]

            if masked:
                mask = self._ws_raw.recv(4)

            data = b''
            while len(data) < length:
                chunk = self._ws_raw.recv(min(length - len(data), 65536))
                if not chunk:
                    return None
                data += chunk

            if masked:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))

            if opcode == 0x08:  # Close
                return None
            if opcode == 0x09:  # Ping
                # Send pong
                pong = bytearray([0x8A, 0x80 | len(data)])
                mask = os.urandom(4)
                pong.extend(mask)
                pong.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
                self._ws_raw.sendall(pong)
                return self._ws_recv()
            if opcode == 0x01:  # Text
                return json.loads(data.decode())
            return None
        except Exception as e:
            log.error(f'Discord WS recv error: {e}')
            return None

    async def _heartbeat_loop(self):
        """Send heartbeat at the required interval."""
        while self._running:
            await asyncio.sleep(self._heartbeat_interval / 1000)
            if self._running:
                self._ws_send({'op': 1, 'd': self._seq})

    async def _identify(self):
        """Send IDENTIFY payload."""
        self._ws_send({
            'op': 2,
            'd': {
                'token': self.token,
                'intents': 33281,  # GUILDS + GUILD_MESSAGES + DM_MESSAGES + MESSAGE_CONTENT
                'properties': {
                    'os': 'linux',
                    'browser': 'salmalm',
                    'device': 'salmalm'
                }
            }
        })

    async def _handle_event(self, data: dict):
        """Handle a gateway event."""
        op = data.get('op')
        t = data.get('t')
        d = data.get('d', {})
        s = data.get('s')

        if s:
            self._seq = s

        if op == 10:  # Hello
            self._heartbeat_interval = d.get('heartbeat_interval', 41250)
            asyncio.create_task(self._heartbeat_loop())
            await self._identify()

        elif op == 11:  # Heartbeat ACK
            pass

        elif op == 0:  # Dispatch
            if t == 'READY':
                self._session_id = d.get('session_id')
                self._bot_user = d.get('user', {})
                log.info(f"🎮 Discord ready: {self._bot_user.get('username')}#{self._bot_user.get('discriminator')}")

            elif t == 'MESSAGE_CREATE':
                # Ignore own messages
                author = d.get('author', {})
                if author.get('id') == self._bot_user.get('id'):
                    return
                if author.get('bot'):
                    return

                content = d.get('content', '').strip()
                channel_id = d.get('channel_id')
                message_id = d.get('id')

                # Check if bot is mentioned or DM
                is_dm = d.get('guild_id') is None
                mentions = [m.get('id') for m in d.get('mentions', [])]
                is_mentioned = self._bot_user and self._bot_user.get('id') in mentions

                if not is_dm and not is_mentioned:
                    return  # Only respond to DMs and mentions

                # Strip bot mention from content
                if self._bot_user:
                    content = content.replace(f'<@{self._bot_user["id"]}>', '').strip()
                    content = content.replace(f'<@!{self._bot_user["id"]}>', '').strip()

                if not content:
                    return

                if self._on_message:
                    self.send_typing(channel_id)
                    try:
                        response = await self._on_message(content, d)
                        if response:
                            # Split long messages
                            while response:
                                chunk = response[:2000]
                                response = response[2000:]
                                self.send_message(channel_id, chunk, reply_to=message_id)
                    except Exception as e:
                        log.error(f'Discord message handler error: {e}')
                        self.send_message(channel_id, f'❌ Error: {str(e)[:200]}', reply_to=message_id)

    async def poll(self):
        """Main gateway loop."""
        if not self.token:
            log.warning('Discord token not configured')
            return

        self._running = True
        retry_delay = 1

        while self._running:
            try:
                await self._gateway_connect()
                retry_delay = 1

                while self._running:
                    data = await asyncio.to_thread(self._ws_recv)
                    if data is None:
                        break
                    await self._handle_event(data)

            except Exception as e:
                log.error(f'Discord gateway error: {e}')

            if self._running:
                log.info(f'🎮 Discord reconnecting in {retry_delay}s...')
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    def stop(self):
        self._running = False
        try:
            if self._ws_raw:
                self._ws_raw.close()
        except Exception:
            pass


discord_bot = DiscordBot()
