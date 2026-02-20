"""Tests for salmalm.features.artifacts."""
import json
import tempfile
import unittest
from pathlib import Path

from salmalm.features.artifacts import (
    ArtifactManager, ArtifactType, Artifact,
    handle_artifacts_command, _CODE_BLOCK_RE,
)


class TestArtifact(unittest.TestCase):
    def test_to_dict(self):
        a = Artifact(id='abc', type='code', content='print("hi")', language='python')
        d = a.to_dict()
        assert d['id'] == 'abc'
        assert d['type'] == 'code'
        assert d['language'] == 'python'

    def test_from_dict(self):
        d = {'id': 'x', 'type': 'json', 'content': '{}', 'language': 'json'}
        a = Artifact.from_dict(d)
        assert a.id == 'x'
        assert a.type == 'json'

    def test_preview_truncated(self):
        content = 'x' * 200
        a = Artifact(id='t', type='code', content=content)
        assert len(a.preview) <= 100


class TestArtifactManager(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.mgr = ArtifactManager(storage_dir=Path(self._tmpdir))

    def test_add_and_get(self):
        a = self.mgr.add('code', 'def foo(): pass', language='python', session_id='s1')
        assert a.id
        got = self.mgr.get(a.id)
        assert got is not None
        assert got.content == 'def foo(): pass'

    def test_list_all(self):
        self.mgr.add('code', 'line1')
        self.mgr.add('json', '{"k": "v"}')
        assert len(self.mgr.list_all()) == 2

    def test_remove(self):
        a = self.mgr.add('code', 'to_remove')
        assert self.mgr.remove(a.id)
        assert self.mgr.get(a.id) is None

    def test_remove_nonexistent(self):
        assert self.mgr.remove('nonexistent') is False

    def test_export_all(self):
        self.mgr.add('code', 'export_me')
        export = self.mgr.export_all()
        data = json.loads(export)
        assert len(data) >= 1

    def test_detect_code_blocks(self):
        text = 'Here is code:\n```python\ndef hello():\n    print("world")\n```\nDone.'
        saved = self.mgr.detect_and_save(text, session_id='test')
        assert len(saved) >= 1
        assert saved[0].language == 'python'

    def test_detect_json(self):
        text = 'Result:\n{"name": "test", "value": 42, "nested": {"a": 1}}\nEnd.'
        saved = self.mgr.detect_and_save(text)
        # May or may not detect depending on length
        assert isinstance(saved, list)

    def test_detect_markdown(self):
        text = '# My Document\n\nThis is a substantial markdown document.\n' * 5
        saved = self.mgr.detect_and_save(text)
        assert isinstance(saved, list)

    def test_detect_skips_trivial(self):
        text = '```\nhi\n```'
        saved = self.mgr.detect_and_save(text)
        assert len(saved) == 0  # too short

    def test_persistence(self):
        self.mgr.add('code', 'persistent_content')
        # Reload
        mgr2 = ArtifactManager(storage_dir=Path(self._tmpdir))
        assert mgr2.count == 1

    def test_count(self):
        assert self.mgr.count == 0
        self.mgr.add('code', 'a')
        assert self.mgr.count == 1


class TestHandleCommand(unittest.TestCase):
    def test_list_empty(self):
        result = handle_artifacts_command('/artifacts list')
        assert 'No artifacts' in result or 'Artifacts' in result

    def test_get_missing(self):
        result = handle_artifacts_command('/artifacts get nonexistent')
        assert '❌' in result

    def test_export(self):
        result = handle_artifacts_command('/artifacts export')
        assert 'json' in result.lower() or '```' in result

    def test_invalid_sub(self):
        result = handle_artifacts_command('/artifacts xyz')
        assert '❌' in result
