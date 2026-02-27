"""Test model selection and routing."""
import pytest
from unittest.mock import MagicMock, patch


class TestSwitchModel:
    """Test llm_router.switch_model handles 'auto' and other models."""

    def test_switch_to_auto(self):
        from salmalm.core.llm_router import LLMRouter
        router = LLMRouter()
        result = router.switch_model('auto')
        assert '✅' in result
        assert router.current_model == 'auto'

    def test_switch_to_specific_model(self):
        from salmalm.core.llm_router import LLMRouter
        router = LLMRouter()
        with patch('salmalm.core.llm_router.is_provider_available', return_value=True):
            result = router.switch_model('anthropic/claude-opus-4-6')
            assert '✅' in result
            assert router.current_model == 'anthropic/claude-opus-4-6'

    def test_switch_to_unavailable_provider(self):
        from salmalm.core.llm_router import LLMRouter
        router = LLMRouter()
        with patch('salmalm.core.llm_router.is_provider_available', return_value=False):
            result = router.switch_model('anthropic/claude-opus-4-6')
            assert '❌' in result


class TestSelectModel:
    """Test select_model routing logic."""

    def _make_session(self, override=None):
        s = MagicMock()
        s.model_override = override or 'auto'
        s._default_model = None
        s.thinking_enabled = False
        return s

    @patch('salmalm.core.model_selection.load_routing_config',
           return_value={'simple': '', 'moderate': '', 'complex': ''})
    def test_short_message_routes_simple(self, _):
        from salmalm.core.model_selection import select_model
        session = self._make_session('auto')
        model, level = select_model('hi', session)
        assert level == 'simple'

    @patch('salmalm.core.model_selection.load_routing_config',
           return_value={'simple': '', 'moderate': '', 'complex': ''})
    def test_long_message_routes_complex(self, _):
        from salmalm.core.model_selection import select_model
        from unittest.mock import MagicMock, patch as _patch
        mock_router = MagicMock()
        mock_router.force_model = None
        with _patch('salmalm.core.core.router', mock_router):
            session = self._make_session('auto')
            model, level = select_model('x' * 350, session)  # 300자 초과 → complex
        assert level == 'complex'

    def test_manual_override_respected(self):
        from salmalm.core.model_selection import select_model
        session = self._make_session('anthropic/claude-opus-4-6')
        model, level = select_model('hi', session)
        assert model == 'anthropic/claude-opus-4-6'
        assert level == 'manual'

    def test_haiku_override(self):
        from salmalm.core.model_selection import select_model
        session = self._make_session('haiku')
        model, level = select_model('complex architecture question', session)
        assert level == 'simple'  # haiku forces simple

    @patch('salmalm.core.model_selection.load_routing_config',
           return_value={'simple': '', 'moderate': '', 'complex': ''})
    def test_thinking_enabled_routes_complex(self, _):
        from salmalm.core.model_selection import select_model
        session = self._make_session('auto')
        session.thinking_enabled = True
        model, level = select_model('hi', session)
        assert level == 'complex'
