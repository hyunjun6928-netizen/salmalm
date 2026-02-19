"""Tests for graceful shutdown, health endpoint, plugin hot-reload, and conversation export."""
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestHealthEndpoint(unittest.TestCase):
    """Test health report generation."""

    def test_get_health_report_returns_dict(self):
        from salmalm.core.health import get_health_report
        report = get_health_report()
        self.assertIsInstance(report, dict)
        self.assertIn('status', report)
        self.assertIn('version', report)
        self.assertIn('uptime_seconds', report)
        self.assertIn('uptime_human', report)
        self.assertIn('memory_mb', report)
        self.assertIn('active_sessions', report)
        self.assertIn('disk', report)
        self.assertIn('threads', report)

    def test_health_status_values(self):
        from salmalm.core.health import get_health_report
        report = get_health_report()
        self.assertIn(report['status'], ('healthy', 'degraded', 'unhealthy'))

    def test_uptime_is_positive(self):
        from salmalm.core.health import get_health_report
        report = get_health_report()
        self.assertGreaterEqual(report['uptime_seconds'], 0)

    def test_memory_mb_is_number(self):
        from salmalm.core.health import get_health_report
        report = get_health_report()
        self.assertIsInstance(report['memory_mb'], (int, float))

    def test_disk_info(self):
        from salmalm.core.health import get_health_report
        report = get_health_report()
        disk = report.get('disk', {})
        # On Linux, should have free_mb and total_mb
        if disk:
            self.assertIn('free_mb', disk)
            self.assertIn('total_mb', disk)

    def test_llm_status_structure(self):
        from salmalm.core.health import get_health_report
        report = get_health_report()
        llm = report.get('llm', {})
        self.assertIn('connected', llm)

    def test_format_uptime(self):
        from salmalm.core.health import _format_uptime
        result = _format_uptime()
        self.assertIsInstance(result, str)
        # Should contain 'h' and 'm'
        self.assertTrue('h' in result or 'd' in result or 'm' in result)


class TestConversationExport(unittest.TestCase):
    """Test conversation export to md/json/html."""

    def _make_session(self):
        """Create a mock session for testing."""
        session = MagicMock()
        session.id = 'test-session-123'
        session.messages = [
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': 'Hello, how are you?'},
            {'role': 'assistant', 'content': 'I am doing well, thank you!'},
            {'role': 'user', 'content': 'Tell me about Python.'},
            {'role': 'assistant', 'content': 'Python is a great programming language.'},
        ]
        return session

    def test_export_markdown(self):
        from salmalm.core.export import export_session
        session = self._make_session()
        result = export_session(session, fmt='md')
        self.assertTrue(result['ok'])
        self.assertTrue(result['filename'].endswith('.md'))
        self.assertGreater(result['size'], 0)
        # Check file content
        content = Path(result['path']).read_text(encoding='utf-8')
        self.assertIn('# SalmAlm Conversation Export', content)
        self.assertIn('Hello, how are you?', content)
        self.assertIn('Python is a great programming language.', content)
        # System message should be excluded
        self.assertNotIn('You are a helpful assistant.', content)
        # Cleanup
        os.unlink(result['path'])

    def test_export_json(self):
        from salmalm.core.export import export_session
        session = self._make_session()
        result = export_session(session, fmt='json')
        self.assertTrue(result['ok'])
        self.assertTrue(result['filename'].endswith('.json'))
        content = Path(result['path']).read_text(encoding='utf-8')
        data = json.loads(content)
        self.assertEqual(data['session_id'], 'test-session-123')
        self.assertGreater(data['message_count'], 0)
        # System messages excluded
        roles = [m['role'] for m in data['messages']]
        self.assertNotIn('system', roles)
        os.unlink(result['path'])

    def test_export_html(self):
        from salmalm.core.export import export_session
        session = self._make_session()
        result = export_session(session, fmt='html')
        self.assertTrue(result['ok'])
        self.assertTrue(result['filename'].endswith('.html'))
        content = Path(result['path']).read_text(encoding='utf-8')
        self.assertIn('<!DOCTYPE html>', content)
        self.assertIn('Hello, how are you?', content)
        os.unlink(result['path'])

    def test_export_invalid_format(self):
        from salmalm.core.export import export_session
        session = self._make_session()
        result = export_session(session, fmt='pdf')
        self.assertFalse(result['ok'])
        self.assertIn('Unsupported format', result['error'])

    def test_export_multimodal_content(self):
        """Test export handles list-type content blocks."""
        from salmalm.core.export import export_session
        session = self._make_session()
        session.messages.append({
            'role': 'user',
            'content': [
                {'type': 'text', 'text': 'Analyze this image'},
                {'type': 'image', 'source': {'type': 'base64', 'data': 'abc'}},
            ]
        })
        result = export_session(session, fmt='md')
        self.assertTrue(result['ok'])
        content = Path(result['path']).read_text(encoding='utf-8')
        self.assertIn('Analyze this image', content)
        os.unlink(result['path'])

    def test_export_tool_result_content(self):
        """Test export handles tool_result blocks."""
        from salmalm.core.export import export_session
        session = self._make_session()
        session.messages.append({
            'role': 'user',
            'content': [
                {'type': 'tool_result', 'tool_use_id': 'abc', 'content': 'tool output here'},
            ]
        })
        result = export_session(session, fmt='json')
        self.assertTrue(result['ok'])
        os.unlink(result['path'])


class TestExportCommand(unittest.TestCase):
    """Test /export command handler."""

    def test_cmd_export_default_md(self):
        from salmalm.core.engine import _cmd_export
        session = MagicMock()
        session.id = 'cmd-test'
        session.messages = [
            {'role': 'user', 'content': 'test'},
            {'role': 'assistant', 'content': 'reply'},
        ]
        result = _cmd_export('/export', session)
        self.assertIn('exported', result)
        self.assertIn('MD', result)

    def test_cmd_export_json(self):
        from salmalm.core.engine import _cmd_export
        session = MagicMock()
        session.id = 'cmd-test-json'
        session.messages = [
            {'role': 'user', 'content': 'test'},
            {'role': 'assistant', 'content': 'reply'},
        ]
        result = _cmd_export('/export json', session)
        self.assertIn('exported', result)
        self.assertIn('JSON', result)

    def test_cmd_export_html(self):
        from salmalm.core.engine import _cmd_export
        session = MagicMock()
        session.id = 'cmd-test-html'
        session.messages = [
            {'role': 'user', 'content': 'test'},
            {'role': 'assistant', 'content': 'reply'},
        ]
        result = _cmd_export('/export html', session)
        self.assertIn('exported', result)
        self.assertIn('HTML', result)


class TestShutdownManager(unittest.TestCase):
    """Test graceful shutdown manager."""

    def test_shutdown_manager_exists(self):
        from salmalm.core.shutdown import shutdown_manager
        self.assertFalse(shutdown_manager.is_shutting_down)

    def test_shutdown_sets_flag(self):
        from salmalm.core.shutdown import ShutdownManager
        sm = ShutdownManager()
        self.assertFalse(sm.is_shutting_down)
        # Can't easily test full async execute without mocking everything,
        # but we can verify the flag mechanism
        sm._shutting_down = True
        self.assertTrue(sm.is_shutting_down)


class TestPluginWatcher(unittest.TestCase):
    """Test plugin hot-reload watcher."""

    def test_plugin_watcher_exists(self):
        from salmalm.core.plugin_watcher import plugin_watcher
        self.assertFalse(plugin_watcher.running)

    def test_extract_plugin_name(self):
        from salmalm.core.plugin_watcher import PluginWatcher, PLUGINS_DIR
        pw = PluginWatcher()
        # Test with a path inside plugins dir
        test_path = PLUGINS_DIR / 'my_plugin' / '__init__.py'
        name = pw._extract_plugin_name(test_path)
        self.assertEqual(name, 'my_plugin')

    def test_extract_plugin_name_outside(self):
        from salmalm.core.plugin_watcher import PluginWatcher
        pw = PluginWatcher()
        name = pw._extract_plugin_name(Path('/tmp/random/file.py'))
        self.assertIsNone(name)

    def test_reload_all(self):
        from salmalm.core.plugin_watcher import PluginWatcher
        pw = PluginWatcher()
        result = pw.reload_all()
        self.assertIn('Reloaded', result)

    def test_start_stop(self):
        from salmalm.core.plugin_watcher import PluginWatcher
        pw = PluginWatcher(interval=1)
        pw.start()
        self.assertTrue(pw.running)
        time.sleep(0.1)
        pw.stop()
        self.assertFalse(pw.running)


class TestPluginsCommand(unittest.TestCase):
    """Test /plugins reload command."""

    def test_plugins_reload(self):
        from salmalm.core.engine import _cmd_plugins
        session = MagicMock()
        result = _cmd_plugins('/plugins reload', session)
        self.assertIn('Reloaded', result)

    def test_plugins_list(self):
        from salmalm.core.engine import _cmd_plugins
        session = MagicMock()
        result = _cmd_plugins('/plugins list', session)
        # Should return either plugins or "no plugins" message
        self.assertIsInstance(result, str)


if __name__ == '__main__':
    unittest.main()
