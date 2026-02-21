"""Tests for core/error_recovery.py"""
import pytest
import asyncio


def test_classify_rate_limit():
    from salmalm.core.error_recovery import classify_error, ErrorKind
    assert classify_error(Exception("rate limit exceeded"), 429) == ErrorKind.TRANSIENT


def test_classify_auth():
    from salmalm.core.error_recovery import classify_error, ErrorKind
    assert classify_error(Exception("Invalid API key"), 401) == ErrorKind.PERMANENT


def test_classify_overloaded():
    from salmalm.core.error_recovery import classify_error, ErrorKind
    assert classify_error(Exception("overloaded"), 529) == ErrorKind.OVERLOADED


def test_classify_network():
    from salmalm.core.error_recovery import classify_error, ErrorKind
    assert classify_error(Exception("ETIMEDOUT")) == ErrorKind.NETWORK
    assert classify_error(Exception("connection refused")) == ErrorKind.NETWORK


def test_classify_server_error():
    from salmalm.core.error_recovery import classify_error, ErrorKind
    assert classify_error(Exception("internal"), 500) == ErrorKind.TRANSIENT
    assert classify_error(Exception("bad gateway"), 502) == ErrorKind.TRANSIENT


def test_backoff_delay():
    from salmalm.core.error_recovery import backoff_delay
    d0 = backoff_delay(0, base=1.0, jitter=False)
    assert d0 == 1.0
    d1 = backoff_delay(1, base=1.0, jitter=False)
    assert d1 == 2.0
    d2 = backoff_delay(2, base=1.0, jitter=False)
    assert d2 == 4.0
    # Max delay cap
    d10 = backoff_delay(10, base=1.0, max_delay=60.0, jitter=False)
    assert d10 == 60.0


def test_backoff_jitter():
    from salmalm.core.error_recovery import backoff_delay
    delays = [backoff_delay(1, jitter=True) for _ in range(10)]
    # With jitter, not all should be identical
    assert len(set(delays)) > 1


def test_circuit_breaker_closed():
    from salmalm.core.error_recovery import CircuitState
    cb = CircuitState()
    assert cb.is_available()
    assert cb.state == "closed"


def test_circuit_breaker_opens():
    from salmalm.core.error_recovery import CircuitState
    cb = CircuitState(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_available()  # Still closed
    cb.record_failure()
    assert not cb.is_available()  # Now open
    assert cb.state == "open"


def test_circuit_breaker_recovery():
    from salmalm.core.error_recovery import CircuitState
    import time
    cb = CircuitState(failure_threshold=2, recovery_timeout=0.1)
    cb.record_failure()
    cb.record_failure()
    assert not cb.is_available()
    time.sleep(0.15)
    assert cb.is_available()  # Half-open
    assert cb.state == "half-open"


def test_circuit_breaker_success_resets():
    from salmalm.core.error_recovery import CircuitState
    cb = CircuitState(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.failures == 0
    assert cb.state == "closed"


def test_circuit_breaker_registry():
    from salmalm.core.error_recovery import CircuitBreakerRegistry
    reg = CircuitBreakerRegistry()
    assert reg.is_available("anthropic")
    reg.record_failure("anthropic")
    assert reg.is_available("anthropic")
    status = reg.status()
    assert "anthropic" in status


def test_stream_buffer():
    from salmalm.core.error_recovery import StreamBuffer
    buf = StreamBuffer()
    buf.start(model="test")
    assert not buf.has_content
    buf.add_chunk("Hello ")
    buf.add_chunk("world")
    assert buf.has_content
    assert buf.content == "Hello world"
    recovered = buf.recover()
    assert "Hello world" in recovered["content"]
    assert recovered["_partial"] is True


def test_friendly_error_api_key():
    from salmalm.core.error_recovery import friendly_error
    msg = friendly_error("Invalid API key", "Anthropic")
    assert "API key" in msg
    assert "Anthropic" in msg


def test_friendly_error_rate_limit():
    from salmalm.core.error_recovery import friendly_error
    msg = friendly_error("Rate limit exceeded", "OpenAI")
    assert "rate limit" in msg.lower()


def test_friendly_error_timeout():
    from salmalm.core.error_recovery import friendly_error
    msg = friendly_error("Request timeout after 30s", "Google")
    assert "timed out" in msg.lower()
