"""Tests for File Watcher."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from salmalm.watcher import FileWatcher, RAGFileWatcher


class TestFileWatcher(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.changes = []

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _on_change(self, path, event):
        self.changes.append((path, event))

    def test_init(self):
        fw = FileWatcher(paths=[self.tmpdir], interval=1)
        self.assertFalse(fw.running)

    def test_start_stop(self):
        fw = FileWatcher(paths=[self.tmpdir], interval=1, on_change=self._on_change)
        fw.start()
        self.assertTrue(fw.running)
        fw.stop()
        self.assertFalse(fw.running)

    def test_detect_created_file(self):
        fw = FileWatcher(paths=[self.tmpdir], interval=1,
                         extensions={'.txt'}, on_change=self._on_change)
        fw._initial_scan()

        # Create a file
        fpath = os.path.join(self.tmpdir, 'new.txt')
        with open(fpath, 'w') as f:
            f.write('hello')

        fw._scan()
        fw._flush_changes()
        created = [c for c in self.changes if c[1] == 'created']
        self.assertTrue(len(created) >= 1)

    def test_detect_modified_file(self):
        fpath = os.path.join(self.tmpdir, 'mod.txt')
        with open(fpath, 'w') as f:
            f.write('v1')

        fw = FileWatcher(paths=[self.tmpdir], interval=1,
                         extensions={'.txt'}, on_change=self._on_change)
        fw._initial_scan()

        time.sleep(0.1)
        with open(fpath, 'w') as f:
            f.write('v2')
        # Force different mtime
        os.utime(fpath, (time.time() + 1, time.time() + 1))

        fw._scan()
        fw._flush_changes()
        modified = [c for c in self.changes if c[1] == 'modified']
        self.assertTrue(len(modified) >= 1)

    def test_detect_deleted_file(self):
        fpath = os.path.join(self.tmpdir, 'del.txt')
        with open(fpath, 'w') as f:
            f.write('bye')

        fw = FileWatcher(paths=[self.tmpdir], interval=1,
                         extensions={'.txt'}, on_change=self._on_change)
        fw._initial_scan()

        os.unlink(fpath)
        fw._scan()
        fw._flush_changes()
        deleted = [c for c in self.changes if c[1] == 'deleted']
        self.assertTrue(len(deleted) >= 1)

    def test_extension_filter(self):
        # .py file should be ignored if only .txt is watched
        fpath = os.path.join(self.tmpdir, 'ignore.py')
        fw = FileWatcher(paths=[self.tmpdir], interval=1,
                         extensions={'.txt'}, on_change=self._on_change)
        fw._initial_scan()

        with open(fpath, 'w') as f:
            f.write('python')
        fw._scan()
        fw._flush_changes()
        self.assertEqual(len(self.changes), 0)

    def test_exclude_patterns(self):
        subdir = os.path.join(self.tmpdir, '.git')
        os.makedirs(subdir)
        fpath = os.path.join(subdir, 'config.txt')
        with open(fpath, 'w') as f:
            f.write('git config')

        fw = FileWatcher(paths=[self.tmpdir], interval=1,
                         extensions={'.txt'}, exclude_patterns={'.git'},
                         on_change=self._on_change)
        fw._initial_scan()
        self.assertNotIn(fpath, fw.get_watched_files())

    def test_get_watched_files(self):
        fpath = os.path.join(self.tmpdir, 'watch.txt')
        with open(fpath, 'w') as f:
            f.write('data')
        fw = FileWatcher(paths=[self.tmpdir], extensions={'.txt'})
        fw._initial_scan()
        files = fw.get_watched_files()
        self.assertIn(fpath, files)

    def test_rag_file_watcher_init(self):
        mock_rag = type('MockRAG', (), {'index_file': lambda s, l, p: None, 'remove_file': lambda s, p: None})()
        rfw = RAGFileWatcher(rag_engine=mock_rag, paths=[self.tmpdir])
        self.assertFalse(rfw.running)


if __name__ == '__main__':
    unittest.main()
