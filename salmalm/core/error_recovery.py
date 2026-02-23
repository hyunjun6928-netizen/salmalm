"""Error recovery and resilience — OpenClaw-level fault tolerance.

Provides:
1. Structured error classification (transient vs permanent)
2. Exponential backoff with jitter for retries
3. Circuit breaker per provider
4. Partial response recovery (save what we got before failure)
5. Graceful degradation messaging
"""

import random
import time
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from salmalm.security.crypto import log


# ── Error Classification ──


class ErrorKind:
    TRANSIENT = "transient"  # Retry-able: rate limit, timeout, 5xx
    PERMANENT = "permanent"  # Not retry-able: auth, invalid request, 4xx
    OVERLOADED = "overloaded"  # Provider overloaded: back off longer
    NETWORK = "network"  # Network issue: DNS, connection refused


def classify_error(error: Exception, status_code: int = 0, body: str = "") -> str:
    """Classify an error for recovery strategy."""
    error_str = str(error).lower()
    body_lower = body.lower()

    # Rate limiting
    if status_code == 429 or "rate limit" in error_str or "rate_limit" in body_lower:
        return ErrorKind.TRANSIENT

    # Server overloaded
    if status_code == 529 or "overloaded" in error_str or "overloaded" in body_lower:
        return ErrorKind.OVERLOADED

    # Server errors (5xx)
    if 500 <= status_code < 600:
        return ErrorKind.TRANSIENT

    # Auth errors
    if status_code in (401, 403) or "api key" in error_str or "authentication" in error_str:
        return ErrorKind.PERMANENT

    # Invalid request
    if status_code == 400 or "invalid" in error_str:
        return ErrorKind.PERMANENT

    # Network errors
    if any(
        w in error_str
        for w in ["timeout", "connection", "dns", "socket", "network", "etimedout", "econnrefused", "enotfound"]
    ):  # noqa: E127
        return ErrorKind.NETWORK

    # Default: treat as transient (safer to retry)
    return ErrorKind.TRANSIENT


# ── Exponential Backoff with Jitter ──


def backoff_delay(attempt: int, base: float = 1.0, max_delay: float = 60.0, jitter: bool = True) -> float:
    """Calculate exponential backoff delay with optional jitter.

    attempt 0 → base, attempt 1 → base*2, attempt 2 → base*4, etc.
    """
    delay = min(base * (2**attempt), max_delay)
    if jitter:
        delay = delay * (0.5 + random.random() * 0.5)  # 50-100% of calculated delay
    return delay


# ── Circuit Breaker ──


@dataclass
class CircuitState:
    failures: int = 0
    last_failure: float = 0
    opened_at: float = 0
    state: str = "closed"  # closed, open, half-open

    # Config
    failure_threshold: int = 5
    recovery_timeout: float = 60.0  # seconds before trying again

    def record_failure(self):
        self.failures += 1
        self.last_failure = time.time()
        if self.failures >= self.failure_threshold and self.state == "closed":
            self.state = "open"
            self.opened_at = time.time()
            log.warning(f"[CIRCUIT] Opened after {self.failures} failures")

    def record_success(self):
        self.failures = 0
        self.state = "closed"

    def is_available(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            # Check if recovery timeout has passed
            if time.time() - self.opened_at > self.recovery_timeout:
                self.state = "half-open"
                return True
            return False
        # half-open: allow one request
        return True


class CircuitBreakerRegistry:
    """Per-provider circuit breakers."""

    def __init__(self):
        self._circuits: Dict[str, CircuitState] = {}
        self._lock = threading.Lock()

    def get(self, provider: str) -> CircuitState:
        with self._lock:
            if provider not in self._circuits:
                self._circuits[provider] = CircuitState()
            return self._circuits[provider]

    def record_failure(self, provider: str):
        self.get(provider).record_failure()

    def record_success(self, provider: str):
        self.get(provider).record_success()

    def is_available(self, provider: str) -> bool:
        return self.get(provider).is_available()

    def status(self) -> Dict[str, dict]:
        with self._lock:
            return {
                p: {"state": c.state, "failures": c.failures, "last_failure": c.last_failure}
                for p, c in self._circuits.items()
            }


# Singleton
circuit_breakers = CircuitBreakerRegistry()


# ── Retry with Recovery ──


async def retry_with_recovery(
    fn: Callable,
    max_retries: int = 3,
    provider: str = "unknown",
    on_retry: Optional[Callable] = None,
) -> Tuple[Any, Optional[str]]:
    """Execute fn with automatic retry, backoff, and circuit breaker.

    Args:
        fn: Async callable to execute
        max_retries: Maximum retry attempts
        provider: Provider name for circuit breaker
        on_retry: Optional callback(attempt, delay, error) on retry

    Returns:
        (result, warning_or_None)
    """
    if not circuit_breakers.is_available(provider):
        return (
            {
                "content": f"⚠️ {provider} is temporarily unavailable (circuit breaker open)",
                "tool_calls": [],
                "usage": {"input": 0, "output": 0},
                "_failed": True,
            },
            f"⚠️ {provider} circuit breaker open",
        )

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = await fn()

            # Check for soft failures (200 but error content)
            content = result.get("content", "") if isinstance(result, dict) else ""
            if isinstance(content, str) and content.startswith("❌"):
                raise RuntimeError(content)

            circuit_breakers.record_success(provider)
            warn = f"⚠️ Succeeded after {attempt} retries" if attempt > 0 else None
            return result, warn

        except Exception as e:
            last_error = e
            kind = classify_error(e)

            # Don't retry permanent errors
            if kind == ErrorKind.PERMANENT:
                circuit_breakers.record_failure(provider)
                return (
                    {"content": f"❌ {e}", "tool_calls": [], "usage": {"input": 0, "output": 0}, "_failed": True},
                    None,
                )

            # Record failure
            circuit_breakers.record_failure(provider)

            # Calculate delay
            if kind == ErrorKind.OVERLOADED:
                delay = backoff_delay(attempt, base=5.0, max_delay=120.0)
            elif kind == ErrorKind.NETWORK:
                delay = backoff_delay(attempt, base=2.0, max_delay=30.0)
            else:
                delay = backoff_delay(attempt, base=1.0, max_delay=60.0)

            if attempt < max_retries:
                log.warning(
                    f"[RETRY] {provider} attempt {attempt + 1}/{max_retries}: {e} (kind={kind}, delay={delay:.1f}s)"
                )  # noqa: E128
                if on_retry:
                    try:
                        on_retry(attempt, delay, e)
                    except Exception as e:
                        log.debug(f"Suppressed: {e}")
                await _async_sleep(delay)
            else:
                log.error(f"[RETRY] {provider} all {max_retries} retries exhausted: {e}")

    # All retries failed
    return (
        {
            "content": f"❌ All retries failed: {last_error}",
            "tool_calls": [],
            "usage": {"input": 0, "output": 0},
            "_failed": True,
        },
        f"⚠️ {provider} failed after {max_retries} retries",
    )


async def _async_sleep(seconds: float):
    """Async sleep wrapper."""
    import asyncio

    await asyncio.sleep(seconds)


# ── Partial Response Recovery ──


class StreamBuffer:
    """Buffer for streaming responses — saves partial content on failure.

    If a stream breaks mid-way, we can recover what was already received
    instead of losing everything.
    """

    def __init__(self):
        self._chunks: list = []
        self._total_tokens: int = 0
        self._model: str = ""
        self._started_at: float = 0

    def start(self, model: str = ""):
        self._chunks = []
        self._total_tokens = 0
        self._model = model
        self._started_at = time.time()

    def add_chunk(self, text: str):
        self._chunks.append(text)

    def set_tokens(self, tokens: int):
        self._total_tokens = tokens

    @property
    def content(self) -> str:
        return "".join(self._chunks)

    @property
    def has_content(self) -> bool:
        return len(self._chunks) > 0

    def recover(self) -> Dict[str, Any]:
        """Recover partial response as a result dict."""
        content = self.content
        if not content:
            return {}
        return {
            "content": content + "\n\n⚠️ *(response interrupted — partial content recovered)*",
            "tool_calls": [],
            "usage": {"input": 0, "output": self._total_tokens or len(content) // 4},
            "model": self._model,
            "_partial": True,
        }


# ── User-Friendly Error Messages ──


def friendly_error(error: str, provider: str = "") -> str:
    """Convert technical errors to user-friendly messages."""
    error_lower = error.lower()

    if "api key" in error_lower or "authentication" in error_lower or "401" in error_lower:
        return f"🔑 {provider} API key is missing or invalid. Check Settings → API Keys."

    if "rate limit" in error_lower or "429" in error_lower:
        return f"⏳ {provider} rate limit hit. Waiting a moment before retrying..."

    if "overloaded" in error_lower or "529" in error_lower:
        return f"🏋️ {provider} is overloaded right now. Trying again shortly..."

    if "timeout" in error_lower:
        return f"⏰ {provider} request timed out. This usually means the response was too complex."

    if "connection" in error_lower or "network" in error_lower:
        return f"🌐 Can't reach {provider}. Check your internet connection."

    if "context" in error_lower and ("long" in error_lower or "length" in error_lower):
        return "📏 Conversation too long. Try /compact to compress context."

    return f"❌ {provider}: {error[:200]}"
