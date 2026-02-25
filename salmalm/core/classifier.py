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
    # ── Calendar ──────────────────────────────────────────────────────────────
    "calendar":     ["google_calendar", "calendar_list", "calendar_add", "calendar_delete"],
    "일정":         ["google_calendar", "calendar_list", "calendar_add", "calendar_delete"],
    "캘린더":       ["google_calendar", "calendar_list", "calendar_add", "calendar_delete"],
    "schedule":     ["google_calendar", "calendar_list", "calendar_add", "calendar_delete"],
    "스케줄":       ["google_calendar", "calendar_list", "calendar_add", "calendar_delete"],
    "약속":         ["google_calendar", "calendar_list", "calendar_add"],
    "회의":         ["google_calendar", "calendar_list", "calendar_add"],
    "미팅":         ["google_calendar", "calendar_list", "calendar_add"],

    # ── Email ─────────────────────────────────────────────────────────────────
    "email":        ["gmail", "email_inbox", "email_read", "email_send", "email_search"],
    "메일":         ["gmail", "email_inbox", "email_read", "email_send", "email_search"],
    "이메일":       ["gmail", "email_inbox", "email_read", "email_send", "email_search"],
    "gmail":        ["gmail", "email_inbox", "email_read", "email_send", "email_search"],
    "받은 편지함":  ["gmail", "email_inbox"],
    "inbox":        ["gmail", "email_inbox"],
    "메일 보내":    ["gmail", "email_send"],
    "메일 읽":      ["gmail", "email_read", "email_inbox"],

    # ── Reminder / Notification ───────────────────────────────────────────────
    "remind":       ["reminder", "notification"],
    "reminder":     ["reminder", "notification"],
    "알림":         ["reminder", "notification"],
    "알람":         ["reminder", "notification"],
    "alarm":        ["reminder", "notification"],
    "timer":        ["reminder", "notification"],
    "타이머":       ["reminder", "notification"],
    "나중에 알":    ["reminder", "notification"],
    "분 후":        ["reminder", "notification"],
    "시간 후":      ["reminder", "notification"],
    "내일":         ["reminder", "google_calendar", "calendar_list"],
    "알려줘":       ["reminder", "notification"],

    # ── Web Search ────────────────────────────────────────────────────────────
    "search":       ["brave_search", "web_search", "web_fetch"],
    "검색":         ["brave_search", "web_search", "web_fetch"],
    "검색해":       ["brave_search", "web_search", "web_fetch"],
    "검색해줘":     ["brave_search", "web_search", "web_fetch"],
    "조사":         ["brave_search", "web_search", "web_fetch"],
    "조사해":       ["brave_search", "web_search", "web_fetch"],
    "조사해줘":     ["brave_search", "web_search", "web_fetch"],
    "알아봐":       ["brave_search", "web_search", "web_fetch"],
    "알아봐줘":     ["brave_search", "web_search", "web_fetch"],
    "찾아봐":       ["brave_search", "web_search", "web_fetch"],
    "찾아줘":       ["brave_search", "web_search", "web_fetch"],
    "찾아봐줘":     ["brave_search", "web_search", "web_fetch"],
    "구글":         ["brave_search", "web_search"],
    "google":       ["brave_search", "web_search"],
    "최신 정보":    ["brave_search", "web_search"],
    "최신정보":     ["brave_search", "web_search"],
    "최근 동향":    ["brave_search", "web_search"],
    "최근 소식":    ["brave_search", "web_search"],
    "최신":         ["brave_search", "web_search"],
    "지금":         ["brave_search", "web_search"],
    "현재":         ["brave_search", "web_search"],
    "오늘":         ["brave_search", "web_search"],
    "what is":      ["brave_search", "web_search"],
    "who is":       ["brave_search", "web_search"],
    "how to":       ["brave_search", "web_search", "web_fetch"],
    "where is":     ["brave_search", "web_search"],
    "search for":   ["brave_search", "web_search", "web_fetch"],
    "look up":      ["brave_search", "web_search", "web_fetch"],
    "find info":    ["brave_search", "web_search", "web_fetch"],
    "뉴스":         ["brave_news", "brave_search", "web_search"],
    "news":         ["brave_news", "brave_search", "web_search"],
    "속보":         ["brave_news", "brave_search"],
    "이미지 검색":  ["brave_images", "brave_search"],

    # ── Web Fetch / URL ───────────────────────────────────────────────────────
    "fetch":        ["web_fetch", "http_request"],
    "가져와":       ["web_fetch", "web_search"],
    "불러와":       ["web_fetch", "web_search"],
    "url":          ["web_fetch", "http_request"],
    "링크":         ["web_fetch", "save_link"],
    "웹사이트":     ["web_fetch", "browser"],
    "사이트":       ["web_fetch", "browser"],
    "페이지":       ["web_fetch", "browser"],
    "http":         ["http_request", "web_fetch"],
    "api 호출":     ["http_request"],
    "curl":         ["http_request"],
    "post 요청":    ["http_request"],

    # ── File Operations ───────────────────────────────────────────────────────
    "파일":         ["read_file", "write_file", "edit_file"],
    "file":         ["read_file", "write_file", "edit_file"],
    "읽어줘":       ["read_file", "tts", "tts_generate"],
    "파일 읽":      ["read_file"],
    "파일 써":      ["write_file"],
    "파일 저장":    ["write_file"],
    "파일 수정":    ["edit_file"],
    "파일 편집":    ["edit_file"],
    "read file":    ["read_file"],
    "write file":   ["write_file"],
    "edit file":    ["edit_file"],
    "저장":         ["write_file", "note"],
    "폴더":         ["read_file", "file_index"],
    "디렉토리":     ["read_file", "file_index"],
    "directory":    ["read_file", "file_index"],
    "diff":         ["diff_files"],
    "비교":         ["diff_files"],
    "파일 비교":    ["diff_files"],
    "file index":   ["file_index"],
    "파일 인덱스":  ["file_index"],
    "인덱싱":       ["file_index"],

    # ── Code / Execution ──────────────────────────────────────────────────────
    "실행":         ["exec", "python_eval"],
    "run":          ["exec", "sandbox_exec"],
    "execute":      ["exec", "sandbox_exec"],
    "python":       ["python_eval", "exec"],
    "파이썬":       ["python_eval"],
    "코드 실행":    ["python_eval", "exec"],
    "code":         ["python_eval", "exec"],
    "코드":         ["python_eval", "exec"],
    "계산":         ["python_eval"],
    "calculate":    ["python_eval"],
    "eval":         ["python_eval"],
    "스크립트":     ["exec", "python_eval"],
    "script":       ["exec", "sandbox_exec"],
    "터미널":       ["exec"],
    "terminal":     ["exec"],
    "shell":        ["exec"],
    "bash":         ["exec"],
    "명령어":       ["exec"],
    "커맨드":       ["exec"],
    "sandbox":      ["sandbox_exec"],
    "regex":        ["regex_test"],
    "정규식":       ["regex_test"],
    "regexp":       ["regex_test"],
    "패턴 매칭":    ["regex_test"],
    "json":         ["json_query"],
    "json 파싱":    ["json_query"],
    "json 쿼리":    ["json_query"],
    "hash":         ["hash_text"],
    "해시":         ["hash_text"],
    "md5":          ["hash_text"],
    "sha":          ["hash_text"],

    # ── System Monitoring ─────────────────────────────────────────────────────
    "system":       ["system_monitor", "health_check"],
    "시스템":       ["system_monitor"],
    "cpu":          ["system_monitor"],
    "memory usage": ["system_monitor"],
    "메모리 사용":  ["system_monitor"],
    "디스크":       ["system_monitor"],
    "disk":         ["system_monitor"],
    "모니터링":     ["system_monitor"],
    "monitor":      ["system_monitor"],
    "프로세스":     ["system_monitor"],
    "process":      ["system_monitor"],
    "서버 상태":    ["health_check", "system_monitor"],
    "health":       ["health_check"],
    "상태 확인":    ["health_check"],

    # ── Image / Screenshot ────────────────────────────────────────────────────
    "image":        ["image_generate", "image_analyze", "screenshot"],
    "이미지":       ["image_generate", "image_analyze", "screenshot"],
    "사진":         ["image_analyze", "screenshot"],
    "그림":         ["image_generate"],
    "그려줘":       ["image_generate"],
    "그려":         ["image_generate"],
    "draw":         ["image_generate"],
    "generate image": ["image_generate"],
    "이미지 생성":  ["image_generate"],
    "이미지 분석":  ["image_analyze"],
    "analyze image": ["image_analyze"],
    "screenshot":   ["screenshot"],
    "스크린샷":     ["screenshot"],
    "화면 캡처":    ["screenshot"],
    "캡처":         ["screenshot"],

    # ── TTS / STT / Voice ─────────────────────────────────────────────────────
    "tts":          ["tts", "tts_generate"],
    "음성":         ["tts", "tts_generate", "stt"],
    "말해줘":       ["tts", "tts_generate"],
    "소리내어":     ["tts", "tts_generate"],
    "낭독":         ["tts", "tts_generate"],
    "읽어줘":       ["tts", "tts_generate"],
    "speak":        ["tts", "tts_generate"],
    "read aloud":   ["tts", "tts_generate"],
    "text to speech": ["tts", "tts_generate"],
    "stt":          ["stt"],
    "받아쓰기":     ["stt"],
    "음성 인식":    ["stt"],
    "transcribe":   ["stt"],
    "speech to text": ["stt"],

    # ── Weather ───────────────────────────────────────────────────────────────
    "weather":      ["weather"],
    "날씨":         ["weather"],
    "온도":         ["weather"],
    "temperature":  ["weather"],
    "비":           ["weather"],
    "눈":           ["weather"],
    "기온":         ["weather"],
    "forecast":     ["weather"],
    "예보":         ["weather"],
    "강수":         ["weather"],

    # ── Translation ───────────────────────────────────────────────────────────
    "translate":    ["translate"],
    "번역":         ["translate"],
    "translation":  ["translate"],
    "영어로":       ["translate"],
    "한국어로":     ["translate"],
    "일본어로":     ["translate"],
    "중국어로":     ["translate"],

    # ── Memory / Notes ────────────────────────────────────────────────────────
    "note":         ["note"],
    "메모":         ["note", "memory_write"],
    "기록":         ["note", "memory_write"],
    "기억":         ["memory_read", "memory_write", "memory_search"],
    "remember":     ["memory_read", "memory_write"],
    "기억해줘":     ["memory_write"],
    "저장해줘":     ["memory_write", "note"],
    "기록해줘":     ["memory_write", "note"],
    "기억 검색":    ["memory_search", "memory_read"],
    "memory":       ["memory_read", "memory_write", "memory_search"],
    "bookmark":     ["save_link"],
    "북마크":       ["save_link"],
    "링크 저장":    ["save_link"],
    "나중에 읽":    ["save_link"],
    "save link":    ["save_link"],

    # ── RSS ───────────────────────────────────────────────────────────────────
    "rss":          ["rss_reader"],
    "피드":         ["rss_reader"],
    "구독":         ["rss_reader"],
    "feed":         ["rss_reader"],

    # ── Expense / Finance ─────────────────────────────────────────────────────
    "expense":      ["expense"],
    "지출":         ["expense"],
    "가계부":       ["expense"],
    "지출 기록":    ["expense"],
    "소비":         ["expense"],
    "지출 내역":    ["expense"],

    # ── QR Code ───────────────────────────────────────────────────────────────
    "qr":           ["qr_code"],
    "qr코드":       ["qr_code"],
    "qr 코드":      ["qr_code"],
    "qr code":      ["qr_code"],

    # ── Pomodoro / Routine ────────────────────────────────────────────────────
    "pomodoro":     ["pomodoro"],
    "포모도로":     ["pomodoro"],
    "뽀모도로":     ["pomodoro"],
    "집중 타이머":  ["pomodoro"],
    "집중 모드":    ["pomodoro"],
    "routine":      ["routine"],
    "루틴":         ["routine"],
    "반복 작업":    ["routine"],
    "습관":         ["routine"],
    "habit":        ["routine"],

    # ── Briefing / Summary ────────────────────────────────────────────────────
    "briefing":     ["briefing"],
    "브리핑":       ["briefing"],
    "일일 브리핑":  ["briefing"],
    "오늘 정리":    ["briefing"],
    "데일리":       ["briefing"],
    "daily summary": ["briefing"],

    # ── RAG / Document Search ─────────────────────────────────────────────────
    "rag":          ["rag_search", "file_index"],
    "문서 검색":    ["rag_search", "file_index"],
    "문서":         ["rag_search", "read_file"],
    "pdf":          ["rag_search", "read_file"],
    "knowledge":    ["rag_search"],
    "지식 베이스":  ["rag_search"],

    # ── Usage / Stats ─────────────────────────────────────────────────────────
    "usage":        ["usage_report"],
    "사용량":       ["usage_report"],
    "비용":         ["usage_report"],
    "cost":         ["usage_report"],
    "통계":         ["usage_report"],
    "얼마나 썼":    ["usage_report"],
    "토큰":         ["usage_report"],

    # ── Cron / Scheduling ─────────────────────────────────────────────────────
    "cron":         ["cron_manage"],
    "크론":         ["cron_manage"],
    "예약":         ["cron_manage", "reminder"],
    "예약 작업":    ["cron_manage"],
    "scheduled":    ["cron_manage"],
    "자동 실행":    ["cron_manage"],

    # ── Sub-agent / Delegation ────────────────────────────────────────────────
    "sub-agent":    ["sub_agent"],
    "subagent":     ["sub_agent"],
    "서브 에이전트": ["sub_agent"],
    "대리":         ["sub_agent"],
    "위임":         ["sub_agent"],
    "백그라운드 작업": ["sub_agent"],

    # ── Skill / Plugin Management ─────────────────────────────────────────────
    "skill":        ["skill_manage"],
    "스킬":         ["skill_manage"],
    "plugin":       ["plugin_manage"],
    "플러그인":     ["plugin_manage"],

    # ── MCP / Workflow / Mesh ─────────────────────────────────────────────────
    "mcp":          ["mcp_manage"],
    "workflow":     ["workflow"],
    "워크플로우":   ["workflow"],
    "mesh":         ["mesh"],
    "메쉬":         ["mesh"],

    # ── Browser / Canvas ──────────────────────────────────────────────────────
    "browser":      ["browser"],
    "브라우저":     ["browser"],
    "canvas":       ["canvas"],
    "캔버스":       ["canvas"],
    "차트":         ["canvas"],
    "chart":        ["canvas"],
    "그래프":       ["canvas"],

    # ── Node Management ───────────────────────────────────────────────────────
    "node":         ["node_manage"],
    "노드":         ["node_manage"],
    "기기":         ["node_manage"],
    "device":       ["node_manage"],

    # ── Clipboard ─────────────────────────────────────────────────────────────
    "clipboard":    ["clipboard"],
    "클립보드":     ["clipboard"],
    "복사":         ["clipboard"],
    "붙여넣기":     ["clipboard"],

    # ── UI / Settings ─────────────────────────────────────────────────────────
    "settings":     ["ui_control"],
    "설정":         ["ui_control"],
    "theme":        ["ui_control"],
    "테마":         ["ui_control"],
    "dark mode":    ["ui_control"],
    "light mode":   ["ui_control"],
    "다크모드":     ["ui_control"],
    "라이트모드":   ["ui_control"],
    "language":     ["ui_control"],
    "언어":         ["ui_control"],
    "폰트":         ["ui_control"],
    "font":         ["ui_control"],
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
