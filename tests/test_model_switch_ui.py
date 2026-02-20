"""Tests for model switch UI backend endpoints and llm_router integration."""
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestLLMRouterAPI(unittest.TestCase):
    """Test llm_router functions used by the Model tab."""

    def test_list_available_models_no_keys(self):
        from salmalm.core.llm_router import list_available_models
        with patch.dict(os.environ, {}, clear=True):
            models = list_available_models()
            # Ollama is always available
            ollama_models = [m for m in models if m['provider'] == 'ollama']
            self.assertTrue(len(ollama_models) > 0)

    def test_detect_provider(self):
        from salmalm.core.llm_router import detect_provider
        self.assertEqual(detect_provider('anthropic/claude-opus-4-6'), ('anthropic', 'claude-opus-4-6'))
        self.assertEqual(detect_provider('openai/gpt-4.1'), ('openai', 'gpt-4.1'))
        self.assertEqual(detect_provider('google/gemini-2.5-pro'), ('google', 'gemini-2.5-pro'))
        self.assertEqual(detect_provider('groq/llama-3.3-70b-versatile'), ('groq', 'llama-3.3-70b-versatile'))
        self.assertEqual(detect_provider('ollama/llama3.2'), ('ollama', 'llama3.2'))

    def test_detect_provider_heuristic(self):
        from salmalm.core.llm_router import detect_provider
        self.assertEqual(detect_provider('claude-opus-4-6')[0], 'anthropic')
        self.assertEqual(detect_provider('gpt-4.1')[0], 'openai')
        self.assertEqual(detect_provider('gemini-2.5-pro')[0], 'google')

    def test_switch_model(self):
        from salmalm.core.llm_router import LLMRouter
        r = LLMRouter()
        # Ollama doesn't need key
        msg = r.switch_model('ollama/llama3.2')
        self.assertIn('✅', msg)
        self.assertEqual(r.current_model, 'ollama/llama3.2')

    def test_switch_model_unavailable(self):
        from salmalm.core.llm_router import LLMRouter
        r = LLMRouter()
        with patch.dict(os.environ, {}, clear=True):
            msg = r.switch_model('anthropic/claude-opus-4-6')
            self.assertIn('❌', msg)

    def test_is_provider_available(self):
        from salmalm.core.llm_router import is_provider_available
        self.assertTrue(is_provider_available('ollama'))
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-test'}):
            self.assertTrue(is_provider_available('anthropic'))
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_provider_available('anthropic'))

    def test_providers_structure(self):
        from salmalm.core.llm_router import PROVIDERS
        for name, cfg in PROVIDERS.items():
            self.assertIn('env_key', cfg)
            self.assertIn('base_url', cfg)
            self.assertIn('models', cfg)
            self.assertIsInstance(cfg['models'], list)

    def test_get_llm_router_providers_response_shape(self):
        """Simulate what _get_llm_router_providers returns."""
        from salmalm.core.llm_router import PROVIDERS, is_provider_available, list_available_models, llm_router
        providers = []
        for name, cfg in PROVIDERS.items():
            providers.append({
                'name': name,
                'available': is_provider_available(name),
                'env_key': cfg.get('env_key', ''),
                'models': [{'name': m, 'full': f'{name}/{m}'} for m in cfg['models']],
            })
        self.assertTrue(len(providers) >= 5)
        for p in providers:
            self.assertIn('name', p)
            self.assertIn('available', p)
            self.assertIn('models', p)
            for m in p['models']:
                self.assertIn('name', m)
                self.assertIn('full', m)
                self.assertIn('/', m['full'])

    def test_model_switch_endpoint_body(self):
        """Test that model switch returns expected keys."""
        from salmalm.core.llm_router import llm_router
        msg = llm_router.switch_model('ollama/llama3.2')
        ok = '✅' in msg
        result = {'ok': ok, 'message': msg, 'current_model': llm_router.current_model}
        self.assertTrue(result['ok'])
        self.assertEqual(result['current_model'], 'ollama/llama3.2')

    def test_route_aliases_exist_in_web_handler(self):
        """Verify that /api/model/switch and /api/test-provider routes exist."""
        import importlib
        web_mod = importlib.import_module('salmalm.web.web')
        source = open(web_mod.__file__).read()
        self.assertIn('/api/model/switch', source)
        self.assertIn('/api/test-provider', source)

    def test_model_router_html_elements(self):
        """Verify the frontend has required HTML elements."""
        html_path = os.path.join(os.path.dirname(__file__), '..', 'salmalm', 'static', 'index.html')
        with open(html_path) as f:
            html = f.read()
        self.assertIn('settings-model-router', html)
        self.assertIn('mr-providers', html)
        self.assertIn('mr-keys', html)
        self.assertIn('mr-current-name', html)
        self.assertIn('_loadModelRouter', html)
        self.assertIn('/api/model/switch', html)
        self.assertIn('/api/test-provider', html)
        self.assertIn('mr-model-btn', html)
        self.assertIn('mr-test-btn', html)
        self.assertIn('mr-save-btn', html)


if __name__ == '__main__':
    unittest.main()
