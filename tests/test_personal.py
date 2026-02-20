"""Tests for personal assistant tools — notes, expenses, save_link, pomodoro, briefing."""

import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


def _mock_execute_tool(name, args):
    """Route to real tool handlers but with mocked externals."""
    from salmalm.tools.tool_registry import _registry
    handler = _registry.get(name)
    if handler:
        return handler(args)
    return f"mock {name}"


class TestNotes(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import salmalm.tools_personal as tp
        self._orig_db = getattr(tp, '_DB_PATH', None)
        tp._DB_PATH = Path(self.tmpdir) / 'test_personal.db'
        tp._init_db()

    def tearDown(self):
        import salmalm.tools_personal as tp
        if self._orig_db is not None:
            tp._DB_PATH = self._orig_db
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_note(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('note', {'action': 'save', 'content': 'Test note', 'tags': 'test'})
        self.assertTrue(len(result) > 0)

    def test_list_notes(self):
        from salmalm.tool_handlers import execute_tool
        execute_tool('note', {'action': 'save', 'content': 'Note 1', 'tags': 'a'})
        execute_tool('note', {'action': 'save', 'content': 'Note 2', 'tags': 'b'})
        result = execute_tool('note', {'action': 'list'})
        self.assertIn('Note 1', result)

    def test_search_notes(self):
        from salmalm.tool_handlers import execute_tool
        execute_tool('note', {'action': 'save', 'content': 'Python tutorial', 'tags': 'code'})
        result = execute_tool('note', {'action': 'search', 'query': 'Python'})
        self.assertIn('Python', result)


class TestExpenses(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import salmalm.tools_personal as tp
        self._orig_db = getattr(tp, '_DB_PATH', None)
        tp._DB_PATH = Path(self.tmpdir) / 'test_personal.db'
        tp._init_db()

    def tearDown(self):
        import salmalm.tools_personal as tp
        if self._orig_db is not None:
            tp._DB_PATH = self._orig_db
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_add_expense(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('expense', {'action': 'add', 'amount': 15.50, 'category': '식비', 'description': '점심'})
        self.assertTrue(len(result) > 0)

    def test_expense_summary(self):
        from salmalm.tool_handlers import execute_tool
        execute_tool('expense', {'action': 'add', 'amount': 10, 'category': '식비'})
        execute_tool('expense', {'action': 'add', 'amount': 20, 'category': '교통'})
        result = execute_tool('expense', {'action': 'month'})
        self.assertTrue(len(result) > 0)


class TestSaveLink(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import salmalm.tools_personal as tp
        self._orig_db = getattr(tp, '_DB_PATH', None)
        tp._DB_PATH = Path(self.tmpdir) / 'test_personal.db'
        tp._init_db()

    def tearDown(self):
        import salmalm.tools_personal as tp
        if self._orig_db is not None:
            tp._DB_PATH = self._orig_db
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_link(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('save_link', {'action': 'save', 'url': 'https://example.com', 'title': 'Example'})
        self.assertTrue(len(result) > 0)

    def test_list_links(self):
        from salmalm.tool_handlers import execute_tool
        execute_tool('save_link', {'action': 'save', 'url': 'https://a.com', 'title': 'A'})
        result = execute_tool('save_link', {'action': 'list'})
        self.assertTrue(len(result) > 0)


class TestPomodoro(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import salmalm.tools_personal as tp
        self._orig_db = getattr(tp, '_DB_PATH', None)
        tp._DB_PATH = Path(self.tmpdir) / 'test_personal.db'
        tp._init_db()

    def tearDown(self):
        import salmalm.tools_personal as tp
        if self._orig_db is not None:
            tp._DB_PATH = self._orig_db
        # Cancel any running pomodoro timer
        import salmalm.tools.tools_personal as tp2
        state = getattr(tp2, '_pomodoro_state', {})
        t = state.get('timer_thread')
        if t and t.is_alive():
            state['cancelled'] = True
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('salmalm.tools.tools_personal.threading.Thread')
    def test_start_pomodoro(self, mock_thread):
        mock_thread.return_value = MagicMock()
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('pomodoro', {'action': 'start', 'task': 'Coding', 'minutes': 25})
        self.assertTrue(len(result) > 0)

    def test_pomodoro_status(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('pomodoro', {'action': 'status'})
        self.assertTrue(len(result) > 0)


class TestBriefing(unittest.TestCase):
    @patch('salmalm.tool_registry.execute_tool', side_effect=lambda name, args: f"mock {name}")
    def test_briefing_returns_string(self, mock_et):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('briefing', {'action': 'generate'})
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)


if __name__ == '__main__':
    unittest.main()
