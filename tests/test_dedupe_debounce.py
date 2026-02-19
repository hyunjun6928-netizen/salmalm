"""Tests for message deduplication and channel-aware debouncing."""
import time
import pytest
from salmalm.dedup import (
    MessageDeduplicator, message_deduplicator,
    get_debounce_ms, should_skip_debounce,
    CHANNEL_DEBOUNCE_MS,
)


def test_dedup_basic():
    d = MessageDeduplicator(ttl=5.0)
    assert not d.is_duplicate('tg', 'acc1', 'peer1', 'msg1')
    assert d.is_duplicate('tg', 'acc1', 'peer1', 'msg1')


def test_dedup_different_keys():
    d = MessageDeduplicator(ttl=5.0)
    assert not d.is_duplicate('tg', 'acc1', 'peer1', 'msg1')
    assert not d.is_duplicate('tg', 'acc1', 'peer1', 'msg2')
    assert not d.is_duplicate('discord', 'acc1', 'peer1', 'msg1')


def test_dedup_ttl_expiry():
    d = MessageDeduplicator(ttl=0.1)
    assert not d.is_duplicate('tg', 'a', 'p', 'm1')
    time.sleep(0.15)
    # Force cleanup
    d._last_cleanup = 0
    assert not d.is_duplicate('tg', 'a', 'p', 'm1')


def test_dedup_clear():
    d = MessageDeduplicator()
    d.is_duplicate('tg', 'a', 'p', 'm1')
    assert d.size > 0
    d.clear()
    assert d.size == 0


def test_debounce_channel_times():
    assert get_debounce_ms('telegram') == 2000
    assert get_debounce_ms('whatsapp') == 5000
    assert get_debounce_ms('web') == 1000
    assert get_debounce_ms('unknown') == 1000


def test_skip_debounce_media():
    assert should_skip_debounce('hello', has_media=True)
    assert not should_skip_debounce('hello', has_media=False)


def test_skip_debounce_command():
    assert should_skip_debounce('/help')
    assert should_skip_debounce('/clear')
    assert not should_skip_debounce('hello')


def test_singleton_exists():
    assert message_deduplicator is not None
    assert isinstance(message_deduplicator, MessageDeduplicator)
