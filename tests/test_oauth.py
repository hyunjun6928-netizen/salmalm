"""Tests for oauth.py — OAuth subscription authentication."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from salmalm.web.oauth import (
    AnthropicOAuth, OpenAIOAuth, OAuthManager,
    _encrypt_tokens, _decrypt_tokens, _xor_bytes,
)


class TestXorObfuscation:
    def test_roundtrip(self):
        data = {'access_token': 'sk-test-123', 'refresh_token': 'rt-456'}
        encrypted = _encrypt_tokens(data)
        assert isinstance(encrypted, str)
        decrypted = _decrypt_tokens(encrypted)
        assert decrypted == data

    def test_xor_roundtrip(self):
        key = b'secret'
        data = b'hello world'
        assert _xor_bytes(_xor_bytes(data, key), key) == data


class TestAnthropicOAuth:
    def test_get_auth_url(self):
        oauth = AnthropicOAuth(client_id='test-id')
        url = oauth.get_auth_url('http://localhost/callback', state='abc')
        assert 'console.anthropic.com' in url
        assert 'test-id' in url
        assert 'abc' in url

    def test_get_auth_url_auto_state(self):
        oauth = AnthropicOAuth(client_id='test-id')
        url = oauth.get_auth_url('http://localhost/callback')
        assert 'state=' in url

    def test_is_expired_true(self):
        td = {'obtained_at': time.time() - 7200, 'expires_in': 3600}
        assert AnthropicOAuth.is_expired(td) is True

    def test_is_expired_false(self):
        td = {'obtained_at': time.time(), 'expires_in': 3600}
        assert AnthropicOAuth.is_expired(td) is False

    def test_is_expiring_soon(self):
        td = {'obtained_at': time.time() - 3000, 'expires_in': 3600}
        assert AnthropicOAuth.is_expiring_soon(td, threshold=700) is True

    def test_not_expiring_soon(self):
        td = {'obtained_at': time.time(), 'expires_in': 3600}
        assert AnthropicOAuth.is_expiring_soon(td, threshold=100) is False


class TestOpenAIOAuth:
    def test_get_auth_url(self):
        oauth = OpenAIOAuth(client_id='oi-test')
        url = oauth.get_auth_url('http://localhost/cb', state='xyz')
        assert 'auth.openai.com' in url
        assert 'oi-test' in url

    def test_is_expired(self):
        td = {'obtained_at': time.time() - 7200, 'expires_in': 3600}
        assert OpenAIOAuth.is_expired(td) is True


class TestOAuthManager:
    @pytest.fixture
    def manager(self, tmp_path):
        with patch('salmalm.web.oauth._TOKENS_PATH', tmp_path / 'tokens.json'), \
             patch('salmalm.web.oauth._CONFIG_DIR', tmp_path):
            mgr = OAuthManager()
            yield mgr

    def test_status_empty(self, manager):
        result = manager.status()
        assert 'No OAuth tokens' in result

    def test_setup_anthropic(self, manager):
        result = manager.setup('anthropic')
        assert 'http' in result.lower() or 'URL' in result or 'url' in result.lower()
        assert 'anthropic.com' in result

    def test_setup_openai(self, manager):
        result = manager.setup('openai')
        assert 'openai.com' in result

    def test_setup_unknown(self, manager):
        result = manager.setup('unknown')
        assert '❌' in result

    def test_revoke(self, manager):
        manager._tokens = {'anthropic': {'access_token': 'x'}}
        with patch('salmalm.web.oauth._TOKENS_PATH') as mp:
            mp.exists.return_value = False
            result = manager.revoke()
        assert 'revoked' in result.lower()
        assert not manager._tokens

    def test_get_token_none(self, manager):
        assert manager.get_token('anthropic') is None

    def test_get_token_exists(self, manager):
        manager._tokens = {
            'anthropic': {
                'access_token': 'test-token',
                'obtained_at': time.time(),
                'expires_in': 3600,
            }
        }
        assert manager.get_token('anthropic') == 'test-token'

    def test_handle_callback_invalid_state(self, manager):
        result = manager.handle_callback('code', 'bad-state')
        assert '❌' in result

    def test_api_status_empty(self, manager):
        result = manager.get_api_status()
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_api_status_with_token(self, manager):
        manager._tokens = {
            'anthropic': {
                'access_token': 'x',
                'obtained_at': time.time(),
                'expires_in': 3600,
            }
        }
        result = manager.get_api_status()
        assert 'anthropic' in result
        assert result['anthropic']['has_token'] is True
