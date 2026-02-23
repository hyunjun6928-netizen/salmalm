"""Tests for commands.py — extended slash command router."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from salmalm.features.commands import (
    ALIASES, COMMAND_DEFS, CommandRouter, DIRECTIVE_COMMANDS,
    INLINE_SHORTCUTS, TELEGRAM_COMMANDS, get_router, _runtime_overrides,
)


@pytest.fixture
def router():
    return CommandRouter()


@pytest.fixture
def session():
    s = MagicMock()
    s.user_id = 'test-user-123'
    s.session_id = 'sess-001'
    s.messages = []
    return s


def _run(coro):
    return asyncio.run(coro)


class TestCommandRouter:
    def test_help(self, router, session):
        result = _run(router.dispatch('/help', session))
        assert 'SalmAlm Commands' in result

    def test_commands_list(self, router, session):
        result = _run(router.dispatch('/commands', session))
        assert '/help' in result
        assert '/status' in result

    def test_whoami(self, router, session):
        result = _run(router.dispatch('/whoami', session))
        assert 'test-user-123' in result

    def test_whoami_alias_id(self, router, session):
        result = _run(router.dispatch('/id', session))
        assert 'test-user-123' in result

    def test_reset(self, router, session):
        session.messages = [{'role': 'user', 'content': 'hi'}]
        result = _run(router.dispatch('/reset', session))
        assert 'reset' in result.lower()
        assert session.messages == []

    def test_new_session(self, router, session):
        result = _run(router.dispatch('/new claude-4', session))
        assert 'New session' in result
        assert 'claude-4' in result

    def test_stop(self, router, session):
        result = _run(router.dispatch('/stop', session))
        assert 'Stop' in result

    def test_debug_show_empty(self, router, session):
        _runtime_overrides.clear()
        result = _run(router.dispatch('/debug show', session))
        assert 'No runtime overrides' in result

    def test_debug_set_and_show(self, router, session):
        _runtime_overrides.clear()
        _run(router.dispatch('/debug set foo bar', session))
        result = _run(router.dispatch('/debug show', session))
        assert 'foo' in result
        assert 'bar' in result
        _runtime_overrides.clear()

    def test_debug_unset(self, router, session):
        _runtime_overrides['x'] = '1'
        _run(router.dispatch('/debug unset x', session))
        assert 'x' not in _runtime_overrides
        _runtime_overrides.clear()

    def test_debug_reset(self, router, session):
        _runtime_overrides['a'] = '1'
        _run(router.dispatch('/debug reset', session))
        assert len(_runtime_overrides) == 0

    def test_config_show_empty(self, router, session):
        with patch('salmalm.features.commands._CONFIG_PATH', Path(tempfile.mktemp())):
            result = _run(router.dispatch('/config show', session))
            assert 'empty' in result.lower() or 'Config' in result

    def test_config_set_get(self, router, session):
        tmp = Path(tempfile.mktemp())
        with patch('salmalm.features.commands._CONFIG_PATH', tmp):
            _run(router.dispatch('/config set mykey myval', session))
            result = _run(router.dispatch('/config get mykey', session))
            assert 'myval' in result
        tmp.unlink(missing_ok=True)

    def test_think_levels(self, router, session):
        for level in ('off', 'low', 'medium', 'high'):
            result = _run(router.dispatch(f'/think {level}', session))
            assert level in result

    def test_think_colon_syntax(self, router, session):
        result = _run(router.dispatch('/think: high', session))
        assert 'high' in result

    def test_verbose(self, router, session):
        result = _run(router.dispatch('/verbose full', session))
        assert 'full' in result

    def test_reasoning(self, router, session):
        result = _run(router.dispatch('/reasoning stream', session))
        assert 'stream' in result

    def test_dock(self, router, session):
        result = _run(router.dispatch('/dock telegram', session))
        assert 'telegram' in result

    def test_dock_invalid(self, router, session):
        result = _run(router.dispatch('/dock invalid', session))
        assert 'Usage' in result

    def test_send_toggle(self, router, session):
        result = _run(router.dispatch('/send on', session))
        assert 'on' in result

    def test_activation(self, router, session):
        result = _run(router.dispatch('/activation mention', session))
        assert 'mention' in result

    def test_allowlist_empty(self, router, session):
        with patch('salmalm.features.commands._CONFIG_DIR', Path(tempfile.mkdtemp())):
            result = _run(router.dispatch('/allowlist list', session))
            assert 'empty' in result.lower() or 'Allowlist' in result

    def test_bash_empty(self, router, session):
        result = _run(router.dispatch('/bash ', session))
        assert 'Usage' in result

    def test_bash_echo(self, router, session):
        with patch('salmalm.features.commands.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='hello', stderr='', returncode=0)
            result = _run(router.dispatch('/bash echo hello', session))
            assert 'hello' in result

    def test_skill(self, router, session):
        result = _run(router.dispatch('/skill myskill some input', session))
        assert 'myskill' in result

    def test_unknown_command_returns_none(self, router, session):
        result = _run(router.dispatch('/nonexistent_xyz', session))
        assert result is None

    def test_not_a_command(self, router, session):
        result = _run(router.dispatch('hello world', session))
        assert result is None


class TestDirectiveParsing:
    def test_parse_think_directive(self, router):
        text, dirs = router.parse_directives('/think high Tell me about cats')
        assert dirs.get('/think') == 'high'
        assert 'Tell me about cats' in text

    def test_parse_verbose_directive(self, router):
        text, dirs = router.parse_directives('/verbose on Hello')
        assert dirs.get('/verbose') == 'on'

    def test_parse_colon_directive(self, router):
        text, dirs = router.parse_directives('/think: medium hey')
        assert dirs.get('/think') == 'medium'


class TestInlineShortcuts:
    def test_find_inline(self, router):
        found = router.find_inline_shortcuts('Can you /help me?')
        assert '/help' in found

    def test_no_inline(self, router):
        found = router.find_inline_shortcuts('Hello world')
        assert found == []


class TestCompletions:
    def test_completions_list(self, router):
        comps = router.get_completions()
        assert len(comps) > 20
        names = [c['command'] for c in comps]
        assert '/help' in names
        assert '/think' in names


class TestTelegramCommands:
    def test_telegram_commands_count(self):
        assert len(TELEGRAM_COMMANDS) >= 15

    def test_telegram_commands_format(self):
        for cmd, desc in TELEGRAM_COMMANDS:
            assert isinstance(cmd, str)
            assert isinstance(desc, str)
            assert not cmd.startswith('/')


class TestSingleton:
    def test_get_router(self):
        import salmalm.features.commands as mod
        mod._router = None
        r = get_router()
        assert isinstance(r, CommandRouter)
        r2 = get_router()
        assert r is r2
        mod._router = None
