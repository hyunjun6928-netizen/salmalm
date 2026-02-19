"""Tests for v0.12 new tools: reminder, workflow, file_index, notification, tts, calendar, gmail."""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Ensure salmalm is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestReminderTool(unittest.TestCase):
    """Test reminder tool handler."""

    def setUp(self):
        from salmalm.tool_handlers import _reminders, _reminder_lock
        with _reminder_lock:
            _reminders.clear()

    def test_set_reminder_relative(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('reminder', {'action': 'set', 'message': 'Test reminder', 'time': '30m'})
        self.assertIn('Reminder set', result)
        self.assertIn('Test reminder', result)

    def test_set_reminder_iso(self):
        from salmalm.tool_handlers import execute_tool
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        result = execute_tool('reminder', {'action': 'set', 'message': 'ISO test', 'time': future})
        self.assertIn('Reminder set', result)

    def test_list_reminders(self):
        from salmalm.tool_handlers import execute_tool
        execute_tool('reminder', {'action': 'set', 'message': 'List test', 'time': '1h'})
        result = execute_tool('reminder', {'action': 'list'})
        self.assertIn('List test', result)

    def test_delete_reminder(self):
        from salmalm.tool_handlers import execute_tool, _reminders
        execute_tool('reminder', {'action': 'set', 'message': 'Delete me', 'time': '1h'})
        rid = _reminders[0]['id'] if _reminders else 'nonexistent'
        result = execute_tool('reminder', {'action': 'delete', 'reminder_id': rid})
        self.assertIn('deleted', result)

    def test_delete_nonexistent(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('reminder', {'action': 'delete', 'reminder_id': 'fake123'})
        self.assertIn('not found', result)

    def test_set_missing_args(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('reminder', {'action': 'set', 'message': 'no time'})
        self.assertIn('required', result)

    def test_parse_relative_hours(self):
        from salmalm.tool_handlers import _parse_relative_time
        result = _parse_relative_time('2h')
        self.assertGreater(result, datetime.now())

    def test_parse_relative_days(self):
        from salmalm.tool_handlers import _parse_relative_time
        result = _parse_relative_time('3d')
        self.assertGreater(result, datetime.now() + timedelta(days=2))

    def test_parse_relative_weeks(self):
        from salmalm.tool_handlers import _parse_relative_time
        result = _parse_relative_time('1w')
        self.assertGreater(result, datetime.now() + timedelta(days=6))

    def test_parse_invalid_time(self):
        from salmalm.tool_handlers import _parse_relative_time
        with self.assertRaises(ValueError):
            _parse_relative_time('not a time')

    def test_repeating_reminder(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('reminder', {
            'action': 'set', 'message': 'Daily check', 'time': '1d', 'repeat': 'daily'})
        self.assertIn('repeat: daily', result)


class TestWorkflowTool(unittest.TestCase):
    """Test workflow tool handler."""

    def test_list_empty(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('workflow', {'action': 'list'})
        self.assertIn('orkflow', result)  # "Workflow" or "workflows"

    def test_save_and_list(self):
        from salmalm.tool_handlers import execute_tool, _workflows_file
        steps = [{'tool': 'hash_text', 'args': {'text': 'hello', 'algorithm': 'md5'}}]
        result = execute_tool('workflow', {'action': 'save', 'name': '_test_wf', 'steps': steps})
        self.assertIn('saved', result)
        # Cleanup
        try:
            wf = json.loads(_workflows_file.read_text())
            if '_test_wf' in wf:
                del wf['_test_wf']
                _workflows_file.write_text(json.dumps(wf))
        except Exception:
            pass

    def test_run_inline(self):
        from salmalm.tool_handlers import execute_tool
        steps = [
            {'tool': 'hash_text', 'args': {'text': 'test123', 'algorithm': 'md5'}, 'output_var': 'hash_result'},
        ]
        result = execute_tool('workflow', {'action': 'run', 'steps': steps})
        self.assertIn('Workflow Complete', result)

    def test_run_nonexistent(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('workflow', {'action': 'run', 'name': '_nonexistent_wf_xyz'})
        self.assertIn('not found', result)

    def test_save_missing_args(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('workflow', {'action': 'save', 'name': ''})
        self.assertIn('required', result)

    def test_delete_nonexistent(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('workflow', {'action': 'delete', 'name': '_nonexistent_xyz'})
        self.assertIn('not found', result)


class TestFileIndexTool(unittest.TestCase):
    """Test file_index tool handler."""

    def test_index_workspace(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('file_index', {'action': 'index'})
        self.assertIn('Indexed', result)

    def test_status(self):
        from salmalm.tool_handlers import execute_tool
        execute_tool('file_index', {'action': 'index'})
        result = execute_tool('file_index', {'action': 'status'})
        self.assertIn('File index', result)

    def test_search(self):
        from salmalm.tool_handlers import execute_tool
        execute_tool('file_index', {'action': 'index'})
        result = execute_tool('file_index', {'action': 'search', 'query': 'import json'})
        # Should find at least some Python files
        self.assertTrue('File Search' in result or 'No files' in result)

    def test_search_empty_query(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('file_index', {'action': 'search', 'query': ''})
        self.assertIn('required', result)

    def test_index_nonexistent_dir(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('file_index', {'action': 'index', 'path': '/nonexistent_xyz_dir'})
        self.assertIn('not found', result)


class TestNotificationTool(unittest.TestCase):
    """Test notification tool handler."""

    def test_missing_message(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('notification', {'message': ''})
        self.assertIn('required', result)

    @patch('salmalm.tool_handlers._send_notification_impl')
    def test_send_notification(self, mock_send):
        mock_send.return_value = ['desktop: ✅']
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('notification', {'message': 'Test notification', 'channel': 'desktop'})
        self.assertIn('Notification sent', result)


class TestTTSGenerateTool(unittest.TestCase):
    """Test tts_generate tool handler."""

    def test_missing_text(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('tts_generate', {'text': ''})
        self.assertIn('required', result)

    def test_unknown_provider(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('tts_generate', {'text': 'hello', 'provider': 'fakeprovider'})
        self.assertIn('Unknown TTS provider', result)

    def test_openai_tts(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('tts_generate', {'text': 'hello', 'provider': 'openai'})
        # Either no key configured, or 401/error from API
        self.assertTrue('not configured' in result or 'error' in result.lower() or 'TTS' in result)


class TestGoogleCalendarTool(unittest.TestCase):
    """Test google_calendar tool handler (without real credentials)."""

    def test_no_credentials(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('google_calendar', {'action': 'list'})
        self.assertTrue('credentials' in result.lower() or 'error' in result.lower())

    def test_create_missing_args(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('google_calendar', {'action': 'create'})
        self.assertTrue('required' in result or 'credentials' in result.lower() or 'error' in result.lower())

    def test_delete_missing_id(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('google_calendar', {'action': 'delete'})
        self.assertTrue('required' in result or 'credentials' in result.lower() or 'error' in result.lower())


class TestGmailTool(unittest.TestCase):
    """Test gmail tool handler (without real credentials)."""

    def test_no_credentials(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('gmail', {'action': 'list'})
        self.assertTrue('credentials' in result.lower() or 'error' in result.lower())

    def test_read_missing_id(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('gmail', {'action': 'read'})
        self.assertTrue('required' in result or 'credentials' in result.lower() or 'error' in result.lower())

    def test_send_missing_args(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('gmail', {'action': 'send'})
        self.assertTrue('required' in result or 'credentials' in result.lower() or 'error' in result.lower())


class TestToolCount(unittest.TestCase):
    """Verify tool count is updated."""

    def test_tool_count_39(self):
        from salmalm.tools import TOOL_DEFINITIONS
        self.assertEqual(len(TOOL_DEFINITIONS), 39)

    def test_all_tools_have_names(self):
        from salmalm.tools import TOOL_DEFINITIONS
        for t in TOOL_DEFINITIONS:
            self.assertIn('name', t)
            self.assertTrue(len(t['name']) > 0)

    def test_new_tools_present(self):
        from salmalm.tools import TOOL_DEFINITIONS
        names = {t['name'] for t in TOOL_DEFINITIONS}
        expected = {'google_calendar', 'gmail', 'reminder', 'tts_generate',
                    'workflow', 'file_index', 'notification'}
        self.assertTrue(expected.issubset(names), f'Missing: {expected - names}')


if __name__ == '__main__':
    unittest.main()
