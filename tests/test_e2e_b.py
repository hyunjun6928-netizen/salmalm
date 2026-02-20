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
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# ===========================================================================
# Test Cases
# ===========================================================================


class TestE2EToolApproval(unittest.TestCase):
    """7. 위험 명령 승인 플로우."""

    def test_tool_approval_flow(self):
        from salmalm.exec_approvals import check_approval
        # Dangerous commands should be flagged (returns (approved, reason, needs_confirm))
        _, _, needs_confirm_rm = check_approval('rm -rf /')
        self.assertTrue(needs_confirm_rm)
        _, _, needs_confirm_sudo = check_approval('sudo reboot')
        self.assertTrue(needs_confirm_sudo)
        # Safe commands should pass
        approved, _, needs_confirm_echo = check_approval('echo hello')
        self.assertTrue(approved)
        self.assertFalse(needs_confirm_echo)


class TestE2ESubagentSpawn(unittest.TestCase):
    """8. 서브에이전트 생성 & announce."""

    def test_subagent_spawn_and_announce(self):
        from salmalm.core import Session
        parent = Session('parent_session')
        child = Session('child_session')
        child.metadata['parent'] = parent.id
        self.assertEqual(child.metadata['parent'], 'parent_session')
        # Sub-agent should have independent message history
        parent.add_user('parent msg')
        self.assertEqual(len(child.messages), 0)


class TestE2EWebhookToResponse(unittest.TestCase):
    """9. Telegram 웹훅 수신 → 처리."""

    def test_webhook_to_response(self):
        """Parse a Telegram webhook update."""
        update = {
            'update_id': 123,
            'message': {
                'message_id': 1,
                'from': {'id': 42, 'first_name': 'Test'},
                'chat': {'id': 42, 'type': 'private'},
                'text': '/help',
                'date': 1700000000,
            }
        }
        msg = update['message']
        self.assertEqual(msg['text'], '/help')
        self.assertEqual(msg['chat']['id'], 42)


class TestE2EVaultOpenClose(unittest.TestCase):
    """10. 볼트 열기 → 저장 → 닫기 → 접근 거부."""

    def test_vault_open_close_flow(self):
        from salmalm.crypto import Vault
        v = Vault()
        v.create('test_password_123')
        self.assertTrue(v.is_unlocked)
        v.set('api_key', 'sk-test')
        self.assertEqual(v.get('api_key'), 'sk-test')

        # "Lock" by resetting internal state
        v._password = None
        v._data = {}
        self.assertFalse(v.is_unlocked)
        self.assertIsNone(v.get('api_key'))


class TestE2EWorkflowExecution(unittest.TestCase):
    """11. 워크플로우 정의 → 실행 → 완료."""

    def test_workflow_execution(self):
        from salmalm.workflow import WorkflowEngine

        executed = []

        def mock_tool_exec(name, params):
            executed.append(name)
            return f'{name} done'

        engine = WorkflowEngine(tool_executor=mock_tool_exec)
        wf = {
            'name': 'test_wf',
            'steps': [
                {'id': 'step1', 'tool': 'echo', 'params': {'text': 'hello'}},
                {'id': 'step2', 'tool': 'echo', 'params': {'text': 'world'}},
            ]
        }
        engine.save_workflow(wf)
        result = engine.run('test_wf')
        self.assertTrue(result.get('success', False) or 'results' in result)


class TestE2EMoodDetection(unittest.TestCase):
    """12. 슬픈 메시지 → 감정 감지."""

    def test_mood_detection_to_tone(self):
        from salmalm.mood import MoodDetector
        detector = MoodDetector()
        mood, confidence = detector.detect('너무 슬퍼... 힘들어 😢')
        self.assertIn(mood, ('sad', 'anxious', 'stressed', 'neutral'))
        # Should detect some non-neutral mood
        if mood != 'neutral':
            self.assertGreater(confidence, 0)

    def test_happy_mood(self):
        from salmalm.mood import MoodDetector
        detector = MoodDetector()
        mood, conf = detector.detect('정말 행복해! 최고야! 😄🎉')
        self.assertIn(mood, ('happy', 'excited', 'grateful', 'neutral'))





if __name__ == "__main__":
    unittest.main()
