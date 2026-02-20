"""Tests for smart block chunking — code fence aware, coalescing, human-like pacing."""
import time
from unittest.mock import MagicMock

import pytest

from salmalm.utils.chunker import (
    BREAK_HARD, BREAK_NEWLINE, BREAK_PARAGRAPH, BREAK_SENTENCE, BREAK_WHITESPACE,
    CHANNEL_DISCORD, CHANNEL_TELEGRAM, CHANNEL_WEB,
    ChunkerConfig, EmbeddedBlockChunker,
    _count_open_fences, _find_best_break, _find_fence_safe_split,
)


# ── 1. Code fence split prevention ──────────────────────────

class TestCodeFenceSplitPrevention:
    def test_no_split_inside_code_block(self):
        """Code blocks should never be split mid-content."""
        config = ChunkerConfig(channel="web", maxChars=50)
        chunks = []
        chunker = EmbeddedBlockChunker(config, on_chunk=lambda t, f: chunks.append(t))

        text = "Hello\n```python\nfor i in range(100):\n    print(i)\n```\nDone"
        chunker.feed(text)
        chunker.flush()

        # Verify no chunk has an unclosed fence (unless it's properly closed+reopened)
        for chunk in chunks:
            fence_count = chunk.count('```')
            assert fence_count % 2 == 0, f"Unclosed fence in chunk: {chunk!r}"

    def test_fence_close_reopen_on_forced_split(self):
        """When split is unavoidable, fences should be closed and reopened."""
        # Build text with a very long code block exceeding hard cap
        code_content = "x = 1\n" * 300  # ~1800 chars
        text = f"```python\n{code_content}```"

        chunk, rest = _find_fence_safe_split(text, 200)

        assert chunk.endswith("```"), "First chunk must close the fence"
        assert rest.startswith("```python\n") or rest.startswith("```\n"), \
            "Second chunk must reopen the fence"

    def test_count_open_fences_balanced(self):
        assert not _count_open_fences("```python\ncode\n```")
        assert not _count_open_fences("no fences here")
        assert not _count_open_fences("```\na\n```\n```\nb\n```")

    def test_count_open_fences_unbalanced(self):
        assert _count_open_fences("```python\ncode without close")
        assert _count_open_fences("```\na\n```\n```\nstill open")


# ── 2. Break-point priority ─────────────────────────────────

class TestBreakPointPriority:
    def test_paragraph_preferred_over_newline(self):
        text = "Line one.\nLine two.\n\nNew paragraph. More text that goes on."
        pos = _find_best_break(text, 35)
        # Should break at \n\n (paragraph boundary)
        before = text[:pos]
        assert before.endswith('\n\n') or '\n\n' in before

    def test_newline_preferred_over_sentence(self):
        text = "First sentence. Second sentence.\nThird line here and more text."
        pos = _find_best_break(text, 40, [BREAK_NEWLINE, BREAK_SENTENCE, BREAK_HARD])
        before = text[:pos]
        assert before.endswith('\n') or '\n' in before[-3:]

    def test_sentence_break(self):
        text = "First sentence. Second sentence. Third word word word word."
        pos = _find_best_break(text, 45, [BREAK_SENTENCE, BREAK_WHITESPACE, BREAK_HARD])
        before = text[:pos]
        # Should break after a sentence-ending period+space
        assert '. ' in before

    def test_custom_break_preference(self):
        """breakPreference config should be respected."""
        text = "Word word.\n\nParagraph. More words and more."
        # Force whitespace-only preference
        pos = _find_best_break(text, 30, [BREAK_WHITESPACE])
        before = text[:pos]
        # Should break at a whitespace, not necessarily paragraph
        assert before[-1] == ' ' or before.endswith('\n\n')

    def test_hard_break_fallback(self):
        text = "abcdefghijklmnopqrstuvwxyz"  # no whitespace
        pos = _find_best_break(text, 10)
        assert pos == 10  # forced hard break


# ── 3. Coalescing ────────────────────────────────────────────

class TestCoalescing:
    def test_short_blocks_buffered(self):
        """Blocks shorter than minChars should be buffered."""
        config = ChunkerConfig(minChars=200, maxChars=2000)
        chunks = []
        chunker = EmbeddedBlockChunker(config, on_chunk=lambda t, f: chunks.append(t))

        chunker.feed("Short text.")  # 11 chars < 200
        assert len(chunks) == 0, "Should not emit below minChars"

    def test_max_chars_forces_flush(self):
        """Exceeding maxChars should force emission."""
        config = ChunkerConfig(minChars=10, maxChars=50)
        chunks = []
        chunker = EmbeddedBlockChunker(config, on_chunk=lambda t, f: chunks.append(t))

        chunker.feed("A" * 60)
        assert len(chunks) >= 1, "Should emit when exceeding maxChars"

    def test_idle_flush(self):
        """Buffer should flush after idleMs with no new tokens."""
        config = ChunkerConfig(minChars=200, maxChars=2000, idleMs=50)
        chunks = []
        chunker = EmbeddedBlockChunker(config, on_chunk=lambda t, f: chunks.append(t))

        chunker.feed("Hello world")
        chunker._last_feed_time = time.time() - 0.1  # Simulate 100ms idle
        result = chunker.check_idle()
        assert result is not None, "Should flush on idle timeout"

    def test_no_idle_flush_when_recently_fed(self):
        config = ChunkerConfig(minChars=200, maxChars=2000, idleMs=500)
        chunker = EmbeddedBlockChunker(config)

        chunker.feed("Hello")
        result = chunker.check_idle()
        assert result is None, "Should not flush when recently fed"


# ── 4. Channel-specific caps ────────────────────────────────

class TestChannelCaps:
    def test_telegram_4096_hard_cap(self):
        config = ChunkerConfig(channel=CHANNEL_TELEGRAM)
        chunker = EmbeddedBlockChunker(config)
        text = "A" * 5000
        chunks = chunker.split_for_channel(text)
        for chunk in chunks:
            assert len(chunk) <= 4096, f"Telegram chunk exceeds 4096: {len(chunk)}"

    def test_discord_2000_cap(self):
        config = ChunkerConfig(channel=CHANNEL_DISCORD)
        chunker = EmbeddedBlockChunker(config)
        text = "A" * 3000
        chunks = chunker.split_for_channel(text)
        for chunk in chunks:
            assert len(chunk) <= 2000, f"Discord chunk exceeds 2000: {len(chunk)}"

    def test_discord_max_lines(self):
        config = ChunkerConfig(channel=CHANNEL_DISCORD)
        chunker = EmbeddedBlockChunker(config)
        text = "\n".join(f"Line {i}" for i in range(30))
        chunks = chunker.split_for_channel(text)
        for chunk in chunks:
            assert chunk.count('\n') <= 17, f"Discord chunk exceeds 17 lines"

    def test_web_unlimited(self):
        config = ChunkerConfig(channel=CHANNEL_WEB)
        chunker = EmbeddedBlockChunker(config)
        text = "A" * 50000
        chunks = chunker.split_for_channel(text)
        assert len(chunks) == 1, "Web should have no splitting"


# ── 5. Human-like delay ─────────────────────────────────────

class TestHumanDelay:
    def test_no_delay_first_chunk(self):
        config = ChunkerConfig(humanDelay="natural")
        chunker = EmbeddedBlockChunker(config)
        chunker._chunk_count = 1
        delay = chunker.compute_delay()
        assert delay == 0.0, "First chunk should have no delay"

    def test_natural_delay_range(self):
        config = ChunkerConfig(humanDelay="natural", humanDelayMin=0.8, humanDelayMax=2.5)
        chunker = EmbeddedBlockChunker(config)
        chunker._chunk_count = 2  # Not the first chunk

        delays = [chunker.compute_delay() for _ in range(100)]
        assert all(0.8 <= d <= 2.5 for d in delays), \
            f"Delays out of range: min={min(delays)}, max={max(delays)}"
        # Should have some variation (not all identical)
        assert len(set(round(d, 3) for d in delays)) > 1, "Delays should vary"

    def test_delay_off(self):
        config = ChunkerConfig(humanDelay="off")
        chunker = EmbeddedBlockChunker(config)
        chunker._chunk_count = 5
        assert chunker.compute_delay() == 0.0

    def test_custom_delay_range(self):
        config = ChunkerConfig(humanDelay="custom", humanDelayMin=0.1, humanDelayMax=0.3)
        chunker = EmbeddedBlockChunker(config)
        chunker._chunk_count = 3
        delays = [chunker.compute_delay() for _ in range(50)]
        assert all(0.1 <= d <= 0.3 for d in delays)


# ── 6. End-to-end streaming simulation ──────────────────────

class TestEndToEnd:
    def test_full_stream_with_code(self):
        """Simulate streaming a response with code blocks."""
        config = ChunkerConfig(channel=CHANNEL_TELEGRAM, minChars=50, maxChars=200)
        chunks = []
        chunker = EmbeddedBlockChunker(config, on_chunk=lambda t, f: chunks.append(t))

        tokens = [
            "Here's ", "a ", "simple ", "example:\n\n",
            "```python\n", "def ", "hello():\n", "    print('hi')\n", "```\n\n",
            "That's ", "it!"
        ]
        for token in tokens:
            chunker.feed(token)
        chunker.flush()

        full = "".join(chunks)
        expected = "".join(tokens)
        assert full == expected, f"Reconstructed text doesn't match.\nGot: {full!r}\nExpected: {expected!r}"

        # Verify all chunks have balanced fences
        for chunk in chunks:
            assert chunk.count('```') % 2 == 0, f"Unbalanced fence: {chunk!r}"

    def test_flush_returns_remaining(self):
        config = ChunkerConfig(minChars=1000)
        chunker = EmbeddedBlockChunker(config)
        chunker.feed("Small text")
        result = chunker.flush()
        assert result == "Small text"
        assert chunker.buffer == ""
