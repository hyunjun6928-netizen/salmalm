"""Tests for core/compaction.py (enhanced compaction)."""
import pytest


def test_estimate_tokens_empty():
    from salmalm.core.compaction import estimate_tokens
    assert estimate_tokens("") == 0


def test_estimate_tokens_english():
    from salmalm.core.compaction import estimate_tokens
    t = estimate_tokens("hello world this is a test")
    assert 5 < t < 15


def test_estimate_tokens_korean():
    from salmalm.core.compaction import estimate_tokens
    t = estimate_tokens("안녕하세요 세계")
    assert t >= 7  # Each Korean char ~1 token


def test_importance_score_system():
    from salmalm.core.compaction import _importance_score
    assert _importance_score({"role": "system", "content": "x"}) == 10.0


def test_importance_score_tool_low():
    from salmalm.core.compaction import _importance_score
    score = _importance_score({"role": "tool", "content": "result data"})
    assert score < 1.0


def test_importance_score_tool_error():
    from salmalm.core.compaction import _importance_score
    score = _importance_score({"role": "tool", "content": "Error: not found"})
    assert score > 0.5


def test_importance_score_user_decision():
    from salmalm.core.compaction import _importance_score
    score = _importance_score({"role": "user", "content": "Always use Korean for comments"})
    assert score >= 3.0


def test_split_by_importance():
    from salmalm.core.compaction import _split_by_importance
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "old1"},
        {"role": "assistant", "content": "old2"},
        {"role": "user", "content": "recent1"},
        {"role": "assistant", "content": "recent2"},
    ]
    sys, old, recent = _split_by_importance(msgs, keep_recent=2)
    assert len(sys) == 1
    assert len(recent) == 2
    assert len(old) == 2


def test_extract_key_facts():
    from salmalm.core.compaction import _extract_key_facts
    msgs = [
        {"role": "user", "content": "Always remember to use TypeScript for all new code"},
        {"role": "assistant", "content": "short"},
        {"role": "assistant", "content": "```python\ndef foo(): pass\n```" + "x" * 500},
    ]
    facts = _extract_key_facts(msgs)
    assert len(facts) >= 1
    assert any("TypeScript" in f for f in facts)


def test_enhanced_compact_short_noop():
    from salmalm.core.compaction import enhanced_compact
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    result = enhanced_compact(msgs, target_tokens=1000)
    assert len(result) == 3  # No compaction needed


def test_msg_text_string():
    from salmalm.core.compaction import _msg_text
    assert _msg_text({"content": "hello"}) == "hello"


def test_msg_text_list():
    from salmalm.core.compaction import _msg_text
    msg = {"content": [{"type": "text", "text": "hello"}, {"type": "image"}]}
    assert "hello" in _msg_text(msg)
