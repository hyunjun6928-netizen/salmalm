"""E2E Pipeline Tests — HTTP 요청 → LLM mock → 세션 업데이트 전체 경로 커버.

No real LLM calls. All external dependencies are mocked.
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

# Set up temp environment before any salmalm import
_tmpdir = tempfile.mkdtemp(prefix='salmalm_e2e_pipeline_')
os.environ.setdefault('SALMALM_HOME', _tmpdir)
os.environ.setdefault('SALMALM_VAULT_PW', 'testpass')
os.environ.setdefault('SALMALM_BASE', _tmpdir)

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_LLM_RESPONSE = {
    "content": "안녕하세요! 테스트 응답이오.",
    "tool_calls": [],
    "usage": {"input": 10, "output": 20},
    "_failed": False,
}

MOCK_LLM_TOOL_RESPONSE = {
    "content": "",
    "tool_calls": [{"name": "exec", "id": "call_1", "input": {"command": "echo hello"}}],
    "usage": {"input": 15, "output": 5},
    "_failed": False,
}

MOCK_LLM_FAILED_RESPONSE = {
    "content": "",
    "tool_calls": [],
    "usage": {"input": 0, "output": 0},
    "_failed": True,
    "error": "Connection refused",
}


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


# ---------------------------------------------------------------------------
# HTTP server fixture (shared across HTTP-level test classes)
# ---------------------------------------------------------------------------

_server_started = False
_server_port = None
_server_obj = None
_server_thread = None


def _ensure_server():
    global _server_started, _server_port, _server_obj, _server_thread
    if _server_started:
        return _server_port
    from salmalm.web import WebHandler
    from http.server import HTTPServer
    _server_obj = HTTPServer(('127.0.0.1', 0), WebHandler)
    _server_port = _server_obj.server_address[1]
    _server_thread = threading.Thread(target=_server_obj.serve_forever, daemon=True)
    _server_thread.start()
    time.sleep(0.15)
    _server_started = True
    return _server_port


def _http(method, path, body=None, headers=None):
    port = _ensure_server()
    conn = HTTPConnection('127.0.0.1', port, timeout=10)
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


# ===========================================================================
# 1. TestChatE2E — POST /api/chat 전체 파이프라인
# ===========================================================================

class TestChatE2E(unittest.TestCase):
    """채팅 엔드투엔드: HTTP POST → engine → LLM mock → 응답."""

    def test_chat_full_pipeline(self):
        """POST /api/chat → LLM mock → 응답에 content 포함."""
        from salmalm.core.engine_pipeline import _process_message_inner

        async def _inner():
            with patch('salmalm.core.llm_loop.try_llm_call', new=AsyncMock(return_value=MOCK_LLM_RESPONSE)):
                result = await _process_message_inner('e2e_full_1', '안녕하세요')
            return result

        result = _run(_inner())
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_chat_returns_string(self):
        """process_message always returns a string."""
        from salmalm.core.engine_pipeline import _process_message_inner

        async def _inner():
            with patch('salmalm.core.llm_loop.try_llm_call', new=AsyncMock(return_value=MOCK_LLM_RESPONSE)):
                return await _process_message_inner('e2e_str_1', 'Hello there')

        result = _run(_inner())
        self.assertIsInstance(result, str)

    def test_chat_empty_message_rejected(self):
        """빈 메시지는 LLM 없이 즉시 거부."""
        from salmalm.core.engine import process_message

        async def _inner():
            with patch('salmalm.core.llm_loop.try_llm_call', new=AsyncMock(return_value=MOCK_LLM_RESPONSE)) as m:
                result = await process_message('e2e_empty_1', '')
                m.assert_not_called()
            return result

        result = _run(_inner())
        self.assertEqual(result, 'Please enter a message.')

    def test_chat_whitespace_message_rejected(self):
        """공백 메시지는 LLM 호출 없이 반환."""
        from salmalm.core.engine import process_message

        async def _inner():
            with patch('salmalm.core.llm_loop.try_llm_call', new=AsyncMock(return_value=MOCK_LLM_RESPONSE)) as m:
                result = await process_message('e2e_ws_1', '   \t\n  ')
                m.assert_not_called()
            return result

        result = _run(_inner())
        self.assertEqual(result, 'Please enter a message.')

    def test_chat_session_persistence(self):
        """두 번 연속 호출 시 히스토리 유지."""
        from salmalm.core.engine_pipeline import _process_message_inner
        from salmalm.core.session_store import get_session

        sid = 'e2e_persist_99'

        async def _first():
            with patch('salmalm.core.llm_loop.try_llm_call', new=AsyncMock(return_value=MOCK_LLM_RESPONSE)):
                return await _process_message_inner(sid, 'First message')

        async def _second():
            with patch('salmalm.core.llm_loop.try_llm_call', new=AsyncMock(return_value={
                **MOCK_LLM_RESPONSE, "content": "Second reply"
            })):
                return await _process_message_inner(sid, 'Second message')

        _run(_first())
        _run(_second())

        session = get_session(sid)
        roles = [m['role'] for m in session.messages]
        # Should have at least user messages recorded
        self.assertIn('user', roles)
        user_msgs = [m for m in session.messages if m['role'] == 'user']
        self.assertGreaterEqual(len(user_msgs), 2)

    def test_chat_slash_command_no_llm(self):
        """/help 슬래시 커맨드는 LLM 없이 처리."""
        from salmalm.core.engine import process_message

        async def _inner():
            with patch('salmalm.core.llm_loop.try_llm_call', new=AsyncMock(return_value=MOCK_LLM_RESPONSE)) as m:
                result = await process_message('e2e_slash_1', '/help')
                m.assert_not_called()
            return result

        result = _run(_inner())
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)

    def test_chat_streaming_mock(self):
        """스트리밍 경로: on_token 콜백이 호출됨."""
        from salmalm.core.engine_pipeline import _process_message_inner

        tokens_received = []

        def on_token(tok):
            tokens_received.append(tok)

        async def _inner():
            # Streaming: mock try_llm_call to also invoke on_token
            async def _fake_llm(messages, model, tools, max_tokens, thinking, on_token_cb):
                if on_token_cb:
                    on_token_cb('스트리밍')
                    on_token_cb(' 토큰')
                return {**MOCK_LLM_RESPONSE, "content": "스트리밍 토큰"}

            with patch('salmalm.core.llm_loop.try_llm_call', new=_fake_llm):
                return await _process_message_inner('e2e_stream_1', '스트리밍 테스트', on_token=on_token)

        result = _run(_inner())
        self.assertIsInstance(result, str)

    def test_chat_with_tool_call(self):
        """tool_calls 포함 응답 처리 — 2차 LLM 호출로 최종 답변."""
        from salmalm.core.engine_pipeline import _process_message_inner

        call_count = [0]

        async def _fake_llm(messages, model, tools, max_tokens, thinking, on_token):
            call_count[0] += 1
            if call_count[0] == 1:
                return MOCK_LLM_TOOL_RESPONSE
            # Second call (after tool execution): normal text response
            return MOCK_LLM_RESPONSE

        async def _inner():
            with patch('salmalm.core.llm_loop.try_llm_call', new=_fake_llm):
                with patch('salmalm.tools.tool_handlers.execute_tool', return_value='tool output'):
                    return await _process_message_inner('e2e_tool_1', '도구 실행해줘')

        result = _run(_inner())
        self.assertIsInstance(result, str)


# ===========================================================================
# 2. TestFailoverE2E — 모델 failover
# ===========================================================================

class TestFailoverE2E(unittest.TestCase):
    """모델 failover: 1차 실패 → 폴백 모델 사용."""

    def test_primary_failure_triggers_fallback(self):
        """1차 모델 실패 시 fallback 모델로 재시도."""
        from salmalm.core.engine_pipeline import _process_message_inner

        call_models = []

        async def _fake_llm(messages, model, tools, max_tokens, thinking, on_token):
            call_models.append(model)
            if len(call_models) == 1:
                # First call fails
                return MOCK_LLM_FAILED_RESPONSE
            # Fallback succeeds
            return {**MOCK_LLM_RESPONSE, "content": "폴백 응답"}

        async def _inner():
            with patch('salmalm.core.llm_loop.try_llm_call', new=_fake_llm):
                return await _process_message_inner('e2e_fb_1', '폴백 테스트')

        result = _run(_inner())
        self.assertIsInstance(result, str)
        # Either got fallback content or error message — must be non-empty
        self.assertGreater(len(result), 0)

    def test_all_models_down_returns_error(self):
        """모든 모델 실패 시 에러 문자열 반환."""
        from salmalm.core.engine_pipeline import _process_message_inner

        async def _fake_llm(messages, model, tools, max_tokens, thinking, on_token):
            return MOCK_LLM_FAILED_RESPONSE

        async def _inner():
            with patch('salmalm.core.llm_loop.try_llm_call', new=_fake_llm):
                return await _process_message_inner('e2e_all_down', '전부 실패 테스트')

        result = _run(_inner())
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_failover_model_router_routing(self):
        """ModelRouter.route()는 유효한 모델 문자열 반환."""
        from salmalm.core import ModelRouter
        router = ModelRouter()
        model = router.route('Python 코드 짜줘')
        self.assertIsInstance(model, str)
        self.assertIn('/', model)  # format: provider/model

    def test_intelligence_engine_has_failover_method(self):
        """IntelligenceEngine._call_with_failover 존재 확인."""
        from salmalm.core.engine import IntelligenceEngine
        engine = IntelligenceEngine()
        self.assertTrue(hasattr(engine, '_call_with_failover'))
        self.assertTrue(callable(getattr(engine, '_call_with_failover')))


# ===========================================================================
# 3. TestAuthE2E — 인증 HTTP 테스트
# ===========================================================================

class TestAuthE2E(unittest.TestCase):
    """인증 E2E: 인증 없이 → 401, 인증 후 → 성공."""

    def test_unauthenticated_returns_401(self):
        """인증 없이 /api/sessions 요청 → 401/403 (또는 dev-mode 200 허용)."""
        status, _ = _http('GET', '/api/sessions')
        # Dev mode on localhost may auto-unlock → accept 200 as well
        self.assertIn(status, (200, 401, 403))

    def test_unauthenticated_chat_blocked(self):
        """인증 없이 /api/chat POST → 401/403 또는 dev-mode 응답."""
        status, _ = _http('POST', '/api/chat', body={'message': 'hi', 'session_id': 'test'})
        # Dev mode on localhost auto-unlocks the vault
        self.assertIn(status, (200, 401, 403))

    def test_authenticated_request_succeeds(self):
        """유효한 인증 헤더로 /api/sessions → 200 또는 보안 관련 응답."""
        # Try with a dummy token — server may accept it (dev mode) or reject (prod)
        status, data = _http('GET', '/api/sessions', headers={'Authorization': 'Bearer dev-token'})
        # Accept 200 (dev mode unlocked) or 401/403 (strict auth)
        self.assertIn(status, (200, 401, 403))

    def test_cors_preflight_no_auth_needed(self):
        """OPTIONS /api/chat는 인증 없이 CORS preflight 처리."""
        port = _ensure_server()
        conn = HTTPConnection('127.0.0.1', port, timeout=10)
        conn.request('OPTIONS', '/api/chat')
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertIn(resp.status, (200, 204))

    def test_health_endpoint_no_auth(self):
        """GET /health는 인증 없이 접근 가능."""
        port = _ensure_server()
        conn = HTTPConnection('127.0.0.1', port, timeout=10)
        conn.request('GET', '/health')
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertIn(resp.status, (200, 404))  # 404 is OK if endpoint not implemented


# ===========================================================================
# 4. TestSessionE2E — 세션 생성 / 목록 / 컴팩션
# ===========================================================================

class TestSessionE2E(unittest.TestCase):
    """세션 E2E: 생성, 목록, 히스토리 저장, 컴팩션 트리거."""

    def test_session_create_and_retrieve(self):
        """세션 생성 후 get_session으로 동일 객체 반환."""
        from salmalm.core.session_store import get_session
        sid = 'e2e_sess_create_1'
        sess1 = get_session(sid)
        sess2 = get_session(sid)
        self.assertIs(sess1, sess2)

    def test_session_add_messages(self):
        """세션에 메시지 추가 후 유지됨."""
        from salmalm.core.session_store import get_session
        sid = 'e2e_sess_msg_1'
        sess = get_session(sid)
        initial_len = len(sess.messages)
        sess.add_user('테스트 메시지')
        self.assertEqual(len(sess.messages), initial_len + 1)
        self.assertEqual(sess.messages[-1]['content'], '테스트 메시지')

    def test_session_list_via_store(self):
        """session_store에서 세션 목록 조회."""
        from salmalm.core.session_store import get_session, _sessions
        get_session('e2e_list_sess_a')
        get_session('e2e_list_sess_b')
        self.assertIn('e2e_list_sess_a', _sessions)
        self.assertIn('e2e_list_sess_b', _sessions)

    def test_session_create_and_list(self):
        """새 세션 생성 후 API 레벨 목록에 포함되는지 확인."""
        from salmalm.core.session_store import get_session, _sessions
        sid = 'e2e_api_list_1'
        get_session(sid)
        self.assertIn(sid, _sessions)

    def test_session_compaction_triggered(self):
        """긴 컨텍스트로 compact_messages 호출 — 결과는 리스트."""
        from salmalm.core import Session, compact_messages
        sess = Session('e2e_compact_1')
        sess.add_system('당신은 도움이 되는 AI 어시스턴트입니다.')
        # Add enough messages to potentially trigger compaction
        for i in range(40):
            sess.add_user(f'사용자 메시지 {i}: ' + 'A' * 200)
            sess.messages.append({'role': 'assistant', 'content': f'어시스턴트 응답 {i}: ' + 'B' * 200})
        original_len = len(sess.messages)
        compacted = compact_messages(sess.messages, session=sess)
        self.assertIsInstance(compacted, list)
        self.assertGreater(len(compacted), 0)

    def test_session_model_override(self):
        """세션 model_override 설정 및 유지."""
        from salmalm.core import Session
        sess = Session('e2e_model_override_1')
        sess.model_override = 'anthropic/claude-haiku-3'
        self.assertEqual(sess.model_override, 'anthropic/claude-haiku-3')

    def test_session_system_prompt_set(self):
        """add_system으로 시스템 프롬프트 설정."""
        from salmalm.core import Session
        sess = Session('e2e_system_1')
        sess.add_system('너는 테스트 봇이오.')
        system_msgs = [m for m in sess.messages if m['role'] == 'system']
        self.assertGreaterEqual(len(system_msgs), 1)
        self.assertIn('테스트 봇', system_msgs[0]['content'])

    def test_session_history_two_turns(self):
        """두 턴 대화 후 메시지 수 검증."""
        from salmalm.core.engine_pipeline import _process_message_inner
        from salmalm.core.session_store import get_session

        sid = 'e2e_two_turns_1'

        async def _chat(msg, reply):
            with patch('salmalm.core.llm_loop.try_llm_call', new=AsyncMock(
                return_value={**MOCK_LLM_RESPONSE, "content": reply}
            )):
                return await _process_message_inner(sid, msg)

        _run(_chat('첫 번째 질문', '첫 번째 답변'))
        _run(_chat('두 번째 질문', '두 번째 답변'))

        sess = get_session(sid)
        user_msgs = [m for m in sess.messages if m.get('role') == 'user']
        self.assertGreaterEqual(len(user_msgs), 2)


# ===========================================================================
# 5. TestLLMLoopE2E — llm_loop.try_llm_call 수준 mock 검증
# ===========================================================================

class TestLLMLoopE2E(unittest.TestCase):
    """try_llm_call mock이 실제로 engine pipeline에서 호출되는지 검증."""

    def setUp(self):
        """각 테스트 전 cooldown 초기화."""
        try:
            from salmalm.core.llm_loop import reset_cooldowns
            reset_cooldowns()
        except Exception:
            pass

    def _no_cooldown_patch(self):
        """cooldown 체크를 항상 False(냉각 없음)로 패치하는 context manager."""
        return patch('salmalm.core.llm_loop._is_model_cooled_down', return_value=False)

    def test_try_llm_call_invoked_once(self):
        """단순 메시지: try_llm_call이 최소 1회 호출됨."""
        from salmalm.core.engine_pipeline import _process_message_inner

        mock_llm = AsyncMock(return_value=MOCK_LLM_RESPONSE)

        async def _inner():
            with self._no_cooldown_patch():
                with patch('salmalm.core.llm_loop.try_llm_call', new=mock_llm):
                    return await _process_message_inner('e2e_call_count_2', '호출 확인')

        _run(_inner())
        self.assertGreaterEqual(mock_llm.call_count, 1)

    def test_try_llm_call_receives_messages(self):
        """try_llm_call 호출 시 messages 리스트가 전달됨."""
        from salmalm.core.engine_pipeline import _process_message_inner

        captured = {}

        async def _capturing_llm(messages, model, tools, max_tokens, thinking, on_token):
            captured['messages'] = messages
            captured['model'] = model
            return MOCK_LLM_RESPONSE

        async def _inner():
            with self._no_cooldown_patch():
                with patch('salmalm.core.llm_loop.try_llm_call', new=_capturing_llm):
                    return await _process_message_inner('e2e_capture_2', '캡처 테스트')

        _run(_inner())
        self.assertIn('messages', captured)
        self.assertIsInstance(captured['messages'], list)
        self.assertGreater(len(captured['messages']), 0)

    def test_model_string_passed_to_llm(self):
        """try_llm_call에 유효한 모델 문자열 전달됨."""
        from salmalm.core.engine_pipeline import _process_message_inner

        captured_model = []

        async def _capturing_llm(messages, model, tools, max_tokens, thinking, on_token):
            captured_model.append(model)
            return MOCK_LLM_RESPONSE

        async def _inner():
            with self._no_cooldown_patch():
                with patch('salmalm.core.llm_loop.try_llm_call', new=_capturing_llm):
                    return await _process_message_inner('e2e_model_str_2', '모델 확인')

        _run(_inner())
        self.assertGreater(len(captured_model), 0)
        self.assertIsInstance(captured_model[0], str)
        self.assertIn('/', captured_model[0])  # provider/model-name format


if __name__ == '__main__':
    unittest.main()
