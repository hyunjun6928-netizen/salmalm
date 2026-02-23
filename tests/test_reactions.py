"""Tests for tools_reaction module."""
import json
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from salmalm.tools.tools_reaction import (
    send_reaction, _react_telegram, _react_discord, _react_slack, _react_web,
    REACTION_TOOL,
)


class TestSendReaction(unittest.TestCase):
    def test_unsupported_channel(self):
        result = send_reaction('irc', '123', '👍')
        self.assertFalse(result['ok'])
        self.assertIn('Unsupported', result['error'])

    def test_telegram_no_token(self):
        result = send_reaction('telegram', '123', '👍', chat_id='456', config={})
        self.assertFalse(result['ok'])
        self.assertIn('token', result['error'].lower())

    def test_discord_no_token(self):
        result = send_reaction('discord', '123', '👍', channel_id='456', config={})
        self.assertFalse(result['ok'])

    def test_slack_no_token(self):
        result = send_reaction('slack', '123', '👍', channel_id='456', config={})
        self.assertFalse(result['ok'])

    @patch('salmalm.tools.tools_reaction.urllib.request.urlopen')
    def test_telegram_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({'ok': True}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = _react_telegram('123', '456', '👍', {'token': 'fake_token'})
        self.assertTrue(result['ok'])

    @patch('salmalm.tools.tools_reaction.urllib.request.urlopen')
    def test_discord_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b''
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = _react_discord('ch1', 'msg1', '👍', {'token': 'fake'})
        self.assertTrue(result['ok'])

    def test_web_with_broadcast(self):
        broadcaster = MagicMock()
        result = _react_web('msg1', '👍', {'ws_broadcast': broadcaster})
        self.assertTrue(result['ok'])
        broadcaster.assert_called_once()
        call_args = broadcaster.call_args[0][0]
        self.assertEqual(call_args['type'], 'reaction')
        self.assertEqual(call_args['emoji'], '👍')

    def test_web_without_broadcast(self):
        result = _react_web('msg1', '👍', {})
        self.assertTrue(result['ok'])
        self.assertTrue(result.get('queued'))


class TestReactionToolDefinition(unittest.TestCase):
    def test_tool_structure(self):
        self.assertEqual(REACTION_TOOL['type'], 'function')
        fn = REACTION_TOOL['function']
        self.assertEqual(fn['name'], 'send_reaction')
        self.assertIn('emoji', fn['parameters']['properties'])
        self.assertIn('emoji', fn['parameters']['required'])


if __name__ == '__main__':
    unittest.main()
