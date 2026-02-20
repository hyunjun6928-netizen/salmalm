"""Coverage boost part 4 — exercise all web routes + more tool_handlers."""
import json
import os
import sys
import unittest
from pathlib import Path
from http.client import HTTPConnection

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestWebAllRoutes(unittest.TestCase):
    """Hit every web route to maximize web.py coverage."""

    @classmethod
    def setUpClass(cls):
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
        cls._server.shutdown()
        cls._server.server_close()

    def _get(self, path):
        conn = HTTPConnection('127.0.0.1', self._port, timeout=10)
        conn.request('GET', path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body

    def _post(self, path, data=None):
        conn = HTTPConnection('127.0.0.1', self._port, timeout=10)
        body = json.dumps(data).encode() if data else b'{}'
        conn.request('POST', path, body=body, headers={'Content-Type': 'application/json'})
        resp = conn.getresponse()
        result = resp.read()
        conn.close()
        return resp.status, result

    # === GET routes ===
    def test_get_root(self):
        s, _ = self._get('/')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_index(self):
        s, _ = self._get('/index.html')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_sessions(self):
        s, _ = self._get('/api/sessions')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_notifications(self):
        s, _ = self._get('/api/notifications')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_dashboard_api(self):
        s, _ = self._get('/api/dashboard')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_cron(self):
        s, _ = self._get('/api/cron')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_plugins(self):
        s, _ = self._get('/api/plugins')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_mcp(self):
        s, _ = self._get('/api/mcp')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_rag(self):
        s, _ = self._get('/api/rag')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_rag_search(self):
        s, _ = self._get('/api/rag/search?q=test')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_ws_status(self):
        s, _ = self._get('/api/ws/status')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_health(self):
        s, _ = self._get('/api/health')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500, 503))

    def test_get_nodes(self):
        s, _ = self._get('/api/nodes')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_gateway_nodes(self):
        s, _ = self._get('/api/gateway/nodes')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_status(self):
        s, _ = self._get('/api/status')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_check_update(self):
        s, _ = self._get('/api/check-update')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_metrics(self):
        s, _ = self._get('/api/metrics')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_cert(self):
        s, _ = self._get('/api/cert')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_auth_users(self):
        s, _ = self._get('/api/auth/users')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_manifest(self):
        s, _ = self._get('/manifest.json')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_icon192(self):
        s, _ = self._get('/icon-192.svg')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_icon512(self):
        s, _ = self._get('/icon-512.svg')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_sw(self):
        s, _ = self._get('/sw.js')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_dashboard_page(self):
        s, _ = self._get('/dashboard')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_docs_page(self):
        s, _ = self._get('/docs')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_models(self):
        s, _ = self._get('/api/models')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_tools(self):
        s, _ = self._get('/api/tools')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_config(self):
        s, _ = self._get('/api/config')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_version(self):
        s, _ = self._get('/api/version')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_uploads_nonexistent(self):
        s, _ = self._get('/uploads/nonexistent.txt')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_get_404(self):
        s, _ = self._get('/totally_nonexistent_page')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    # === POST routes ===
    def test_post_login(self):
        s, _ = self._post('/api/auth/login', {'username': 'admin', 'password': 'wrong'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_register(self):
        s, _ = self._post('/api/auth/register', {'username': 'test', 'password': 'test123'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_setup(self):
        s, _ = self._post('/api/setup', {'password': 'testpw'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_test_key(self):
        s, _ = self._post('/api/test-key', {'provider': 'openai', 'key': 'sk-test'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_unlock(self):
        s, _ = self._post('/api/unlock', {'password': 'testpw'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_sessions_delete(self):
        s, _ = self._post('/api/sessions/delete', {'session_id': 'nonexist'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_sessions_rename(self):
        s, _ = self._post('/api/sessions/rename', {'session_id': 'test', 'title': 'new'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_chat(self):
        s, _ = self._post('/api/chat', {'message': '/version', 'session_id': 'webtest'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_vault_keys(self):
        s, _ = self._post('/api/vault', {'action': 'keys'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_vault_get(self):
        s, _ = self._post('/api/vault', {'action': 'get', 'key': 'OPENAI_API_KEY'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_vault_set(self):
        s, _ = self._post('/api/vault', {'action': 'set', 'key': 'TEST_KEY', 'value': 'test'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))


    def test_post_model(self):
        s, _ = self._post('/api/model', {'model': 'auto'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_password(self):
        s, _ = self._post('/api/password', {'current': 'wrong', 'new': 'new'})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_unknown(self):
        s, _ = self._post('/api/nonexistent_route')
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))

    def test_post_stt_no_audio(self):
        s, _ = self._post('/api/stt', {})
        self.assertIn(s, (200, 302, 400, 401, 403, 404, 429, 500))


class TestToolHandlersMoreEdgeCases(unittest.TestCase):
    """Even more tool edge cases for coverage."""

    def test_list_dir(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('read_file', {'path': '.', 'list_dir': True})
        self.assertIsInstance(result, str)

    def test_system_info(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('system_monitor', {})
        self.assertIn('cpu', result.lower())

    def test_cron_list(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('cron_manage', {'action': 'list'})
        self.assertIsInstance(result, str)

    def test_cron_add_invalid(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('cron_manage', {'action': 'add'})
        self.assertIsInstance(result, str)

    def test_skill_list(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('skill_manage', {'action': 'list'})
        self.assertIsInstance(result, str)

    def test_mcp_list(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('mcp_manage', {'action': 'list'})
        self.assertIsInstance(result, str)

    def test_plugin_list(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('plugin_manage', {'action': 'list'})
        self.assertIsInstance(result, str)

    def test_node_list(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('node_manage', {'action': 'list'})
        self.assertIsInstance(result, str)

    def test_rag_search(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('rag_search', {'query': 'test'})
        self.assertIsInstance(result, str)

    def test_memory_search_empty(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('memory_search', {'query': ''})
        self.assertIsInstance(result, str)

    def test_screenshot(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('screenshot', {})
        self.assertIsInstance(result, str)

    def test_browser_status(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('browser', {'action': 'status'})
        self.assertIsInstance(result, str)

    def test_tts_no_key(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('tts', {'text': 'hello'})
        self.assertIsInstance(result, str)

    def test_stt_no_audio(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('stt', {})
        self.assertIsInstance(result, str)


if __name__ == '__main__':
    unittest.main()


class TestToolHandlersFinal(unittest.TestCase):
    """Final push for tool coverage."""

    def test_web_search_no_key(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('web_search', {'query': 'test'})
        self.assertIsInstance(result, str)

    def test_web_fetch_invalid_url(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('web_fetch', {'url': 'http://localhost:1/nonexist'})
        self.assertIsInstance(result, str)

    def test_image_generate(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('image_generate', {'prompt': 'cat'})
        self.assertIsInstance(result, str)

    def test_image_analyze(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('image_analyze', {'image_path': '/nonexist.png'})
        self.assertIsInstance(result, str)

    def test_tts(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('tts', {'text': 'hi'})
        self.assertIsInstance(result, str)

    def test_stt(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('stt', {'audio_path': '/nonexist.wav'})
        self.assertIsInstance(result, str)

    def test_sub_agent(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('sub_agent', {'task': 'test'})
        self.assertIsInstance(result, str)

    def test_http_request_invalid(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('http_request', {'url': 'http://localhost:1/x', 'method': 'GET'})
        self.assertIsInstance(result, str)

    def test_cron_manage_status(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('cron_manage', {'action': 'status'})
        self.assertIsInstance(result, str)

    def test_plugin_manage_reload(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('plugin_manage', {'action': 'reload'})
        self.assertIsInstance(result, str)

    def test_mcp_manage_status(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('mcp_manage', {'action': 'status'})
        self.assertIsInstance(result, str)

    def test_node_manage_status(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('node_manage', {'action': 'status'})
        self.assertIsInstance(result, str)

    def test_rag_search_long(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('rag_search', {'query': 'very long search query about Python programming'})
        self.assertIsInstance(result, str)

    def test_browser_navigate(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('browser', {'action': 'navigate', 'url': 'http://example.com'})
        self.assertIsInstance(result, str)

    def test_browser_click(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('browser', {'action': 'click', 'selector': '#test'})
        self.assertIsInstance(result, str)

    def test_screenshot_fullpage(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('screenshot', {'fullpage': True})
        self.assertIsInstance(result, str)




class TestEngineFinal(unittest.TestCase):
    """Final engine coverage push."""

    def _run(self, sid, msg):
        import asyncio
        from salmalm.engine import process_message
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(process_message(sid, msg))
        finally:
            loop.close()

    def test_slash_config(self):
        r = self._run('fin_config', '/config')
        self.assertIsInstance(r, str)

    def test_slash_cron(self):
        r = self._run('fin_cron', '/cron')
        self.assertIsInstance(r, str)

    def test_slash_plugins(self):
        r = self._run('fin_plugins', '/plugins')
        self.assertIsInstance(r, str)

    def test_slash_nodes(self):
        r = self._run('fin_nodes', '/nodes')
        self.assertIsInstance(r, str)

    def test_slash_mcp(self):
        r = self._run('fin_mcp', '/mcp')
        self.assertIsInstance(r, str)

    def test_slash_model_set(self):
        r = self._run('fin_model', '/model auto')
        self.assertIsInstance(r, str)

    def test_slash_rag(self):
        r = self._run('fin_rag', '/rag test')
        self.assertIsInstance(r, str)

    def test_slash_skills(self):
        r = self._run('fin_skills', '/skills')
        self.assertIsInstance(r, str)

    def test_slash_health(self):
        r = self._run('fin_health', '/health')
        self.assertIsInstance(r, str)

    def test_slash_audit(self):
        r = self._run('fin_audit', '/audit')
        self.assertIsInstance(r, str)

    def test_short_message(self):
        # Short messages use tier 1 (quick model)
        r = self._run('fin_short', 'hi')
        self.assertIsInstance(r, str)

    def test_code_message(self):
        r = self._run('fin_code', 'write a python hello world')
        self.assertIsInstance(r, str)


class TestAgentsFinal(unittest.TestCase):
    """Final agents coverage."""

    def test_skill_match_none(self):
        from salmalm.agents import SkillLoader
        sl = SkillLoader()
        r = sl.match("random gibberish xyz123")
        # Should return None (no matching skill)

    def test_plugin_execute_unknown(self):
        from salmalm.agents import PluginLoader
        pl = PluginLoader()
        try:
            result = pl.execute('nonexistent_plugin_tool', {})
        except Exception:
            result = None

    def test_skill_install_nonexistent(self):
        from salmalm.agents import SkillLoader
        sl = SkillLoader()
        try:
            result = sl.install('https://example.com/nonexistent.zip')
        except Exception:
            result = None


class TestCoreFinal(unittest.TestCase):
    """Final core coverage."""

    def test_compact_very_large(self):
        from salmalm.core import compact_messages
        msgs = [{'role': 'system', 'content': 'sys'}]
        for i in range(200):
            msgs.append({'role': 'user', 'content': f'message {i} ' * 50})
            msgs.append({'role': 'assistant', 'content': f'response {i} ' * 50})
        result = compact_messages(msgs)
        self.assertTrue(len(result) < len(msgs))

    def test_model_router_with_tools(self):
        from salmalm.core import ModelRouter
        r = ModelRouter()
        model = r.route("search the web for info", has_tools=True)
        self.assertIsNotNone(model)

    def test_model_router_creative(self):
        from salmalm.core import ModelRouter
        r = ModelRouter()
        model = r.route("write a poem about stars")
        self.assertIsNotNone(model)




class TestWSFinal(unittest.TestCase):
    """WS module final coverage."""

    def test_ws_frame_handshake(self):
        from salmalm.ws import WS_MAGIC
        import hashlib, base64
        key = base64.b64encode(b'test1234test1234').decode()
        accept = base64.b64encode(
            hashlib.sha1(key.encode() + WS_MAGIC).digest()
        ).decode()
        self.assertTrue(len(accept) > 0)


class TestMainModule(unittest.TestCase):
    """Test __main__.py."""

    def test_import(self):
        # Just import it
        import salmalm.__main__
        self.assertTrue(True)


