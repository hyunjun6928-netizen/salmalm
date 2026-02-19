"""Tests for channel_router module."""
import asyncio
import json
import sys
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from salmalm.channel_router import (
    ChannelRouter, format_for_channel, CHANNEL_FORMAT,
    _load_config, _save_config, channel_router,
)


class TestFormatForChannel(unittest.TestCase):
    def test_telegram_truncate(self):
        text = 'a' * 5000
        result = format_for_channel(text, 'telegram')
        self.assertLessEqual(len(result), 4096)
        self.assertIn('truncated', result)

    def test_discord_truncate_chars(self):
        text = 'a' * 3000
        result = format_for_channel(text, 'discord')
        self.assertLessEqual(len(result), 2000)

    def test_discord_truncate_lines(self):
        text = '\n'.join([f'line {i}' for i in range(30)])
        result = format_for_channel(text, 'discord')
        lines = result.split('\n')
        self.assertLessEqual(len(lines), 18)  # 17 + truncated line

    def test_web_no_truncate(self):
        text = 'a' * 100000
        result = format_for_channel(text, 'web')
        self.assertEqual(len(result), 100000)

    def test_table_removal_discord(self):
        text = '| A | B |\n|---|---|\n| 1 | 2 |'
        result = format_for_channel(text, 'discord')
        self.assertNotIn('|', result)
        self.assertIn('•', result)

    def test_table_removal_slack(self):
        text = '| Header1 | Header2 |\n|---|---|\n| val1 | val2 |'
        result = format_for_channel(text, 'slack')
        self.assertNotIn('|---|', result)
        self.assertIn('•', result)

    def test_unknown_channel_defaults_web(self):
        text = 'a' * 100
        result = format_for_channel(text, 'unknown_channel')
        self.assertEqual(result, text)

    def test_empty_text(self):
        result = format_for_channel('', 'telegram')
        self.assertEqual(result, '')


class TestChannelRouter(unittest.TestCase):
    def setUp(self):
        self.router = ChannelRouter()

    def test_register_channel(self):
        send_fn = MagicMock()
        self.router.register('test_ch', send_fn=send_fn)
        self.assertTrue(self.router.is_enabled('test_ch'))
        channels = self.router.list_channels()
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]['name'], 'test_ch')

    def test_unregister_channel(self):
        self.router.register('ch', send_fn=MagicMock())
        self.assertTrue(self.router.unregister('ch'))
        self.assertFalse(self.router.is_enabled('ch'))
        self.assertFalse(self.router.unregister('ch'))

    def test_route_outbound(self):
        send_fn = MagicMock()
        self.router.register('telegram', send_fn=send_fn)
        result = self.router.route_outbound('telegram', text='hello', chat_id='123')
        self.assertTrue(result)
        send_fn.assert_called_once()
        call_kwargs = send_fn.call_args
        self.assertIn('hello', str(call_kwargs))

    def test_route_outbound_disabled(self):
        self.router.register('ch', send_fn=MagicMock(), enabled=False)
        result = self.router.route_outbound('ch', text='hi')
        self.assertFalse(result)

    def test_route_outbound_unknown_channel(self):
        result = self.router.route_outbound('nonexistent', text='hi')
        self.assertFalse(result)

    def test_route_inbound(self):
        async def handler(msg):
            return f"echo: {msg['text']}"

        self.router.set_handler('web', handler)
        result = asyncio.get_event_loop().run_until_complete(
            self.router.route_inbound('web', {'text': 'test'})
        )
        self.assertEqual(result, 'echo: test')

    def test_route_inbound_no_handler(self):
        result = asyncio.get_event_loop().run_until_complete(
            self.router.route_inbound('web', {'text': 'test'})
        )
        self.assertIsNone(result)

    def test_channels_property_hides_send_fn(self):
        self.router.register('ch', send_fn=MagicMock())
        channels = self.router.channels
        self.assertNotIn('send_fn', channels['ch'])

    def test_list_multiple_channels(self):
        self.router.register('a', send_fn=MagicMock())
        self.router.register('b', send_fn=MagicMock())
        self.router.register('c', send_fn=MagicMock(), enabled=False)
        channels = self.router.list_channels()
        self.assertEqual(len(channels), 3)
        names = {c['name'] for c in channels}
        self.assertEqual(names, {'a', 'b', 'c'})


class TestChannelFormat(unittest.TestCase):
    def test_all_channels_defined(self):
        for ch in ['telegram', 'discord', 'slack', 'web', 'webhook']:
            self.assertIn(ch, CHANNEL_FORMAT)

    def test_telegram_format(self):
        fmt = CHANNEL_FORMAT['telegram']
        self.assertEqual(fmt['max_chars'], 4096)
        self.assertEqual(fmt['markdown'], 'MarkdownV2')

    def test_discord_format(self):
        fmt = CHANNEL_FORMAT['discord']
        self.assertEqual(fmt['max_chars'], 2000)
        self.assertTrue(fmt['no_tables'])


if __name__ == '__main__':
    unittest.main()
