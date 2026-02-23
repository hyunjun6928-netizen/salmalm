"""Shared fixtures for SalmAlm tests.

HIGH-7: Known test isolation issues
-------------------------------------
- Global singletons (e.g. ``_logging_initialized`` in ``salmalm/__init__.py``,
  ``_all_db_connections`` in ``salmalm/core/core.py``, thread-local DB handles)
  persist across tests in the same process.
- Some tests start HTTP servers or asyncio loops that pollute process state.
- For full isolation, run with ``pytest --forked`` or per-file in CI.
"""
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Reset known global singletons between tests to reduce state leakage."""
    yield
    # Reset logging init flag so each test can re-init if needed
    try:
        import salmalm
        salmalm._logging_initialized = False
        # Remove handlers added during test
        root = logging.getLogger("salmalm")
        root.handlers.clear()
    except Exception:
        pass
    # Clear tracked DB connections list (connections themselves stay open
    # for the thread-local owner to close)
    try:
        from salmalm.core.core import _all_db_connections, _db_connections_lock
        with _db_connections_lock:
            _all_db_connections.clear()
    except Exception:
        pass
