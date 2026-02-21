"""Model selection — single authority for choosing which model handles a message.

LLMRouter handles provider availability/failover only.
All routing decisions flow through select_model().
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Tuple

from salmalm.constants import MODELS as _MODELS

# ── Complexity keywords ──
_SIMPLE_PATTERNS = re.compile(
    r'^(안녕|hi|hello|hey|ㅎㅇ|ㅎㅎ|ㄱㅅ|고마워|감사|ㅋㅋ|ㅎㅎ|ok|lol|yes|no|네|아니|응|ㅇㅇ|뭐해|잘자|굿|bye|잘가|좋아|ㅠㅠ|ㅜㅜ|오|와|대박|진짜|뭐|어|음|흠|뭐야|왜|어떻게|언제|어디|누구|얼마)[\?!？！.\s]*$',
    re.IGNORECASE)
_MODERATE_KEYWORDS = ['분석', '리뷰', '요약', '코드', 'code', 'analyze', 'review', 'summarize',
                      'summary', 'compare', '비교', 'refactor', '리팩', 'debug', '디버그',
                      'explain', '설명', '번역', 'translate']
_COMPLEX_KEYWORDS = ['설계', '아키텍처', 'architecture', 'design', 'system design',
                     'from scratch', '처음부터', '전체', 'migration', '마이그레이션']

# ── Model name corrections ──
_MODEL_NAME_FIXES = {
    'claude-haiku-3.5-20241022': 'claude-haiku-4-5-20251001',
    'anthropic/claude-haiku-3.5-20241022': 'anthropic/claude-haiku-4-5-20251001',
    'claude-haiku-4-5-20250414': 'claude-haiku-4-5-20251001',
    'claude-sonnet-4-20250514': 'claude-sonnet-4-6',
    'anthropic/claude-sonnet-4-20250514': 'anthropic/claude-sonnet-4-6',
    'gpt-5.3-codex': 'gpt-5.2-codex',
    'openai/gpt-5.3-codex': 'openai/gpt-5.2-codex',
    'grok-4': 'grok-4-0709',
    'xai/grok-4': 'xai/grok-4-0709',
}

# ── Routing config ──
_ROUTING_CONFIG_FILE = Path.home() / '.salmalm' / 'routing.json'


def fix_model_name(model: str) -> str:
    """Correct outdated model names to actual API IDs."""
    return _MODEL_NAME_FIXES.get(model, model)


def load_routing_config() -> dict:
    """Load user's model routing config. Returns {simple, moderate, complex} model IDs."""
    defaults = {'simple': '', 'moderate': '', 'complex': ''}
    try:
        if _ROUTING_CONFIG_FILE.exists():
            cfg = json.loads(_ROUTING_CONFIG_FILE.read_text(encoding='utf-8'))
            for k in ('simple', 'moderate', 'complex'):
                if k in cfg and cfg[k]:
                    defaults[k] = cfg[k]
    except Exception:
        pass
    return defaults


def save_routing_config(config: dict) -> None:
    """Save user's model routing config."""
    try:
        _ROUTING_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _ROUTING_CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding='utf-8')
    except Exception:
        pass


def select_model(message: str, session) -> Tuple[str, str]:
    """Select optimal model based on message complexity.

    Returns (model_id, complexity_level) where complexity is 'simple'|'moderate'|'complex'|'manual'.
    Respects session-level model_override (from /model command).
    """
    override = getattr(session, 'model_override', None)
    if override and override != 'auto':
        if override == 'haiku':
            return _MODELS['haiku'], 'simple'
        elif override == 'sonnet':
            return _MODELS['sonnet'], 'moderate'
        elif override == 'opus':
            return _MODELS['opus'], 'complex'
        else:
            return override, 'manual'

    rc = load_routing_config()
    _default_fallback = getattr(session, '_default_model', None) or _MODELS.get('sonnet', '')
    for k in ('simple', 'moderate', 'complex'):
        if not rc[k]:
            rc[k] = _default_fallback
    msg_lower = message.lower()
    msg_len = len(message)

    if getattr(session, 'thinking_enabled', False):
        return rc['complex'], 'complex'

    if msg_len > 500:
        return rc['complex'], 'complex'
    for kw in _COMPLEX_KEYWORDS:
        if kw in msg_lower:
            return rc['complex'], 'complex'

    if '```' in message or 'def ' in message or 'class ' in message:
        return rc['moderate'], 'moderate'
    for kw in _MODERATE_KEYWORDS:
        if kw in msg_lower:
            return rc['moderate'], 'moderate'

    if msg_len < 50 and _SIMPLE_PATTERNS.match(message.strip()):
        return rc['simple'], 'simple'
    if msg_len < 50:
        return rc['simple'], 'simple'

    return rc['moderate'], 'moderate'
