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

    # ── 한글 누락 보완 ─────────────────────────────────────────────────────────

    # what is / who is / how to / where is → 웹 검색 자연어
    "뭐야":         ["brave_search", "web_search"],
    "뭔가요":       ["brave_search", "web_search"],
    "뭔지":         ["brave_search", "web_search"],
    "뭔데":         ["brave_search", "web_search"],
    "뭐임":         ["brave_search", "web_search"],
    "뭔가":         ["brave_search", "web_search"],
    "누구야":       ["brave_search", "web_search"],
    "누구임":       ["brave_search", "web_search"],
    "누군지":       ["brave_search", "web_search"],
    "누군가요":     ["brave_search", "web_search"],
    "방법":         ["brave_search", "web_search", "web_fetch"],
    "어떻게":       ["brave_search", "web_search"],
    "하는 법":      ["brave_search", "web_search"],
    "하는 방법":    ["brave_search", "web_search"],
    "어디야":       ["brave_search", "web_search"],
    "어디에":       ["brave_search", "web_search"],
    "어디 있어":    ["brave_search", "web_search"],
    "어디임":       ["brave_search", "web_search"],
    "정보 알려줘":  ["brave_search", "web_search"],
    "알려줘":       ["brave_search", "web_search", "reminder", "notification"],
    "알려주세요":   ["brave_search", "web_search"],
    "언제":         ["brave_search", "web_search"],
    "왜":           ["brave_search", "web_search"],
    "어때":         ["brave_search", "web_search", "weather"],

    # URL / 링크 열기
    "주소":         ["web_fetch", "browser"],
    "링크 열어줘":  ["web_fetch", "browser"],
    "열어줘":       ["web_fetch", "browser", "read_file"],
    "웹 열어줘":    ["web_fetch", "browser"],

    # 파일 자연어 동사형
    "파일 보여줘":  ["read_file"],
    "파일 열어줘":  ["read_file"],
    "파일 만들어줘": ["write_file"],
    "파일 고쳐줘":  ["edit_file"],
    "파일 바꿔줘":  ["edit_file"],
    "파일 수정해줘": ["edit_file"],
    "다른 점":      ["diff_files"],
    "차이점":       ["diff_files"],
    "뭐가 달라":    ["diff_files"],

    # 코드 자연어 동사형
    "돌려줘":       ["exec", "python_eval"],
    "실행해줘":     ["exec", "python_eval"],
    "코드 짜줘":    ["python_eval", "exec"],
    "코드 써줘":    ["python_eval", "exec"],
    "프로그램 실행": ["exec"],
    "계산해줘":     ["python_eval"],
    "셸":           ["exec"],
    "쉘":           ["exec"],
    "배시":         ["exec"],
    "샌드박스":     ["sandbox_exec"],
    "격리 실행":    ["sandbox_exec"],
    "정규 표현식":  ["regex_test"],

    # 시스템 자연어
    "CPU 사용률":   ["system_monitor"],
    "CPU 사용량":   ["system_monitor"],
    "메모리 얼마나": ["system_monitor"],
    "메모리 부족":  ["system_monitor"],
    "디스크 용량":  ["system_monitor"],
    "헬스체크":     ["health_check"],
    "시스템 점검":  ["health_check", "system_monitor"],
    "서비스 점검":  ["health_check"],
    "서버 점검":    ["health_check", "system_monitor"],

    # 이미지 자연어
    "사진 만들어줘": ["image_generate"],
    "이미지 만들어줘": ["image_generate"],
    "그림 만들어줘": ["image_generate"],
    "사진 봐줘":    ["image_analyze"],
    "사진 분석해줘": ["image_analyze"],
    "이미지 봐줘":  ["image_analyze"],
    "화면 찍어줘":  ["screenshot"],
    "사진 찍어줘":  ["screenshot"],

    # TTS/STT 자연어
    "음성 합성":    ["tts", "tts_generate"],
    "TTS 변환":     ["tts", "tts_generate"],
    "문자를 음성으로": ["tts", "tts_generate"],
    "소리로 들려줘": ["tts", "tts_generate"],
    "음성으로 읽어줘": ["tts", "tts_generate"],
    "불러줘":       ["tts", "tts_generate"],
    "음성 텍스트":  ["stt"],
    "음성 받아쓰기": ["stt"],
    "녹음 텍스트":  ["stt"],

    # 날씨 자연어
    "우산 필요해":  ["weather"],
    "비 올까":      ["weather"],
    "비 오냐":      ["weather"],
    "날씨 어때":    ["weather"],
    "오늘 날씨":    ["weather"],
    "내일 날씨":    ["weather"],
    "몇 도야":      ["weather"],
    "춥냐":         ["weather"],
    "더워":         ["weather"],

    # 번역 자연어
    "번역해줘":     ["translate"],
    "번역해주세요": ["translate"],
    "다른 언어로":  ["translate"],
    "외국어로":     ["translate"],
    "영어로 번역":  ["translate"],
    "한국어로 번역": ["translate"],

    # 메모/기억 자연어
    "적어줘":       ["note", "memory_write"],
    "메모해줘":     ["note", "memory_write"],
    "기억해뒀어":   ["memory_read"],
    "기억나":       ["memory_read", "memory_search"],
    "뭐 기억해":    ["memory_read", "memory_search"],
    "기록 찾아줘":  ["memory_search"],
    "노트 써줘":    ["note"],
    "노트":         ["note"],

    # 지출/가계부 자연어
    "돈 썼어":      ["expense"],
    "돈 쓴":        ["expense"],
    "영수증":       ["expense"],
    "지출 얼마":    ["expense"],

    # 사용량/비용 자연어
    "얼마나 사용":  ["usage_report"],
    "API 비용":     ["usage_report"],
    "비용 확인":    ["usage_report"],
    "토큰 얼마":    ["usage_report"],
    "사용 내역":    ["usage_report"],

    # 크론/예약 자연어
    "정기 실행":    ["cron_manage"],
    "자동 반복":    ["cron_manage"],
    "주기 설정":    ["cron_manage"],
    "매일":         ["cron_manage", "routine"],
    "매주":         ["cron_manage", "routine"],

    # 서브 에이전트 자연어
    "병렬 처리":    ["sub_agent"],
    "백그라운드에서": ["sub_agent"],
    "동시에 여러":  ["sub_agent"],

    # RAG / 문서 자연어
    "문서에서 찾아":  ["rag_search", "file_index"],
    "파일에서 검색":  ["rag_search", "file_index"],
    "파일에서 찾아":  ["rag_search", "file_index"],
    "PDF 읽어줘":     ["rag_search", "read_file"],
    "PDF 분석":       ["rag_search", "read_file"],

    # 브라우저/캔버스 자연어
    "크롬":         ["browser"],
    "웹 브라우저":  ["browser"],
    "시각화":       ["canvas"],
    "그래프 그려줘": ["canvas"],
    "차트 그려줘":  ["canvas"],

    # 노드/기기 자연어
    "연결된 기기":  ["node_manage"],
    "페어링된 기기": ["node_manage"],
    "기기 목록":    ["node_manage"],

    # 클립보드 자연어
    "복사한 내용":  ["clipboard"],
    "붙여넣기 내용": ["clipboard"],
    "클립보드에":   ["clipboard"],

    # 워크플로우/자동화 자연어
    "자동화":       ["workflow", "cron_manage"],
    "자동화 흐름":  ["workflow"],
    "작업 흐름":    ["workflow"],
    "파이프라인":   ["workflow"],

    # 스킬/플러그인 자연어
    "기능 추가":    ["skill_manage", "plugin_manage"],
    "새 기능":      ["skill_manage"],
    "확장 기능":    ["plugin_manage"],

    # 알림/타이머 추가 자연어
    "몇 분 뒤":     ["reminder", "notification"],
    "잊지 않게":    ["reminder", "notification"],
    "리마인더":     ["reminder", "notification"],
    "미리 알려줘":  ["reminder", "notification"],

    # 브리핑/정리 자연어
    "오늘 뭐 있어": ["briefing", "google_calendar"],
    "오늘 요약":    ["briefing"],
    "일일 요약":    ["briefing"],
    "아침 정리":    ["briefing"],
    "하루 정리":    ["briefing"],

    # 이메일 추가 자연어
    "메일 왔어":    ["gmail", "email_inbox"],
    "메일 확인":    ["gmail", "email_inbox"],
    "이메일 보내줘": ["gmail", "email_send"],
    "답장":         ["gmail", "email_send", "email_read"],

    # 일정 추가 자연어
    "오늘 일정":    ["google_calendar", "calendar_list"],
    "이번 주 일정": ["google_calendar", "calendar_list"],
    "일정 추가":    ["google_calendar", "calendar_add"],
    "일정 잡아줘":  ["google_calendar", "calendar_add"],
    "회의 잡아줘":  ["google_calendar", "calendar_add"],

    # ── 요약 (Summarize / TL;DR) ───────────────────────────────────────────────
    "summarize":        ["web_fetch", "rag_search"],
    "요약":             ["web_fetch", "rag_search"],
    "요약해줘":         ["web_fetch", "rag_search"],
    "요약해주세요":     ["web_fetch", "rag_search"],
    "정리해줘":         ["web_fetch", "rag_search", "briefing"],
    "핵심만":           ["web_fetch", "rag_search"],
    "줄여줘":           ["web_fetch", "rag_search"],
    "한 줄로":          ["web_fetch", "rag_search"],
    "간단히":           ["web_fetch", "rag_search"],
    "tldr":             ["web_fetch", "rag_search"],
    "tl;dr":            ["web_fetch", "rag_search"],
    "what's this":      ["web_fetch", "rag_search"],
    "what is this":     ["web_fetch", "rag_search"],
    "이게 뭐야":        ["web_fetch", "rag_search", "brave_search"],
    "이게 뭔지":        ["web_fetch", "rag_search", "brave_search"],
    "이 링크":          ["web_fetch", "rag_search"],
    "이 url":           ["web_fetch", "rag_search"],
    "이 URL":           ["web_fetch", "rag_search"],
    "링크 내용":        ["web_fetch", "rag_search"],
    "링크 요약":        ["web_fetch", "rag_search"],
    "링크 뭐야":        ["web_fetch", "rag_search"],
    "이 비디오":        ["web_fetch", "stt"],
    "이 영상":          ["web_fetch", "stt"],
    "동영상 요약":      ["web_fetch", "rag_search", "stt"],
    "유튜브 요약":      ["web_fetch", "rag_search", "stt"],
    "유튜브":           ["web_fetch", "brave_search"],
    "youtube":          ["web_fetch", "brave_search"],
    "이 글":            ["web_fetch", "rag_search"],
    "this article":     ["web_fetch", "rag_search"],
    "this link":        ["web_fetch", "rag_search"],
    "this url":         ["web_fetch", "rag_search"],
    "this video":       ["web_fetch", "stt"],
    "summarize this":   ["web_fetch", "rag_search"],
    "summarize url":    ["web_fetch", "rag_search"],
    "article":          ["web_fetch", "rag_search"],
    "기사 요약":        ["web_fetch", "rag_search"],

    # ── 설명 / 정의 (Explain / Define) ────────────────────────────────────────
    "explain":          ["brave_search", "web_search"],
    "설명해줘":         ["brave_search", "web_search"],
    "설명해주세요":     ["brave_search", "web_search"],
    "뭔지 알려줘":      ["brave_search", "web_search"],
    "어떻게 작동해":    ["brave_search", "web_search"],
    "어떻게 돼":        ["brave_search", "web_search"],
    "define":           ["brave_search", "web_search"],
    "definition":       ["brave_search", "web_search"],
    "뜻":               ["brave_search", "web_search"],
    "의미":             ["brave_search", "web_search"],
    "차이가 뭐야":      ["brave_search", "web_search", "diff_files"],
    "compare":          ["brave_search", "web_search", "diff_files"],
    "비교해줘":         ["brave_search", "web_search", "diff_files"],
    "vs":               ["brave_search", "web_search"],
    "어느게 나아":      ["brave_search", "web_search"],
    "추천해줘":         ["brave_search", "web_search"],
    "추천":             ["brave_search", "web_search"],
    "recommend":        ["brave_search", "web_search"],

    # ── 금융 / 주식 / 환율 (Finance) ─────────────────────────────────────────
    "환율":             ["brave_search", "web_search"],
    "exchange rate":    ["brave_search", "web_search"],
    "달러":             ["brave_search", "python_eval"],
    "원화":             ["brave_search", "python_eval"],
    "주식":             ["brave_search", "web_search"],
    "stock":            ["brave_search", "web_search"],
    "stock price":      ["brave_search", "web_search"],
    "코인":             ["brave_search", "web_search"],
    "crypto":           ["brave_search", "web_search"],
    "비트코인":         ["brave_search", "web_search"],
    "bitcoin":          ["brave_search", "web_search"],
    "이더리움":         ["brave_search", "web_search"],
    "ethereum":         ["brave_search", "web_search"],
    "가격":             ["brave_search", "web_search"],
    "price":            ["brave_search", "web_search"],
    "얼마야":           ["brave_search", "web_search", "expense"],
    "얼마예요":         ["brave_search", "web_search"],
    "최저가":           ["brave_search", "web_search"],
    "할인":             ["brave_search", "web_search"],
    "쇼핑":             ["brave_search", "web_search"],
    "shopping":         ["brave_search", "web_search"],
    "투자":             ["brave_search", "web_search"],
    "펀드":             ["brave_search", "web_search"],
    "금리":             ["brave_search", "web_search"],
    "이자":             ["brave_search", "web_search"],
    "interest rate":    ["brave_search", "web_search"],

    # ── 시간 / 날짜 (Time / Date) ─────────────────────────────────────────────
    "몇 시야":          ["python_eval"],
    "지금 시간":        ["python_eval"],
    "몇 시":            ["python_eval"],
    "what time":        ["python_eval"],
    "날짜":             ["python_eval"],
    "오늘 날짜":        ["python_eval"],
    "today's date":     ["python_eval"],
    "날짜 계산":        ["python_eval"],
    "며칠 남았":        ["python_eval"],
    "시간대":           ["python_eval", "brave_search"],
    "time zone":        ["python_eval", "brave_search"],
    "timezone":         ["python_eval"],
    "d-day":            ["python_eval"],
    "디데이":           ["python_eval"],
    "몇 주 후":         ["python_eval"],
    "몇 달 후":         ["python_eval"],

    # ── 단위 변환 / 계산기 (Conversion / Calculator) ─────────────────────────
    "변환":             ["python_eval"],
    "convert":          ["python_eval"],
    "단위 변환":        ["python_eval"],
    "unit conversion":  ["python_eval"],
    "킬로그램":         ["python_eval"],
    "파운드":           ["python_eval"],
    "섭씨":             ["python_eval"],
    "화씨":             ["python_eval"],
    "celsius":          ["python_eval"],
    "fahrenheit":       ["python_eval"],
    "kilometer":        ["python_eval"],
    "mile":             ["python_eval"],
    "마일":             ["python_eval"],
    "계산기":           ["python_eval"],
    "calculator":       ["python_eval"],
    "더하기":           ["python_eval"],
    "빼기":             ["python_eval"],
    "곱하기":           ["python_eval"],
    "나누기":           ["python_eval"],
    "퍼센트":           ["python_eval"],
    "percent":          ["python_eval"],
    "제곱근":           ["python_eval"],
    "sqrt":             ["python_eval"],
    "수식":             ["python_eval"],
    "formula":          ["python_eval"],

    # ── 장소 / 지도 (Places / Maps) ───────────────────────────────────────────
    "장소":             ["brave_search", "web_search"],
    "places":           ["brave_search", "web_search"],
    "근처":             ["brave_search", "web_search"],
    "nearby":           ["brave_search", "web_search"],
    "맛집":             ["brave_search", "web_search"],
    "restaurant":       ["brave_search", "web_search"],
    "레스토랑":         ["brave_search", "web_search"],
    "카페":             ["brave_search", "web_search"],
    "cafe":             ["brave_search", "web_search"],
    "지도":             ["brave_search", "web_search"],
    "map":              ["brave_search", "web_search"],
    "길 찾기":          ["brave_search", "web_search"],
    "navigation":       ["brave_search", "web_search"],
    "어떻게 가":        ["brave_search", "web_search"],
    "거리":             ["brave_search", "web_search", "python_eval"],
    "교통":             ["brave_search", "web_search"],
    "대중교통":         ["brave_search", "web_search"],
    "버스":             ["brave_search", "web_search"],
    "지하철":           ["brave_search", "web_search"],
    "여행":             ["brave_search", "web_search"],
    "travel":           ["brave_search", "web_search"],
    "항공권":           ["brave_search", "web_search"],
    "flight":           ["brave_search", "web_search"],
    "호텔":             ["brave_search", "web_search"],
    "hotel":            ["brave_search", "web_search"],

    # ── 엔터테인먼트 (Entertainment) ──────────────────────────────────────────
    "음악":             ["brave_search", "web_search"],
    "노래":             ["brave_search", "web_search"],
    "song":             ["brave_search", "web_search"],
    "music":            ["brave_search", "web_search"],
    "틀어줘":           ["brave_search", "web_search"],
    "재생":             ["brave_search", "web_search"],
    "play":             ["brave_search", "web_search"],
    "spotify":          ["brave_search", "web_search"],
    "영화":             ["brave_search", "web_search"],
    "movie":            ["brave_search", "web_search"],
    "드라마":           ["brave_search", "web_search"],
    "series":           ["brave_search", "web_search"],
    "넷플릭스":         ["brave_search", "web_search"],
    "netflix":          ["brave_search", "web_search"],
    "게임":             ["brave_search", "web_search"],
    "game":             ["brave_search", "web_search"],
    "책":               ["brave_search", "web_search"],
    "book":             ["brave_search", "web_search"],
    "소설":             ["brave_search", "web_search"],
    "웹툰":             ["brave_search", "web_search"],
    "manhwa":           ["brave_search", "web_search"],
    "anime":            ["brave_search", "web_search"],
    "애니":             ["brave_search", "web_search"],
    "만화":             ["brave_search", "web_search"],
    "podcast":          ["web_fetch", "brave_search"],
    "팟캐스트":         ["web_fetch", "brave_search"],

    # ── 건강 / 의료 (Health / Medical) ───────────────────────────────────────
    "건강":             ["brave_search", "web_search"],
    "health":           ["brave_search", "web_search"],
    "증상":             ["brave_search", "web_search"],
    "symptom":          ["brave_search", "web_search"],
    "의약품":           ["brave_search", "web_search"],
    "약":               ["brave_search", "web_search"],
    "병원":             ["brave_search", "web_search"],
    "hospital":         ["brave_search", "web_search"],
    "칼로리":           ["brave_search", "python_eval"],
    "calorie":          ["brave_search", "python_eval"],
    "nutrition":        ["brave_search", "web_search"],
    "영양":             ["brave_search", "web_search"],
    "다이어트":         ["brave_search", "web_search"],
    "diet":             ["brave_search", "web_search"],
    "운동":             ["brave_search", "web_search"],
    "exercise":         ["brave_search", "web_search"],
    "수면":             ["brave_search", "web_search"],
    "sleep":            ["brave_search", "web_search"],

    # ── 소셜 / 뉴스미디어 (Social / Media) ───────────────────────────────────
    "트위터":           ["brave_news", "brave_search"],
    "twitter":          ["brave_news", "brave_search"],
    "인스타":           ["brave_search", "web_search"],
    "instagram":        ["brave_search", "web_search"],
    "페이스북":         ["brave_search", "web_search"],
    "facebook":         ["brave_search", "web_search"],
    "틱톡":             ["brave_search", "web_search"],
    "tiktok":           ["brave_search", "web_search"],
    "레딧":             ["brave_search", "web_search"],
    "reddit":           ["brave_search", "web_search"],
    "트렌드":           ["brave_news", "brave_search"],
    "trending":         ["brave_news", "brave_search"],
    "화제":             ["brave_news", "brave_search"],
    "핫한":             ["brave_news", "brave_search"],
    "viral":            ["brave_news", "brave_search"],

    # ── 개발 / 코드 (Dev / Code) ──────────────────────────────────────────────
    "debug":            ["python_eval", "exec"],
    "디버그":           ["python_eval", "exec"],
    "버그":             ["python_eval", "exec"],
    "에러":             ["python_eval", "exec", "brave_search"],
    "오류":             ["python_eval", "exec", "brave_search"],
    "error":            ["python_eval", "exec", "brave_search"],
    "exception":        ["python_eval", "exec"],
    "traceback":        ["python_eval", "exec"],
    "fix this":         ["edit_file", "python_eval"],
    "고쳐":             ["edit_file", "python_eval"],
    "리뷰해줘":         ["python_eval", "exec"],
    "코드 리뷰":        ["python_eval", "exec"],
    "review":           ["python_eval", "exec", "brave_search"],
    "리팩토링":         ["edit_file", "exec"],
    "refactor":         ["edit_file", "exec"],
    "테스트":           ["python_eval", "exec"],
    "test":             ["python_eval", "exec"],
    "unittest":         ["python_eval", "exec"],
    "단위 테스트":      ["python_eval", "exec"],
    "git":              ["exec"],
    "깃":               ["exec"],
    "commit":           ["exec"],
    "push":             ["exec"],
    "pull":             ["exec"],
    "github":           ["exec", "brave_search"],
    "깃허브":           ["exec", "brave_search"],
    "docker":           ["exec"],
    "도커":             ["exec"],
    "database":         ["exec", "python_eval"],
    "db":               ["exec", "python_eval"],
    "데이터베이스":     ["exec", "python_eval"],
    "sql":              ["exec", "python_eval"],
    "쿼리":             ["exec", "python_eval"],
    "api test":         ["http_request"],
    "api 테스트":       ["http_request"],
    "swagger":          ["http_request", "web_fetch"],

    # ── 작성 / 초안 (Writing / Draft) ────────────────────────────────────────
    "써줘":             ["write_file", "note"],
    "작성해줘":         ["write_file", "note"],
    "초안":             ["write_file", "note"],
    "draft":            ["write_file", "note"],
    "write":            ["write_file", "note"],
    "create":           ["write_file", "exec"],
    "만들어":           ["write_file", "exec", "image_generate"],
    "보고서":           ["write_file", "note"],
    "report":           ["write_file", "note"],
    "이메일 초안":      ["note", "gmail"],
    "이력서":           ["write_file", "note"],
    "문서 작성":        ["write_file", "note"],
    "편지":             ["write_file", "note"],
    "letter":           ["write_file", "note"],

    # ── 보안 / 암호화 (Security) ─────────────────────────────────────────────
    "비밀번호":         ["hash_text", "brave_search"],
    "password":         ["hash_text"],
    "패스워드":         ["hash_text"],
    "암호화":           ["hash_text", "exec"],
    "encrypt":          ["hash_text", "exec"],
    "복호화":           ["exec"],
    "decrypt":          ["exec"],
    "보안":             ["hash_text", "brave_search"],
    "security":         ["hash_text", "brave_search"],
    "취약점":           ["brave_search", "exec"],
    "vulnerability":    ["brave_search", "exec"],
    "인증":             ["brave_search", "exec"],
    "auth":             ["brave_search", "exec"],
    "token":            ["exec", "python_eval"],
    "jwt":              ["exec", "python_eval"],
    "ssh":              ["exec"],

    # ── 압축 / 포맷 (Compression / Format) ───────────────────────────────────
    "압축":             ["exec"],
    "compress":         ["exec"],
    "압축 해제":        ["exec"],
    "decompress":       ["exec"],
    "zip":              ["exec"],
    "tar":              ["exec"],
    "unzip":            ["exec"],
    "포맷":             ["python_eval", "exec"],
    "format":           ["python_eval", "exec"],
    "인코딩":           ["python_eval", "exec"],
    "encoding":         ["python_eval", "exec"],
    "base64":           ["python_eval", "exec"],
    "csv":              ["python_eval", "exec"],
    "xml":              ["python_eval", "exec"],
    "yaml":             ["python_eval", "exec"],
    "markdown":         ["write_file", "note"],

    # ── brave_context (심층 검색) ─────────────────────────────────────────────
    "deep search":      ["brave_context", "brave_search"],
    "심층 검색":        ["brave_context", "brave_search"],
    "자세히 검색":      ["brave_context", "brave_search"],
    "상세 검색":        ["brave_context", "brave_search"],
    "detailed search":  ["brave_context", "brave_search"],

    # ── exec_session (지속 세션) ──────────────────────────────────────────────
    "interactive":      ["exec_session", "exec"],
    "지속 세션":        ["exec_session"],
    "대화형 실행":      ["exec_session"],
    "repl":             ["exec_session", "python_eval"],
}

# ── Emoji → tool injection ────────────────────────────────────────────────────
# When user message contains these emoji, inject corresponding tools
_EMOJI_TOOLS: dict[str, list[str]] = {
    # Screenshot / Image capture
    "📸": ["screenshot", "screen_capture"],
    "🖼️": ["screenshot", "screen_capture"],
    "📷": ["screenshot", "screen_capture"],
    "🤳": ["screenshot", "screen_capture"],
    # Calendar / Schedule
    "📅": ["google_calendar", "calendar_list", "calendar_add"],
    "📆": ["google_calendar", "calendar_list", "calendar_add"],
    "🗓️": ["google_calendar", "calendar_list", "calendar_add"],
    # Search / Web
    "🔍": ["web_search", "brave_search"],
    "🔎": ["web_search", "brave_search"],
    "🌐": ["web_search", "web_fetch"],
    "🌍": ["web_search", "web_fetch"],
    "🌎": ["web_search", "web_fetch"],
    # TTS / Audio
    "🎵": ["tts"],
    "🎶": ["tts"],
    "🔊": ["tts"],
    "📢": ["tts"],
    # STT / Microphone
    "🎙️": ["stt"],
    "🎤": ["stt"],
    # File operations
    "📁": ["read_file", "list_files"],
    "📂": ["read_file", "list_files"],
    "📄": ["read_file", "write_file"],
    # Notes / Writing
    "📝": ["note", "write_file"],
    "✏️": ["note", "write_file"],
    "📋": ["note", "write_file"],
    "📖": ["read_file", "rag_search"],
    # Reminder / Timer
    "⏰": ["reminder", "notification"],
    "⏱️": ["reminder", "notification"],
    "🔔": ["reminder", "notification"],
    "⏲️": ["reminder", "notification", "cron_manage"],
    # Weather
    "🌤️": ["weather"],
    "⛅": ["weather"],
    "☁️": ["weather"],
    "🌧️": ["weather"],
    "🌡️": ["weather"],
    "☀️": ["weather"],
    "❄️": ["weather"],
    # Email
    "📧": ["gmail", "email_inbox", "email_send"],
    "✉️": ["gmail", "email_inbox", "email_send"],
    "📨": ["gmail", "email_inbox"],
    "📩": ["gmail", "email_send"],
    # Finance / Price
    "💰": ["brave_search"],
    "💹": ["brave_search"],
    "💲": ["brave_search"],
    "🪙": ["brave_search"],
    # Data / Chart
    "📊": ["python_eval", "brave_search"],
    "📈": ["python_eval", "brave_search"],
    "📉": ["python_eval", "brave_search"],
    # Code / Terminal
    "💻": ["exec", "python_eval"],
    "🖥️": ["exec", "system_monitor"],
    "🐍": ["python_eval", "exec"],
    "⚙️": ["exec", "system_monitor"],
    "🔧": ["exec", "system_monitor"],
    "🛠️": ["exec", "system_monitor"],
    # Security
    "🔐": ["hash_text", "exec"],
    "🔒": ["hash_text"],
    "🔑": ["exec", "hash_text"],
    # Bookmark / Link
    "📌": ["note", "bookmark"],
    "🔖": ["note", "bookmark"],
    "🔗": ["web_fetch", "web_search"],
    # Trash / Delete
    "🗑️": ["exec"],
    # Map / Location
    "🗺️": ["web_search", "web_fetch"],
    "📍": ["web_search"],
    # Document / Clipboard
    "🗒️": ["note", "write_file"],
    # Summarize / Document (OpenClaw summarize skill)
    "🧾": ["web_fetch", "rag_search"],
    # Coding agent / Plugin (OpenClaw coding-agent skill)
    "🧩": ["exec", "python_eval", "write_file"],
    # GitHub / Code review (OpenClaw github skill)
    "🐙": ["exec", "web_fetch"],
}


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
