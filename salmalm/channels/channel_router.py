"""SalmAlm Channel Router — Multi-channel message routing."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from salmalm import log

# ── Channel format rules ──
CHANNEL_FORMAT: Dict[str, Dict[str, Any]] = {
    'telegram': {'max_chars': 4096, 'markdown': 'MarkdownV2', 'code_fence': True},
    'discord': {'max_chars': 2000, 'max_lines': 17, 'markdown': 'discord', 'no_tables': True},
    'slack': {'max_chars': 40000, 'markdown': 'mrkdwn', 'no_tables': True},
    'web': {'max_chars': None, 'markdown': 'full'},
    'webhook': {'max_chars': 65536, 'markdown': 'full'},
}

CONFIG_DIR = Path.home() / '.salmalm'
CONFIG_FILE = CONFIG_DIR / 'channels.json'


from salmalm.config_manager import ConfigManager


def _load_config() -> Dict[str, Any]:
    """Load channel configuration from ~/.salmalm/channels.json."""
    return ConfigManager.load('channels')


def _save_config(cfg: Dict[str, Any]) -> None:
    ConfigManager.save('channels', cfg)


def format_for_channel(text: str, channel: str) -> str:
    """Format text according to channel-specific rules."""
    fmt = CHANNEL_FORMAT.get(channel, CHANNEL_FORMAT['web'])

    # Strip tables if channel doesn't support them
    if fmt.get('no_tables'):
        import re  # noqa: F401
        lines = text.split('\n')
        out: List[str] = []
        for line in lines:
            stripped = line.strip()
            # Skip table separator lines like |---|---|
            if stripped.startswith('|') and set(stripped.replace('|', '').replace('-', '').replace(' ', '')) <= {':', ''}:
                continue
            # Convert table rows to bullet points
            if stripped.startswith('|') and stripped.endswith('|'):
                cells = [c.strip() for c in stripped.strip('|').split('|')]
                cells = [c for c in cells if c]
                if cells:
                    out.append('• ' + ' — '.join(cells))
                continue
            out.append(line)
        text = '\n'.join(out)

    # Truncate max lines (discord)
    max_lines = fmt.get('max_lines')
    if max_lines:
        lines = text.split('\n')
        if len(lines) > max_lines:
            text = '\n'.join(lines[:max_lines]) + '\n…(truncated)'

    # Truncate max chars
    max_chars = fmt.get('max_chars')
    if max_chars and len(text) > max_chars:
        text = text[:max_chars - 20] + '\n…(truncated)'

    return text


class ChannelRouter:
    """Routes messages between multiple channels and the agent engine."""

    def __init__(self):
        self._channels: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, Callable] = {}
        self._config = _load_config()

    def register(self, name: str, *, send_fn: Callable, enabled: bool = True,
                 meta: Optional[Dict[str, Any]] = None) -> None:
        """Register a channel for routing."""
        self._channels[name] = {
            'name': name,
            'send_fn': send_fn,
            'enabled': enabled,
            'meta': meta or {},
            'registered_at': time.time(),
        }
        log.info(f'Channel registered: {name}')

    def unregister(self, name: str) -> bool:
        if name in self._channels:
            del self._channels[name]
            return True
        return False

    def set_handler(self, channel: str, handler: Callable) -> None:
        """Set inbound message handler for a channel."""
        self._handlers[channel] = handler

    def get_handler(self, channel: str) -> Optional[Callable]:
        return self._handlers.get(channel)

    @property
    def channels(self) -> Dict[str, Dict[str, Any]]:
        return {k: {kk: vv for kk, vv in v.items() if kk != 'send_fn'}
                for k, v in self._channels.items()}

    def is_enabled(self, name: str) -> bool:
        ch = self._channels.get(name)
        return ch['enabled'] if ch else False

    def _get_response_prefix(self, channel: str, is_group: bool = False) -> str:
        """Get response prefix for channel. Only applied in group chats."""
        if not is_group:
            return ''
        cfg = self._config
        # Per-channel override
        by_ch = cfg.get('byChannel', {})
        if channel in by_ch:
            prefix = by_ch[channel].get('responsePrefix')
            if prefix is not None:
                return prefix
        return cfg.get('responsePrefix', '')

    def route_outbound(self, channel: str, is_group: bool = False, **kwargs) -> bool:
        """Send a message through the specified channel."""
        ch = self._channels.get(channel)
        if not ch or not ch['enabled']:
            log.warning(f'Channel {channel} not available for outbound')
            return False
        try:
            text = kwargs.get('text', '')
            if text:
                prefix = self._get_response_prefix(channel, is_group)
                if prefix:
                    text = prefix + text
                kwargs['text'] = format_for_channel(text, channel)
            ch['send_fn'](**kwargs)
            return True
        except Exception as e:
            log.error(f'Outbound to {channel} failed: {e}')
            return False

    async def route_inbound(self, channel: str, message: Dict[str, Any],
                            process_fn: Optional[Callable] = None) -> Optional[str]:
        """Route an inbound message from a channel to the agent, return response."""
        handler = self._handlers.get(channel) or process_fn
        if not handler:
            log.warning(f'No handler for channel {channel}')
            return None
        try:
            import asyncio
            if asyncio.iscoroutinefunction(handler):
                return await handler(message)
            return handler(message)
        except Exception as e:
            log.error(f'Inbound from {channel} failed: {e}')
            return None

    def list_channels(self) -> List[Dict[str, Any]]:
        """List all registered channels with status."""
        result = []
        for name, ch in self._channels.items():
            result.append({
                'name': name,
                'enabled': ch['enabled'],
                'registered_at': ch['registered_at'],
                'meta': ch['meta'],
            })
        return result

    def save_config(self) -> None:
        """Persist current channel config."""
        cfg = {}
        for name, ch in self._channels.items():
            cfg[name] = {'enabled': ch['enabled'], 'meta': ch['meta']}
        _save_config(cfg)

    def load_config(self) -> None:
        """Load and apply saved config."""
        self._config = _load_config()
        for name, settings in self._config.items():
            if name in self._channels:
                self._channels[name]['enabled'] = settings.get('enabled', True)
                self._channels[name]['meta'] = settings.get('meta', {})


# Singleton
channel_router = ChannelRouter()
