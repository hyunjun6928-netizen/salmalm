"""SalmAlm Reaction Tools — Send emoji reactions across channels."""
from __future__ import annotations

import json, urllib.request
from typing import Any, Dict, Optional

from salmalm import log


def send_reaction(channel: str, message_id: str, emoji: str, *,
                  chat_id: Optional[str] = None,
                  channel_id: Optional[str] = None,
                  config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Send an emoji reaction to a message.

    Args:
        channel: Channel type ('telegram', 'discord', 'slack', 'web')
        message_id: Message identifier
        emoji: Emoji to react with (e.g. '👍', ':thumbsup:')
        chat_id: Telegram chat ID
        channel_id: Discord/Slack channel ID
        config: Channel-specific config (tokens etc)

    Returns:
        Result dict with 'ok' status.
    """
    config = config or {}

    if channel == 'telegram':
        return _react_telegram(chat_id or '', message_id, emoji, config)
    elif channel == 'discord':
        return _react_discord(channel_id or '', message_id, emoji, config)
    elif channel == 'slack':
        return _react_slack(channel_id or '', message_id, emoji, config)
    elif channel == 'web':
        return _react_web(message_id, emoji, config)
    else:
        return {'ok': False, 'error': f'Unsupported channel: {channel}'}


def _react_telegram(chat_id: str, message_id: str, emoji: str,
                    config: Dict[str, Any]) -> Dict[str, Any]:
    """Send reaction via Telegram setMessageReaction API."""
    token = config.get('token', '')
    if not token:
        return {'ok': False, 'error': 'No Telegram token'}

    url = f'https://api.telegram.org/bot{token}/setMessageReaction'
    data = json.dumps({
        'chat_id': chat_id,
        'message_id': int(message_id),
        'reaction': [{'type': 'emoji', 'emoji': emoji}],
        'is_big': False,
    }).encode()
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return {'ok': result.get('ok', False), 'result': result}
    except Exception as e:
        log.error(f'Telegram reaction error: {e}')
        return {'ok': False, 'error': str(e)}


def _react_discord(channel_id: str, message_id: str, emoji: str,
                   config: Dict[str, Any]) -> Dict[str, Any]:
    """Send reaction via Discord addReaction API."""
    token = config.get('token', '')
    if not token:
        return {'ok': False, 'error': 'No Discord token'}

    import urllib.parse
    encoded_emoji = urllib.parse.quote(emoji)
    url = f'https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me'
    req = urllib.request.Request(url, method='PUT')
    req.add_header('Authorization', f'Bot {token}')
    req.add_header('Content-Length', '0')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {'ok': True}
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8', errors='replace')
        log.error(f'Discord reaction error: {e.code} {err[:200]}')
        return {'ok': False, 'error': f'{e.code}: {err[:200]}'}
    except Exception as e:
        log.error(f'Discord reaction error: {e}')
        return {'ok': False, 'error': str(e)}


def _react_slack(channel_id: str, timestamp: str, emoji: str,
                 config: Dict[str, Any]) -> Dict[str, Any]:
    """Send reaction via Slack reactions.add API."""
    token = config.get('token', '')
    if not token:
        return {'ok': False, 'error': 'No Slack token'}

    url = 'https://slack.com/api/reactions.add'
    data = json.dumps({
        'channel': channel_id,
        'timestamp': timestamp,
        'name': emoji.strip(':'),
    }).encode()
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return {'ok': result.get('ok', False), 'error': result.get('error')}
    except Exception as e:
        log.error(f'Slack reaction error: {e}')
        return {'ok': False, 'error': str(e)}


def _react_web(message_id: str, emoji: str,
               config: Dict[str, Any]) -> Dict[str, Any]:
    """Queue a reaction event for WebSocket delivery."""
    # Web reactions are dispatched via WS broadcast
    ws_broadcast = config.get('ws_broadcast')
    if ws_broadcast and callable(ws_broadcast):
        ws_broadcast({
            'type': 'reaction',
            'messageId': message_id,
            'emoji': emoji,
        })
        return {'ok': True}
    return {'ok': True, 'queued': True}


# ── Tool definition for engine registration ──

REACTION_TOOL = {
    'type': 'function',
    'function': {
        'name': 'send_reaction',
        'description': 'React to a message with an emoji. Works across Telegram, Discord, Slack, and web.',
        'parameters': {
            'type': 'object',
            'properties': {
                'emoji': {
                    'type': 'string',
                    'description': 'Emoji to react with (e.g. 👍, ❤️, 😂)',
                },
                'message_id': {
                    'type': 'string',
                    'description': 'ID of the message to react to',
                },
                'channel': {
                    'type': 'string',
                    'description': 'Channel type (telegram, discord, slack, web)',
                    'enum': ['telegram', 'discord', 'slack', 'web'],
                },
            },
            'required': ['emoji'],
        },
    },
}
