"""SalmAlm Retry Policy — exponential backoff with jitter.

Provides robust retry logic for API calls:
- Exponential backoff: 1s → 2s → 4s (configurable)
- Jitter: ±10% randomization (thundering herd prevention)
- 429 Rate Limit: respects Retry-After header
- 5xx: retries
- 4xx (400, 401, 403): no retry
- Timeout: retries
- 529 Overloaded: 30s wait + retry
"""

from __future__ import annotations

import functools
import random
import time
import urllib.error
from typing import Any, Callable, Optional

from salmalm.security.crypto import log

# ── Constants ──
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0
JITTER_FACTOR = 0.10  # ±10%
OVERLOADED_WAIT = 30.0  # 529 wait time

# Non-retryable HTTP status codes
_NO_RETRY_CODES = frozenset({400, 401, 403, 404, 405})


def _should_retry(error: Exception) -> tuple:
    """Determine if an error is retryable.

    Returns (should_retry: bool, wait_seconds: float | None).
    wait_seconds is set for rate-limit/overloaded responses.
    """
    if isinstance(error, urllib.error.HTTPError):
        code = error.code
        if code in _NO_RETRY_CODES:
            return False, None
        if code == 429:
            # Respect Retry-After header
            retry_after = error.headers.get("Retry-After") if hasattr(error, "headers") else None
            if retry_after:
                try:
                    wait = float(retry_after)
                    return True, min(wait, DEFAULT_MAX_DELAY)
                except (ValueError, TypeError):
                    pass
            return True, DEFAULT_BASE_DELAY
        if code == 529:
            return True, OVERLOADED_WAIT
        if 500 <= code < 600:
            return True, None
        return False, None

    if isinstance(error, urllib.error.URLError):
        return True, None  # Network error, retry

    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return True, None

    if isinstance(error, ValueError):
        msg = str(error).lower()
        if "rate limit" in msg or "429" in msg:
            return True, DEFAULT_BASE_DELAY
        if "overloaded" in msg or "529" in msg:
            return True, OVERLOADED_WAIT
        if "timeout" in msg:
            return True, None
        return False, None

    return False, None


def _add_jitter(delay: float) -> float:
    """Add ±10% jitter to delay."""
    jitter = delay * JITTER_FACTOR
    return delay + random.uniform(-jitter, jitter)


def retry_with_backoff(
    fn: Optional[Callable] = None,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
):
    """Decorator: retry function with exponential backoff + jitter.

    Usage:
        @retry_with_backoff
        def my_api_call():
            ...

        @retry_with_backoff(max_attempts=5, base_delay=2.0)
        def my_api_call():
            ...
    """

    def decorator(func: Callable) -> Callable:
        import asyncio as _asyncio
        if _asyncio.iscoroutinefunction(func):
            raise TypeError(
                f"retry_with_backoff cannot decorate async function '{func.__name__}'. "
                "Use async_retry_with_backoff() instead."
            )

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            """Wrapper."""
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    should_retry, forced_wait = _should_retry(e)

                    if not should_retry or attempt >= max_attempts:
                        log.warning(f"[RETRY] {func.__name__} failed after {attempt} attempts: {e}")
                        raise

                    if forced_wait is not None:
                        wait = _add_jitter(forced_wait)
                    else:
                        delay = base_delay * (2 ** (attempt - 1))
                        wait = _add_jitter(min(delay, max_delay))

                    log.info(
                        f"[RETRY] {func.__name__} attempt {attempt}/{max_attempts} "
                        f"failed ({type(e).__name__}), retrying in {wait:.1f}s"
                    )
                    time.sleep(wait)

            raise last_error  # Should not reach here

        return wrapper

    if fn is not None:
        return decorator(fn)
    return decorator


async def async_retry_with_backoff(
    coro_fn: Callable,
    *args,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    **kwargs,
) -> Any:
    """Async version: retry an async callable with exponential backoff.

    Usage:
        result = await async_retry_with_backoff(my_async_fn, arg1, arg2)
    """
    import asyncio

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            should_retry, forced_wait = _should_retry(e)

            if not should_retry or attempt >= max_attempts:
                log.warning(f"[RETRY] {coro_fn.__name__} failed after {attempt} attempts: {e}")
                raise

            if forced_wait is not None:
                wait = _add_jitter(forced_wait)
            else:
                delay = base_delay * (2 ** (attempt - 1))
                wait = _add_jitter(min(delay, max_delay))

            log.info(
                f"[RETRY] {coro_fn.__name__} attempt {attempt}/{max_attempts} "
                f"failed ({type(e).__name__}), retrying in {wait:.1f}s"
            )
            await asyncio.sleep(wait)

    raise last_error


def retry_call(
    fn: Callable, *args, max_attempts: int = DEFAULT_MAX_ATTEMPTS, base_delay: float = DEFAULT_BASE_DELAY, **kwargs
) -> Any:
    """Functional retry: call fn with retry logic (not a decorator).

    Usage:
        result = retry_call(requests.post, url, json=data)
    """
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            should_retry, forced_wait = _should_retry(e)

            if not should_retry or attempt >= max_attempts:
                raise

            if forced_wait is not None:
                wait = _add_jitter(forced_wait)
            else:
                delay = base_delay * (2 ** (attempt - 1))
                wait = _add_jitter(min(delay, DEFAULT_MAX_DELAY))

            log.info(f"[RETRY] attempt {attempt}/{max_attempts}: {type(e).__name__}, wait {wait:.1f}s")
            time.sleep(wait)

    raise last_error
