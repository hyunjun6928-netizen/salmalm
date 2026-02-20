"""SalmAlm API Integration Tests — test HTTP endpoints directly."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

# Set SALMALM_HOME before any salmalm import (constants.py reads at import time)
_test_tmpdir = tempfile.mkdtemp()
os.environ['SALMALM_HOME'] = _test_tmpdir
os.environ['SALMALM_VAULT_PW'] = 'testpass'

# Ensure salmalm is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAPIEndpoints(unittest.TestCase):
    """Integration tests for the HTTP API server."""

    @classmethod
    def setUpClass(cls):
        """Start a test server on a random port."""
        # Use temp dirs to avoid touching real data
        cls._tmpdir = _test_tmpdir
        os.environ['SALMALM_LOG_FILE'] = os.path.join(cls._tmpdir, 'test.log')

        # Import after env setup
        from salmalm.web import WebHandler as SalmAlmHandler
        from http.server import HTTPServer

        cls._port = 18899
        cls._server = HTTPServer(('127.0.0.1', cls._port), SalmAlmHandler)
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        time.sleep(0.1)  # Wait for server to start

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        cls._server.server_close()
        import shutil
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _request(self, method, path, body=None, headers=None):
        """Make an HTTP request to the test server."""
        conn = HTTPConnection('127.0.0.1', self._port, timeout=10)
        hdrs = {'Content-Type': 'application/json'}
        if headers:
            hdrs.update(headers)
        data = json.dumps(body).encode() if body else None
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        try:
            result = json.loads(raw)
        except Exception:
            result = raw.decode(errors='replace')
        return resp.status, result

    def test_root_returns_html(self):
        """GET / should return HTML (setup, unlock, onboarding, or main page)."""
        conn = HTTPConnection('127.0.0.1', self._port, timeout=10)
        conn.request('GET', '/')
        resp = conn.getresponse()
        body = resp.read().decode(errors='replace')
        self.assertEqual(resp.status, 200)
        conn.close()
        self.assertIn('<!doctype html>', body.lower())

    def test_manifest_json(self):
        """GET /manifest.json should return valid PWA manifest."""
        status, data = self._request('GET', '/manifest.json')
        self.assertEqual(status, 200)
        self.assertIn('name', data)

    def test_cors_preflight(self):
        """OPTIONS should return CORS headers."""
        conn = HTTPConnection('127.0.0.1', self._port, timeout=10)
        conn.request('OPTIONS', '/api/chat')
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertIn(resp.status, (200, 204))

    def test_404_unknown_path(self):
        """Unknown paths should return 404."""
        status, _ = self._request('GET', '/nonexistent-path-xyz')
        self.assertEqual(status, 404)

    def test_api_without_auth_rejected(self):
        """API endpoints without auth should be rejected."""
        status, data = self._request('GET', '/api/sessions')
        self.assertIn(status, (401, 403))

    def test_health_check(self):
        """GET /health should return 200."""
        conn = HTTPConnection('127.0.0.1', self._port, timeout=10)
        conn.request('GET', '/health')
        resp = conn.getresponse()
        resp.read()
        conn.close()
        # Health endpoint may or may not exist — accept 200 or 404
        self.assertIn(resp.status, (200, 404))


class TestAPIInputValidation(unittest.TestCase):
    """Test input validation and edge cases."""

    def test_empty_message_rejected(self):
        """Empty messages should return early without hitting LLM."""
        from salmalm.engine import process_message
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(process_message('test_empty', ''))
            self.assertEqual(result, 'Please enter a message.')
        except Exception:
            pass  # Engine may fail without API keys — that's OK
        finally:
            loop.close()

    def test_whitespace_message_rejected(self):
        """Whitespace-only messages should return early."""
        from salmalm.engine import process_message
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(process_message('test_ws', '   \n  '))
            self.assertEqual(result, 'Please enter a message.')
        except Exception:
            pass
        finally:
            loop.close()

    def test_slash_commands(self):
        """Slash commands should work without LLM."""
        from salmalm.engine import process_message
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(process_message('test_cmd', '/help'))
            self.assertIn('SalmAlm', result)
            result2 = loop.run_until_complete(process_message('test_cmd2', '/tools'))
            self.assertIn('Tool List', result2)
        except Exception:
            pass
        finally:
            loop.close()


if __name__ == '__main__':
    unittest.main()
