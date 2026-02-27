"""Numeric limits and thresholds."""

from __future__ import annotations

import os as _os

DEFAULT_MAX_TOKENS = 4096
COMPACTION_THRESHOLD = 20000
CACHE_TTL = int(_os.environ.get("SALMALM_CACHE_TTL", "3600"))

INTENT_SHORT_MSG = 500
INTENT_COMPLEX_MSG = 1500
INTENT_CONTEXT_DEPTH = 40
REFLECT_SNIPPET_LEN = 500
