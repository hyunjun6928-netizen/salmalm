"""Conversation Summary Card (대화 요약 카드) — BIG-AGI style."""
from __future__ import annotations

from typing import Dict, Optional


def get_summary_card(session_id: str) -> Optional[Dict]:
    from salmalm.core import get_session

    session = get_session(session_id)
    msgs = session.messages

    user_msgs = [m for m in msgs if m.get('role') == 'user' and isinstance(m.get('content'), str)]
    asst_msgs = [m for m in msgs if m.get('role') == 'assistant']

    if len(user_msgs) < 3:
        return None

    system_msg = next((m for m in msgs if m.get('role') == 'system'), None)
    summary = None
    if system_msg:
        content = system_msg.get('content', '')
        marker = '## Conversation Summary'
        if marker in content:
            summary = content.split(marker, 1)[1].split('\n\n')[0].strip()
            summary = summary[:500]

    if not summary:
        topics = []
        for m in user_msgs[:5]:
            text = m.get('content', '')[:100]
            if text:
                topics.append(text)
        if topics:
            summary = ' → '.join(t[:50] for t in topics[:3])

    if not summary:
        return None

    total_chars = sum(len(str(m.get('content', ''))) for m in msgs)
    token_estimate = total_chars // 4

    return {
        'summary': summary,
        'message_count': len(user_msgs) + len(asst_msgs),
        'token_estimate': token_estimate,
        'first_topic': user_msgs[0].get('content', '')[:100] if user_msgs else '',
    }
