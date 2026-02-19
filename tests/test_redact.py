"""Tests for sensitive data redaction."""
import pytest
from salmalm.security import redact_sensitive, REDACT_PATTERNS


def test_redact_openai_key():
    text = 'API key: sk-abcdefghijklmnopqrstuvwxyz1234567890'
    result = redact_sensitive(text)
    assert 'sk-' not in result
    assert '[REDACTED]' in result


def test_redact_github_token():
    text = 'Token: ghp_abcdefghijklmnopqrstuvwxyz1234567890'
    result = redact_sensitive(text)
    assert 'ghp_' not in result
    assert '[REDACTED]' in result


def test_redact_slack_token():
    text = 'Bot: xoxb-123-456-abcdef'
    result = redact_sensitive(text)
    assert 'xoxb-' not in result


def test_redact_telegram_token():
    text = 'Bot: 123456789:AAabcdefghij_klmnopqrstu-vwxyz12345'
    result = redact_sensitive(text)
    assert ':AA' not in result


def test_redact_password():
    text = 'password: mysecretpass123'
    result = redact_sensitive(text)
    assert 'mysecretpass' not in result


def test_redact_jwt():
    text = 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature'
    result = redact_sensitive(text)
    assert 'eyJ' not in result


def test_redact_preserves_normal_text():
    text = 'Hello, this is a normal message with no secrets.'
    result = redact_sensitive(text)
    assert result == text


def test_redact_none_and_empty():
    assert redact_sensitive('') == ''
    assert redact_sensitive(None) is None
