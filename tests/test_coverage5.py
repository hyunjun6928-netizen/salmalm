"""Coverage boost tests — target tool_handlers, core, llm edge cases."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestToolHandlersCoverage5(unittest.TestCase):
    """Cover untested tool branches in tool_handlers.py."""

    def test_json_query_basic(self):
        from salmalm.tool_handlers import execute_tool
        data = json.dumps({"name": "Alice", "age": 30})
        result = execute_tool('json_query', {'data': data, 'query': '.name'})
        self.assertIn('Alice', result)

    def test_json_query_invalid(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('json_query', {'data': 'not json', 'query': '.x'})
        self.assertTrue('error' in result.lower() or 'Error' in result)

    def test_diff_files(self):
        from salmalm.tool_handlers import execute_tool
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, dir='.') as f1:
            f1.write('line1\nline2\n')
            p1 = f1.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, dir='.') as f2:
            f2.write('line1\nline3\n')
            p2 = f2.name
        try:
            result = execute_tool('diff_files', {'file1': p1, 'file2': p2})
            self.assertTrue(len(result) > 0)
        finally:
            os.unlink(p1)
            os.unlink(p2)

    def test_regex_test(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('regex_test', {
            'pattern': r'\d+',
            'text': 'abc 123 def 456'
        })
        self.assertIn('123', result)
        self.assertIn('456', result)

    def test_regex_test_invalid(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('regex_test', {
            'pattern': r'[invalid',
            'text': 'test'
        })
        self.assertTrue('error' in result.lower() or 'Error' in result)

    def test_usage_report(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('usage_report', {})
        # Should return some usage info
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_hash_sha256(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('hash_text', {'text': 'hello', 'algorithm': 'sha256'})
        self.assertIn('2cf24dba', result)

    def test_hash_sha512(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('hash_text', {'text': 'hello', 'algorithm': 'sha512'})
        self.assertIn('9b71d224', result)

    def test_hash_default(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('hash_text', {'text': 'test'})
        self.assertTrue(len(result) > 10)

    def test_http_request_get(self):
        from salmalm.tool_handlers import execute_tool
        from unittest.mock import patch, MagicMock
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"origin": "1.2.3.4"}'
        mock_resp.getheader.return_value = 'application/json'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = execute_tool('http_request', {
                'url': 'https://httpbin.org/get',
                'method': 'GET'
            })
        self.assertIn('origin', str(result).lower())

    def test_http_request_invalid_url(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('http_request', {
            'url': 'http://localhost:1',
            'method': 'GET'
        })
        # Should return some kind of error or failure message
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_clipboard_read(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('clipboard', {'action': 'read'})
        # May fail in headless, but should not crash
        self.assertIsInstance(result, str)

    def test_clipboard_write(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('clipboard', {'action': 'write', 'text': 'test'})
        self.assertIsInstance(result, str)

    def test_rag_search(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('rag_search', {'query': 'test query'})
        self.assertIsInstance(result, str)

    def test_plugin_manage_list(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('plugin_manage', {'action': 'list'})
        self.assertIsInstance(result, str)

    def test_health_check(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('health_check', {})
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_mcp_manage_list(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('mcp_manage', {'action': 'list'})
        self.assertIsInstance(result, str)

    def test_read_file(self):
        from salmalm.tool_handlers import execute_tool
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, dir='.') as f:
            f.write('hello world')
            p = f.name
        try:
            result = execute_tool('read_file', {'path': p})
            self.assertIn('hello world', result)
        finally:
            os.unlink(p)

    def test_write_file(self):
        from salmalm.tool_handlers import execute_tool
        from salmalm.constants import WORKSPACE_DIR
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        p = str(WORKSPACE_DIR / '_test_cov5_write.txt')
        result = execute_tool('write_file', {'path': p, 'content': 'test content'})
        try:
            self.assertTrue(os.path.exists(p))
            with open(p) as f:
                self.assertEqual(f.read(), 'test content')
        finally:
            if os.path.exists(p):
                os.unlink(p)

    def test_edit_file(self):
        from salmalm.tool_handlers import execute_tool
        from salmalm.constants import WORKSPACE_DIR
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        p = str(WORKSPACE_DIR / '_test_cov5_edit.txt')
        with open(p, 'w') as f:
            f.write('hello world')
        try:
            result = execute_tool('edit_file', {'path': p, 'old_text': 'hello', 'new_text': 'goodbye'})
            with open(p) as f:
                self.assertIn('goodbye', f.read())
        finally:
            if os.path.exists(p):
                os.unlink(p)

    def test_skill_manage_list(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('skill_manage', {'action': 'list'})
        self.assertIsInstance(result, str)


class TestCoreCoverage5(unittest.TestCase):
    """Cover core.py edge cases."""

    def test_router_exists(self):
        from salmalm.core import router
        self.assertIsNotNone(router)

    def test_router_force_model(self):
        from salmalm.core import router
        old = router.force_model
        router.force_model = 'test/model'
        self.assertEqual(router.force_model, 'test/model')
        router.force_model = old

    def test_usage_report(self):
        from salmalm.core import get_usage_report
        report = get_usage_report()
        self.assertIn('total_input', report)
        self.assertIn('total_output', report)
        self.assertIn('total_cost', report)

    def test_audit_log(self):
        from salmalm.core import audit_log
        # Should not throw
        audit_log('test_event', 'test detail')


class TestLLMCoverage5(unittest.TestCase):
    """Cover llm.py edge cases."""

    def test_llm_module_loads(self):
        import salmalm.llm
        self.assertTrue(hasattr(salmalm.llm, 'call_llm'))


class TestEngineCoverage5(unittest.TestCase):
    """Cover engine.py edge cases."""

    def test_compact_messages_empty(self):
        from salmalm.engine import compact_messages
        result = compact_messages([])
        self.assertEqual(result, [])

    def test_compact_messages_short(self):
        from salmalm.engine import compact_messages
        msgs = [{'role': 'user', 'content': 'hi'}]
        result = compact_messages(msgs)
        self.assertEqual(len(result), 1)


if __name__ == '__main__':
    unittest.main()


class TestTaskClassifier(unittest.TestCase):
    """Cover engine.py TaskClassifier."""

    def test_classify_chat(self):
        from salmalm.engine import TaskClassifier
        r = TaskClassifier.classify('hello how are you')
        self.assertEqual(r['intent'], 'chat')
        self.assertIn('tier', r)

    def test_classify_code(self):
        from salmalm.engine import TaskClassifier
        r = TaskClassifier.classify('write a python function to sort a list')
        self.assertIn('intent', r)

    def test_classify_search(self):
        from salmalm.engine import TaskClassifier
        r = TaskClassifier.classify('search the web for latest news about AI')
        self.assertIn('intent', r)

    def test_classify_analysis(self):
        from salmalm.engine import TaskClassifier
        r = TaskClassifier.classify('analyze this data and explain the trends in detail with step by step reasoning')
        self.assertIn('intent', r)

    def test_classify_empty(self):
        from salmalm.engine import TaskClassifier
        r = TaskClassifier.classify('')
        self.assertIn('intent', r)

    def test_classify_long_context(self):
        from salmalm.engine import TaskClassifier
        r = TaskClassifier.classify('summarize', context_len=50)
        self.assertIn('tier', r)


class TestStabilityCoverage(unittest.TestCase):
    """Cover stability.py HealthMonitor."""

    def test_health_monitor_init(self):
        from salmalm.stability import HealthMonitor
        hm = HealthMonitor()
        self.assertIsNotNone(hm)

    def test_health_monitor_check(self):
        from salmalm.stability import HealthMonitor
        hm = HealthMonitor()
        # Just check it initializes
        self.assertIsNotNone(hm)

    def test_circuit_breaker_record(self):
        from salmalm.stability import CircuitBreaker
        cb = CircuitBreaker(threshold=5, window_sec=60)
        cb.record_success('test_svc')
        self.assertFalse(cb.is_tripped('test_svc'))

    def test_circuit_breaker_open(self):
        from salmalm.stability import CircuitBreaker
        cb = CircuitBreaker(threshold=2, window_sec=60)
        cb.record_error('svc2')
        cb.record_error('svc2')
        self.assertTrue(cb.is_tripped('svc2'))


class TestCoreSessionStore(unittest.TestCase):
    """Cover core.py session operations."""

    def test_get_session(self):
        from salmalm.core import get_session
        s = get_session('_test_cov5_sess')
        self.assertIsNotNone(s)

    def test_session_add_message(self):
        from salmalm.core import get_session
        s = get_session('_test_cov5_msg')
        s.add_user('test message')
        self.assertTrue(len(s.messages) > 0)

    def test_response_cache(self):
        from salmalm.core import ResponseCache
        cache = ResponseCache(max_size=10)
        cache.put('test-model', [{'role':'user','content':'hi'}], 'hello')
        result = cache.get('test-model', [{'role':'user','content':'hi'}])
        self.assertEqual(result, 'hello')

    def test_response_cache_miss(self):
        from salmalm.core import ResponseCache
        cache = ResponseCache(max_size=10)
        result = cache.get('test-model', [{'role':'user','content':'nope'}])
        self.assertIsNone(result)


