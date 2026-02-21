"""Compaction facade — re-exports from core.py for clean import paths.

Actual implementation remains in core.py to avoid circular imports
(compaction logic uses Session, router, _estimate_tokens, etc.).
TODO(v0.18): Break the circular dependency and move implementation here.
"""
from __future__ import annotations


from typing import Callable, List, Optional


def compact_messages(
    messages: List[dict],
    model: Optional[str] = None,
    session: Optional[object] = None,
    on_status: Optional[Callable] = None,
) -> List[dict]:
    """Multi-stage compaction. Delegates to core.compact_messages."""
    from salmalm.core.core import compact_messages as _impl
    return _impl(messages, model=model, session=session, on_status=on_status)


def compact_session(session_id: str, force: bool = False) -> str:
    """Compact a session's conversation. Delegates to core.compact_session."""
    from salmalm.core.core import compact_session as _impl
    return _impl(session_id, force=force)


def auto_compact_if_needed(session_id: str) -> None:
    """Auto-compact if over token threshold. Delegates to core."""
    from salmalm.core.core import auto_compact_if_needed as _impl
    return _impl(session_id)


def persist_compaction_summary(session_id: str, summary: str) -> None:
    """Save compaction summary. Delegates to core."""
    from salmalm.core.core import _persist_compaction_summary as _impl
    return _impl(session_id, summary)


def restore_compaction_summary(session_id: str) -> Optional[str]:
    """Restore last compaction summary. Delegates to core."""
    from salmalm.core.core import _restore_compaction_summary as _impl
    return _impl(session_id)


# ── Re-exports for backward compatibility ──
from salmalm.core.cost import estimate_tokens  # noqa: F401


def _msg_text(msg: dict) -> str:
    """Extract text content from a message dict."""
    c = msg.get('content', '')
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return ' '.join(p.get('text', '') for p in c if isinstance(p, dict))
    return str(c)


def _importance_score(msg: dict) -> float:
    """Score message importance for compaction prioritization (0-10 scale)."""
    role = msg.get('role', '')
    text = _msg_text(msg).lower()
    if role == 'system':
        return 10.0
    if role == 'tool':
        if 'error' in text[:200]:
            return 3.0
        return 0.5
    # User preference/decision messages
    if any(kw in text for kw in ('always', 'never', 'remember', 'decide', 'conclusion',
                                  'important', 'approved', '항상', '결정', '결론', '기억')):
        return 5.0 if role == 'user' else 4.0
    if role == 'user':
        return 3.0
    return 2.0


def _split_by_importance(messages: List[dict], keep_recent: int = 2) -> tuple:
    """Split messages into (system, old, recent) for compaction.

    Returns (system_msgs, old_msgs_to_summarize, recent_msgs_to_keep).
    """
    system = [m for m in messages if m.get('role') == 'system']
    non_system = [m for m in messages if m.get('role') != 'system']
    if len(non_system) <= keep_recent:
        return system, [], non_system
    recent = non_system[-keep_recent:]
    old = non_system[:-keep_recent]
    return system, old, recent


def _extract_key_facts(messages: List[dict]) -> List[str]:
    """Extract key facts from messages for summary."""
    facts = []
    for m in messages:
        text = _msg_text(m)
        if not text.strip() or len(text) < 10:
            continue
        # Preference/decision indicators
        indicators = ('always', 'never', 'remember', 'must', 'decided', 'conclusion',
                      'result', 'error', 'fixed', 'created', 'deleted', 'updated',
                      'use ', 'prefer', '항상', '결정', '결론', '수정', '생성', '삭제')
        lower = text.lower()
        if any(kw in lower for kw in indicators):
            # Use first 200 chars as the fact
            facts.append(text[:200].strip())
    return facts[:20]


def enhanced_compact(messages: List[dict], target_tokens: int = 4000,
                     max_tokens: int = 0) -> List[dict]:
    """Enhanced compaction using importance scoring."""
    from salmalm.core.cost import estimate_tokens as _et
    limit = target_tokens or max_tokens or 4000
    total = sum(_et(_msg_text(m)) for m in messages)
    if total <= limit:
        return messages
    system, old, recent = _split_by_importance(messages, keep_recent=max(2, len(messages) // 3))
    facts = _extract_key_facts(old)
    summary_msg = {
        'role': 'system',
        'content': f'[Compacted {len(old)} messages]\nKey facts: ' + ('; '.join(facts) if facts else 'None extracted')
    }
    return system + [summary_msg] + recent
