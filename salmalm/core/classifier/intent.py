"""Intent classification logic.

Extracted from salmalm.core.classifier.
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
                "api",
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
                "찾기",  # "찾" alone over-matches (찾은, 값을찾 etc.) — use 2+ char form
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
