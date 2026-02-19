"""Tests for token optimization — selective tool injection, prompt truncation, dynamic max_tokens."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock
import unittest


class TestPromptTruncation(unittest.TestCase):
    """Test prompt.py file truncation and caps."""

    def test_truncate_file_short(self):
        from salmalm.prompt import _truncate_file
        self.assertEqual(_truncate_file('hello', 100), 'hello')

    def test_truncate_file_long(self):
        from salmalm.prompt import _truncate_file
        text = 'x' * 20000
        result = _truncate_file(text, 15000)
        self.assertLessEqual(len(result), 15100)
        self.assertIn('truncated', result)

    def test_max_file_chars_constant(self):
        from salmalm.prompt import MAX_FILE_CHARS
        self.assertEqual(MAX_FILE_CHARS, 15000)

    def test_max_memory_chars_constant(self):
        from salmalm.prompt import MAX_MEMORY_CHARS
        self.assertEqual(MAX_MEMORY_CHARS, 5000)

    def test_max_session_memory_chars(self):
        from salmalm.prompt import MAX_SESSION_MEMORY_CHARS
        self.assertEqual(MAX_SESSION_MEMORY_CHARS, 3000)

    def test_build_system_prompt_bounded(self):
        from salmalm.prompt import build_system_prompt
        prompt = build_system_prompt(full=True)
        self.assertLess(len(prompt), 50000, f"System prompt too large: {len(prompt)} chars")

    def test_build_system_prompt_minimal_smaller(self):
        from salmalm.prompt import build_system_prompt
        import salmalm.prompt as pm
        pm._agents_loaded_full = False
        full = build_system_prompt(full=True)
        minimal = build_system_prompt(full=False)
        self.assertLessEqual(len(minimal), len(full))


class TestSelectiveToolInjection(unittest.TestCase):
    """Test intent-based tool filtering."""

    def test_chat_intent_no_tools(self):
        from salmalm.engine import INTENT_TOOLS
        self.assertEqual(INTENT_TOOLS['chat'], [])

    def test_memory_intent_no_tools(self):
        from salmalm.engine import INTENT_TOOLS
        self.assertEqual(INTENT_TOOLS['memory'], [])

    def test_creative_intent_no_tools(self):
        from salmalm.engine import INTENT_TOOLS
        self.assertEqual(INTENT_TOOLS['creative'], [])

    def test_code_intent_bounded(self):
        from salmalm.engine import INTENT_TOOLS
        tools = INTENT_TOOLS['code']
        self.assertGreater(len(tools), 0)
        self.assertLessEqual(len(tools), 15)
        self.assertIn('exec', tools)

    def test_search_intent_has_web(self):
        from salmalm.engine import INTENT_TOOLS
        tools = INTENT_TOOLS['search']
        self.assertIn('web_search', tools)
        self.assertLessEqual(len(tools), 10)

    def test_keyword_tools_korean(self):
        from salmalm.engine import _KEYWORD_TOOLS
        self.assertIn('날씨', _KEYWORD_TOOLS)
        self.assertIn('weather', _KEYWORD_TOOLS['날씨'])

    def test_get_tools_chat_empty(self):
        from salmalm.engine import IntelligenceEngine
        engine = IntelligenceEngine()
        tools = engine._get_tools_for_provider('anthropic', intent='chat')
        self.assertEqual(tools, [])

    def test_get_tools_code_bounded(self):
        from salmalm.engine import IntelligenceEngine
        engine = IntelligenceEngine()
        tools = engine._get_tools_for_provider('anthropic', intent='code')
        self.assertGreater(len(tools), 0)
        self.assertLessEqual(len(tools), 15)

    def test_keyword_injection_weather(self):
        from salmalm.engine import IntelligenceEngine
        engine = IntelligenceEngine()
        tools = engine._get_tools_for_provider('anthropic', intent='chat',
                                               user_message='오늘 날씨 어때?')
        names = {t['name'] for t in tools}
        self.assertIn('weather', names)


class TestDynamicMaxTokens(unittest.TestCase):

    def test_chat_1024(self):
        from salmalm.engine import _get_dynamic_max_tokens
        self.assertEqual(_get_dynamic_max_tokens('chat', 'hello'), 1024)

    def test_code_4096(self):
        from salmalm.engine import _get_dynamic_max_tokens
        self.assertEqual(_get_dynamic_max_tokens('code', 'write code'), 4096)

    def test_search_2048(self):
        from salmalm.engine import _get_dynamic_max_tokens
        self.assertEqual(_get_dynamic_max_tokens('search', 'find'), 2048)

    def test_detail_upgrade(self):
        from salmalm.engine import _get_dynamic_max_tokens
        self.assertEqual(_get_dynamic_max_tokens('chat', '자세히 설명해'), 4096)

    def test_detail_english(self):
        from salmalm.engine import _get_dynamic_max_tokens
        self.assertEqual(_get_dynamic_max_tokens('chat', 'explain in detail'), 4096)


class TestContextCommand(unittest.TestCase):

    def test_command_registered(self):
        from salmalm.engine import _SLASH_COMMANDS
        self.assertIn('/context', _SLASH_COMMANDS)

    def test_command_output(self):
        from salmalm.engine import _cmd_context
        mock_session = MagicMock()
        mock_session.messages = [
            {'role': 'system', 'content': 'You are helpful.'},
            {'role': 'user', 'content': 'Hello'},
        ]
        result = _cmd_context('/context', mock_session)
        self.assertIn('Context Window Usage', result)
        self.assertIn('System Prompt', result)


class TestPromptCaching(unittest.TestCase):

    def test_intent_tools_dict_exists(self):
        from salmalm.engine import INTENT_TOOLS, INTENT_MAX_TOKENS
        self.assertIsInstance(INTENT_TOOLS, dict)
        self.assertIsInstance(INTENT_MAX_TOKENS, dict)
        self.assertEqual(len(INTENT_TOOLS), 7)  # 7 intent categories


if __name__ == '__main__':
    unittest.main()
