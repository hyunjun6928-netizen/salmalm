"""Test configuration."""
import faulthandler
import gc

faulthandler.enable()

import pytest


@pytest.fixture(autouse=True)
def _cleanup():
    """GC between tests to prevent resource leaks."""
    yield
    gc.collect()
