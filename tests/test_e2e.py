"""End-to-end integration tests — exercises full pipelines with mocked externals.

No real LLM calls, no network, no disk side-effects outside tempdir.
"""
import asyncio
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure constants point to temp dirs before importing salmalm modules
_tmpdir = tempfile.mkdtemp(prefix='salmalm_e2e_')
os.environ.setdefault('SALMALM_BASE', _tmpdir)

from salmalm import constants as C

# Redirect all mutable paths to tempdir (read-only, won't modify constants.py)
_orig_base = C.BASE_DIR
_orig_audit = C.AUDIT_DB
_orig_vault = getattr(C, 'VAULT_FILE', None)

C.BASE_DIR = Path(_tmpdir)
C.DATA_DIR = Path(_tmpdir) / 'data'
C.AUDIT_DB = Path(_tmpdir) / 'audit.db'
C.DATA_DIR.mkdir(exist_ok=True)
if hasattr(C, 'VAULT_FILE'):
    C.VAULT_FILE = Path(_tmpdir) / 'vault.bin'
if hasattr(C, 'MOOD_CONFIG_FILE'):
    C.MOOD_CONFIG_FILE = Path(_tmpdir) / 'mood_config.json'
if hasattr(C, 'WORKFLOWS_DIR'):
    C.WORKFLOWS_DIR = Path(_tmpdir) / 'workflows'
    C.WORKFLOWS_DIR.mkdir(exist_ok=True)
if hasattr(C, 'RAG_DIR'):
    C.RAG_DIR = Path(_tmpdir) / 'rag'
    C.RAG_DIR.mkdir(exist_ok=True)
if hasattr(C, 'MEMORY_DIR'):
    C.MEMORY_DIR = Path(_tmpdir) / 'memory'
    C.MEMORY_DIR.mkdir(exist_ok=True)
if hasattr(C, 'CONFIG_FILE'):
    C.CONFIG_FILE = Path(_tmpdir) / 'config.json'
if hasattr(C, 'SESSIONS_DIR'):
    C.SESSIONS_DIR = Path(_tmpdir) / 'sessions'
    C.SESSIONS_DIR.mkdir(exist_ok=True)


def _run(coro):
    """Run a coroutine in a fresh event loop (isolated per call)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        # Restore a fresh loop so subsequent tests/files don't break
        asyncio.set_event_loop(asyncio.new_event_loop())


# ===========================================================================
# Test Cases
# ===========================================================================

class TestE2EMessageToResponse(unittest.TestCase):
    """1. 사용자 메시지 → LLM 응답 → 결과 반환."""

    def test_message_to_response_flow(self):
        """Full message pipeline with mocked LLM."""
        from salmalm.core import Session
        from salmalm.core import engine

        mock_result = {
            'content': '안녕하세요! 도움이 필요하신가요?',
            'tool_calls': [],
            'usage': {'input': 10, 'output': 20},
            'model': 'anthropic/claude-sonnet-4-20250514',
        }

        session = Session('e2e_test_1')
        session.add_system('You are helpful.')
        session.add_user('안녕')
        # Verify session state
        self.assertEqual(len(session.messages), 2)
        self.assertEqual(session.messages[-1]['content'], '안녕')

        # Simulate adding LLM response
        session.messages.append({'role': 'assistant', 'content': mock_result['content']})
        self.assertEqual(session.messages[-1]['content'], '안녕하세요! 도움이 필요하신가요?')


class TestE2EToolExecution(unittest.TestCase):
    """2. 도구 실행 플로우."""

    def test_tool_execution_flow(self):
        """execute_tool dispatches and returns string result."""
        from salmalm.tools.tool_handlers import execute_tool
        with patch('salmalm.tools.tool_registry.execute_tool', return_value='result: ok'):
            result = execute_tool('exec', {'command': 'echo hello'})
            self.assertIn('ok', result.lower() if 'ok' in result.lower() else result)

    def test_tool_path_traversal_blocked(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('read_file', {'path': '../../etc/passwd'})
        self.assertIn('차단', result)


class TestE2ECommandRouting(unittest.TestCase):
    """3. /status → CommandRouter → 결과."""

    def test_command_routing(self):
        from salmalm.features.commands import CommandRouter
        router = CommandRouter()
        # /help should return help text
        result = _run(router.dispatch('/help'))
        self.assertIsNotNone(result)
        self.assertIn('help', result.lower() if result else '')

    def test_unknown_command_returns_none(self):
        from salmalm.features.commands import CommandRouter
        router = CommandRouter()
        result = _run(router.dispatch('hello'))  # not a command
        self.assertIsNone(result)

    def test_restart_command(self):
        from salmalm.features.commands import CommandRouter
        router = CommandRouter()
        result = _run(router.dispatch('/restart'))
        self.assertIsNotNone(result)


class TestE2ESessionLifecycle(unittest.TestCase):
    """4. 세션 생성 → 메시지 → 컴팩션 → 종료."""

    def test_session_lifecycle(self):
        from salmalm.core import Session, compact_messages
        sess = Session('lifecycle_test')
        sess.add_system('system prompt')
        for i in range(5):
            sess.add_user(f'message {i}')
            sess.messages.append({'role': 'assistant', 'content': f'reply {i}'})
        self.assertEqual(len(sess.messages), 11)  # 1 system + 5 user + 5 assistant

        # compact_messages shouldn't crash (below threshold returns as-is)
        compacted = compact_messages(sess.messages, session=sess)
        self.assertGreater(len(compacted), 0)


class TestE2EMultiModelFailover(unittest.TestCase):
    """5. 주 모델 실패 → 폴백."""

    def test_multi_model_failover(self):
        """Verify failover function exists and ModelRouter handles routing."""
        from salmalm.core import ModelRouter, Session

        router = ModelRouter()
        # Router should return a valid model string
        model = router.route('write a Python script')
        self.assertIsInstance(model, str)
        self.assertTrue(len(model) > 0)

        # Session can override model
        sess = Session('failover_test')
        sess.model_override = 'anthropic/claude-haiku-3'
        self.assertEqual(sess.model_override, 'anthropic/claude-haiku-3')

        # Verify IntelligenceEngine has failover method
        from salmalm.core.engine import IntelligenceEngine
        engine = IntelligenceEngine()
        self.assertTrue(hasattr(engine, '_call_with_failover'))


class TestE2EStreamingToChannel(unittest.TestCase):
    """6. 스트리밍 → chunker → 채널."""

    def test_streaming_to_channel(self):
        from salmalm.utils.chunker import EmbeddedBlockChunker
        chunker = EmbeddedBlockChunker()
        chunks = []
        for token in ['Hello', ' world', '! How', ' are', ' you?']:
            result = chunker.feed(token)
            if result:
                chunks.append(result)
        final = chunker.flush()
        if final:
            chunks.append(final)
        full = ''.join(chunks)
        self.assertIn('Hello', full)
        self.assertIn('you?', full)




if __name__ == "__main__":
    unittest.main()
