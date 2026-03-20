"""Task classification and intent-based tool selection.

Extracted from engine.py to reduce God Object anti-pattern.
"""

from __future__ import annotations


from typing import Any, Dict, Optional

from salmalm.constants import (
    INTENT_SHORT_MSG,
    INTENT_COMPLEX_MSG,
    INTENT_CONTEXT_DEPTH,
)


class TaskClassifier:
    """Classify user intent to determine execution strategy."""

    # Intent categories with weighted keywords
    INTENTS = {
        "code": {
            "keywords": [
                "code",
                "코드",
                "implement",
                "구현",
                "function",
                "class",
                "bug",
                "버그",
                "fix",
                "수정",
                "refactor",
                "리팩",
                "debug",
                "디버그",
                "API",
                "server",
                "서버",
                "deploy",
                "배포",
                "build",
                "빌드",
                "개발",
                "코딩",
                "프로그래밍",
            ],
            "tier": 3,
            "thinking": False,
        },
        "analysis": {
            "keywords": [
                "analyze",
                "분석",
                "compare",
                "비교",
                "review",
                "리뷰",
                "audit",
                "감사",
                "security",
                "보안",
                "performance",
                "성능",
                "검토",
                "조사",
                "평가",
                "진단",
            ],
            "tier": 3,
            "thinking": False,
        },
        "creative": {
            "keywords": [
                "write",
                "작성",
                "story",
                "이야기",
                "poem",
                "시",
                "translate",
                "번역",
                "summarize",
                "요약",
                "글",
            ],
            "tier": 2,
            "thinking": False,
        },
        "search": {
            "keywords": [
                "search",
                "검색",
                "find",
                "찾",
                "news",
                "뉴스",
                "latest",
                "최신",
                "weather",
                "날씨",
                "price",
                "가격",
            ],
            "tier": 2,
            "thinking": False,
        },
        "system": {
            "keywords": [
                "file",
                "파일",
                "exec",
                "run",
                "실행",
                "install",
                "설치",
                "process",
                "프로세스",
                "disk",
                "디스크",
                "memory",
                "메모리",
            ],
            "tier": 2,
            "thinking": False,
        },
        "memory": {
            "keywords": ["remember", "기억", "memo", "메모", "record", "기록", "diary", "일지", "learn", "학습"],
            "tier": 1,
            "thinking": False,
        },
        "chat": {"keywords": [], "tier": 1, "thinking": False},
    }

    @classmethod
    def classify(cls, message: str, context_len: int = 0) -> Dict[str, Any]:
        """Classify user message intent and determine processing tier.

        Thin wrapper around :func:`classify_task` for backward compatibility.
        """
        return classify_task(message, context_len=context_len, intents=cls.INTENTS)


def classify_task(
    message: str,
    context_len: int = 0,
    intents: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Classify user message intent and determine processing tier."""
    if intents is None:
        intents = TaskClassifier.INTENTS
    msg = message.lower()
    msg_len = len(message)
    scores = {}
    for intent, info in intents.items():
        score = sum(2 for kw in info["keywords"] if kw in msg)  # type: ignore[attr-defined, misc]
        if intent == "code" and any(c in message for c in ["```", "def ", "class ", "{", "}"]):
            score += 3
        if intent in ("code", "analysis") and "github.com" in msg:
            score += 3
        scores[intent] = score

    best = max(scores, key=scores.get) if any(scores.values()) else "chat"  # type: ignore[arg-type]
    if scores[best] == 0:
        best = "chat"

    info = intents[best]
    # Escalate tier for long/complex messages
    tier = info["tier"]
    if msg_len > INTENT_SHORT_MSG:
        tier = max(tier, 2)  # type: ignore[call-overload]
    if msg_len > INTENT_COMPLEX_MSG or context_len > INTENT_CONTEXT_DEPTH:
        tier = max(tier, 3)  # type: ignore[call-overload]

    # Adaptive thinking budget
    thinking = info["thinking"]
    thinking_budget = 0
    if thinking:
        if msg_len < 300:
            thinking_budget = 5000
        elif msg_len < 1000:
            thinking_budget = 10000
        else:
            thinking_budget = 16000

    return {
        "intent": best,
        "tier": tier,
        "thinking": thinking,
        "thinking_budget": thinking_budget,
        "score": scores[best],
    }


# ── Intent-based tool selection (token optimization) ──
# ── Classifier keyword/intent/emoji data — loaded from classifier_data.json ──
# Data was extracted from inline dicts (880+ lines) to keep this file readable.
# To update keywords, edit salmalm/core/classifier_data.json directly.
import json as _json
import pathlib as _pathlib

def _load_classifier_data():
    _data_file = _pathlib.Path(__file__).parent / "classifier_data.json"
    try:
        return _json.loads(_data_file.read_text(encoding="utf-8"))
    except Exception as _e:
        import logging as _logging
        _logging.getLogger("salmalm").warning("[CLASSIFIER] Failed to load classifier_data.json: %s", _e)
        return {"keyword_tools": {}, "emoji_tools": {}, "intent_tools": {}}

_classifier_data = _load_classifier_data()
INTENT_TOOLS: dict = _classifier_data["intent_tools"]
_KEYWORD_TOOLS: dict = _classifier_data["keyword_tools"]
_EMOJI_TOOLS: dict = _classifier_data["emoji_tools"]

# ── Fallback keywords when classifier_data.json is missing/empty ──
# These ensure critical tool keywords exist even without the JSON file.
_FALLBACK_KEYWORDS = {
    "서브에이전트": ["sub_agent"], "sub_agent": ["sub_agent"],
    "검색": ["web_search"], "실행": ["exec"],
    "파일": ["read_file", "write_file"], "계산": ["python_eval"],
}
for _kw, _tools in _FALLBACK_KEYWORDS.items():
    if _kw not in _KEYWORD_TOOLS:
        _KEYWORD_TOOLS[_kw] = _tools


import re as _re

# ── Time-pattern regex → remind + cron tool injection ────────────────────────
# Matches natural language time expressions in Korean and English
_TIME_PATTERN_RE = _re.compile(
    r"""
      (\d+\s*분\s*후)                             # 5분 후
    | (\d+\s*시간\s*후)                           # 2시간 후
    | (\d+\s*일\s*후)                             # 3일 후
    | (\d+\s*주\s*후)                             # 2주 후
    | (내일\s*(오전|오후|\d)?)                    # 내일 오전 / 내일 9
    | (모레)                                      # 모레
    | (다음\s*주)                                 # 다음 주
    | (이번\s*주)                                 # 이번 주
    | (오늘\s*(오전|오후|\d)?)                    # 오늘 오후
    | (\d{1,2}시\s*(에|쯤|까지|전|후)?)          # 3시에
    | (\d{1,2}:\d{2})                             # 15:30
    | (in\s+\d+\s*(min|hour|day|week|month)s?)    # in 5 minutes
    | (at\s+\d{1,2}(:\d{2})?\s*(am|pm)?)         # at 3pm
    | (remind\s+me)                               # remind me
    | (set\s+(a\s+)?(reminder|alarm|timer))       # set a reminder
    | (알람\s*(맞춰|설정|켜))                     # 알람 맞춰
    | (매일\s*(오전|오후|\d)?)                    # 매일 오전
    | (every\s+(day|week|hour|morning|night))     # every day
    """,
    _re.IGNORECASE | _re.VERBOSE,
)
_TIME_INJECT_TOOLS = ["reminder", "notification", "cron_manage"]

# ── Question-word → web_search injection ─────────────────────────────────────
# When user asks a factual question, inject search tools even if intent == "chat"
_QUESTION_WORDS = [
    # Korean — only specific factual question words (NOT generic "tell me" phrases)
    # Removed: "어떻게", "설명해줘", "가르쳐줘", "알고 싶" → too broad, trigger on code/task questions
    "왜",           # why — factual
    "누가", "누구", # who — factual
    "무엇", "뭐야", "뭔지", "뭐가",  # what is — factual
    "언제",         # when — factual
    "어디서", "어디에", "어디야",     # where — factual
    "뜻이 뭐", "의미가 뭐", "뜻은", "의미는", "정의가", "정의는",  # definition
    # English — only specific factual starters (NOT "explain" / "define" — too broad for code)
    "how do", "how to", "how does",
    "what is", "what are", "what does", "what's", "what was", "what were",
    "why is", "why does", "why are", "why did", "why can't", "why won't",
    "who is", "who are", "who was", "who were", "who made", "who created",
    "when is", "when did", "when was", "when will", "when does",
    "where is", "where are", "where can",
    "which is", "which one", "which are",
    "tell me about",
]
_QUESTION_INJECT_TOOLS = ["web_search", "brave_search", "web_fetch"]


def get_extra_tools(message: str) -> list[str]:
    """Return extra tools based on emoji, time patterns, and question words.

    Called by tool_selector to augment keyword-based tool injection.
    """
    tools: list[str] = []
    # 1. Emoji detection
    for emoji, emoji_tools in _EMOJI_TOOLS.items():
        if emoji in message:
            tools.extend(emoji_tools)
    # 2. Time pattern detection
    if _TIME_PATTERN_RE.search(message):
        tools.extend(_TIME_INJECT_TOOLS)
    # 3. Question word detection → inject search tools
    msg_lower = message.lower()
    if any(qw in msg_lower for qw in _QUESTION_WORDS):
        tools.extend(_QUESTION_INJECT_TOOLS)
    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for t in tools:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


# Dynamic max_tokens per intent
import os as _os

INTENT_MAX_TOKENS = {
    "chat": int(_os.environ.get("SALMALM_MAX_TOKENS_CHAT", "512")),
    "memory": 512,
    "creative": 1024,
    "search": 1024,
    "analysis": 2048,
    "code": int(_os.environ.get("SALMALM_MAX_TOKENS_CODE", "4096")),
    "system": 1024,
}

# Keywords that trigger higher max_tokens
_DETAIL_KEYWORDS = {"자세히", "상세", "detail", "detailed", "verbose", "explain", "설명", "thorough", "구체적"}


_MODEL_DEFAULT_MAX = {
    "anthropic": 8192,
    "openai": 16384,
    "google": 8192,
    "xai": 4096,
}


def _get_dynamic_max_tokens(intent: str, user_message: str, model: str = "") -> int:
    """Return max_tokens based on intent + user request.

    If INTENT_MAX_TOKENS[intent] == 0, use model-provider default (dynamic allocation).
    """
    base = INTENT_MAX_TOKENS.get(intent, 2048)
    if base == 0:
        # Dynamic: use provider default
        provider = model.split("/")[0] if "/" in model else "anthropic"
        base = _MODEL_DEFAULT_MAX.get(provider, 8192)
    msg_lower = user_message.lower()
    # Scale up for detailed requests
    if any(kw in msg_lower for kw in _DETAIL_KEYWORDS):
        return max(base * 2, 8192)
    # Scale up for long input (long question → likely long answer)
    if len(user_message) > 500:
        return max(base, 8192)
    return base


# ── Auto-generated keyword tool mapping ──────────────────────────────────────
# build_keyword_tools_from_registry() generates a base _KEYWORD_TOOLS dict from
# TOOL_DEFINITIONS without manual maintenance.  The returned dict is shallow —
# it maps each tool name and its description keywords to the tool itself.
# The manual _KEYWORD_TOOLS above overrides/extends this for multilingual entries.

def build_keyword_tools_from_registry() -> dict:
    """Auto-generate a keyword→tool mapping from the tool registry.

    Returns a dict {keyword: [tool_name]} derived from:
    1. The tool name itself (underscore-separated words)
    2. Key words extracted from the tool description

    This supplements (not replaces) the hand-curated _KEYWORD_TOOLS entries
    above which carry multilingual (Korean) and domain-specific mappings.
    """
    import re as _re
    try:
        from salmalm.tools.tool_registry import get_all_tool_definitions
        defs = get_all_tool_definitions()
    except Exception:
        return {}

    # Stop-words to ignore when extracting description keywords
    _STOP = frozenset({
        "a", "an", "the", "and", "or", "for", "to", "in", "on", "of", "with",
        "from", "is", "are", "be", "can", "use", "uses", "used", "given",
        "by", "at", "as", "it", "its", "that", "this", "get", "set", "do",
        "any", "all", "via", "per", "not", "no",
    })

    result: dict = {}
    for tool_def in defs:
        name = tool_def.get("name", "")
        if not name:
            continue
        # 1. Register each underscore-separated word of the tool name
        for word in name.split("_"):
            if len(word) > 2 and word not in _STOP:
                result.setdefault(word, [])
                if name not in result[word]:
                    result[word].append(name)
        # 2. Register the full name as a keyword
        result.setdefault(name, [])
        if name not in result[name]:
            result[name].append(name)
        # 3. Extract meaningful words from description
        desc = tool_def.get("description", "")
        words = _re.findall(r"\b[a-zA-Z]{4,}\b", desc)
        for word in words:
            wl = word.lower()
            if wl in _STOP or len(wl) < 4:
                continue
            result.setdefault(wl, [])
            if name not in result[wl]:
                result[wl].append(name)

    return result


def get_merged_keyword_tools() -> dict:
    """Return the merged keyword tool mapping: auto-generated base + manual overrides.

    Manual _KEYWORD_TOOLS entries take precedence (they carry multilingual
    and domain-specific mappings that auto-generation cannot produce).
    """
    merged = build_keyword_tools_from_registry()
    # Manual entries override auto-generated ones
    for kw, tools in _KEYWORD_TOOLS.items():
        merged[kw] = tools
    return merged
