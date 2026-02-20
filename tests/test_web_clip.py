"""Tests for salmalm.features.web_clip."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from salmalm.features.web_clip import (
    ClipManager, WebClip, extract_readable, _TagStripper,
    handle_clip_command, fetch_url,
)


class TestExtractReadable(unittest.TestCase):
    def test_basic_html(self):
        html = '<html><head><title>Test Page</title></head><body><p>Hello world</p></body></html>'
        result = extract_readable(html)
        assert result['title'] == 'Test Page'
        assert 'Hello world' in result['text']

    def test_strips_scripts(self):
        html = '<p>Before</p><script>alert("bad")</script><p>After</p>'
        result = extract_readable(html)
        assert 'alert' not in result['text']
        assert 'Before' in result['text']
        assert 'After' in result['text']

    def test_strips_style(self):
        html = '<style>body{color:red}</style><p>Content</p>'
        result = extract_readable(html)
        assert 'color' not in result['text']
        assert 'Content' in result['text']

    def test_strips_nav(self):
        html = '<nav>Menu items</nav><article>Real content</article>'
        result = extract_readable(html)
        assert 'Menu' not in result['text']
        assert 'Real content' in result['text']

    def test_block_tags_newlines(self):
        html = '<p>Para 1</p><p>Para 2</p>'
        result = extract_readable(html)
        assert 'Para 1' in result['text']
        assert 'Para 2' in result['text']

    def test_empty_html(self):
        result = extract_readable('')
        assert result['title'] == ''
        assert result['text'] == ''

    def test_malformed_html(self):
        html = '<p>Unclosed <b>tags <i>everywhere'
        result = extract_readable(html)
        assert 'Unclosed' in result['text']


class TestWebClip(unittest.TestCase):
    def test_to_dict(self):
        c = WebClip(id='abc', url='https://example.com', title='Test', content='Hello')
        d = c.to_dict()
        assert d['id'] == 'abc'
        assert d['url'] == 'https://example.com'
        assert d['word_count'] == 1

    def test_from_dict(self):
        d = {'id': 'x', 'url': 'http://test.com', 'title': 'T', 'content': 'C'}
        c = WebClip.from_dict(d)
        assert c.id == 'x'
        assert c.title == 'T'

    def test_word_count(self):
        c = WebClip(id='wc', url='u', title='t', content='one two three four')
        assert c.word_count == 4


class TestClipManager(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.mgr = ClipManager(storage_dir=Path(self._tmpdir))

    def test_add_and_get(self):
        c = self.mgr.add_clip('http://test.com', 'Test', 'Content here')
        assert c.id
        got = self.mgr.get(c.id)
        assert got is not None
        assert got.title == 'Test'

    def test_list_all(self):
        self.mgr.add_clip('http://a.com', 'A', 'Content A')
        self.mgr.add_clip('http://b.com', 'B', 'Content B')
        assert len(self.mgr.list_all()) == 2

    def test_remove(self):
        c = self.mgr.add_clip('http://rm.com', 'RM', 'Remove me')
        assert self.mgr.remove(c.id)
        assert self.mgr.get(c.id) is None

    def test_remove_nonexistent(self):
        assert self.mgr.remove('nope') is False

    def test_search(self):
        self.mgr.add_clip('http://py.com', 'Python Tutorial', 'Learn python programming')
        self.mgr.add_clip('http://js.com', 'JavaScript', 'Learn javascript')
        results = self.mgr.search('python')
        assert len(results) >= 1
        assert results[0].title == 'Python Tutorial'

    def test_search_no_results(self):
        results = self.mgr.search('nonexistent-xyz')
        assert len(results) == 0

    def test_count(self):
        assert self.mgr.count == 0
        self.mgr.add_clip('http://c.com', 'C', 'content')
        assert self.mgr.count == 1

    def test_persistence(self):
        self.mgr.add_clip('http://p.com', 'Persist', 'data')
        mgr2 = ClipManager(storage_dir=Path(self._tmpdir))
        assert mgr2.count == 1

    def test_clip_url_mocked(self):
        html = '<html><head><title>Mocked</title></head><body><p>Body text</p></body></html>'
        with patch('salmalm.features.web_clip.fetch_url', return_value=html):
            c = self.mgr.clip_url('http://example.com')
            assert c.title == 'Mocked'
            assert 'Body text' in c.content


class TestHandleCommand(unittest.TestCase):
    def test_list_empty(self):
        result = handle_clip_command('/clip list')
        assert 'No clips' in result or 'Clips' in result

    def test_search_no_query(self):
        result = handle_clip_command('/clip search')
        assert '❌' in result

    def test_get_missing(self):
        result = handle_clip_command('/clip get nonexistent')
        assert '❌' in result

    def test_no_args(self):
        result = handle_clip_command('/clip')
        assert '❌' in result

    def test_clip_url_fail(self):
        with patch('salmalm.features.web_clip.fetch_url', side_effect=Exception('Network error')):
            result = handle_clip_command('/clip http://fail.example.com')
            assert '❌' in result
