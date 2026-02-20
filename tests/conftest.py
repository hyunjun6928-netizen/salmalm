"""Test configuration — network safety + resource cleanup."""
import faulthandler
import gc
import socket
import threading
import urllib.request

faulthandler.enable()

# Speed up PBKDF2 in tests (200K → 1K iterations)
import salmalm.constants as _c
_c.PBKDF2_ITER = 1_000

import pytest

# ---------------------------------------------------------------------------
# 1. Block all non-localhost network I/O at the socket level
# ---------------------------------------------------------------------------
_original_socket_connect = socket.socket.connect
_original_socket_connect_ex = socket.socket.connect_ex
_original_urlopen = urllib.request.urlopen

_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _get_host(address):
    """Extract host from address tuple or return None."""
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
    # Allow localhost URLs
    if any(h in url_str for h in ("://127.0.0.1", "://localhost", "://[::1]", "://0.0.0.0")):
        return _original_urlopen(url, *args, **kwargs)
    raise urllib.error.URLError(f"[conftest] Network blocked: urlopen {url_str}")


# Patch at module level so it's active for the entire test session
socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex
urllib.request.urlopen = _guarded_urlopen

# ---------------------------------------------------------------------------
# 2. Per-test cleanup: GC + kill stale threads
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _cleanup():
    """GC + thread cleanup between tests."""
    threads_before = set(threading.enumerate())
    yield
    gc.collect()
    # Give daemon threads a moment to die, don't block on non-daemon ones
    import time
    for t in threading.enumerate():
        if t not in threads_before and t is not threading.current_thread() and t.daemon:
            t.join(timeout=0.5)


# ---------------------------------------------------------------------------
# 3. Global test timeout (per-test) to prevent infinite hangs
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _test_timeout():
    """Kill any individual test that runs longer than 30s."""
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
