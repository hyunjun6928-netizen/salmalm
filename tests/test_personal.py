"""Tests for personal assistant tools — notes, expenses, save_link, pomodoro, briefing."""

import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestNotes(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import salmalm.tools_personal as tp
        self._orig_db = tp._DB_PATH
        tp._DB_PATH = Path(self.tmpdir) / 'test_personal.db'
        tp._init_db()

    def tearDown(self):
        import salmalm.tools_personal as tp
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
        self._orig_db = tp._DB_PATH
        tp._DB_PATH = Path(self.tmpdir) / 'test_personal.db'
        tp._init_db()

    def tearDown(self):
        import salmalm.tools_personal as tp
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
        self._orig_db = tp._DB_PATH
        tp._DB_PATH = Path(self.tmpdir) / 'test_personal.db'
        tp._init_db()

    def tearDown(self):
        import salmalm.tools_personal as tp
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
        self._orig_db = tp._DB_PATH
        tp._DB_PATH = Path(self.tmpdir) / 'test_personal.db'
        tp._init_db()

    def tearDown(self):
        import salmalm.tools_personal as tp
        tp._DB_PATH = self._orig_db
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_start_pomodoro(self):
        from salmalm.tool_handlers import execute_tool
        result = execute_tool('pomodoro', {'action': 'start', 'task': 'Coding', 'minutes': 25})
        self.assertTrue(len(result) > 0)

    def test_pomodoro_status(self):
        from salmalm.tool_handlers import execute_tool
        execute_tool('pomodoro', {'action': 'start', 'task': 'Work'})
        result = execute_tool('pomodoro', {'action': 'status'})
        self.assertTrue(len(result) > 0)


class TestBriefing(unittest.TestCase):
    def test_briefing_returns_string(self):
        from unittest.mock import patch
        from salmalm.tool_handlers import execute_tool
        # Mock inner execute_tool calls (weather, calendar, email) to avoid network/blocking
        with patch('salmalm.tool_registry.execute_tool', side_effect=lambda name, args: f"mock {name}"):
            result = execute_tool('briefing', {'action': 'generate'})
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)


if __name__ == '__main__':
    unittest.main()
