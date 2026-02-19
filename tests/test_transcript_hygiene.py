"""Tests for Transcript Hygiene."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from salmalm.transcript_hygiene import TranscriptHygiene, PROVIDER_RULES


class TestTranscriptHygieneAnthropic(unittest.TestCase):

    def setUp(self):
        self.th = TranscriptHygiene('anthropic')

    def test_merge_consecutive_user(self):
        msgs = [
            {'role': 'user', 'content': 'hello'},
            {'role': 'user', 'content': 'world'},
        ]
        result = self.th.clean(msgs)
        user_msgs = [m for m in result if m['role'] == 'user']
        self.assertEqual(len(user_msgs), 1)
        self.assertIn('hello', user_msgs[0]['content'])
        self.assertIn('world', user_msgs[0]['content'])

    def test_remove_empty_assistant(self):
        msgs = [
            {'role': 'user', 'content': 'hi'},
            {'role': 'assistant', 'content': ''},
            {'role': 'assistant', 'content': 'real response'},
        ]
        result = self.th.clean(msgs)
        assistant_msgs = [m for m in result if m['role'] == 'assistant']
        self.assertEqual(len(assistant_msgs), 1)
        self.assertEqual(assistant_msgs[0]['content'], 'real response')

    def test_orphan_tool_result_removed(self):
        msgs = [
            {'role': 'user', 'content': [
                {'type': 'tool_result', 'tool_use_id': 'orphan_123', 'content': 'stale'}
            ]},
        ]
        result = self.th.clean(msgs)
        # Should be removed since no matching tool_use
        user_msgs = [m for m in result if m['role'] == 'user']
        self.assertEqual(len(user_msgs), 0)

    def test_synthetic_tool_result(self):
        msgs = [
            {'role': 'assistant', 'content': [
                {'type': 'tool_use', 'id': 'tu_1', 'name': 'test', 'input': {}}
            ]},
        ]
        result = self.th.clean(msgs)
        # Should have synthetic result added
        user_msgs = [m for m in result if m['role'] == 'user']
        self.assertTrue(len(user_msgs) >= 1)

    def test_invalid_tool_use_dropped(self):
        msgs = [
            {'role': 'assistant', 'content': [
                {'type': 'tool_use', 'id': 'bad', 'name': 'test'},  # no input
                {'type': 'text', 'text': 'keep this'},
            ]},
        ]
        result = self.th.clean(msgs)
        assistant = [m for m in result if m['role'] == 'assistant']
        self.assertEqual(len(assistant), 1)
        blocks = assistant[0]['content']
        tool_uses = [b for b in blocks if b.get('type') == 'tool_use']
        self.assertEqual(len(tool_uses), 0)

    def test_original_not_modified(self):
        msgs = [{'role': 'user', 'content': 'original'}]
        import copy
        original = copy.deepcopy(msgs)
        self.th.clean(msgs)
        self.assertEqual(msgs, original)


class TestTranscriptHygieneGoogle(unittest.TestCase):

    def setUp(self):
        self.th = TranscriptHygiene('google')

    def test_turn_alternation(self):
        msgs = [
            {'role': 'user', 'content': 'a'},
            {'role': 'user', 'content': 'b'},
            {'role': 'assistant', 'content': 'c'},
        ]
        result = self.th.clean(msgs)
        for i in range(1, len(result)):
            self.assertNotEqual(result[i]['role'], result[i-1]['role'])

    def test_prepend_user_bootstrap(self):
        msgs = [{'role': 'assistant', 'content': 'first'}]
        result = self.th.clean(msgs)
        self.assertEqual(result[0]['role'], 'user')

    def test_sanitize_tool_ids(self):
        msgs = [{'role': 'assistant', 'content': [
            {'type': 'tool_use', 'id': 'tool-call-123!@#', 'name': 'x', 'input': {}}
        ]}]
        result = self.th.clean(msgs)
        for m in result:
            if isinstance(m.get('content'), list):
                for b in m['content']:
                    if 'id' in b:
                        import re
                        self.assertTrue(re.match(r'^[a-zA-Z0-9_]+$', b['id']))


class TestTranscriptHygieneMistral(unittest.TestCase):

    def test_tool_id_length_9(self):
        th = TranscriptHygiene('mistral')
        msgs = [{'role': 'assistant', 'content': [
            {'type': 'tool_use', 'id': 'very-long-tool-id-12345', 'name': 'x', 'input': {}}
        ]}]
        result = th.clean(msgs)
        for m in result:
            if isinstance(m.get('content'), list):
                for b in m['content']:
                    if 'id' in b:
                        self.assertEqual(len(b['id']), 9)


class TestTranscriptHygieneOpenAI(unittest.TestCase):

    def test_image_only(self):
        th = TranscriptHygiene('openai')
        msgs = [{'role': 'user', 'content': 'simple text'}]
        result = th.clean(msgs)
        self.assertEqual(len(result), 1)


class TestProviderRules(unittest.TestCase):

    def test_all_providers_defined(self):
        for provider in ('anthropic', 'google', 'openai', 'mistral'):
            self.assertIn(provider, PROVIDER_RULES)


if __name__ == '__main__':
    unittest.main()
