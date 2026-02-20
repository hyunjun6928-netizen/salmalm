"""Tests for Brave Search API tools."""
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _mock_urlopen(response_data, status=200):
    """Create a mock urlopen context manager."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode('utf-8')
    mock_resp.status = status
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestBraveWebSearch(unittest.TestCase):

    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-key'})
    @patch('urllib.request.urlopen')
    def test_web_search_basic(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            'web': {'results': [
                {'title': 'Test', 'url': 'https://example.com', 'description': 'A test result'}
            ]}
        })
        from salmalm.tools.tools_brave import brave_web_search
        result = brave_web_search({'query': 'hello'})
        self.assertIn('Test', result)
        self.assertIn('example.com', result)

    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-key'})
    @patch('urllib.request.urlopen')
    def test_web_search_no_results(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({'web': {'results': []}})
        from salmalm.tools.tools_brave import brave_web_search
        result = brave_web_search({'query': 'obscure'})
        self.assertEqual(result, 'No results found.')

    def test_web_search_no_query(self):
        from salmalm.tools.tools_brave import brave_web_search
        result = brave_web_search({})
        self.assertIn('query is required', result)

    @patch.dict(os.environ, {}, clear=True)
    def test_web_search_no_api_key(self):
        # Clear any cached modules to force re-evaluation
        from salmalm.tools.tools_brave import _brave_request
        result = _brave_request('web/search', {'q': 'test'})
        self.assertIn('_error', result)
        self.assertIn('BRAVE_API_KEY', result['_error'])

    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-key'})
    @patch('urllib.request.urlopen')
    def test_web_search_extra_snippets(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            'web': {'results': [
                {'title': 'Snippet', 'url': 'https://a.com', 'description': 'desc',
                 'extra_snippets': ['extra1', 'extra2', 'extra3']}
            ]}
        })
        from salmalm.tools.tools_brave import brave_web_search
        result = brave_web_search({'query': 'test', 'extra_snippets': True})
        self.assertIn('extra1', result)
        self.assertIn('extra2', result)


class TestBraveLLMContext(unittest.TestCase):

    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-key'})
    @patch('urllib.request.urlopen')
    def test_llm_context_basic(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            'web': {'results': [
                {'title': 'Context', 'url': 'https://ctx.com', 'description': 'Context info'}
            ]},
            'summary': 'This is a summary.'
        })
        from salmalm.tools.tools_brave import brave_llm_context
        result = brave_llm_context({'query': 'test'})
        self.assertIn('Summary', result)
        self.assertIn('Context', result)

    def test_llm_context_no_query(self):
        from salmalm.tools.tools_brave import brave_llm_context
        result = brave_llm_context({})
        self.assertIn('query is required', result)


class TestBraveNewsSearch(unittest.TestCase):

    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-key'})
    @patch('urllib.request.urlopen')
    def test_news_search_basic(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            'results': [
                {'title': 'Breaking News', 'url': 'https://news.com/1',
                 'description': 'Something happened', 'age': '2h'}
            ]
        })
        from salmalm.tools.tools_brave import brave_news_search
        result = brave_news_search({'query': 'news'})
        self.assertIn('Breaking News', result)
        self.assertIn('2h', result)

    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-key'})
    @patch('urllib.request.urlopen')
    def test_news_search_empty(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({'results': []})
        from salmalm.tools.tools_brave import brave_news_search
        result = brave_news_search({'query': 'nothing'})
        self.assertEqual(result, 'No news found.')

    def test_news_no_query(self):
        from salmalm.tools.tools_brave import brave_news_search
        result = brave_news_search({})
        self.assertIn('query is required', result)


class TestBraveImageSearch(unittest.TestCase):

    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-key'})
    @patch('urllib.request.urlopen')
    def test_image_search_basic(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            'results': [
                {'title': 'Cat Photo', 'url': 'https://img.com/cat.jpg',
                 'properties': {'url': 'https://img.com/cat.jpg'},
                 'thumbnail': {'src': 'https://img.com/cat_thumb.jpg'}}
            ]
        })
        from salmalm.tools.tools_brave import brave_image_search
        result = brave_image_search({'query': 'cats'})
        self.assertIn('Cat Photo', result)
        self.assertIn('thumb', result.lower())

    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-key'})
    @patch('urllib.request.urlopen')
    def test_image_search_empty(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({'results': []})
        from salmalm.tools.tools_brave import brave_image_search
        result = brave_image_search({'query': 'nothing'})
        self.assertEqual(result, 'No images found.')


class TestBraveRequest(unittest.TestCase):

    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-key'})
    @patch('urllib.request.urlopen')
    def test_http_error_handling(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'https://api.search.brave.com/', 429, 'Too Many Requests',
            {}, BytesIO(b'Rate limited'))
        from salmalm.tools.tools_brave import _brave_request
        result = _brave_request('web/search', {'q': 'test'})
        self.assertIn('_error', result)
        self.assertIn('429', result['_error'])

    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-key'})
    @patch('urllib.request.urlopen')
    def test_count_capped_at_20(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({'web': {'results': []}})
        from salmalm.tools.tools_brave import brave_web_search
        brave_web_search({'query': 'test', 'count': 50})
        call_url = mock_urlopen.call_args[0][0].full_url
        self.assertIn('count=20', call_url)

    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-key'})
    @patch('urllib.request.urlopen')
    def test_params_filtering(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({'web': {'results': []}})
        from salmalm.tools.tools_brave import brave_web_search
        brave_web_search({'query': 'test', 'freshness': 'pd', 'country': 'KR'})
        call_url = mock_urlopen.call_args[0][0].full_url
        self.assertIn('freshness=pd', call_url)
        self.assertIn('country=KR', call_url)


class TestBraveRAGAugment(unittest.TestCase):

    @patch('salmalm.config_manager.ConfigManager.load', return_value={'rag_augment': True})
    @patch.dict(os.environ, {'BRAVE_API_KEY': 'test-key'})
    @patch('urllib.request.urlopen')
    def test_augment_enabled(self, mock_urlopen, mock_load):
        mock_urlopen.return_value = _mock_urlopen({
            'web': {'results': [
                {'title': 'Web Info', 'url': 'https://web.com', 'description': 'Augmented'}
            ]}
        })
        from salmalm.features.rag import brave_augment_context
        result = brave_augment_context('test query')
        self.assertIn('Web context', result)

    @patch('salmalm.config_manager.ConfigManager.load', return_value={'rag_augment': False})
    def test_augment_disabled(self, mock_load):
        from salmalm.features.rag import brave_augment_context
        result = brave_augment_context('test query')
        self.assertEqual(result, '')


if __name__ == '__main__':
    unittest.main()
