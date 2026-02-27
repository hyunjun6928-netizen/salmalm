"""SalmAlm Web — WebFeaturesMixin routes."""


class WebFeaturesMixin:
    GET_ROUTES = {
        "/api/features": "_get_features",
    }

    """Mixin for web_features routes."""

    def _get_features(self):
        """Get features."""
        cats = [
            {
                "id": "core",
                "icon": "🤖",
                "title": "Core AI",
                "title_kr": "핵심 AI",
                "features": [
                    {
                        "name": "Multi-model Routing",
                        "name_kr": "멀티 모델 라우팅",
                        "desc": "Auto-routes to haiku/sonnet/opus based on complexity",
                        "desc_kr": "복잡도에 따라 haiku/sonnet/opus 자동 선택",
                        "command": "/model",
                    },
                    {
                        "name": "Extended Thinking",
                        "name_kr": "확장 사고",
                        "desc": "Deep reasoning for complex tasks",
                        "desc_kr": "복잡한 작업을 위한 심층 추론",
                        "command": "/thinking on",
                    },
                    {
                        "name": "Context Compaction",
                        "name_kr": "컨텍스트 압축",
                        "desc": "Auto-summarize long sessions",
                        "desc_kr": "긴 세션 자동 요약",
                        "command": "/compact",
                    },
                    {
                        "name": "Prompt Caching",
                        "name_kr": "프롬프트 캐싱",
                        "desc": "Anthropic cache for cost savings",
                        "desc_kr": "Anthropic 캐시로 비용 절감",
                        "command": "/context",
                    },
                    {
                        "name": "Self-Evolving Prompt",
                        "name_kr": "자가 진화 프롬프트",
                        "desc": "AI learns your preferences over time",
                        "desc_kr": "대화할수록 선호도 자동 학습",
                        "command": "/evolve status",
                    },
                    {
                        "name": "Mood-Aware Response",
                        "name_kr": "기분 감지 응답",
                        "desc": "Adjusts tone based on your emotion",
                        "desc_kr": "감정에 따라 톤 자동 조절",
                        "command": "/mood on",
                    },
                    {
                        "name": "A/B Split Response",
                        "name_kr": "A/B 분할 응답",
                        "desc": "Two perspectives on one question",
                        "desc_kr": "하나의 질문에 두 관점 동시 응답",
                        "command": "/split",
                    },
                ],
            },
            {
                "id": "tools",
                "icon": "🔧",
                "title": "Tools",
                "title_kr": "도구",
                "features": [
                    {
                        "name": "Web Search",
                        "name_kr": "웹 검색",
                        "desc": "Search the internet",
                        "desc_kr": "인터넷 검색",
                    },
                    {
                        "name": "Code Execution",
                        "name_kr": "코드 실행",
                        "desc": "Run code with sandbox protection",
                        "desc_kr": "샌드박스 보호 하에 코드 실행",
                        "command": "/bash",
                    },
                    {
                        "name": "File Operations",
                        "name_kr": "파일 작업",
                        "desc": "Read, write, edit files",
                        "desc_kr": "파일 읽기/쓰기/편집",
                    },
                    {
                        "name": "Browser Automation",
                        "name_kr": "브라우저 자동화",
                        "desc": "Control Chrome via CDP",
                        "desc_kr": "Chrome DevTools Protocol 제어",
                        "command": "/screen",
                    },
                    {
                        "name": "Image Vision",
                        "name_kr": "이미지 분석",
                        "desc": "Analyze images with AI",
                        "desc_kr": "AI로 이미지 분석",
                    },
                    {
                        "name": "TTS / STT",
                        "name_kr": "음성 입출력",
                        "desc": "Text-to-speech and speech-to-text",
                        "desc_kr": "텍스트↔음성 변환",
                    },
                    {
                        "name": "PDF Extraction",
                        "name_kr": "PDF 추출",
                        "desc": "Extract text from PDFs",
                        "desc_kr": "PDF에서 텍스트 추출",
                    },
                ],
            },
            {
                "id": "personal",
                "icon": "👤",
                "title": "Personal Assistant",
                "title_kr": "개인 비서",
                "features": [
                    {
                        "name": "Daily Briefing",
                        "name_kr": "데일리 브리핑",
                        "desc": "Morning/evening digest",
                        "desc_kr": "아침/저녁 종합 브리핑",
                        "command": "/life",
                    },
                    {
                        "name": "Smart Reminders",
                        "name_kr": "스마트 리마인더",
                        "desc": "Natural language time parsing",
                        "desc_kr": "자연어 시간 파싱",
                    },
                    {
                        "name": "Expense Tracker",
                        "name_kr": "가계부",
                        "desc": "Track spending by category",
                        "desc_kr": "카테고리별 지출 추적",
                    },
                    {
                        "name": "Pomodoro Timer",
                        "name_kr": "포모도로 타이머",
                        "desc": "25min focus sessions",
                        "desc_kr": "25분 집중 세션",
                    },
                    {
                        "name": "Notes & Links",
                        "name_kr": "메모 & 링크",
                        "desc": "Save and search notes/links",
                        "desc_kr": "메모와 링크 저장/검색",
                    },
                    {
                        "name": "Routines",
                        "name_kr": "루틴",
                        "desc": "Daily habit tracking",
                        "desc_kr": "일일 습관 추적",
                    },
                    {
                        "name": "Google Calendar",
                        "name_kr": "구글 캘린더",
                        "desc": "View, add, delete events",
                        "desc_kr": "일정 보기/추가/삭제",
                    },
                    {
                        "name": "Gmail",
                        "name_kr": "지메일",
                        "desc": "Read, send, search emails",
                        "desc_kr": "이메일 읽기/보내기/검색",
                    },
                    {
                        "name": "Life Dashboard",
                        "name_kr": "인생 대시보드",
                        "desc": "All-in-one life overview",
                        "desc_kr": "원페이지 인생 현황판",
                        "command": "/life",
                    },
                ],
            },
            {
                "id": "unique",
                "icon": "✨",
                "title": "Unique Features",
                "title_kr": "독자 기능",
                "features": [
                    {
                        "name": "Thought Stream",
                        "name_kr": "생각 스트림",
                        "desc": "Quick thought timeline with tags",
                        "desc_kr": "해시태그 기반 생각 타임라인",
                        "command": "/think",
                    },
                    {
                        "name": "Time Capsule",
                        "name_kr": "타임캡슐",
                        "desc": "Messages to your future self",
                        "desc_kr": "미래의 나에게 보내는 메시지",
                        "command": "/capsule",
                    },
                    {
                        "name": "Dead Man's Switch",
                        "name_kr": "데드맨 스위치",
                        "desc": "Emergency actions on inactivity",
                        "desc_kr": "비활동 시 긴급 조치",
                        "command": "/deadman",
                    },
                    {
                        "name": "Shadow Mode",
                        "name_kr": "분신술",
                        "desc": "AI replies in your style when away",
                        "desc_kr": "부재 시 내 말투로 대리 응답",
                        "command": "/shadow on",
                    },
                    {
                        "name": "Encrypted Vault",
                        "name_kr": "비밀 금고",
                        "desc": "Double-encrypted private chat",
                        "desc_kr": "이중 암호화 비밀 대화",
                        "command": "/vault open",
                    },
                    {
                        "name": "Agent-to-Agent",
                        "name_kr": "AI간 통신",
                        "desc": "Negotiate with other SalmAlm instances",
                        "desc_kr": "다른 SalmAlm과 자동 협상",
                        "command": "/a2a",
                    },
                ],
            },
            {
                "id": "infra",
                "icon": "⚙️",
                "title": "Infrastructure",
                "title_kr": "인프라",
                "features": [
                    {
                        "name": "Workflow Engine",
                        "name_kr": "워크플로우 엔진",
                        "desc": "Multi-step automation pipelines",
                        "desc_kr": "다단계 자동화 파이프라인",
                        "command": "/workflow",
                    },
                    {
                        "name": "MCP Marketplace",
                        "name_kr": "MCP 마켓",
                        "desc": "One-click MCP server install",
                        "desc_kr": "MCP 서버 원클릭 설치",
                        "command": "/mcp catalog",
                    },
                    {
                        "name": "Plugin System",
                        "name_kr": "플러그인",
                        "desc": "Extend with custom plugins",
                        "desc_kr": "커스텀 플러그인으로 확장",
                    },
                    {
                        "name": "Multi-Agent",
                        "name_kr": "다중 에이전트",
                        "desc": "Isolated sub-agents for parallel work",
                        "desc_kr": "병렬 작업용 격리 서브에이전트",
                        "command": "/subagents",
                    },
                    {
                        "name": "Sandboxing",
                        "name_kr": "샌드박싱",
                        "desc": "Docker/subprocess isolation",
                        "desc_kr": "Docker/subprocess 격리 실행",
                    },
                    {
                        "name": "OAuth Auth",
                        "name_kr": "OAuth 인증",
                        "desc": "Anthropic/OpenAI subscription auth",
                        "desc_kr": "API 키 없이 구독 인증",
                        "command": "/oauth",
                    },
                    {
                        "name": "Prompt Caching",
                        "name_kr": "프롬프트 캐싱",
                        "desc": "Reduce API costs with caching",
                        "desc_kr": "캐싱으로 API 비용 절감",
                        "command": "/context",
                    },
                ],
            },
            {
                "id": "channels",
                "icon": "📱",
                "title": "Channels",
                "title_kr": "채널",
                "features": [
                    {
                        "name": "Web UI",
                        "name_kr": "웹 UI",
                        "desc": "Full-featured web interface",
                        "desc_kr": "풀기능 웹 인터페이스",
                    },
                    {
                        "name": "Telegram",
                        "name_kr": "텔레그램",
                        "desc": "Bot with topics, reactions, groups",
                        "desc_kr": "토픽/반응/그룹 지원 봇",
                    },
                    {
                        "name": "Discord",
                        "name_kr": "디스코드",
                        "desc": "Bot with threads and reactions",
                        "desc_kr": "스레드/반응 지원 봇",
                    },
                    {
                        "name": "Slack",
                        "name_kr": "슬랙",
                        "desc": "Event API + Web API",
                        "desc_kr": "Event API + Web API",
                    },
                    {
                        "name": "PWA",
                        "name_kr": "PWA",
                        "desc": "Install as desktop/mobile app",
                        "desc_kr": "데스크톱/모바일 앱 설치",
                    },
                ],
            },
            {
                "id": "commands",
                "icon": "⌨️",
                "title": "Commands",
                "title_kr": "명령어",
                "features": [
                    {"name": "/help", "desc": "Show help", "desc_kr": "도움말"},
                    {
                        "name": "/status",
                        "desc": "Session status",
                        "desc_kr": "세션 상태",
                    },
                    {"name": "/model", "desc": "Switch model", "desc_kr": "모델 전환"},
                    {
                        "name": "/compact",
                        "desc": "Compress context",
                        "desc_kr": "컨텍스트 압축",
                    },
                    {
                        "name": "/context",
                        "desc": "Token breakdown",
                        "desc_kr": "토큰 분석",
                    },
                    {
                        "name": "/usage",
                        "desc": "Token/cost tracking",
                        "desc_kr": "토큰/비용 추적",
                    },
                    {
                        "name": "/think",
                        "desc": "Record a thought / set thinking level",
                        "desc_kr": "생각 기록 / 사고 레벨",
                    },
                    {
                        "name": "/persona",
                        "desc": "Switch persona",
                        "desc_kr": "페르소나 전환",
                    },
                    {
                        "name": "/branch",
                        "desc": "Branch conversation",
                        "desc_kr": "대화 분기",
                    },
                    {
                        "name": "/rollback",
                        "desc": "Rollback messages",
                        "desc_kr": "메시지 롤백",
                    },
                ],
            },
        ]
        self._json({"categories": cats})


# ── FastAPI router ────────────────────────────────────────────────────────────
import asyncio as _asyncio
from fastapi import APIRouter as _APIRouter, Request as _Request, Depends as _Depends, Query as _Query
from fastapi.responses import JSONResponse as _JSON, Response as _Response, HTMLResponse as _HTML, StreamingResponse as _SR, RedirectResponse as _RR
from salmalm.web.fastapi_deps import require_auth as _auth, optional_auth as _optauth

router = _APIRouter()

@router.get("/api/features")
async def get_features():
    from salmalm.web.routes.web_features import WebFeaturesMixin as _WFM
    # Call the mixin logic by building the response from the known structure
    # We reuse the existing Mixin data by monkey-patching _json
    _result = {}
    class _FakeHandler(_WFM):
        def _json(self, data, status=200): _result["data"] = data
    h = _FakeHandler.__new__(_FakeHandler)
    _FakeHandler._json.__get__(h)
    # Directly bind
    import types
    h._json = types.MethodType(_FakeHandler._json, h)
    h._get_features()
    return _JSON(content=_result.get("data", {}))
