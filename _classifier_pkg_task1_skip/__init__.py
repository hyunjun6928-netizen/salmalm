"""Classifier package with backward-compatible public exports."""

from .intent import TaskClassifier, classify, classify_task, get_extra_tools
from .keywords import (
    INTENT_TOOLS,
    _COMPLEX_KEYWORDS,
    _DETAIL_KEYWORDS,
    _KEYWORD_TOOLS,
    _MODERATE_KEYWORDS,
    _SIMPLE_PATTERNS,
)
from .tokens import INTENT_MAX_TOKENS, _MODEL_DEFAULT_MAX, _get_dynamic_max_tokens

__all__ = [
    "TaskClassifier",
    "classify",
    "classify_task",
    "get_extra_tools",
    "INTENT_TOOLS",
    "_KEYWORD_TOOLS",
    "_COMPLEX_KEYWORDS",
    "_MODERATE_KEYWORDS",
    "_SIMPLE_PATTERNS",
    "_DETAIL_KEYWORDS",
    "INTENT_MAX_TOKENS",
    "_MODEL_DEFAULT_MAX",
    "_get_dynamic_max_tokens",
]
