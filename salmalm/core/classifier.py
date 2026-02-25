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
INTENT_TOOLS = {
    "chat": [],
    "memory": [],
    "creative": [],
    "code": [
        "exec",
        "read_file",
        "write_file",
        "edit_file",
        "diff_files",
        "python_eval",
        "sub_agent",
        "system_monitor",
        "skill_manage",
    ],
    "analysis": ["web_search", "web_fetch", "read_file", "rag_search", "python_eval", "exec", "http_request"],
    "search": ["web_search", "web_fetch", "rag_search", "http_request", "brave_search", "brave_context"],
    "system": [
        "exec",
        "read_file",
        "write_file",
        "edit_file",
        "system_monitor",
        "cron_manage",
        "health_check",
        "plugin_manage",
    ],
}

# Extra tools injected by keyword detection in the user message
_KEYWORD_TOOLS = {
    "calendar": ["google_calendar", "calendar_list", "calendar_add", "calendar_delete"],
    "일정": ["google_calendar", "calendar_list", "calendar_add", "calendar_delete"],
    "email": ["gmail", "email_inbox", "email_read", "email_send", "email_search"],
    "메일": ["gmail", "email_inbox", "email_read", "email_send", "email_search"],
    "remind": ["reminder", "notification"],
    "알림": ["reminder", "notification"],
    "알려줘": ["reminder", "notification"],
    "image": ["image_generate", "image_analyze", "screenshot"],
    "이미지": ["image_generate", "image_analyze", "screenshot"],
    "사진": ["image_generate", "image_analyze", "screenshot"],
    "tts": ["tts", "tts_generate"],
    "음성": ["tts", "tts_generate", "stt"],
    "weather": ["weather"],
    "날씨": ["weather"],
    "rss": ["rss_reader"],
    "translate": ["translate"],
    "번역": ["translate"],
    "qr": ["qr_code"],
    "expense": ["expense"],
    "지출": ["expense"],
    "note": ["note"],
    "메모": ["note", "memory_read", "memory_write", "memory_search"],
    "bookmark": ["save_link"],
    "북마크": ["save_link"],
    "pomodoro": ["pomodoro"],
    "routine": ["routine"],
    "briefing": ["briefing"],
    # Web search triggers — ensures brave_search/web_search tools are injected
    # even when overall intent is classified as "chat"
    "검색해": ["brave_search", "web_search", "web_fetch"],
    "조사해": ["brave_search", "web_search", "web_fetch"],
    "알아봐": ["brave_search", "web_search", "web_fetch"],
    "찾아봐": ["brave_search", "web_search", "web_fetch"],
    "찾아줘": ["brave_search", "web_search", "web_fetch"],
    "최신 정보": ["brave_search", "web_search"],
    "최신정보": ["brave_search", "web_search"],
    "최근 동향": ["brave_search", "web_search"],
    "뉴스": ["brave_news", "brave_search", "web_search"],
    "news": ["brave_news", "brave_search", "web_search"],
    "search for": ["brave_search", "web_search", "web_fetch"],
    "look up": ["brave_search", "web_search", "web_fetch"],
    "browser": ["browser"],
    "node": ["node_manage"],
    "mcp": ["mcp_manage"],
    "workflow": ["workflow"],
    "file_index": ["file_index"],
    "clipboard": ["clipboard"],
    "settings": ["ui_control"],
    "설정": ["ui_control"],
    "theme": ["ui_control"],
    "테마": ["ui_control"],
    "dark mode": ["ui_control"],
    "light mode": ["ui_control"],
    "다크모드": ["ui_control"],
    "라이트모드": ["ui_control"],
    "language": ["ui_control"],
    "언어": ["ui_control"],
}

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
