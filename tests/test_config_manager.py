"""Tests for ConfigManager centralized configuration."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestConfigManager(unittest.TestCase):
    """Test ConfigManager CRUD operations."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Patch BASE_DIR to use temp directory
        from salmalm.config_manager import ConfigManager
        self._orig_base = ConfigManager.BASE_DIR
        ConfigManager.BASE_DIR = Path(self.tmpdir)

    def tearDown(self):
        from salmalm.config_manager import ConfigManager
        ConfigManager.BASE_DIR = self._orig_base
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_missing_no_defaults(self):
        from salmalm.config_manager import ConfigManager
        result = ConfigManager.load('nonexistent')
        self.assertEqual(result, {})

    def test_load_missing_with_defaults(self):
        from salmalm.config_manager import ConfigManager
        result = ConfigManager.load('missing', defaults={'key': 'val'})
        self.assertEqual(result, {'key': 'val'})

    def test_save_and_load(self):
        from salmalm.config_manager import ConfigManager
        ConfigManager.save('test', {'hello': 'world', 'num': 42})
        result = ConfigManager.load('test')
        self.assertEqual(result, {'hello': 'world', 'num': 42})

    def test_load_merges_defaults(self):
        from salmalm.config_manager import ConfigManager
        ConfigManager.save('merge', {'a': 1})
        result = ConfigManager.load('merge', defaults={'a': 0, 'b': 2})
        self.assertEqual(result['a'], 1)  # saved value wins
        self.assertEqual(result['b'], 2)  # default fills missing

    def test_get_key(self):
        from salmalm.config_manager import ConfigManager
        ConfigManager.save('gettest', {'x': 10, 'y': 20})
        self.assertEqual(ConfigManager.get('gettest', 'x'), 10)
        self.assertEqual(ConfigManager.get('gettest', 'z', 'default'), 'default')

    def test_set_key(self):
        from salmalm.config_manager import ConfigManager
        ConfigManager.save('settest', {'a': 1})
        ConfigManager.set('settest', 'b', 2)
        result = ConfigManager.load('settest')
        self.assertEqual(result, {'a': 1, 'b': 2})

    def test_exists(self):
        from salmalm.config_manager import ConfigManager
        self.assertFalse(ConfigManager.exists('nope'))
        ConfigManager.save('yep', {'ok': True})
        self.assertTrue(ConfigManager.exists('yep'))

    def test_delete(self):
        from salmalm.config_manager import ConfigManager
        ConfigManager.save('delme', {'x': 1})
        self.assertTrue(ConfigManager.delete('delme'))
        self.assertFalse(ConfigManager.exists('delme'))
        self.assertFalse(ConfigManager.delete('delme'))

    def test_list_configs(self):
        from salmalm.config_manager import ConfigManager
        ConfigManager.save('alpha', {})
        ConfigManager.save('beta', {})
        names = ConfigManager.list_configs()
        self.assertIn('alpha', names)
        self.assertIn('beta', names)

    def test_unicode_content(self):
        from salmalm.config_manager import ConfigManager
        ConfigManager.save('unicode', {'이름': '살말름', 'emoji': '🎉'})
        result = ConfigManager.load('unicode')
        self.assertEqual(result['이름'], '살말름')

    def test_corrupt_json_returns_defaults(self):
        from salmalm.config_manager import ConfigManager
        path = Path(self.tmpdir) / 'corrupt.json'
        path.write_text('not valid json{{{', encoding='utf-8')
        result = ConfigManager.load('corrupt', defaults={'safe': True})
        self.assertEqual(result, {'safe': True})

    def test_set_creates_new_file(self):
        from salmalm.config_manager import ConfigManager
        ConfigManager.set('newfile', 'key', 'value')
        self.assertEqual(ConfigManager.get('newfile', 'key'), 'value')

    def test_list_empty_dir(self):
        from salmalm.config_manager import ConfigManager
        import shutil
        shutil.rmtree(self.tmpdir)
        result = ConfigManager.list_configs()
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
