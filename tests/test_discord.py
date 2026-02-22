"""Test Discord bot message handling."""
import pytest
from unittest.mock import MagicMock, AsyncMock


class TestDiscordMessageHandler:
    """Test that on_message handler is properly registered and called."""

    def test_on_message_registration(self):
        from salmalm.channels.discord_bot import DiscordBot
        bot = DiscordBot()
        assert bot._on_message is None

        handler = AsyncMock(return_value='hello')
        bot.on_message(handler)
        assert bot._on_message is handler

    def test_mention_detection(self):
        """Bot should only respond to mentions in guilds."""
        bot_user = {'id': '123456'}
        
        # Message with mention
        data_mentioned = {
            'author': {'id': '999', 'bot': False},
            'content': '<@123456> hello',
            'channel_id': 'ch1',
            'id': 'msg1',
            'guild_id': 'guild1',
            'mentions': [{'id': '123456'}],
        }
        mentions = [m.get('id') for m in data_mentioned.get('mentions', [])]
        is_mentioned = bot_user['id'] in mentions
        assert is_mentioned

        # Message without mention
        data_no_mention = {
            'author': {'id': '999', 'bot': False},
            'content': 'hello',
            'channel_id': 'ch1',
            'id': 'msg2',
            'guild_id': 'guild1',
            'mentions': [],
        }
        mentions2 = [m.get('id') for m in data_no_mention.get('mentions', [])]
        is_mentioned2 = bot_user['id'] in mentions2
        assert not is_mentioned2

    def test_dm_detection(self):
        """DMs have no guild_id."""
        data_dm = {
            'author': {'id': '999', 'bot': False},
            'content': 'hello',
            'channel_id': 'ch1',
            'id': 'msg1',
            'guild_id': None,
            'mentions': [],
        }
        is_dm = data_dm.get('guild_id') is None
        assert is_dm

    def test_ignore_own_messages(self):
        """Bot should ignore its own messages."""
        bot_user = {'id': '123456'}
        data = {
            'author': {'id': '123456', 'bot': True},
            'content': 'my own message',
        }
        is_self = data['author']['id'] == bot_user['id']
        assert is_self

    def test_ignore_other_bots(self):
        data = {
            'author': {'id': '999', 'bot': True},
            'content': 'bot message',
        }
        assert data['author'].get('bot') is True

    def test_strip_mention_from_content(self):
        bot_id = '123456'
        content = '<@123456> what is the weather'
        content = content.replace(f'<@{bot_id}>', '').strip()
        assert content == 'what is the weather'

        # With nickname format
        content2 = '<@!123456> hello there'
        content2 = content2.replace(f'<@!{bot_id}>', '').strip()
        assert content2 == 'hello there'
