"""Tests for Stage B/C token overflow recovery (session_manager.recover_overflow)."""

import pytest


def _make_msgs(n_pairs: int, chars_each: int = 100) -> list:
    """Build n_pairs user+assistant pairs with ~chars_each chars each."""
    msgs = [{"role": "system", "content": "System prompt."}]
    for i in range(n_pairs):
        msgs.append({"role": "user", "content": "U" * chars_each})
        msgs.append({"role": "assistant", "content": "A" * chars_each})
    return msgs


class TestEstimateTotalTokens:
    def test_basic(self):
        from salmalm.core.session_manager import _estimate_total_tokens
        msgs = [{"role": "user", "content": "a" * 400}]
        assert _estimate_total_tokens(msgs) == 100   # 400 / 4

    def test_list_content(self):
        from salmalm.core.session_manager import _estimate_total_tokens
        msgs = [{"role": "user", "content": [{"type": "text", "text": "a" * 400}]}]
        assert _estimate_total_tokens(msgs) == 100

    def test_empty(self):
        from salmalm.core.session_manager import _estimate_total_tokens
        assert _estimate_total_tokens([]) == 0


class TestStripOrphanToolResults:
    def test_removes_orphan(self):
        from salmalm.core.session_manager import _strip_orphan_tool_results
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "no_such_id", "content": "result"}
            ]},
        ]
        result = _strip_orphan_tool_results(msgs)
        # User message with only orphan tool results should be dropped
        assert len(result) == 0

    def test_keeps_paired(self):
        from salmalm.core.session_manager import _strip_orphan_tool_results
        msgs = [
            {"role": "assistant", "content": [{"type": "tool_use", "id": "tid1", "name": "exec", "input": {}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tid1", "content": "ok"},
            ]},
        ]
        result = _strip_orphan_tool_results(msgs)
        assert len(result) == 2   # Both kept

    def test_keeps_non_tool_user(self):
        from salmalm.core.session_manager import _strip_orphan_tool_results
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        result = _strip_orphan_tool_results(msgs)
        assert len(result) == 2


class TestRecoverOverflow:
    def test_no_recovery_needed(self):
        from salmalm.core.session_manager import recover_overflow
        # 3 pairs × 200 chars × 2 roles = ~300 tokens; window = 10_000
        msgs = _make_msgs(3, 100)
        result, stats = recover_overflow(msgs, 10_000)
        assert stats["stage"] == "A"
        assert stats["pairs_dropped"] == 0

    def test_stage_b_drops_pairs(self):
        from salmalm.core.session_manager import recover_overflow
        # 20 pairs × 2 messages × 2000 chars = 80_000 chars → ~20_000 tokens
        # window = 5_000 tokens, target = 4_250 tokens
        msgs = _make_msgs(20, 2000)
        result, stats = recover_overflow(msgs, 5_000)
        assert stats["stage"] == "B"
        assert stats["pairs_dropped"] > 0
        assert stats["estimated_tokens_after"] <= int(5_000 * 0.85)

    def test_stage_c_critical(self):
        from salmalm.core.session_manager import recover_overflow, _OVERFLOW_STAGE_C_PAIRS
        # Huge messages so even keeping 8 pairs overflows a tiny window
        msgs = _make_msgs(20, 10_000)   # 400k chars total
        result, stats = recover_overflow(msgs, 1_000)   # 1k token window
        assert stats["stage"] == "C"
        # System message preserved
        sys_msgs = [m for m in result if m.get("role") == "system"]
        assert len(sys_msgs) == 1

    def test_system_messages_always_kept(self):
        from salmalm.core.session_manager import recover_overflow
        msgs = _make_msgs(20, 5000)
        result, stats = recover_overflow(msgs, 1_000)
        sys_msgs = [m for m in result if m.get("role") == "system"]
        assert len(sys_msgs) == 1   # Always preserved

    def test_recent_pairs_preserved(self):
        from salmalm.core.session_manager import recover_overflow, _OVERFLOW_STAGE_C_PAIRS
        msgs = _make_msgs(20, 5000)
        result, stats = recover_overflow(msgs, 1_000)
        # At Stage C, last _OVERFLOW_STAGE_C_PAIRS pairs should remain
        asst_msgs = [m for m in result if m.get("role") == "assistant"]
        assert len(asst_msgs) >= _OVERFLOW_STAGE_C_PAIRS

    def test_orphan_tool_results_stripped(self):
        """When pairs are dropped, orphaned tool_result blocks must be removed."""
        from salmalm.core.session_manager import recover_overflow, _OVERFLOW_STAGE_C_PAIRS
        # Build enough pairs that Stage B/C actually drops some
        # Pair 0 has a big tool_result; we need len(pairs) > _OVERFLOW_STAGE_C_PAIRS
        msgs = [{"role": "system", "content": "sys"}]
        # First pair: user + assistant with tool_use + tool_result user message
        msgs += [
            {"role": "user", "content": "q0"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "exec", "input": {}}
            ]},
        ]
        # Tool result as a separate user message (Anthropic style, between pairs)
        msgs.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 4000}
        ]})
        # Fill up more pairs so total > _OVERFLOW_STAGE_C_PAIRS
        for i in range(1, _OVERFLOW_STAGE_C_PAIRS + 3):
            msgs += [
                {"role": "user", "content": f"q{i}"},
                {"role": "assistant", "content": "a" * 100},
            ]
        # Window too small to keep all pairs → Stage B must drop the first pair(s)
        result, stats = recover_overflow(msgs, 1_000)
        assert stats["stage"] in ("B", "C"), f"Expected pruning, got stage={stats['stage']}"
        # If the assistant with tool_use t1 was dropped, t1 must not appear in results
        asst_tool_use_ids = set()
        for m in result:
            if m.get("role") == "assistant":
                c = m.get("content", [])
                if isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            asst_tool_use_ids.add(b.get("id", ""))
        for m in result:
            if isinstance(m.get("content"), list):
                for b in m["content"]:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        tid = b.get("tool_use_id", "")
                        assert tid in asst_tool_use_ids, (
                            f"Orphan tool_result leaked: tool_use_id={tid} not in {asst_tool_use_ids}"
                        )

    def test_does_not_mutate_input(self):
        from salmalm.core.session_manager import recover_overflow
        msgs = _make_msgs(10, 2000)
        original_len = len(msgs)
        recover_overflow(msgs, 2_000)
        assert len(msgs) == original_len   # Input unchanged
