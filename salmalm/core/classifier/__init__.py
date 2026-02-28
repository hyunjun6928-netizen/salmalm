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
    _EMOJI_TOOLS,
    _QUESTION_WORDS,
    _QUESTION_INJECT_TOOLS,
    _TIME_PATTERN_RE,
    _TIME_INJECT_TOOLS,
    get_extra_tools,
)

# Token allocation
from salmalm.core.classifier.tokens import (  # noqa: F401
    INTENT_MAX_TOKENS,
    _DETAIL_KEYWORDS,
    _get_dynamic_max_tokens,
)

# Compat aliases
from salmalm.core.cost import estimate_tokens  # noqa: F401
classify_intent = classify_task  # noqa: F401 — backward-compat alias

__all__ = [
    "TaskClassifier",
    "classify_task",
    "classify_intent",
    "INTENT_TOOLS",
    "_KEYWORD_TOOLS",
    "_EMOJI_TOOLS",
    "_QUESTION_WORDS",
    "_QUESTION_INJECT_TOOLS",
    "_TIME_PATTERN_RE",
    "_TIME_INJECT_TOOLS",
    "get_extra_tools",
    "INTENT_MAX_TOKENS",
    "_DETAIL_KEYWORDS",
    "_get_dynamic_max_tokens",
    "estimate_tokens",
]
