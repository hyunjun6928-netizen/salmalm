"""System Prompt Variables (시스템 프롬프트 변수) — LobeChat style."""
from __future__ import annotations

from datetime import datetime

from salmalm.constants import KST, VERSION


def substitute_prompt_variables(text: str, session_id: str = '',
                                model: str = '', user: str = '') -> str:
    now = datetime.now(KST)
    replacements = {
        '{{date}}': now.strftime('%Y-%m-%d'),
        '{{time}}': now.strftime('%H:%M:%S'),
        '{{datetime}}': now.strftime('%Y-%m-%d %H:%M'),
        '{{user}}': user or 'user',
        '{{model}}': model or 'auto',
        '{{session}}': session_id or 'default',
        '{{version}}': VERSION,
        '{{weekday}}': now.strftime('%A'),
        '{{weekday_kr}}': ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일'][now.weekday()],
    }
    for var, val in replacements.items():
        text = text.replace(var, val)
    return text
