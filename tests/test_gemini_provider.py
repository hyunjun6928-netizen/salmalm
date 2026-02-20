"""Tests for Google Gemini provider integration.

Covers: streaming, non-streaming, API key fallback, tool formatting,
        message conversion, pricing, failover, model aliases, router integration.
"""
from __future__ import annotations

import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# Ensure salmalm is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestBuildGeminiContents(unittest.TestCase):
    """Test _build_gemini_contents message conversion."""

    def test_simple_user_message(self):
        from salmalm.core.llm import _build_gemini_contents
        msgs = [{'role': 'user', 'content': 'Hello'}]
        result = _build_gemini_contents(msgs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['role'], 'user')
        self.assertEqual(result[0]['parts'], [{'text': 'Hello'}])

    def test_system_mapped_to_user(self):
        from salmalm.core.llm import _build_gemini_contents
        msgs = [{'role': 'system', 'content': 'You are helpful'}]
        result = _build_gemini_contents(msgs)
        self.assertEqual(result[0]['role'], 'user')

    def test_assistant_mapped_to_model(self):
        from salmalm.core.llm import _build_gemini_contents
        msgs = [{'role': 'assistant', 'content': 'Hi there'}]
        result = _build_gemini_contents(msgs)
        self.assertEqual(result[0]['role'], 'model')

    def test_consecutive_same_role_merged(self):
        from salmalm.core.llm import _build_gemini_contents
        msgs = [
            {'role': 'system', 'content': 'System prompt'},
            {'role': 'user', 'content': 'Hello'},
        ]
        result = _build_gemini_contents(msgs)
        # system + user both map to 'user', should merge
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]['parts']), 2)

    def test_multimodal_text_extraction(self):
        from salmalm.core.llm import _build_gemini_contents
        msgs = [{'role': 'user', 'content': [
            {'type': 'text', 'text': 'Describe this'},
            {'type': 'image', 'source': {'type': 'base64', 'data': 'abc'}},
        ]}]
        result = _build_gemini_contents(msgs)
        self.assertEqual(result[0]['parts'], [{'text': 'Describe this'}])

    def test_alternating_roles_not_merged(self):
        from salmalm.core.llm import _build_gemini_contents
        msgs = [
            {'role': 'user', 'content': 'Q1'},
            {'role': 'assistant', 'content': 'A1'},
            {'role': 'user', 'content': 'Q2'},
        ]
        result = _build_gemini_contents(msgs)
        self.assertEqual(len(result), 3)


class TestBuildGeminiTools(unittest.TestCase):
    """Test _build_gemini_tools conversion."""

    def test_none_tools(self):
        from salmalm.core.llm import _build_gemini_tools
        self.assertIsNone(_build_gemini_tools(None))

    def test_empty_tools(self):
        from salmalm.core.llm import _build_gemini_tools
        self.assertIsNone(_build_gemini_tools([]))

    def test_single_tool(self):
        from salmalm.core.llm import _build_gemini_tools
        tools = [{'name': 'web_search', 'description': 'Search the web',
                  'parameters': {'type': 'object', 'properties': {'q': {'type': 'string'}}}}]
        result = _build_gemini_tools(tools)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]['functionDeclarations']), 1)
        self.assertEqual(result[0]['functionDeclarations'][0]['name'], 'web_search')
        self.assertIn('parameters', result[0]['functionDeclarations'][0])

    def test_tool_without_properties(self):
        from salmalm.core.llm import _build_gemini_tools
        tools = [{'name': 'noop', 'description': 'No params', 'parameters': {'type': 'object'}}]
        result = _build_gemini_tools(tools)
        self.assertEqual(len(result[0]['functionDeclarations']), 1)
        # Should NOT have parameters key since no properties
        self.assertNotIn('parameters', result[0]['functionDeclarations'][0])


class TestGeminiApiKeyFallback(unittest.TestCase):
    """Test GOOGLE_API_KEY / GEMINI_API_KEY fallback logic."""

    @patch.dict(os.environ, {'GOOGLE_API_KEY': 'gk123'}, clear=False)
    def test_google_api_key_primary(self):
        from salmalm.core.llm_router import get_api_key
        key = get_api_key('google')
        self.assertEqual(key, 'gk123')

    @patch.dict(os.environ, {'GEMINI_API_KEY': 'gem456'}, clear=False)
    def test_gemini_api_key_fallback(self):
        # Remove GOOGLE_API_KEY if present
        env = os.environ.copy()
        env.pop('GOOGLE_API_KEY', None)
        with patch.dict(os.environ, env, clear=True):
            os.environ['GEMINI_API_KEY'] = 'gem456'
            from salmalm.core.llm_router import get_api_key
            key = get_api_key('google')
            self.assertEqual(key, 'gem456')

    @patch.dict(os.environ, {'GOOGLE_API_KEY': 'gk', 'GEMINI_API_KEY': 'gem'}, clear=False)
    def test_google_key_takes_priority(self):
        from salmalm.core.llm_router import get_api_key
        key = get_api_key('google')
        self.assertEqual(key, 'gk')


class TestGeminiProviderDetection(unittest.TestCase):
    """Test provider detection for Gemini models."""

    def test_detect_google_prefix(self):
        from salmalm.core.llm_router import detect_provider
        prov, bare = detect_provider('google/gemini-2.5-pro')
        self.assertEqual(prov, 'google')
        self.assertEqual(bare, 'gemini-2.5-pro')

    def test_detect_gemini_heuristic(self):
        from salmalm.core.llm_router import detect_provider
        prov, bare = detect_provider('gemini-2.0-flash')
        self.assertEqual(prov, 'google')

    def test_gemini_2_0_flash_in_models(self):
        from salmalm.core.llm_router import PROVIDERS
        self.assertIn('gemini-2.0-flash', PROVIDERS['google']['models'])


class TestGeminiPricing(unittest.TestCase):
    """Test Gemini model pricing in engine."""

    def test_gemini_pro_pricing(self):
        from salmalm.core.engine import _get_pricing
        p = _get_pricing('google/gemini-2.5-pro')
        self.assertEqual(p['input'], 1.25)
        self.assertEqual(p['output'], 10.0)

    def test_gemini_flash_pricing(self):
        from salmalm.core.engine import _get_pricing
        p = _get_pricing('google/gemini-2.5-flash')
        self.assertEqual(p['input'], 0.15)

    def test_gemini_2_0_flash_pricing(self):
        from salmalm.core.engine import _get_pricing
        p = _get_pricing('google/gemini-2.0-flash')
        self.assertEqual(p['input'], 0.10)

    def test_unknown_gemini_fallback_flash(self):
        from salmalm.core.engine import _get_pricing
        p = _get_pricing('google/gemini-99-flash-future')
        # Should match gemini fallback (flash because no 'pro' in name)
        self.assertEqual(p['input'], 0.15)

    def test_estimate_cost_gemini(self):
        from salmalm.core.engine import estimate_cost
        cost = estimate_cost('google/gemini-2.5-flash', {'input': 1000, 'output': 500})
        expected = 1000 * 0.15 / 1_000_000 + 500 * 0.60 / 1_000_000
        self.assertAlmostEqual(cost, expected, places=8)


class TestGeminiStreamGoogle(unittest.TestCase):
    """Test stream_google function."""

    def test_stream_no_api_key(self):
        from salmalm.core.llm import stream_google
        with patch('salmalm.core.llm.vault') as mock_vault:
            mock_vault.get.return_value = None
            events = list(stream_google([{'role': 'user', 'content': 'hi'}],
                                         model='google/gemini-2.5-flash'))
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]['type'], 'error')
            self.assertIn('API key', events[0]['error'])

    @patch('salmalm.core.llm.check_cost_cap')
    @patch('salmalm.core.llm.vault')
    @patch('salmalm.core.llm.urllib.request.urlopen')
    @patch('salmalm.core.llm.track_usage')
    def test_stream_success(self, mock_track, mock_urlopen, mock_vault, mock_cap):
        from salmalm.core.llm import stream_google
        mock_vault.get.return_value = 'test-key'

        # Simulate SSE response with two chunks
        sse_data = (
            'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}]}}]}\n\n'
            'data: {"candidates":[{"content":{"parts":[{"text":" world"}]}}],'
            '"usageMetadata":{"promptTokenCount":5,"candidatesTokenCount":2}}\n\n'
        )
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [sse_data.encode('utf-8'), b'']
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        events = list(stream_google([{'role': 'user', 'content': 'hi'}],
                                     model='google/gemini-2.5-flash'))

        text_events = [e for e in events if e.get('type') == 'text_delta']
        self.assertTrue(len(text_events) >= 1)

        end_events = [e for e in events if e.get('type') == 'message_end']
        self.assertEqual(len(end_events), 1)
        self.assertIn('Hello', end_events[0]['content'])


class TestGeminiFailoverConfig(unittest.TestCase):
    """Test failover chains for Gemini models."""

    def test_gemini_fallbacks_defined(self):
        from salmalm.core.llm_loop import _DEFAULT_FALLBACKS
        self.assertIn('google/gemini-2.5-pro', _DEFAULT_FALLBACKS)
        self.assertIn('google/gemini-2.5-flash', _DEFAULT_FALLBACKS)
        self.assertIn('google/gemini-2.0-flash', _DEFAULT_FALLBACKS)

    def test_gemini_pro_falls_to_flash(self):
        from salmalm.core.llm_loop import _DEFAULT_FALLBACKS
        chain = _DEFAULT_FALLBACKS['google/gemini-2.5-pro']
        self.assertIn('google/gemini-2.5-flash', chain)


class TestGeminiModelAliases(unittest.TestCase):
    """Test that Gemini model aliases work in /model command."""

    def test_gemini_alias_exists(self):
        from salmalm.core.engine import MODEL_ALIASES
        self.assertIn('gemini', MODEL_ALIASES)
        self.assertTrue(MODEL_ALIASES['gemini'].startswith('google/'))

    def test_flash_alias_exists(self):
        from salmalm.core.engine import MODEL_ALIASES
        self.assertIn('flash', MODEL_ALIASES)
        self.assertTrue(MODEL_ALIASES['flash'].startswith('google/'))


class TestGeminiRouterAvailability(unittest.TestCase):
    """Test router availability with Google provider."""

    @patch.dict(os.environ, {'GOOGLE_API_KEY': 'test123'}, clear=False)
    def test_google_available_with_key(self):
        from salmalm.core.llm_router import is_provider_available
        self.assertTrue(is_provider_available('google'))

    def test_google_lists_gemini_2_0_flash(self):
        from salmalm.core.llm_router import PROVIDERS
        models = PROVIDERS['google']['models']
        self.assertIn('gemini-2.0-flash', models)
        self.assertIn('gemini-2.5-pro', models)
        self.assertIn('gemini-2.5-flash', models)


class TestGeminiCallGoogle(unittest.TestCase):
    """Test _call_google non-streaming."""

    @patch('salmalm.core.llm._http_post')
    def test_call_google_basic(self, mock_post):
        from salmalm.core.llm import _call_google
        mock_post.return_value = {
            'candidates': [{'content': {'parts': [{'text': 'Hello!'}]}}],
            'usageMetadata': {'promptTokenCount': 10, 'candidatesTokenCount': 5},
        }
        result = _call_google('key123', 'gemini-2.5-flash',
                               [{'role': 'user', 'content': 'Hi'}], 1024)
        self.assertEqual(result['content'], 'Hello!')
        self.assertEqual(result['usage']['input'], 10)
        self.assertEqual(result['usage']['output'], 5)

    @patch('salmalm.core.llm._http_post')
    def test_call_google_with_tools(self, mock_post):
        from salmalm.core.llm import _call_google
        mock_post.return_value = {
            'candidates': [{'content': {'parts': [
                {'functionCall': {'name': 'web_search', 'args': {'q': 'test'}}}
            ]}}],
            'usageMetadata': {'promptTokenCount': 10, 'candidatesTokenCount': 5},
        }
        tools = [{'name': 'web_search', 'description': 'Search',
                  'parameters': {'type': 'object', 'properties': {'q': {'type': 'string'}}}}]
        result = _call_google('key123', 'gemini-2.5-pro',
                               [{'role': 'user', 'content': 'Search for cats'}], 1024, tools=tools)
        self.assertEqual(len(result['tool_calls']), 1)
        self.assertEqual(result['tool_calls'][0]['name'], 'web_search')
        self.assertEqual(result['tool_calls'][0]['arguments'], {'q': 'test'})

    @patch('salmalm.core.llm._http_post')
    def test_call_google_empty_response(self, mock_post):
        from salmalm.core.llm import _call_google
        mock_post.return_value = {'candidates': [], 'usageMetadata': {}}
        result = _call_google('key123', 'gemini-2.0-flash',
                               [{'role': 'user', 'content': 'Hi'}], 1024)
        self.assertEqual(result['content'], '')
        self.assertEqual(result['tool_calls'], [])


class TestGeminiEngineToolsForProvider(unittest.TestCase):
    """Test IntelligenceEngine._get_tools_for_provider for google."""

    def test_google_tool_format(self):
        from salmalm.core.engine import IntelligenceEngine
        engine = IntelligenceEngine()
        # Mock tools
        with patch('salmalm.core.engine.execute_tool'):
            tools = engine._get_tools_for_provider('google')
            if tools:  # may be empty if no tools defined in test env
                # Google format: name, description, parameters (not input_schema)
                for t in tools:
                    self.assertIn('name', t)
                    self.assertIn('description', t)
                    self.assertIn('parameters', t)
                    self.assertNotIn('input_schema', t)


if __name__ == '__main__':
    unittest.main()
