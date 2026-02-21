"""Test configuration — network safety, resource cleanup, isolation.

Sections:
  1. Network guard — block all non-localhost I/O
  2. Per-test cleanup — GC + thread reaper
  3. Per-test timeout — SIGALRM watchdog (Unix only)
  4. Temp directory isolation — DATA_DIR → tempdir
"""
from __future__ import annotations

import faulthandler
import gc
import os
import socket
import tempfile
import threading
import urllib.request

import pytest

faulthandler.enable()

# Speed up PBKDF2 in tests (200K → 1K iterations)
import salmalm.constants as _c
_c.PBKDF2_ITER = 1_000


# ---------------------------------------------------------------------------
# 1. Network guard — block all non-localhost socket connections
# ---------------------------------------------------------------------------
_original_socket_connect = socket.socket.connect
_original_socket_connect_ex = socket.socket.connect_ex
_original_urlopen = urllib.request.urlopen

_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})


def _get_host(address) -> str | None:
    """Extract host from address tuple."""
    if isinstance(address, tuple) and len(address) >= 2:
        return str(address[0])
    return None


def _guarded_connect(self, address):
    host = _get_host(address)
    if host and host not in _ALLOWED_HOSTS:
        raise OSError(f"[conftest] Network blocked: connect to {address}")
    return _original_socket_connect(self, address)


def _guarded_connect_ex(self, address):
    host = _get_host(address)
    if host and host not in _ALLOWED_HOSTS:
        raise OSError(f"[conftest] Network blocked: connect_ex to {address}")
    return _original_socket_connect_ex(self, address)


def _guarded_urlopen(url, *args, **kwargs):
    url_str = url if isinstance(url, str) else getattr(url, 'full_url', str(url))
    if any(h in url_str for h in ("://127.0.0.1", "://localhost", "://[::1]", "://0.0.0.0")):
        return _original_urlopen(url, *args, **kwargs)
    raise urllib.error.URLError(f"[conftest] Network blocked: urlopen {url_str}")


socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex
urllib.request.urlopen = _guarded_urlopen


# ---------------------------------------------------------------------------
# 2. Per-test cleanup — GC + stale thread reaper
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _cleanup():
    """GC + thread join between tests to prevent state leakage."""
    threads_before = set(threading.enumerate())
    yield
    gc.collect()
    stale = [t for t in threading.enumerate()
             if t not in threads_before and t is not threading.current_thread()]
    for t in stale:
        t.join(timeout=1.0)
    gc.collect()


# ---------------------------------------------------------------------------
# 3. Per-test timeout — SIGALRM watchdog (Unix only)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _test_timeout():
    """Kill any individual test that runs longer than 30s (Unix only)."""
    import signal
    import sys

    if sys.platform == "win32":
        yield
        return

    def _handler(signum, frame):
        raise TimeoutError("Test exceeded 30s timeout")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(30)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


# ---------------------------------------------------------------------------
# 4. DATA_DIR isolation note
# ---------------------------------------------------------------------------
# Individual test files that create HTTP servers (test_api, test_coverage, etc.)
# manage their own DATA_DIR via setUpClass. A global autouse fixture here
# conflicts with those setups. DATA_DIR isolation is per-test-file responsibility.
# See CONTRIBUTING.md for the per-file test execution pattern.
