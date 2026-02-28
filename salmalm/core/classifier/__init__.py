"""salmalm.core.classifier — task classification package.

Re-exports all public symbols from sub-modules for backward compatibility.
Original module: salmalm/core/classifier.py (1325 lines, now split into 3 sub-modules).
"""
from __future__ import annotations

# Intent classification
from salmalm.core.classifier.intent import (  # noqa: F401
    TaskClassifier,
    classify_task,
)

# Keyword/pattern constants
from salmalm.core.classifier.keywords import (  # noqa: F401
    INTENT_TOOLS,
    _KEYWORD_TOOLS,
    get_extra_tools,
)

# Token allocation
from salmalm.core.classifier.tokens import (  # noqa: F401
    INTENT_MAX_TOKENS,
    _get_dynamic_max_tokens,
)

__all__ = [
    "TaskClassifier",
    "classify_task",
    "INTENT_TOOLS",
    "_KEYWORD_TOOLS",
    "get_extra_tools",
    "INTENT_MAX_TOKENS",
    "_get_dynamic_max_tokens",
]
