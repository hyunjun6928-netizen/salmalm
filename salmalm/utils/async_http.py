"""Async HTTP client built on stdlib asyncio (no third-party deps).

Provides ``AsyncHTTPClient`` for non-blocking HTTP/1.1 requests with
optional SSE streaming support, suitable for replacing synchronous
``urllib.request`` calls inside async code paths.
"""

from salmalm.security.crypto import log
import asyncio
import json
import ssl
import urllib.parse
from typing import AsyncIterator, Dict, Optional

__all__ = ["AsyncHTTPClient", "AsyncHTTPResponse"]


class AsyncHTTPResponse:
    """Lightweight async HTTP response wrapper."""

    __slots__ = ("status", "headers", "_reader", "_writer", "_body")

    def __init__(
        self, status: int, headers: Dict[str, str], reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Init  ."""
        self.status = status
        self.headers = headers
        self._reader = reader
        self._writer = writer
        self._body: Optional[bytes] = None

    # -- body helpers -------------------------------------------------------

    async def read(self) -> bytes:
        """Read entire response body (handles chunked transfer-encoding)."""
        if self._body is not None:
            return self._body
        if self.headers.get("transfer-encoding", "").lower() == "chunked":
            self._body = await self._read_chunked()
        else:
            length = self.headers.get("content-length")
            if length is not None:
                self._body = await self._reader.readexactly(int(length))
            else:
                self._body = await self._reader.read(-1)
        self._close()
        return self._body

    async def json(self) -> dict:
        """Json."""
        return json.loads(await self.read())

    async def text(self) -> str:
        """Text."""
        return (await self.read()).decode("utf-8", errors="replace")

    # -- streaming ----------------------------------------------------------

    async def iter_lines(self) -> AsyncIterator[str]:
        """Yield lines as they arrive (for SSE / streaming)."""
        buf = b""
        try:
            while True:
                # Handle chunked TE transparently
                chunk = await self._reader.read(4096)
                if not chunk:
                    if buf:
                        yield buf.decode("utf-8", errors="replace")
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    yield line.decode("utf-8", errors="replace")
        finally:
            self._close()

    async def iter_chunks(self, size: int = 4096) -> AsyncIterator[bytes]:
        """Yield raw byte chunks."""
        try:
            while True:
                chunk = await self._reader.read(size)
                if not chunk:
                    break
                yield chunk
        finally:
            self._close()

    # -- internals ----------------------------------------------------------

    async def _read_chunked(self) -> bytes:
        """Decode HTTP chunked transfer-encoding."""
        body = bytearray()
        while True:
            size_line = await self._reader.readline()
            size_str = size_line.strip()
            if not size_str:
                continue
            chunk_len = int(size_str, 16)
            if chunk_len == 0:
                await self._reader.readline()  # trailing CRLF
                break
            data = await self._reader.readexactly(chunk_len)
            body.extend(data)
            await self._reader.readline()  # trailing CRLF after chunk
        return bytes(body)

    def _close(self):
        """Close."""
        try:
            if not self._writer.is_closing():
                self._writer.close()
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")


class AsyncHTTPClient:
    """Pure-stdlib asyncio HTTP/1.1 client.

    Usage::

        client = AsyncHTTPClient()
        resp = await client.get('https://example.com')
        print(await resp.text())
    """

    def __init__(self, default_timeout: float = 30) -> None:
        """Init  ."""
        self._default_timeout = default_timeout

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        timeout: Optional[float] = None,
    ) -> AsyncHTTPResponse:
        """Send an HTTP/1.1 request and return an :class:`AsyncHTTPResponse`."""
        timeout = timeout or self._default_timeout
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # Open connection
        kw = {}
        if parsed.scheme == "https":
            kw["ssl"] = ssl.create_default_context()
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port, **kw), timeout=timeout)

        # Build request
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        lines = [f"{method} {path} HTTP/1.1", f"Host: {host}"]
        hdrs = dict(headers) if headers else {}
        if body and "Content-Length" not in hdrs and "content-length" not in hdrs:
            hdrs["Content-Length"] = str(len(body))
        if "Connection" not in hdrs and "connection" not in hdrs:
            hdrs["Connection"] = "close"
        for k, v in hdrs.items():
            lines.append(f"{k}: {v}")
        lines.append("")
        lines.append("")

        raw = "\r\n".join(lines).encode("utf-8")
        if body:
            raw += body

        writer.write(raw)
        await writer.drain()

        # Parse status line
        status_line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        parts = status_line.split(None, 2)
        status_code = int(parts[1])

        # Parse headers
        resp_headers: Dict[str, str] = {}
        while True:
            hline = await reader.readline()
            if hline in (b"\r\n", b"\n", b""):
                break
            decoded = hline.decode("utf-8", errors="replace")
            key, _, value = decoded.partition(":")
            resp_headers[key.strip().lower()] = value.strip()

        return AsyncHTTPResponse(status_code, resp_headers, reader, writer)

    # -- convenience wrappers -----------------------------------------------

    async def get(self, url: str, **kw) -> AsyncHTTPResponse:
        """Get."""
        return await self.request("GET", url, **kw)

    async def post(self, url: str, **kw) -> AsyncHTTPResponse:
        """Post."""
        return await self.request("POST", url, **kw)

    async def post_json(self, url: str, data, *, headers: Optional[Dict[str, str]] = None, **kw) -> AsyncHTTPResponse:
        """Post json."""
        body = json.dumps(data).encode("utf-8")
        h = dict(headers) if headers else {}
        h["Content-Type"] = "application/json"
        return await self.request("POST", url, headers=h, body=body, **kw)
