"""Tests for salmalm.async_http — AsyncHTTPClient & AsyncHTTPResponse."""
import asyncio
import json
import unittest

from salmalm.async_http import AsyncHTTPClient, AsyncHTTPResponse


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Helpers: fake asyncio reader/writer
# ---------------------------------------------------------------------------

class _FakeWriter:
    def __init__(self):
        self.data = b''
        self._closing = False

    def write(self, data):
        self.data += data

    async def drain(self):
        pass

    def close(self):
        self._closing = True

    def is_closing(self):
        return self._closing


class _FakeReader:
    """Simulate asyncio.StreamReader from pre-loaded bytes."""

    def __init__(self, data: bytes):
        self._buf = data
        self._pos = 0

    async def readline(self):
        start = self._pos
        idx = self._buf.find(b'\n', start)
        if idx == -1:
            self._pos = len(self._buf)
            return self._buf[start:]
        self._pos = idx + 1
        return self._buf[start:self._pos]

    async def read(self, n=-1):
        if n == -1 or n >= len(self._buf) - self._pos:
            out = self._buf[self._pos:]
            self._pos = len(self._buf)
            return out
        out = self._buf[self._pos:self._pos + n]
        self._pos += n
        return out

    async def readexactly(self, n):
        out = self._buf[self._pos:self._pos + n]
        self._pos += n
        if len(out) < n:
            raise asyncio.IncompleteReadError(out, n)
        return out


# ===========================================================================
# Tests
# ===========================================================================

class TestAsyncHTTPResponse(unittest.TestCase):
    """AsyncHTTPResponse body reading & streaming."""

    def test_read_with_content_length(self):
        body = b'Hello World'
        reader = _FakeReader(body)
        writer = _FakeWriter()
        resp = AsyncHTTPResponse(200, {'content-length': str(len(body))}, reader, writer)
        self.assertEqual(_run(resp.read()), body)

    def test_read_no_content_length(self):
        body = b'no length'
        reader = _FakeReader(body)
        writer = _FakeWriter()
        resp = AsyncHTTPResponse(200, {}, reader, writer)
        self.assertEqual(_run(resp.read()), body)

    def test_json(self):
        payload = {'key': 'value', 'num': 42}
        body = json.dumps(payload).encode()
        reader = _FakeReader(body)
        writer = _FakeWriter()
        resp = AsyncHTTPResponse(200, {}, reader, writer)
        self.assertEqual(_run(resp.json()), payload)

    def test_text(self):
        body = '한글 텍스트'.encode('utf-8')
        reader = _FakeReader(body)
        writer = _FakeWriter()
        resp = AsyncHTTPResponse(200, {}, reader, writer)
        self.assertEqual(_run(resp.text()), '한글 텍스트')

    def test_iter_lines(self):
        body = b'line1\nline2\nline3\n'
        reader = _FakeReader(body)
        writer = _FakeWriter()
        resp = AsyncHTTPResponse(200, {}, reader, writer)

        async def collect():
            return [line async for line in resp.iter_lines()]

        lines = _run(collect())
        self.assertEqual(lines, ['line1', 'line2', 'line3'])

    def test_iter_lines_sse_data(self):
        """SSE-style data: lines."""
        body = b'data: {"text":"hello"}\n\ndata: {"text":"world"}\n\n'
        reader = _FakeReader(body)
        writer = _FakeWriter()
        resp = AsyncHTTPResponse(200, {}, reader, writer)

        async def collect():
            return [l async for l in resp.iter_lines() if l.startswith('data:')]

        lines = _run(collect())
        self.assertEqual(len(lines), 2)
        self.assertIn('hello', lines[0])

    def test_chunked_transfer_encoding(self):
        # Manually encode chunked body
        chunk1 = b'Hello '
        chunk2 = b'World'
        raw = (
            f'{len(chunk1):x}\r\n'.encode() + chunk1 + b'\r\n' +
            f'{len(chunk2):x}\r\n'.encode() + chunk2 + b'\r\n' +
            b'0\r\n\r\n'
        )
        reader = _FakeReader(raw)
        writer = _FakeWriter()
        resp = AsyncHTTPResponse(200, {'transfer-encoding': 'chunked'}, reader, writer)
        self.assertEqual(_run(resp.read()), b'Hello World')

    def test_read_caches_body(self):
        body = b'cached'
        reader = _FakeReader(body)
        writer = _FakeWriter()
        resp = AsyncHTTPResponse(200, {}, reader, writer)
        self.assertEqual(_run(resp.read()), body)
        self.assertEqual(_run(resp.read()), body)  # second call returns cached


class TestAsyncHTTPClientRequestBuild(unittest.TestCase):
    """Test request building by intercepting at the connection level."""

    def test_request_formats_path_and_query(self):
        """Verify HTTP request line includes path + query."""
        captured = {}

        async def fake_open_connection(host, port, **kw):
            captured['host'] = host
            captured['port'] = port
            reader = _FakeReader(
                b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK'
            )
            writer = _FakeWriter()
            return reader, writer

        client = AsyncHTTPClient()

        async def run():
            orig = asyncio.open_connection
            asyncio.open_connection = fake_open_connection
            try:
                resp = await client.get('http://example.com:8080/api/v1?q=test', timeout=5)
                self.assertEqual(resp.status, 200)
                self.assertEqual(await resp.text(), 'OK')
            finally:
                asyncio.open_connection = orig

        _run(run())
        self.assertEqual(captured['host'], 'example.com')
        self.assertEqual(captured['port'], 8080)

    def test_post_json_content_type(self):
        """post_json sets Content-Type header."""
        sent_data = {}

        async def fake_open(host, port, **kw):
            reader = _FakeReader(
                b'HTTP/1.1 201 Created\r\nContent-Length: 2\r\n\r\n{}'
            )
            writer = _FakeWriter()
            sent_data['writer'] = writer
            return reader, writer

        client = AsyncHTTPClient()

        async def run():
            orig = asyncio.open_connection
            asyncio.open_connection = fake_open
            try:
                resp = await client.post_json('http://localhost/data', {'key': 'val'})
                self.assertEqual(resp.status, 201)
            finally:
                asyncio.open_connection = orig

        _run(run())
        raw = sent_data['writer'].data.decode()
        self.assertIn('Content-Type: application/json', raw)
        self.assertIn('"key"', raw)

    def test_timeout_on_connect(self):
        """Connection timeout raises TimeoutError."""
        async def slow_open(host, port, **kw):
            await asyncio.sleep(100)

        client = AsyncHTTPClient(default_timeout=0.05)

        async def run():
            orig = asyncio.open_connection
            asyncio.open_connection = slow_open
            try:
                await client.get('http://example.com/')
            finally:
                asyncio.open_connection = orig

        with self.assertRaises(asyncio.TimeoutError):
            _run(run())

    def test_https_uses_ssl(self):
        """HTTPS URL triggers ssl= kwarg."""
        used_ssl = {}

        async def fake_open(host, port, **kw):
            used_ssl['ssl'] = kw.get('ssl')
            reader = _FakeReader(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n')
            writer = _FakeWriter()
            return reader, writer

        client = AsyncHTTPClient()

        async def run():
            orig = asyncio.open_connection
            asyncio.open_connection = fake_open
            try:
                await client.get('https://secure.example.com/path')
            finally:
                asyncio.open_connection = orig

        _run(run())
        self.assertIsNotNone(used_ssl.get('ssl'))


if __name__ == '__main__':
    unittest.main()
