"""Tests for Anthropic prompt caching, /context, /usage, cost estimation."""

import json
import sys
import os
import time
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ── 1. Cache marking structure ──

def test_anthropic_system_prompt_cache_marking():
    """System prompt must use content array with cache_control."""
    from salmalm.llm import _call_anthropic
    # We can't call the real API, but we can verify the body structure
    # by intercepting _http_post
    captured = {}

    def fake_http_post(url, headers, body, timeout=120):
        captured['body'] = body
        captured['headers'] = headers
        return {
            'content': [{'type': 'text', 'text': 'ok'}],
            'usage': {'input_tokens': 10, 'output_tokens': 5}
        }

    with patch('salmalm.llm._http_post', fake_http_post):
        messages = [
            {'role': 'system', 'content': 'You are helpful.'},
            {'role': 'user', 'content': 'hi'}
        ]
        _call_anthropic('fake-key', 'claude-sonnet-4-20250514', messages, None, 1024)

    # System must be array with cache_control
    sys_block = captured['body']['system']
    assert isinstance(sys_block, list), "system must be a list"
    assert sys_block[0]['type'] == 'text'
    assert sys_block[0]['cache_control'] == {'type': 'ephemeral'}


def test_anthropic_beta_header():
    """Anthropic API calls must include prompt-caching beta header."""
    captured = {}

    def fake_http_post(url, headers, body, timeout=120):
        captured['headers'] = headers
        return {
            'content': [{'type': 'text', 'text': 'ok'}],
            'usage': {'input_tokens': 10, 'output_tokens': 5}
        }

    with patch('salmalm.llm._http_post', fake_http_post):
        from salmalm.llm import _call_anthropic
        messages = [{'role': 'user', 'content': 'hi'}]
        _call_anthropic('fake-key', 'claude-sonnet-4-20250514', messages, None, 1024)

    assert 'anthropic-beta' in captured['headers']
    assert 'prompt-caching' in captured['headers']['anthropic-beta']


def test_tool_schema_cache_marking():
    """Last tool in tools list must have cache_control."""
    captured = {}

    def fake_http_post(url, headers, body, timeout=120):
        captured['body'] = body
        return {
            'content': [{'type': 'text', 'text': 'ok'}],
            'usage': {'input_tokens': 10, 'output_tokens': 5}
        }

    with patch('salmalm.llm._http_post', fake_http_post):
        from salmalm.llm import _call_anthropic
        tools = [
            {'name': 'tool_a', 'description': 'A', 'input_schema': {}},
            {'name': 'tool_b', 'description': 'B', 'input_schema': {}},
        ]
        messages = [{'role': 'user', 'content': 'hi'}]
        _call_anthropic('fake-key', 'claude-sonnet-4-20250514', messages, tools, 1024)

    sent_tools = captured['body']['tools']
    # Last tool must have cache_control
    assert sent_tools[-1].get('cache_control') == {'type': 'ephemeral'}
    # First tool must NOT have cache_control
    assert 'cache_control' not in sent_tools[0]


# ── 2. Time injection cache stability ──

def test_system_prompt_no_exact_time():
    """System prompt must NOT contain exact time (would break cache)."""
    from salmalm.prompt import build_system_prompt
    prompt = build_system_prompt(full=False)
    # Should NOT have minute-level time like "2026-02-20 03:40"
    import re
    time_pattern = re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}')
    # Check that "Current: YYYY-MM-DD HH:MM" is NOT present
    assert 'Current:' not in prompt or not time_pattern.search(prompt), \
        "System prompt should not contain exact time"


def test_system_prompt_has_timezone():
    """System prompt must include timezone info."""
    from salmalm.prompt import build_system_prompt
    prompt = build_system_prompt(full=False)
    assert 'Asia/Seoul' in prompt or 'KST' in prompt


def test_system_prompt_stable_across_calls():
    """Two consecutive calls should produce identical prompts (cache-friendly)."""
    from salmalm.prompt import build_system_prompt
    p1 = build_system_prompt(full=False)
    p2 = build_system_prompt(full=False)
    assert p1 == p2, "System prompt must be stable (no time changes)"


# ── 3. /context output format ──

def test_context_command_output():
    """Test /context command produces expected format."""
    from salmalm.engine import _cmd_context

    class FakeSession:
        messages = [
            {'role': 'system', 'content': 'You are helpful.'},
            {'role': 'user', 'content': 'Hello there!'},
        ]

    result = _cmd_context('/context', FakeSession())
    assert 'Context Window Usage' in result
    assert 'System Prompt' in result
    assert 'Tool Schemas' in result
    assert 'Conversation' in result


def test_context_detail_command():
    """Test /context detail includes file and tool breakdown."""
    from salmalm.engine import _cmd_context

    class FakeSession:
        messages = [{'role': 'user', 'content': 'hi'}]

    result = _cmd_context('/context detail', FakeSession())
    assert 'Injected Files' in result or 'Tool Schemas' in result


# ── 4. /usage mode switching ──

def test_usage_modes():
    """Test /usage command mode switching."""
    from salmalm.engine import _cmd_usage, _session_usage

    class FakeSession:
        messages = []

    # Clean state
    _session_usage.pop('test_usage', None)

    result = _cmd_usage('/usage tokens', FakeSession(), session_id='test_usage')
    assert 'tokens' in result.lower()

    result = _cmd_usage('/usage off', FakeSession(), session_id='test_usage')
    assert 'OFF' in result

    result = _cmd_usage('/usage full', FakeSession(), session_id='test_usage')
    assert 'full' in result.lower() or 'Usage' in result

    result = _cmd_usage('/usage cost', FakeSession(), session_id='test_usage')
    assert 'Cost' in result or 'cost' in result


# ── 5. Cost calculation accuracy ──

def test_cost_estimation_opus():
    """Test cost estimation for Opus model."""
    from salmalm.engine import estimate_cost
    usage = {'input': 1_000_000, 'output': 100_000,
             'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0}
    cost = estimate_cost('anthropic/claude-opus-4-6', usage)
    # input: 1M * $15/M = $15, output: 100K * $75/M = $7.5
    assert abs(cost - 22.5) < 0.01, f"Expected ~$22.5, got ${cost}"


def test_cost_estimation_with_cache():
    """Test cost estimation with cache read tokens."""
    from salmalm.engine import estimate_cost
    usage = {'input': 100_000, 'output': 10_000,
             'cache_creation_input_tokens': 0,
             'cache_read_input_tokens': 80_000}
    cost = estimate_cost('anthropic/claude-sonnet-4-20250514', usage)
    # regular input: (100K - 80K) = 20K * $3/M = $0.06
    # cache_read: 80K * $0.3/M = $0.024
    # output: 10K * $15/M = $0.15
    expected = 0.06 + 0.024 + 0.15
    assert abs(cost - expected) < 0.001, f"Expected ~${expected}, got ${cost}"


def test_cost_estimation_haiku():
    """Test cost estimation for Haiku."""
    from salmalm.engine import estimate_cost
    usage = {'input': 500_000, 'output': 50_000,
             'cache_creation_input_tokens': 100_000,
             'cache_read_input_tokens': 0}
    cost = estimate_cost('claude-haiku-4-5', usage)
    # regular: (500K - 100K) * $1.0/M = $0.40
    # cache_write: 100K * $1.25/M = $0.125
    # output: 50K * $5.0/M = $0.25
    expected = 0.40 + 0.125 + 0.25
    assert abs(cost - expected) < 0.001, f"Expected ~${expected}, got ${cost}"


# ── 6. TTL-based pruning ──

def test_ttl_prune_fresh_cache():
    """Should NOT prune when cache is fresh (within TTL)."""
    import salmalm.core.session_manager as sm
    sm._last_api_call_time = time.time()  # Just called
    assert not sm._should_prune_for_cache()


def test_ttl_prune_expired_cache():
    """Should prune when cache TTL expired."""
    import salmalm.core.session_manager as sm
    sm._last_api_call_time = time.time() - 600  # 10 min ago
    assert sm._should_prune_for_cache()


def test_ttl_prune_never_called():
    """Should prune on first call (no previous API call)."""
    import salmalm.core.session_manager as sm
    sm._last_api_call_time = 0.0
    assert sm._should_prune_for_cache()


# ── 7. Token estimation ──

def test_token_estimation_english():
    """English text: ~len/4 tokens."""
    from salmalm.engine import estimate_tokens
    text = "Hello world, this is a test of token estimation."
    tokens = estimate_tokens(text)
    assert abs(tokens - len(text) / 4) < 2


def test_token_estimation_korean():
    """Korean text: ~len/2 tokens."""
    from salmalm.engine import estimate_tokens
    text = "안녕하세요 이것은 토큰 추정 테스트입니다"
    tokens = estimate_tokens(text)
    assert abs(tokens - len(text) / 2) < 2


# ── 8. Cache warmer config ──

def test_cache_config_defaults():
    """Default cache config should be sensible."""
    from salmalm.heartbeat import _DEFAULT_CONFIG
    assert _DEFAULT_CONFIG['promptCaching'] is True
    assert _DEFAULT_CONFIG['cacheTtlMinutes'] == 60
    assert _DEFAULT_CONFIG['warmingEnabled'] is True
    assert _DEFAULT_CONFIG['warmingIntervalMinutes'] == 55


# ── 9. Usage recording ──

def test_record_response_usage():
    """Test per-response usage recording."""
    from salmalm.engine import record_response_usage, _get_session_usage, _session_usage

    _session_usage.pop('test_record', None)
    record_response_usage('test_record', 'anthropic/claude-sonnet-4-20250514', {
        'input': 1000, 'output': 500,
        'cache_creation_input_tokens': 0,
        'cache_read_input_tokens': 0,
    })
    su = _get_session_usage('test_record')
    assert len(su['responses']) == 1
    assert su['responses'][0]['input'] == 1000
    assert su['total_cost'] > 0


# ── 10. Streaming cache headers ──

def test_streaming_has_cache_headers():
    """Streaming path must include prompt-caching beta header."""
    from salmalm.llm import stream_anthropic
    # We'll patch urlopen to capture the request
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured['headers'] = dict(req.headers)
        captured['body'] = json.loads(req.data.decode('utf-8'))
        raise Exception("stop here")

    with patch('urllib.request.urlopen', fake_urlopen):
        with patch('salmalm.llm.vault') as mock_vault:
            mock_vault.get.return_value = 'fake-key'
            try:
                for _ in stream_anthropic(
                    [{'role': 'system', 'content': 'test'}, {'role': 'user', 'content': 'hi'}],
                    model='anthropic/claude-sonnet-4-20250514'
                ):
                    pass
            except Exception:
                pass

    assert 'Anthropic-beta' in captured.get('headers', {}) or \
           'anthropic-beta' in captured.get('headers', {}), \
           f"Missing beta header. Headers: {captured.get('headers', {})}"
    # System must be array
    body = captured.get('body', {})
    assert isinstance(body.get('system'), list), "Streaming: system must be array with cache_control"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
