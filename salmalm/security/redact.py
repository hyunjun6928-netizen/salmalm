"""Shared secret redaction utilities.

Used by memory, audit logging, and error traces to prevent
secrets from being persisted anywhere.
"""

import re
from typing import List

_SECRET_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(sk-[a-zA-Z0-9]{20,})\b"),  # OpenAI keys
    re.compile(r"\b(AIza[a-zA-Z0-9_-]{30,})\b"),  # Google API keys
    re.compile(r"\b(xoxb-[a-zA-Z0-9-]+)\b"),  # Slack tokens
    re.compile(r"\b(ghp_[a-zA-Z0-9]{36,})\b"),  # GitHub PATs
    re.compile(r"\b(AKIA[A-Z0-9]{16})\b"),  # AWS access keys
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\."),  # JWT tokens
    re.compile(r"\b(password|비밀번호|credential|API.?key)\s*[:=]\s*\S+", re.I),  # key=value
    re.compile(r"\b(sk-ant-[a-zA-Z0-9_-]{20,})\b"),  # Anthropic keys
    re.compile(r"\b(xai-[a-zA-Z0-9]{20,})\b"),  # xAI keys
    re.compile(r"\b(hf_[A-Za-z0-9]{37,})\b"),  # Hugging Face tokens
    re.compile(r"\b(sk-or-[a-zA-Z0-9]{40,})\b"),  # OpenRouter keys
    re.compile(r"\b(gh[osr]_[a-zA-Z0-9]{36,})\b"),  # GitHub OAuth/server tokens
    re.compile(r"\b(github_pat_[A-Za-z0-9_]{82})\b"),  # GitHub fine-grained PATs
    re.compile(r"\b([0-9]{8,10}:[A-Za-z0-9_-]{35})\b"),  # Telegram bot tokens
    re.compile(r"[a-zA-Z+]+://[^:@\s]+:[^:@\s]+@[^/\s]+"),  # DSN with creds
]


def contains_secret(text: str) -> bool:
    """Check if text contains potential secrets."""
    return any(pat.search(text) for pat in _SECRET_PATTERNS)


def scrub_secrets(text: str) -> str:
    """Redact secrets from text, keeping surrounding context."""
    result = text
    for pat in _SECRET_PATTERNS:
        result = pat.sub("[REDACTED]", result)
    return result
