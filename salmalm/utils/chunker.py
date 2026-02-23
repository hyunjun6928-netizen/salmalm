"""Smart block chunking — code fence aware, coalescing, human-like pacing.

EmbeddedBlockChunker: accumulates streaming tokens and emits properly-split
Markdown-safe chunks respecting code fences, break-point priorities, channel
limits, and optional human-like pacing.
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Literal, Optional, Tuple
from salmalm.constants import DATA_DIR

# ── Channel presets ──────────────────────────────────────────

CHANNEL_TELEGRAM = "telegram"
CHANNEL_DISCORD = "discord"
CHANNEL_WEB = "web"

CHANNEL_DEFAULTS: Dict[str, dict] = {
    CHANNEL_TELEGRAM: {"hardCap": 4096, "maxLinesPerMessage": None, "plainFallback": True},
    CHANNEL_DISCORD: {"hardCap": 2000, "maxLinesPerMessage": 17, "plainFallback": False},
    CHANNEL_WEB: {"hardCap": 0, "maxLinesPerMessage": None, "plainFallback": False},  # 0 = unlimited
}

# ── Break-point priorities (higher = preferred) ─────────────

BREAK_PARAGRAPH = 5  # \n\n
BREAK_NEWLINE = 4  # \n
BREAK_SENTENCE = 3  # sentence-ending punctuation followed by space
BREAK_WHITESPACE = 2  # any whitespace
BREAK_HARD = 1  # forced mid-word

_SENTENCE_END = re.compile(r"[.!?。！？]\s")


@dataclass
class ChunkerConfig:
    """Configuration for EmbeddedBlockChunker."""

    channel: str = CHANNEL_TELEGRAM
    # Coalescing
    minChars: int = 200
    maxChars: int = 2000
    idleMs: int = 500
    # Human-like pacing
    humanDelay: Literal["off", "natural", "custom"] = "natural"
    humanDelayMin: float = 0.8  # seconds
    humanDelayMax: float = 2.5  # seconds
    # Break preference: list of priorities to try (highest first)
    breakPreference: Optional[List[int]] = None
    # Override hard cap (0 = use channel default)
    hardCap: int = 0
    maxLinesPerMessage: Optional[int] = None

    def effective_hard_cap(self) -> int:
        """Effective hard cap."""
        if self.hardCap > 0:
            return self.hardCap
        ch = CHANNEL_DEFAULTS.get(self.channel, CHANNEL_DEFAULTS[CHANNEL_WEB])
        return ch["hardCap"] or 0

    def effective_max_lines(self) -> Optional[int]:
        """Effective max lines."""
        if self.maxLinesPerMessage is not None:
            return self.maxLinesPerMessage
        ch = CHANNEL_DEFAULTS.get(self.channel, CHANNEL_DEFAULTS[CHANNEL_WEB])
        return ch.get("maxLinesPerMessage")

    def uses_plain_fallback(self) -> bool:
        """Uses plain fallback."""
        ch = CHANNEL_DEFAULTS.get(self.channel, CHANNEL_DEFAULTS[CHANNEL_WEB])
        return ch.get("plainFallback", False)


def load_config_from_file(path: Optional[str] = None) -> ChunkerConfig:
    """Load streaming config from ~/.salmalm/streaming.json if it exists."""
    if path is None:
        path = str(DATA_DIR / "streaming.json")
    try:
        with open(path) as f:
            data = json.load(f)
        return ChunkerConfig(**{k: v for k, v in data.items() if hasattr(ChunkerConfig, k)})
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return ChunkerConfig()


# ── Code fence tracking ──────────────────────────────────────

_FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})", re.MULTILINE)


def _count_open_fences(text: str) -> bool:
    """Return True if text has an unclosed code fence."""
    count = 0
    for m in _FENCE_OPEN.finditer(text):
        count += 1
    return count % 2 != 0


def _find_fence_safe_split(text: str, max_pos: int) -> Tuple[str, str]:
    """Split text at max_pos but ensure code fences stay valid.

    If splitting inside a code fence, close it in the first chunk
    and reopen it in the second (preserving the fence language tag).
    """
    if max_pos >= len(text):
        return text, ""

    chunk = text[:max_pos]
    rest = text[max_pos:]

    if not _count_open_fences(chunk):
        return chunk, rest

    # Find the last opening fence to extract language tag
    last_fence = None
    for m in _FENCE_OPEN.finditer(chunk):
        last_fence = m

    lang_tag = ""
    if last_fence:
        _fence_marker = last_fence.group(1)  # noqa: F841
        # Check for language tag after fence
        fence_end = last_fence.end()
        line_end = chunk.find("\n", fence_end)
        if line_end == -1:
            line_end = len(chunk)
        lang_tag = chunk[fence_end:line_end].strip()
        # Close in chunk, reopen in rest
        chunk = chunk.rstrip() + "\n```"
        rest = f"```{lang_tag}\n" + rest.lstrip("\n")

    return chunk, rest


# ── Smart break-point finder ────────────────────────────────


def _find_best_break(text: str, max_pos: int, preference: Optional[List[int]] = None) -> int:
    """Find the best position to break text before max_pos.

    Returns the split position (exclusive). Falls back to max_pos (hard break).
    """
    if max_pos >= len(text):
        return len(text)

    search_start = max(0, max_pos // 4)  # Don't look too far back
    region = text[search_start:max_pos]

    # Default priority order
    if preference is None:
        preference = [BREAK_PARAGRAPH, BREAK_NEWLINE, BREAK_SENTENCE, BREAK_WHITESPACE, BREAK_HARD]

    for bp in preference:
        pos = -1
        if bp == BREAK_PARAGRAPH:
            pos = region.rfind("\n\n")
            if pos >= 0:
                pos += 2  # include the double newline
        elif bp == BREAK_NEWLINE:
            pos = region.rfind("\n")
            if pos >= 0:
                pos += 1
        elif bp == BREAK_SENTENCE:
            for m in _SENTENCE_END.finditer(region):
                pos = m.end()  # after the space
        elif bp == BREAK_WHITESPACE:
            # Find last whitespace
            for i in range(len(region) - 1, -1, -1):
                if region[i] in " \t":
                    pos = i + 1
                    break

        if pos > 0:
            return search_start + pos

    # Hard break
    return max_pos


# ── Main chunker class ──────────────────────────────────────


class EmbeddedBlockChunker:
    """Accumulates streaming text and emits Markdown-safe chunks.

    Usage:
        chunker = EmbeddedBlockChunker(config, on_chunk=my_callback)
        # Feed tokens as they arrive:
        chunker.feed("Hello ")
        chunker.feed("world!\n\n")
        chunker.feed("```python\nprint('hi')\n```")
        # When done:
        chunker.flush()

    The on_chunk callback receives (text: str, is_final: bool).
    """

    def __init__(self, config: Optional[ChunkerConfig] = None, on_chunk: Optional[Callable[[str, bool], None]] = None) -> None:
        """Init  ."""
        self.config = config or ChunkerConfig()
        self.on_chunk = on_chunk
        self._buffer: str = ""
        self._chunk_count: int = 0
        self._last_emit_time: float = 0.0
        self._last_feed_time: float = 0.0
        self._total_emitted: str = ""

    @property
    def buffer(self) -> str:
        """Buffer."""
        return self._buffer

    @property
    def chunk_count(self) -> int:
        """Chunk count."""
        return self._chunk_count

    def feed(self, text: str) -> Optional[str]:
        """Feed a token/text fragment. May emit a chunk via callback.

        Returns the emitted chunk text if one was emitted, else None.
        """
        self._buffer += text
        self._last_feed_time = time.time()

        hard_cap = self.config.effective_hard_cap()
        max_chars = self.config.maxChars

        # Check if we need to force-flush (exceeds maxChars or hard cap)
        effective_max = min(max_chars, hard_cap) if hard_cap > 0 else max_chars
        if len(self._buffer) >= effective_max:
            return self._emit_chunk(force=True)

        return None

    def check_idle(self) -> Optional[str]:
        """Check if idle timeout has elapsed and flush if needed.

        Call this periodically (e.g., from a timer). Returns emitted chunk or None.
        """
        if not self._buffer:
            return None
        if len(self._buffer) < self.config.minChars:
            # Below minimum — only flush on idle timeout
            elapsed_ms = (time.time() - self._last_feed_time) * 1000
            if elapsed_ms >= self.config.idleMs:
                return self._emit_chunk(force=False)
            return None
        # Above minChars — emit if idle
        elapsed_ms = (time.time() - self._last_feed_time) * 1000
        if elapsed_ms >= self.config.idleMs:
            return self._emit_chunk(force=False)
        return None

    def flush(self) -> Optional[str]:
        """Flush any remaining buffer as the final chunk."""
        if not self._buffer:
            return None
        return self._emit_chunk(force=True, is_final=True)

    def _emit_chunk(self, force: bool = False, is_final: bool = False) -> Optional[str]:
        """Internal: split buffer and emit a chunk."""
        if not self._buffer:
            return None

        hard_cap = self.config.effective_hard_cap()
        max_chars = self.config.maxChars
        effective_max = min(max_chars, hard_cap) if hard_cap > 0 else max_chars

        buf = self._buffer

        if is_final or len(buf) <= effective_max:
            # Emit everything (or fits in one chunk)
            if is_final and hard_cap > 0 and len(buf) > hard_cap:
                # Need to split even final content
                return self._emit_split(buf, hard_cap)
            chunk = buf
            self._buffer = ""
        else:
            # Need to split
            return self._emit_split(buf, effective_max)

        return self._deliver(chunk, is_final)

    def _emit_split(self, buf: str, max_len: int) -> Optional[str]:
        """Split buffer at best break point, emit first part."""
        # Don't split inside code fences
        if _count_open_fences(buf[:max_len]):
            chunk, rest = _find_fence_safe_split(buf, max_len)
        else:
            split_pos = _find_best_break(buf, max_len, self.config.breakPreference)
            chunk = buf[:split_pos]
            rest = buf[split_pos:]

        self._buffer = rest
        return self._deliver(chunk, False)

    def _deliver(self, chunk: str, is_final: bool) -> str:
        """Deliver a chunk via callback and track state."""
        self._chunk_count += 1
        self._total_emitted += chunk
        self._last_emit_time = time.time()

        if self.on_chunk:
            self.on_chunk(chunk, is_final)

        return chunk

    def compute_delay(self) -> float:
        """Compute human-like delay before sending the next chunk.

        Returns 0 for the first chunk or if humanDelay is 'off'.
        """
        if self.config.humanDelay == "off":
            return 0.0
        if self._chunk_count <= 1:
            return 0.0  # No delay for first chunk

        lo = self.config.humanDelayMin
        hi = self.config.humanDelayMax
        return random.uniform(lo, hi)

    def split_for_channel(self, text: str) -> List[str]:
        """Split a complete text into channel-appropriate messages.

        Standalone utility — doesn't use the internal buffer.
        Respects code fences, break points, and channel limits.
        """
        hard_cap = self.config.effective_hard_cap()
        max_lines = self.config.effective_max_lines()

        if hard_cap <= 0 and max_lines is None:
            return [text] if text else []

        chunks: List[str] = []
        remaining = text

        while remaining:
            if hard_cap > 0 and len(remaining) <= hard_cap:
                # Check line limit
                if max_lines and remaining.count("\n") >= max_lines:
                    lines = remaining.split("\n")
                    chunk_lines = "\n".join(lines[:max_lines])
                    remaining = "\n".join(lines[max_lines:])
                    # Handle code fence integrity
                    if _count_open_fences(chunk_lines):
                        chunk_lines, extra = _find_fence_safe_split(chunk_lines, len(chunk_lines))
                        remaining = extra + "\n" + remaining if remaining else extra
                    chunks.append(chunk_lines)
                    continue
                chunks.append(remaining)
                break

            limit = hard_cap if hard_cap > 0 else len(remaining)

            # Apply line limit
            if max_lines:
                lines = remaining[:limit].split("\n")
                if len(lines) > max_lines:
                    limit = sum(len(l) + 1 for l in lines[:max_lines]) - 1  # noqa: E741
                    limit = min(limit, hard_cap) if hard_cap > 0 else limit

            if _count_open_fences(remaining[:limit]):
                chunk, remaining = _find_fence_safe_split(remaining, limit)
            else:
                split_pos = _find_best_break(remaining, limit, self.config.breakPreference)
                chunk = remaining[:split_pos]
                remaining = remaining[split_pos:]

            remaining = remaining.lstrip("\n") if remaining else ""
            if chunk.strip():
                chunks.append(chunk)

        return chunks if chunks else ([text] if text else [])
