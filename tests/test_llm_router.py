"""Tests for salmalm.core.llm_router."""
import json
import os
import unittest
from unittest.mock import patch, MagicMock

from salmalm.core.llm_router import (
    detect_provider, get_api_key, is_provider_available,
    list_available_models, LLMRouter, handle_model_command,
    PROVIDERS, _PREFIX_MAP,
)


class TestDetectProvider(unittest.TestCase):
    def test_anthropic_prefix(self):
        p, m = detect_provider('anthropic/claude-sonnet-4')
        assert p == 'anthropic'
        assert m == 'claude-sonnet-4'

    def test_openai_prefix(self):
        p, m = detect_provider('openai/gpt-4.1')
        assert p == 'openai'
        assert m == 'gpt-4.1'

    def test_google_prefix(self):
        p, m = detect_provider('google/gemini-2.5-pro')
        assert p == 'google'

    def test_groq_prefix(self):
        p, m = detect_provider('groq/llama-3.3-70b')
        assert p == 'groq'

    def test_ollama_prefix(self):
        p, m = detect_provider('ollama/llama3.2')
        assert p == 'ollama'
        assert m == 'llama3.2'

    def test_heuristic_claude(self):
        p, _ = detect_provider('claude-opus-4-6')
        assert p == 'anthropic'

    def test_heuristic_gpt(self):
        p, _ = detect_provider('gpt-5.3-codex')
        assert p == 'openai'

    def test_heuristic_gemini(self):
        p, _ = detect_provider('gemini-3-pro-preview')
        assert p == 'google'

    def test_heuristic_llama_with_groq_key(self):
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test'}):
            p, _ = detect_provider('llama-3.3-70b')
            assert p == 'groq'

    def test_default_openai(self):
        p, _ = detect_provider('unknown-model-xyz')
        assert p == 'openai'


class TestProviderAvailability(unittest.TestCase):
    def test_ollama_always_available(self):
        assert is_provider_available('ollama') is True

    def test_anthropic_needs_key(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('ANTHROPIC_API_KEY', None)
            assert is_provider_available('anthropic') is False

    def test_anthropic_with_key(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-test'}):
            assert is_provider_available('anthropic') is True

    def test_get_api_key(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-123'}):
            assert get_api_key('openai') == 'sk-123'

    def test_get_api_key_ollama(self):
        assert get_api_key('ollama') is None


class TestListModels(unittest.TestCase):
    def test_list_with_keys(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'k', 'OPENAI_API_KEY': 'k'}):
            models = list_available_models()
            providers = {m['provider'] for m in models}
            assert 'anthropic' in providers
            assert 'openai' in providers

    def test_list_includes_ollama(self):
        models = list_available_models()
        providers = {m['provider'] for m in models}
        assert 'ollama' in providers


class TestLLMRouter(unittest.TestCase):
    def test_switch_model_no_key(self):
        r = LLMRouter()
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('ANTHROPIC_API_KEY', None)
            result = r.switch_model('anthropic/claude-opus-4-6')
            assert '❌' in result or 'not configured' in result

    def test_switch_model_with_key(self):
        r = LLMRouter()
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'k'}):
            result = r.switch_model('anthropic/claude-opus-4-6')
            assert '✅' in result
            assert r.current_model == 'anthropic/claude-opus-4-6'

    def test_list_models_format(self):
        r = LLMRouter()
        output = r.list_models()
        assert 'Available Models' in output or 'No providers' in output

    def test_build_request_anthropic(self):
        r = LLMRouter()
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'k'}):
            url, headers, body = r._build_request(
                'anthropic', 'claude-sonnet-4',
                [{'role': 'system', 'content': 'hi'}, {'role': 'user', 'content': 'hello'}],
            )
            assert 'anthropic' in url
            assert 'x-api-key' in headers
            assert 'system' in body  # system extracted

    def test_build_request_openai(self):
        r = LLMRouter()
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'k'}):
            url, headers, body = r._build_request(
                'openai', 'gpt-4.1',
                [{'role': 'user', 'content': 'test'}],
            )
            assert 'openai' in url
            assert 'Authorization' in headers

    def test_build_request_ollama(self):
        r = LLMRouter()
        url, headers, body = r._build_request(
            'ollama', 'llama3.2',
            [{'role': 'user', 'content': 'test'}],
        )
        assert 'stream' in body
        assert body['stream'] is False

    def test_parse_response_anthropic(self):
        r = LLMRouter()
        data = {
            'content': [{'type': 'text', 'text': 'Hello!'}],
            'usage': {'input_tokens': 10, 'output_tokens': 5},
            'model': 'claude-sonnet-4',
        }
        result = r._parse_response('anthropic', data)
        assert result['content'] == 'Hello!'
        assert result['usage']['input'] == 10

    def test_parse_response_openai(self):
        r = LLMRouter()
        data = {
            'choices': [{'message': {'content': 'Hi there'}}],
            'usage': {'prompt_tokens': 8, 'completion_tokens': 3},
            'model': 'gpt-4.1',
        }
        result = r._parse_response('openai', data)
        assert result['content'] == 'Hi there'

    def test_parse_response_ollama(self):
        r = LLMRouter()
        data = {
            'message': {'content': 'Ollama response'},
            'prompt_eval_count': 20,
            'eval_count': 10,
            'model': 'llama3.2',
        }
        result = r._parse_response('ollama', data)
        assert result['content'] == 'Ollama response'

    def test_call_all_fail(self):
        r = LLMRouter()
        r._fallback_order = []  # no fallbacks
        with patch.object(r, '_do_call', side_effect=Exception('fail')):
            result = r.call([{'role': 'user', 'content': 'hi'}], model='anthropic/claude-sonnet-4')
            assert '❌' in result['content']


class TestHandleModelCommand(unittest.TestCase):
    def test_model_list(self):
        result = handle_model_command('/model list')
        assert isinstance(result, str)

    def test_model_switch(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'k'}):
            result = handle_model_command('/model switch openai/gpt-4.1')
            assert '✅' in result

    def test_model_show_current(self):
        result = handle_model_command('/model')
        assert 'Current model' in result
