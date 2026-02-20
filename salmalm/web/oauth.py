"""OAuth subscription authentication for Anthropic and OpenAI.

stdlib-only. Token storage uses simple XOR obfuscation (AES-256 would require
a third-party library; we stay stdlib-only and note that real deployments should
use OS keyring or proper encryption).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional

from salmalm.utils.http import request as _http_request

log = logging.getLogger(__name__)

_CONFIG_DIR = Path.home() / '.salmalm'
_TOKENS_PATH = _CONFIG_DIR / 'oauth_tokens.json'
_OBFUSCATION_KEY = hashlib.sha256(
    (os.environ.get('SALMALM_SECRET', 'salmalm-default-key')).encode()
).digest()


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    """Simple XOR obfuscation (NOT real encryption — stdlib constraint)."""
    return bytes(d ^ key[i % len(key)] for i, d in enumerate(data))


def _encrypt_tokens(data: dict) -> str:
    raw = json.dumps(data).encode()
    return base64.b64encode(_xor_bytes(raw, _OBFUSCATION_KEY)).decode()


def _decrypt_tokens(encoded: str) -> dict:
    raw = _xor_bytes(base64.b64decode(encoded), _OBFUSCATION_KEY)
    return json.loads(raw)


class AnthropicOAuth:
    AUTH_URL = 'https://console.anthropic.com/oauth/authorize'
    TOKEN_URL = 'https://console.anthropic.com/oauth/token'

    def __init__(self, client_id: str = '', client_secret: str = ''):
        self.client_id = client_id or os.environ.get('ANTHROPIC_OAUTH_CLIENT_ID', '')
        self.client_secret = client_secret or os.environ.get('ANTHROPIC_OAUTH_CLIENT_SECRET', '')

    def get_auth_url(self, redirect_uri: str, state: str = '') -> str:
        if not state:
            state = secrets.token_urlsafe(16)
        params = urllib.parse.urlencode({
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'state': state,
            'scope': 'api',
        })
        return f'{self.AUTH_URL}?{params}'

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        data = urllib.parse.urlencode({
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }).encode()
        result = json.loads(_http_request(
            self.TOKEN_URL, data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        ))
        result['obtained_at'] = time.time()
        return result

    def refresh_token(self, refresh_token: str) -> dict:
        data = urllib.parse.urlencode({
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }).encode()
        result = json.loads(_http_request(
            self.TOKEN_URL, data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        ))
        result['obtained_at'] = time.time()
        return result

    @staticmethod
    def is_expired(token_data: dict) -> bool:
        obtained = token_data.get('obtained_at', 0)
        expires_in = token_data.get('expires_in', 3600)
        return time.time() > obtained + expires_in

    @staticmethod
    def is_expiring_soon(token_data: dict, threshold: int = 86400) -> bool:
        obtained = token_data.get('obtained_at', 0)
        expires_in = token_data.get('expires_in', 3600)
        return time.time() > obtained + expires_in - threshold

    def auto_refresh(self, token_data: dict) -> dict:
        if self.is_expiring_soon(token_data) and token_data.get('refresh_token'):
            try:
                return self.refresh_token(token_data['refresh_token'])
            except Exception as e:
                log.warning(f'Auto-refresh failed: {e}')
        return token_data


class OpenAIOAuth:
    AUTH_URL = 'https://auth.openai.com/authorize'
    TOKEN_URL = 'https://auth.openai.com/oauth/token'

    def __init__(self, client_id: str = '', client_secret: str = ''):
        self.client_id = client_id or os.environ.get('OPENAI_OAUTH_CLIENT_ID', '')
        self.client_secret = client_secret or os.environ.get('OPENAI_OAUTH_CLIENT_SECRET', '')

    def get_auth_url(self, redirect_uri: str, state: str = '') -> str:
        if not state:
            state = secrets.token_urlsafe(16)
        params = urllib.parse.urlencode({
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'state': state,
            'scope': 'openai.api',
        })
        return f'{self.AUTH_URL}?{params}'

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        data = urllib.parse.urlencode({
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }).encode()
        result = json.loads(_http_request(
            self.TOKEN_URL, data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        ))
        result['obtained_at'] = time.time()
        return result

    def refresh_token(self, refresh_token: str) -> dict:
        data = urllib.parse.urlencode({
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }).encode()
        result = json.loads(_http_request(
            self.TOKEN_URL, data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        ))
        result['obtained_at'] = time.time()
        return result

    @staticmethod
    def is_expired(token_data: dict) -> bool:
        obtained = token_data.get('obtained_at', 0)
        expires_in = token_data.get('expires_in', 3600)
        return time.time() > obtained + expires_in


class OAuthManager:
    """Manages OAuth tokens for multiple providers."""

    def __init__(self):
        self.anthropic = AnthropicOAuth()
        self.openai = OpenAIOAuth()
        self._tokens: Dict[str, dict] = {}
        self._pending_states: Dict[str, str] = {}  # state -> provider
        self._load()

    def _load(self):
        try:
            if _TOKENS_PATH.exists():
                encrypted = _TOKENS_PATH.read_text().strip()
                if encrypted:
                    self._tokens = _decrypt_tokens(encrypted)
        except Exception as e:
            log.warning(f'Failed to load OAuth tokens: {e}')
            self._tokens = {}

    def _save(self):
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _TOKENS_PATH.write_text(_encrypt_tokens(self._tokens))

    def setup(self, provider: str, redirect_uri: str = 'http://localhost:8080/oauth/callback') -> str:
        state = secrets.token_urlsafe(16)
        self._pending_states[state] = provider
        if provider == 'anthropic':
            url = self.anthropic.get_auth_url(redirect_uri, state)
        elif provider == 'openai':
            url = self.openai.get_auth_url(redirect_uri, state)
        else:
            return f'❌ Unknown provider: {provider}. Use anthropic|openai.'
        return f'🔑 Open this URL to authorize:\n{url}'

    def handle_callback(self, code: str, state: str,
                        redirect_uri: str = 'http://localhost:8080/oauth/callback') -> str:
        provider = self._pending_states.pop(state, None)
        if not provider:
            return '❌ Invalid or expired OAuth state.'
        try:
            if provider == 'anthropic':
                token_data = self.anthropic.exchange_code(code, redirect_uri)
            elif provider == 'openai':
                token_data = self.openai.exchange_code(code, redirect_uri)
            else:
                return '❌ Unknown provider.'
            self._tokens[provider] = token_data
            self._save()
            return f'✅ {provider.capitalize()} OAuth authorized successfully.'
        except Exception as e:
            return f'❌ Token exchange failed: {e}'

    def status(self) -> str:
        if not self._tokens:
            return '🔑 No OAuth tokens configured. Use `/oauth setup anthropic|openai`.'
        lines = ['🔑 **OAuth Status:**']
        for provider, td in self._tokens.items():
            obtained = td.get('obtained_at', 0)
            expires_in = td.get('expires_in', 0)
            expires_at = obtained + expires_in
            remaining = max(0, expires_at - time.time())
            hours = remaining / 3600
            status = '✅ Valid' if remaining > 0 else '❌ Expired'
            lines.append(f'  **{provider}**: {status} ({hours:.1f}h remaining)')
        return '\n'.join(lines)

    def revoke(self, provider: str = '') -> str:
        if provider:
            self._tokens.pop(provider, None)
        else:
            self._tokens.clear()
        self._save()
        target = provider or 'all'
        return f'🗑️ OAuth tokens revoked ({target}).'

    def refresh(self, provider: str = '') -> str:
        providers = [provider] if provider else list(self._tokens.keys())
        results = []
        for p in providers:
            td = self._tokens.get(p)
            if not td or not td.get('refresh_token'):
                results.append(f'  {p}: no refresh token')
                continue
            try:
                if p == 'anthropic':
                    new_td = self.anthropic.refresh_token(td['refresh_token'])
                elif p == 'openai':
                    new_td = self.openai.refresh_token(td['refresh_token'])
                else:
                    continue
                self._tokens[p] = new_td
                results.append(f'  {p}: ✅ refreshed')
            except Exception as e:
                results.append(f'  {p}: ❌ {e}')
        self._save()
        return '🔄 **Token refresh:**\n' + '\n'.join(results)

    def get_token(self, provider: str) -> Optional[str]:
        """Get access token for provider, auto-refreshing if needed."""
        td = self._tokens.get(provider)
        if not td:
            return None
        if provider == 'anthropic':
            td = self.anthropic.auto_refresh(td)
            self._tokens[provider] = td
            self._save()
        if provider == 'openai' and OpenAIOAuth.is_expired(td):
            return None
        return td.get('access_token')

    def get_api_status(self) -> dict:
        """Return status dict for /api/oauth/status."""
        result = {}
        for provider, td in self._tokens.items():
            obtained = td.get('obtained_at', 0)
            expires_in = td.get('expires_in', 0)
            result[provider] = {
                'has_token': bool(td.get('access_token')),
                'expires_at': obtained + expires_in,
                'expired': time.time() > obtained + expires_in,
            }
        return result


# Singleton
oauth_manager = OAuthManager()
