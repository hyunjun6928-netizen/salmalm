"""삶앎 Unit Tests — stdlib unittest, no external deps.

Run: python -m pytest tests/ OR python -m unittest tests.test_all
"""

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAuth(unittest.TestCase):
    """Test authentication system."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Monkey-patch AUTH_DB
        import salmalm.web.auth as auth_mod
        self.orig_db = auth_mod.AUTH_DB
        auth_mod.AUTH_DB = Path(self.tmpdir) / "test_auth.db"
        self.auth = auth_mod.AuthManager()
        self.auth._initialized = False

    def tearDown(self):
        import salmalm.web.auth as auth_mod
        auth_mod.AUTH_DB = self.orig_db
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_password_hashing(self):
        from salmalm.web.auth import _hash_password, _verify_password
        pw_hash, salt = _hash_password("test_password")
        self.assertTrue(_verify_password("test_password", pw_hash, salt))
        self.assertFalse(_verify_password("wrong_password", pw_hash, salt))

    def test_create_user(self):
        user = self.auth.create_user("testuser", "password123", "user")
        self.assertEqual(user['username'], "testuser")
        self.assertEqual(user['role'], "user")
        self.assertTrue(user['api_key'].startswith('sk_'))

    def test_duplicate_user(self):
        self.auth.create_user("unique", "password123")
        with self.assertRaises(ValueError):
            self.auth.create_user("unique", "password456")

    def test_short_password(self):
        with self.assertRaises(ValueError):
            self.auth.create_user("shortpw", "123")

    def test_authenticate_success(self):
        self.auth.create_user("authtest", "mypassword123")
        user = self.auth.authenticate("authtest", "mypassword123")
        self.assertIsNotNone(user)
        self.assertEqual(user['username'], "authtest")

    def test_authenticate_fail(self):
        self.auth.create_user("authfail", "correctpass1")
        user = self.auth.authenticate("authfail", "wrongpass123")
        self.assertIsNone(user)

    def test_api_key_auth(self):
        created = self.auth.create_user("apitest", "password123")
        user = self.auth.authenticate_api_key(created['api_key'])
        self.assertIsNotNone(user)
        self.assertEqual(user['username'], "apitest")

    def test_token_create_verify(self):
        user = self.auth.create_user("tokentest", "password123")
        token = self.auth.create_token(user)
        self.assertIsInstance(token, str)
        payload = self.auth.verify_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['usr'], "tokentest")

    def test_token_expired(self):
        user = self.auth.create_user("exptest", "password123")
        token = self.auth.create_token(user, expires_in=-1)  # Already expired
        payload = self.auth.verify_token(token)
        self.assertIsNone(payload)

    def test_token_tampered(self):
        user = self.auth.create_user("tamptest", "password123")
        token = self.auth.create_token(user)
        tampered = token[:-1] + ('a' if token[-1] != 'a' else 'b')
        payload = self.auth.verify_token(tampered)
        self.assertIsNone(payload)

    def test_list_users(self):
        users = self.auth.list_users()
        self.assertIsInstance(users, list)
        # Default admin should exist
        self.assertTrue(any(u['username'] == 'admin' for u in users))

    def test_change_password(self):
        self.auth.create_user("pwchange", "oldpassword1")
        self.auth.change_password("pwchange", "newpassword1")
        self.assertIsNone(self.auth.authenticate("pwchange", "oldpassword1"))
        self.assertIsNotNone(self.auth.authenticate("pwchange", "newpassword1"))

    def test_rbac(self):
        admin = {'role': 'admin'}
        user = {'role': 'user'}
        readonly = {'role': 'readonly'}
        self.assertTrue(self.auth.has_permission(admin, 'exec'))
        self.assertFalse(self.auth.has_permission(user, 'exec'))
        self.assertFalse(self.auth.has_permission(readonly, 'tools'))
        self.assertTrue(self.auth.has_permission(readonly, 'chat'))


class TestRateLimiter(unittest.TestCase):

    def test_basic_limit(self):
        from salmalm.web.auth import RateLimiter, RateLimitExceeded
        rl = RateLimiter()
        # Anonymous: 5 req/min, burst 10
        for _ in range(10):
            rl.check("test_ip", "anonymous")
        with self.assertRaises(RateLimitExceeded):
            rl.check("test_ip", "anonymous")

    def test_different_keys(self):
        from salmalm.web.auth import RateLimiter
        rl = RateLimiter()
        for _ in range(10):
            rl.check("ip_a", "anonymous")
        # Different key should be fine
        rl.check("ip_b", "anonymous")

    def test_admin_higher_limit(self):
        from salmalm.web.auth import RateLimiter
        rl = RateLimiter()
        for _ in range(50):
            rl.check("admin_key", "admin")
        # Admin has burst of 100, should still be fine


class TestTokenManager(unittest.TestCase):

    def test_create_and_verify(self):
        from salmalm.web.auth import TokenManager
        tm = TokenManager(b'test_secret')
        token = tm.create({'user': 'test'})
        payload = tm.verify(token)
        self.assertEqual(payload['user'], 'test')

    def test_different_secret(self):
        from salmalm.web.auth import TokenManager
        tm1 = TokenManager(b'secret1')
        tm2 = TokenManager(b'secret2')
        token = tm1.create({'user': 'test'})
        self.assertIsNone(tm2.verify(token))


class TestRAG(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "test_rag.db"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_tokenize(self):
        from salmalm.features.rag import RAGEngine
        tokens = RAGEngine._tokenize("머슴포커 랭크 매치 시스템")
        self.assertIn('머슴포커', tokens)
        self.assertIn('시스템', tokens)
        # Bigrams
        self.assertTrue(any('_' in t for t in tokens))

    def test_search_empty(self):
        from salmalm.features.rag import RAGEngine
        engine = RAGEngine(db_path=self.db_path)
        engine._get_indexable_files = lambda: []
        engine._get_session_files = lambda: []
        results = engine.search("test query")
        self.assertEqual(results, [])
        engine.close()

    def test_build_context(self):
        from salmalm.features.rag import RAGEngine
        engine = RAGEngine(db_path=self.db_path)
        # Patch to avoid indexing real workspace files
        engine._get_indexable_files = lambda: []
        engine._get_session_files = lambda: []
        ctx = engine.build_context("nonexistent query")
        self.assertEqual(ctx, "")
        engine.close()


class TestTLS(unittest.TestCase):

    def test_cert_info_no_cert(self):
        from salmalm.utils.tls import get_cert_info
        info = get_cert_info()
        self.assertIn('cert_exists', info)


class TestStability(unittest.TestCase):

    def test_circuit_breaker(self):
        from salmalm.features.stability import CircuitBreaker
        cb = CircuitBreaker(threshold=3, window_sec=60)
        self.assertFalse(cb.is_tripped('test'))
        for _ in range(3):
            cb.record_error('test', 'err')
        self.assertTrue(cb.is_tripped('test'))

    def test_circuit_breaker_reset(self):
        from salmalm.features.stability import CircuitBreaker
        # Errors with very short window so they expire
        cb = CircuitBreaker(threshold=3, window_sec=0.01, cooldown_sec=0)
        for _ in range(3):
            cb.record_error('test2', 'err')
        self.assertTrue(cb.is_tripped('test2'))
        import time; time.sleep(0.05)  # Wait for 0.01s window to expire
        self.assertFalse(cb.is_tripped('test2'))

    def test_health_monitor_system(self):
        from salmalm.features.stability import health_monitor
        health = health_monitor.check_health()
        self.assertIn('status', health)
        self.assertIn('components', health)
        self.assertIn('system', health)
        self.assertIn('uptime_seconds', health)

    def test_selftest(self):
        from salmalm.features.stability import health_monitor
        result = health_monitor.startup_selftest()
        self.assertTrue(result['all_ok'])
        self.assertGreaterEqual(result['passed'], 14)


class TestWebSocket(unittest.TestCase):

    def test_ws_client_init(self):
        from salmalm.web.ws import WSClient
        # Just test object creation
        client = WSClient(None, None, "test")
        self.assertEqual(client.session_id, "test")
        self.assertTrue(client.connected)

    def test_streaming_response_init(self):
        from salmalm.web.ws import StreamingResponse
        client = type('MockClient', (), {'session_id': 'test', 'connected': True,
                                          'send_json': lambda self, d: None})()
        sr = StreamingResponse(client)
        self.assertIsNotNone(sr.request_id)
        self.assertEqual(sr._chunks, [])


class TestMCP(unittest.TestCase):

    def test_rpc_request(self):
        from salmalm.features.mcp import _rpc_request
        msg = _rpc_request("test/method", {"key": "val"}, id=1)
        self.assertEqual(msg['method'], 'test/method')
        self.assertEqual(msg['id'], 1)

    def test_rpc_response(self):
        from salmalm.features.mcp import _rpc_response
        msg = _rpc_response(1, result={"ok": True})
        self.assertEqual(msg['id'], 1)
        self.assertTrue(msg['result']['ok'])

    def test_mcp_manager_empty(self):
        from salmalm.features.mcp import MCPManager
        mgr = MCPManager()
        self.assertEqual(mgr.list_servers(), [])
        self.assertEqual(mgr.get_all_tools(), [])


class TestBrowser(unittest.TestCase):

    def test_browser_status_disconnected(self):
        from salmalm.utils.browser import BrowserController
        bc = BrowserController()
        self.assertFalse(bc.connected)
        status = bc.get_status()
        self.assertFalse(status['connected'])


class TestNodes(unittest.TestCase):

    def test_node_manager_empty(self):
        from salmalm.features.nodes import NodeManager
        nm = NodeManager()
        self.assertEqual(nm.list_nodes(), [])

    def test_wol_invalid_mac(self):
        from salmalm.features.nodes import NodeManager
        nm = NodeManager()
        result = nm.wake_on_lan("invalid")
        self.assertIn('error', result)


class TestTools(unittest.TestCase):

    def test_no_duplicate_tools(self):
        from salmalm.tools import TOOL_DEFINITIONS
        from collections import Counter
        names = [t['name'] for t in TOOL_DEFINITIONS]
        dupes = [n for n, c in Counter(names).items() if c > 1]
        self.assertEqual(dupes, [], f"Duplicate tools: {dupes}")

    def test_all_tools_have_schema(self):
        from salmalm.tools import TOOL_DEFINITIONS
        for t in TOOL_DEFINITIONS:
            self.assertIn('name', t)
            self.assertIn('description', t)
            self.assertIn('input_schema', t)
            self.assertEqual(t['input_schema']['type'], 'object')

    def test_tool_count(self):
        from salmalm.tools import TOOL_DEFINITIONS
        self.assertGreaterEqual(len(TOOL_DEFINITIONS), 30)


class TestLogging(unittest.TestCase):

    def test_json_formatter(self):
        from salmalm.utils.logging_ext import JSONFormatter
        import logging
        fmt = JSONFormatter()
        record = logging.LogRecord('test', logging.INFO, '', 0, 'test message', (), None)
        output = fmt.format(record)
        parsed = json.loads(output)
        self.assertEqual(parsed['msg'], 'test message')
        self.assertEqual(parsed['level'], 'INFO')

    def test_request_logger_metrics(self):
        from salmalm.utils.logging_ext import RequestLogger
        rl = RequestLogger()
        rl.log_request('GET', '/api/status', status_code=200, duration_ms=15)
        rl.log_request('POST', '/api/chat', status_code=200, duration_ms=1500)
        rl.log_request('GET', '/api/bad', status_code=500, duration_ms=5)
        metrics = rl.get_metrics()
        self.assertEqual(metrics['total_requests'], 3)
        self.assertEqual(metrics['total_errors'], 1)
        self.assertIn('200', metrics['by_status'])


class TestConstants(unittest.TestCase):

    def test_version_format(self):
        from salmalm.constants import VERSION
        parts = VERSION.split('.')
        self.assertEqual(len(parts), 3)

    def test_model_costs(self):
        from salmalm.constants import MODEL_COSTS
        self.assertGreaterEqual(len(MODEL_COSTS), 20)
        for model, costs in MODEL_COSTS.items():
            self.assertIn('input', costs)
            self.assertIn('output', costs)
            self.assertGreater(costs['input'], 0)


class TestEngineAliases(unittest.TestCase):

    def test_model_aliases(self):
        from salmalm.core.engine import MODEL_ALIASES
        self.assertIn('opus', MODEL_ALIASES)
        self.assertIn('grok', MODEL_ALIASES)
        self.assertIn('auto', MODEL_ALIASES)
        self.assertIsNone(MODEL_ALIASES['auto'])

    def test_task_classifier(self):
        from salmalm.core.engine import TaskClassifier
        result = TaskClassifier.classify("refactor this code please")
        self.assertEqual(result['intent'], 'code')
        self.assertGreaterEqual(result['tier'], 2)

    def test_chat_classification(self):
        from salmalm.core.engine import TaskClassifier
        result = TaskClassifier.classify("안녕")
        self.assertEqual(result['intent'], 'chat')
        self.assertEqual(result['tier'], 1)


if __name__ == '__main__':
    unittest.main()
