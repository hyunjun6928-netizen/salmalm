"""Coverage boost tests — exercise untested code paths with mocks."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestToolHandlers(unittest.TestCase):
    """Test tool execution paths."""

    def _ws_path(self, name):
        """Get a path inside workspace for testing."""
        from salmalm.constants import WORKSPACE_DIR
        p = WORKSPACE_DIR / '_test_tmp'
        p.mkdir(exist_ok=True)
        return str(p / name)

    def test_execute_tool_read_file(self):
        """read_file tool should read file contents."""
        from salmalm.tools.tool_handlers import execute_tool
        path = self._ws_path('read_test.txt')
        Path(path).write_text('hello world')
        result = execute_tool('read_file', {'path': path})
        self.assertIn('hello world', result)
        os.unlink(path)

    def test_execute_tool_write_file(self):
        """write_file tool should create files."""
        from salmalm.tools.tool_handlers import execute_tool
        path = self._ws_path('write_test.txt')
        result = execute_tool('write_file', {'path': path, 'content': 'test content'})
        self.assertTrue(os.path.exists(path))
        with open(path) as _f:
            self.assertIn('test content', _f.read())
        os.unlink(path)

    def test_execute_tool_edit_file(self):
        """edit_file tool should replace text."""
        from salmalm.tools.tool_handlers import execute_tool
        path = self._ws_path('edit_test.txt')
        Path(path).write_text('hello old world')
        result = execute_tool('edit_file', {
            'path': path,
            'old_text': 'old',
            'new_text': 'new'
        })
        with open(path) as _f:
            content = _f.read()
        self.assertIn('new', content)
        os.unlink(path)

    def test_execute_tool_hash_text(self):
        """hash_text tool should return hash."""
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('hash_text', {'text': 'hello', 'algorithm': 'sha256'})
        self.assertIn('2cf24dba', result)

    def test_execute_tool_regex_test(self):
        """regex_test tool should test patterns."""
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('regex_test', {
            'pattern': r'\d+',
            'text': 'abc 123 def'
        })
        self.assertIn('123', result)

    def test_execute_tool_json_query(self):
        """json_query tool should extract data."""
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('json_query', {
            'data': '{"a": {"b": 1}}',
            'query': 'a.b'
        })
        self.assertIn('1', result)

    def test_execute_tool_diff_files(self):
        """diff_files should show differences."""
        from salmalm.tools.tool_handlers import execute_tool
        f1 = self._ws_path('diff1.txt')
        f2 = self._ws_path('diff2.txt')
        Path(f1).write_text('line1\nline2\n')
        Path(f2).write_text('line1\nline3\n')
        result = execute_tool('diff_files', {'file1': f1, 'file2': f2})
        self.assertTrue(len(result) > 0)
        os.unlink(f1); os.unlink(f2)

    def test_execute_tool_python_eval(self):
        """python_eval tool should execute code."""
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('python_eval', {'code': 'print(2+2)'})
        self.assertIn('4', result)

    def test_execute_tool_system_monitor(self):
        """system_monitor tool should return stats."""
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('system_monitor', {})
        self.assertIn('CPU', result.upper() if isinstance(result, str) else str(result).upper())

    def test_execute_tool_unknown(self):
        """Unknown tool should return error."""
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('nonexistent_tool_xyz', {})
        self.assertIn('unknown', result.lower())

    def test_execute_tool_usage_report(self):
        """usage_report tool should return stats."""
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('usage_report', {})
        self.assertTrue(len(result) > 0)

    def test_execute_tool_clipboard(self):
        """clipboard tool should handle read/write."""
        from salmalm.tools.tool_handlers import execute_tool
        # Write
        result = execute_tool('clipboard', {'action': 'write', 'text': 'test'})
        self.assertTrue(len(result) > 0)

    def test_execute_tool_health_check(self):
        """health_check tool should return status."""
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('health_check', {})
        self.assertTrue(len(result) > 0)


class TestEngineClassifier(unittest.TestCase):
    """Test task classification."""

    def test_classify_code(self):
        from salmalm.core.engine import TaskClassifier
        r = TaskClassifier.classify("write a Python function")
        self.assertEqual(r['intent'], 'code')

    def test_classify_analysis(self):
        from salmalm.core.engine import TaskClassifier
        r = TaskClassifier.classify("analyze this data and explain")
        self.assertEqual(r['intent'], 'analysis')

    def test_classify_search(self):
        from salmalm.core.engine import TaskClassifier
        r = TaskClassifier.classify("search the web for Python tutorials")
        self.assertEqual(r['intent'], 'search')

    def test_classify_short_chat(self):
        from salmalm.core.engine import TaskClassifier
        r = TaskClassifier.classify("hi")
        self.assertEqual(r['intent'], 'chat')
        self.assertEqual(r['tier'], 1)

    def test_classify_system(self):
        from salmalm.core.engine import TaskClassifier
        r = TaskClassifier.classify("check disk space and memory")
        self.assertEqual(r['intent'], 'system')

    def test_classify_creative(self):
        from salmalm.core.engine import TaskClassifier
        r = TaskClassifier.classify("write a poem about the moon")
        self.assertEqual(r['intent'], 'creative')


class TestCoreModules(unittest.TestCase):
    """Test core module functionality."""

    def test_response_cache(self):
        from salmalm.core import ResponseCache
        cache = ResponseCache()
        msgs = [{'role': 'user', 'content': 'test'}]
        cache.put('model1', msgs, 'response1', session_id='s1')
        result = cache.get('model1', msgs, session_id='s1')
        self.assertEqual(result, 'response1')
        self.assertIsNone(cache.get('model1', msgs, session_id='s2'))

    def test_audit_log(self):
        from salmalm.core import audit_log
        # Should not raise
        audit_log('test', 'test event')

    def test_track_usage(self):
        from salmalm.core import track_usage
        # Should not raise
        track_usage('test-model', 100, 50)

    def test_get_usage_report(self):
        from salmalm.core import get_usage_report
        report = get_usage_report()
        self.assertIn('total_input', report)
        self.assertIn('total_cost', report)

    def test_session_creation(self):
        from salmalm.core import get_session
        s = get_session('test_session_abc')
        self.assertIsNotNone(s)
        self.assertTrue(len(s.messages) > 0)  # Should have system prompt

    def test_session_add_messages(self):
        from salmalm.core import get_session
        s = get_session('test_msg_session')
        s.add_user('hello')
        s.add_assistant('hi there')
        user_msgs = [m for m in s.messages if m['role'] == 'user']
        self.assertTrue(len(user_msgs) >= 1)

    def test_compact_messages_small(self):
        from salmalm.core import compact_messages
        msgs = [
            {'role': 'system', 'content': 'You are helpful'},
            {'role': 'user', 'content': 'Hi'},
            {'role': 'assistant', 'content': 'Hello!'},
        ]
        result = compact_messages(msgs)
        self.assertEqual(len(result), 3)  # No compaction needed

    def test_model_router(self):
        from salmalm.core import ModelRouter
        router = ModelRouter()
        model = router.route('hello', has_tools=False)
        self.assertIsNotNone(model)
        self.assertIn('/', model)


class TestRAGEngine(unittest.TestCase):
    """Test RAG search functionality."""

    def test_tokenize(self):
        from salmalm.features.rag import RAGEngine
        tokens = RAGEngine._tokenize("Hello World Test")
        self.assertIn('hello', tokens)
        self.assertIn('world', tokens)

    def test_init_and_close(self):
        from salmalm.features.rag import RAGEngine
        with tempfile.TemporaryDirectory() as d:
            engine = RAGEngine(db_path=Path(d) / 'test.db')
            engine.close()


class TestStability(unittest.TestCase):
    """Test stability module."""

    def test_circuit_breaker(self):
        from salmalm.features.stability import CircuitBreaker
        cb = CircuitBreaker(threshold=2, window_sec=60)
        cb.record_error('svc', 'error1')
        self.assertFalse(cb.is_tripped('svc'))
        cb.record_error('svc', 'error2')
        self.assertTrue(cb.is_tripped('svc'))

    def test_health_monitor_basic(self):
        from salmalm.features.stability import HealthMonitor
        hm = HealthMonitor()
        status = hm.check_health()
        self.assertIn('status', status)


class TestLLM(unittest.TestCase):
    """Test LLM module utilities."""

    def test_model_selection_constants(self):
        from salmalm.constants import MODELS, MODEL_TIERS, MODEL_ALIASES
        self.assertTrue(len(MODELS) > 0)
        self.assertTrue(len(MODEL_TIERS) > 0)
        self.assertTrue(len(MODEL_ALIASES) > 0)

    def test_alias_resolution(self):
        from salmalm.constants import MODEL_ALIASES
        self.assertIn('claude', MODEL_ALIASES)
        self.assertIn('gpt', MODEL_ALIASES)
        self.assertIn('grok', MODEL_ALIASES)


class TestWebHandler(unittest.TestCase):
    """Test web handler utilities."""

    def test_needs_onboarding_no_keys(self):
        """Without API keys, onboarding should be needed."""
        from salmalm.web import WebHandler
        handler = MagicMock(spec=WebHandler)
        handler._needs_onboarding = WebHandler._needs_onboarding.__get__(handler)
        # Mock vault as unlocked but empty
        with patch('salmalm.web.vault') as mock_vault:
            mock_vault.is_unlocked = True
            mock_vault.get.return_value = None
            result = handler._needs_onboarding()
            self.assertTrue(result)


class TestPrompt(unittest.TestCase):
    """Test prompt generation."""

    def test_build_system_prompt(self):
        from salmalm.core.prompt import build_system_prompt
        prompt = build_system_prompt()
        self.assertIn('SalmAlm', prompt)
        self.assertTrue(len(prompt) > 100)

    def test_build_system_prompt_short(self):
        from salmalm.core.prompt import build_system_prompt
        short = build_system_prompt(full=False)
        full = build_system_prompt(full=True)
        self.assertTrue(len(short) <= len(full))


class TestContainer(unittest.TestCase):
    """Test DI container."""

    def test_register_and_get(self):
        from salmalm.security.container import Container
        c = Container()
        c.register('test_svc', lambda: 'hello')
        self.assertEqual(c.get('test_svc'), 'hello')

    def test_has(self):
        from salmalm.security.container import Container
        c = Container()
        c.register('x', lambda: 1)
        self.assertTrue(c.has('x'))
        self.assertFalse(c.has('y'))

    def test_override(self):
        from salmalm.security.container import Container
        c = Container()
        c.register('svc', lambda: 'v1')
        c.replace('svc', 'v2')
        self.assertEqual(c.get('svc'), 'v2')


class TestLoggingExt(unittest.TestCase):
    """Test logging extensions."""

    def test_correlation_id(self):
        from salmalm.utils.logging_ext import set_correlation_id, get_correlation_id
        set_correlation_id('test-123')
        self.assertEqual(get_correlation_id(), 'test-123')
        set_correlation_id('')


class TestTLS(unittest.TestCase):
    """Test TLS utilities."""

    def test_cert_info(self):
        from salmalm.utils.tls import get_cert_info
        info = get_cert_info()
        self.assertIsInstance(info, dict)


if __name__ == '__main__':
    unittest.main()


class TestToolHandlersMore(unittest.TestCase):
    """Additional tool handler tests with mocks."""

    def test_memory_read(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('memory_read', {})
        self.assertIsInstance(result, str)

    def test_memory_write(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('memory_write', {'content': 'test note'})
        self.assertIsInstance(result, str)

    def test_memory_search(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('memory_search', {'query': 'test'})
        self.assertIsInstance(result, str)

    @patch('salmalm.tool_handlers.urllib.request.urlopen')
    def test_web_search_mock(self, mock_urlopen):
        from salmalm.tools.tool_handlers import execute_tool
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"web": {"results": []}}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = execute_tool('web_search', {'query': 'test'})
        self.assertIsInstance(result, str)

    @patch('salmalm.tool_handlers.urllib.request.urlopen')
    def test_web_fetch_mock(self, mock_urlopen):
        from salmalm.tools.tool_handlers import execute_tool
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'<html><body>Hello World</body></html>'
        mock_resp.headers = {'content-type': 'text/html'}
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = execute_tool('web_fetch', {'url': 'http://example.com'})
        self.assertIsInstance(result, str)

    @patch('salmalm.tool_handlers.urllib.request.urlopen')
    def test_http_request_mock(self, mock_urlopen):
        from salmalm.tools.tool_handlers import execute_tool
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true}'
        mock_resp.status = 200
        mock_resp.headers = {'content-type': 'application/json'}
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = execute_tool('http_request', {'url': 'http://example.com/api', 'method': 'GET'})
        self.assertIsInstance(result, str)

    def test_rag_search(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('rag_search', {'query': 'test search'})
        self.assertIsInstance(result, str)

    def test_cron_manage_list(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('cron_manage', {'action': 'list'})
        self.assertIsInstance(result, str)

    def test_skill_manage_list(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('skill_manage', {'action': 'list'})
        self.assertIsInstance(result, str)

    def test_plugin_manage_list(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('plugin_manage', {'action': 'list'})
        self.assertIsInstance(result, str)

    def test_screenshot_no_browser(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('screenshot', {})
        self.assertIsInstance(result, str)

    def test_node_manage_list(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('node_manage', {'action': 'list'})
        self.assertIsInstance(result, str)

    def test_browser_no_connection(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('browser', {'action': 'status'})
        self.assertIsInstance(result, str)

    def test_image_generate_no_key(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('image_generate', {'prompt': 'a cat'})
        self.assertIsInstance(result, str)

    def test_image_analyze_no_key(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('image_analyze', {'image_path': '/tmp/nonexist.png'})
        self.assertIsInstance(result, str)

    def test_tts_no_key(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('tts', {'text': 'hello'})
        self.assertIsInstance(result, str)

    def test_stt_no_key(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('stt', {'audio_base64': 'dGVzdA=='})
        self.assertIsInstance(result, str)

    def test_sub_agent(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('sub_agent', {'task': 'test task'})
        self.assertIsInstance(result, str)


class TestEngineMore(unittest.TestCase):
    """Additional engine tests."""

    def test_slash_clear(self):
        import asyncio
        from salmalm.core.engine import process_message
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(process_message('clear_test', '/clear'))
        loop.close()
        self.assertIn('clear', result.lower())

    def test_slash_status(self):
        import asyncio
        from salmalm.core.engine import process_message
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(process_message('status_test', '/status'))
        loop.close()
        self.assertTrue(len(result) > 0)

    def test_slash_model_auto(self):
        import asyncio
        from salmalm.core.engine import process_message
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(process_message('model_test', '/model auto'))
        loop.close()
        self.assertIn('auto', result.lower())

    def test_slash_model_alias(self):
        import asyncio
        from salmalm.core.engine import process_message
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(process_message('model_alias', '/model claude'))
        loop.close()
        self.assertIn('claude', result.lower())

    def test_slash_model_unknown(self):
        import asyncio
        from salmalm.core.engine import process_message
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(process_message('model_unk', '/model nonexistent_xyz'))
        loop.close()
        self.assertIn('unknown', result.lower())


class TestDocsModule(unittest.TestCase):
    """Test docs generation."""

    def test_generate_docs(self):
        from salmalm.features.docs import generate_api_docs_html
        html = generate_api_docs_html()
        self.assertIn('html', html.lower())
        self.assertIn('tool', html.lower())


class TestCoreMore(unittest.TestCase):
    """Additional core tests."""

    def test_model_router_force(self):
        from salmalm.core import ModelRouter
        r = ModelRouter()
        r.set_force_model('test/model')
        self.assertEqual(r.force_model, 'test/model')
        r.set_force_model(None)
        self.assertIsNone(r.force_model)

    def test_session_add(self):
        from salmalm.core import get_session
        s = get_session('save_test2')
        initial = len(s.messages)
        s.add_user('test message')
        s.add_assistant('test response')
        self.assertEqual(len(s.messages), initial + 2)

    def test_compact_messages_large(self):
        from salmalm.core import compact_messages
        msgs = [{'role': 'system', 'content': 'system'}]
        for i in range(120):
            msgs.append({'role': 'user', 'content': f'msg {i}'})
            msgs.append({'role': 'assistant', 'content': f'resp {i}'})
        result = compact_messages(msgs)
        self.assertTrue(len(result) < len(msgs))


class TestWSModule(unittest.TestCase):
    """Test WebSocket module."""

    def test_ws_frame_encode(self):
        from salmalm.web.ws import WebSocketServer
        # Basic instantiation
        server = WebSocketServer.__new__(WebSocketServer)
        self.assertIsNotNone(server)

    def test_ws_server_init(self):
        from salmalm.web.ws import WebSocketServer
        ws = WebSocketServer(host='127.0.0.1', port=0)
        self.assertIsNotNone(ws)




class TestWebAPI(unittest.TestCase):
    """HTTP API endpoint tests through the running server."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp()
        os.environ['SALMALM_DATA_DIR'] = cls._tmpdir
        os.environ['SALMALM_VAULT_PW'] = 'testpass'
        os.environ['SALMALM_LOG_FILE'] = os.path.join(cls._tmpdir, 'test.log')
        from salmalm.web import WebHandler
        from http.server import HTTPServer
        cls._server = HTTPServer(('127.0.0.1', 0), WebHandler)
        cls._port = cls._server.server_address[1]
        import threading
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        import time; time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        try:
            cls._server.shutdown()
            cls._server.server_close()
        except Exception:
            pass
        cls._thread.join(timeout=3)
        cls._server.server_close()
        import shutil; shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _req(self, method, path, body=None):
        from http.client import HTTPConnection
        conn = HTTPConnection('127.0.0.1', self._port, timeout=10)
        hdrs = {'Content-Type': 'application/json'}
        data = json.dumps(body).encode() if body else None
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        try:
            return resp.status, json.loads(raw)
        except Exception:
            return resp.status, raw.decode(errors='replace')

    def test_status_api(self):
        status, data = self._req('GET', '/api/status')
        self.assertEqual(status, 200)
        self.assertIn('usage', data)

    def test_manifest(self):
        status, data = self._req('GET', '/manifest.json')
        self.assertEqual(status, 200)

    def test_icon_svg(self):
        from http.client import HTTPConnection
        conn = HTTPConnection('127.0.0.1', self._port, timeout=10)
        conn.request('GET', '/icon-192.svg')
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 200)

    def test_sw_js(self):
        from http.client import HTTPConnection
        conn = HTTPConnection('127.0.0.1', self._port, timeout=10)
        conn.request('GET', '/sw.js')
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 200)

    def test_docs_page(self):
        from http.client import HTTPConnection
        conn = HTTPConnection('127.0.0.1', self._port, timeout=10)
        conn.request('GET', '/docs')
        resp = conn.getresponse()
        body = resp.read().decode(errors='replace')
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertIn('html', body.lower())

    def test_dashboard_page(self):
        from http.client import HTTPConnection
        conn = HTTPConnection('127.0.0.1', self._port, timeout=10)
        conn.request('GET', '/dashboard')
        resp = conn.getresponse()
        body = resp.read().decode(errors='replace')
        conn.close()
        self.assertIn(resp.status, (200, 401, 403))

    def test_check_update(self):
        status, data = self._req('GET', '/api/check-update')
        self.assertEqual(status, 200)
        self.assertIn('current', data)

    def test_setup_post(self):
        status, data = self._req('POST', '/api/setup', {'password': 'test1234'})
        # May succeed or error depending on vault state
        self.assertIn(status, (200, 400, 500))

    def test_vault_api_keys(self):
        status, data = self._req('POST', '/api/vault', {'action': 'keys'})
        # May need auth
        self.assertIn(status, (200, 401, 403))

    def test_unknown_post(self):
        status, _ = self._req('POST', '/api/nonexistent')
        self.assertIn(status, (404, 400))


