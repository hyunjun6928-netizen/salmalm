"""Smart Context Window — intelligent context injection with token budget.

stdlib-only. Provides:
  - Topic analysis from current conversation
  - Related past conversation/memory retrieval
  - Token-budgeted context assembly
  - /context show, /context budget <tokens>
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# Approximate tokens per char (for budget estimation)
_CHARS_PER_TOKEN = 4
_DEFAULT_BUDGET = 8000  # tokens


def estimate_tokens(text: str) -> int:
    """Rough token count estimate."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def extract_keywords(text: str, top_n: int = 10) -> List[str]:
    """Extract top keywords from text using simple TF analysis."""
    _STOP = frozenset(
        [
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "that",
            "this",
            "it",
            "not",
            "if",
            "so",
            "as",
            "by",
            "from",
            "has",
            "have",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "can",
            "could",
            "may",
            "might",
            "i",
            "you",
            "he",
            "she",
            "we",
            "they",
            "의",
            "가",
            "이",
            "은",
            "는",
            "을",
            "를",
            "에",
            "에서",
            "로",
            "으로",
            "와",
            "과",
            "도",
            "만",
            "하다",
            "있다",
            "되다",
            "하는",
            "있는",
        ]
    )
    words = re.findall(r"[a-zA-Z가-힣]{2,}", text.lower())
    counts = Counter(w for w in words if w not in _STOP)
    return [w for w, _ in counts.most_common(top_n)]


def relevance_score(keywords: List[str], text: str) -> float:
    """Score text relevance against keywords (0.0-1.0)."""
    if not keywords or not text:
        return 0.0
    text_lower = text.lower()
    matches = sum(1 for k in keywords if k in text_lower)
    return matches / len(keywords) if keywords else 0.0


class ContextChunk:
    """A piece of context with metadata."""

    __slots__ = ("source", "content", "relevance", "tokens", "timestamp")

    def __init__(self, source: str, content: str, relevance: float = 0.0, timestamp: float = 0.0) -> None:
        """Init  ."""
        self.source = source
        self.content = content
        self.relevance = relevance
        self.tokens = estimate_tokens(content)
        self.timestamp = timestamp or time.time()

    def __repr__(self) -> str:
        return f"ContextChunk({self.source}, rel={self.relevance:.2f}, tok={self.tokens})"


class SmartContextWindow:
    """Intelligent context window manager."""

    def __init__(self, token_budget: int = _DEFAULT_BUDGET) -> None:
        """Init  ."""
        self._budget = token_budget
        self._injected: List[ContextChunk] = []
        self._recent_messages: List[Dict] = []

    @property
    def budget(self) -> int:
        """Budget."""
        return self._budget

    @budget.setter
    def budget(self, tokens: int) -> None:
        """Budget."""
        self._budget = max(100, tokens)

    @property
    def used_tokens(self) -> int:
        """Used tokens."""
        return sum(c.tokens for c in self._injected)

    @property
    def remaining_tokens(self) -> int:
        """Remaining tokens."""
        return max(0, self._budget - self.used_tokens)

    def set_recent_messages(self, messages: List[Dict]) -> None:
        """Set recent conversation messages for topic analysis."""
        self._recent_messages = messages[-20:]  # keep last 20

    def analyze_topic(self) -> List[str]:
        """Analyze current conversation topic from recent messages."""
        text = " ".join(m.get("content", "") for m in self._recent_messages if isinstance(m.get("content"), str))
        return extract_keywords(text)

    def gather_context(self, sources: Optional[List[Dict]] = None) -> List[ContextChunk]:
        """Gather and rank context chunks within token budget.

        sources: list of {source, content, timestamp?}
        """
        keywords = self.analyze_topic()
        candidates: List[ContextChunk] = []

        # Score provided sources
        if sources:
            for s in sources:
                content = s.get("content", "")
                if not content:
                    continue
                rel = relevance_score(keywords, content)
                chunk = ContextChunk(
                    source=s.get("source", "unknown"),
                    content=content,
                    relevance=rel,
                    timestamp=s.get("timestamp", 0),
                )
                candidates.append(chunk)

        # Sort by relevance (desc), then recency
        candidates.sort(key=lambda c: (c.relevance, c.timestamp), reverse=True)

        # Fill budget
        self._injected = []
        used = 0
        for c in candidates:
            if used + c.tokens <= self._budget:
                self._injected.append(c)
                used += c.tokens

        return self._injected

    def build_context_string(self) -> str:
        """Build the injected context as a single string."""
        if not self._injected:
            return ""
        parts = []
        for c in self._injected:
            parts.append(f"[{c.source}] (relevance: {c.relevance:.2f})\n{c.content}")
        return "\n---\n".join(parts)

    def show(self) -> str:
        """Format current injected context for display."""
        if not self._injected:
            return "📋 No context currently injected."
        lines = [f"**Smart Context** (budget: {self._budget} tokens, used: {self.used_tokens})\n"]
        for c in self._injected:
            preview = c.content[:80].replace("\n", " ")
            lines.append(f"• [{c.source}] rel={c.relevance:.2f} tok={c.tokens} — {preview}…")
        lines.append(f"\n_Remaining: {self.remaining_tokens} tokens_")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear injected context."""
        self._injected = []


# Singleton
smart_context = SmartContextWindow()


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def handle_context_command(cmd: str, session=None, **kw) -> str:
    """Handle /context show | /context budget <tokens>."""
    parts = cmd.strip().split()
    sub = parts[1] if len(parts) > 1 else "show"

    if sub == "show":
        return smart_context.show()

    if sub == "budget":
        if len(parts) < 3:
            return f"Current budget: {smart_context.budget} tokens\nUsage: `/context budget <tokens>`"
        try:
            n = int(parts[2])
            smart_context.budget = n
            return f"✅ Context budget set to {smart_context.budget} tokens"
        except ValueError:
            return "❌ Invalid number"

    if sub == "clear":
        smart_context.clear()
        return "🗑️ Context cleared."

    return "❌ Usage: `/context show|budget <tokens>|clear`"


def register_commands(router: object) -> None:
    """Register /context commands."""
    router.register_prefix("/context", handle_context_command)


def register_tools(registry_module: Optional[object] = None) -> None:
    """Register smart context tools."""
    try:
        from salmalm.tools.tool_registry import register_dynamic

        register_dynamic(
            "context_show",
            lambda args: smart_context.show(),
            {
                "name": "context_show",
                "description": "Show currently injected smart context",
                "input_schema": {"type": "object", "properties": {}},
            },
        )
    except Exception as e:
        log.warning(f"Failed to register context tools: {e}")
