<div align="center">

# 😈 SalmAlm

### Personal AI Gateway — Your AI Assistant in One Command
### 개인 AI 게이트웨이 — 한 줄로 시작하는 AI 비서

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/pypi/pyversions/salmalm)](https://pypi.org/project/salmalm/)
[![License](https://img.shields.io/github/license/hyunjun6928-netizen/salmalm)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-586%20passing-brightgreen)]()
[![Tools](https://img.shields.io/badge/tools-56%20built--in-blue)]()

</div>

---

## ⚡ Quick Start / 빠른 시작

```bash
pip install salmalm
python -m salmalm start
```

→ Open **http://localhost:18800** and start chatting!
→ **http://localhost:18800** 을 열고 바로 대화를 시작하세요!

---

## ✨ Features / 기능 (v0.14.0)

### 🤖 AI Engine / AI 엔진

| Feature | 설명 |
|---|---|
| Multi-model routing (Opus/Sonnet/Haiku auto-select) | 멀티모델 자동 라우팅 |
| Extended thinking mode | 확장 사고 모드 |
| Context compaction (auto at 80K tokens) | 컨텍스트 자동 압축 (80K 토큰 시 자동) |
| Session pruning (tool result cleanup) | 세션 프루닝 (도구 결과 정리) |
| Model failover (exponential backoff) | 모델 자동 전환 (지수 백오프) |
| 56 built-in tools | 56개 내장 도구 |

### 💬 Chat & UI / 채팅 및 UI

- **WebSocket-native real-time streaming** / 웹소켓 실시간 스트리밍
- **Image drag & drop + Vision analysis** / 이미지 드래그앤드롭 + 비전 분석
- **Inline buttons** (web + Telegram) / 인라인 버튼
- **Session branching & rollback** / 세션 분기 및 롤백
- **Message edit/delete** / 메시지 편집/삭제
- **Conversation search** (`Ctrl+K`) / 대화 검색
- **Command palette** (`Ctrl+Shift+P`) / 커맨드 팔레트
- **Code syntax highlighting** (6 languages) / 코드 구문 강조 (6개 언어)
- **PWA installable** / PWA 설치 가능
- **Mobile responsive** / 모바일 반응형
- **Dark/Light theme** / 다크/라이트 테마
- **Export** (JSON/Markdown) / 내보내기
- **TTS** (Web Speech + OpenAI) / 음성 합성
- **Session groups & bookmarks** / 세션 그룹 및 북마크
- **Regenerate & response comparison** / 응답 재생성 및 비교
- **Keyboard shortcuts** / 키보드 단축키

### 🔗 Integrations / 통합

- **Telegram** (polling + webhook) / 텔레그램 (폴링 + 웹훅)
- **Discord** / 디스코드
- **Google Calendar** / 구글 캘린더
- **Gmail** / 지메일
- **Google OAuth** / 구글 OAuth

### 🧑‍💼 Personal Assistant / 개인 비서

- **Daily briefing** (weather + calendar + email) / 데일리 브리핑 (날씨 + 캘린더 + 이메일)
- **Smart reminders** (natural language, KR/EN) / 스마트 리마인더 (자연어, 한/영)
- **Notes & knowledge base** / 메모 및 지식 베이스
- **Expense tracker** / 가계부
- **Link saver with auto-summary** / 링크 저장 (자동 요약)
- **Pomodoro timer** / 포모도로 타이머
- **Morning/evening routines** / 아침/저녁 루틴
- **Quick translate** / 빠른 번역

### 🔒 Security & Reliability / 보안 및 안정성

- **OWASP Top 10 compliant** / OWASP Top 10 준수
- **Rate limiting** (IP-based) / 요청 빈도 제한 (IP 기반)
- **SSRF protection** / SSRF 방지
- **SQL injection prevention** / SQL 인젝션 방지
- **AES-256-GCM vault encryption** / AES-256-GCM 볼트 암호화
- **Audit logging** / 감사 로깅
- **Graceful shutdown** / 안전한 종료

### 📊 SLA & Monitoring / SLA 및 모니터링

- **Uptime monitoring** (99.9% tracking) / 업타임 모니터링
- **Response time SLA** (P50/P95/P99) / 응답 시간 SLA
- **Auto watchdog** (self-healing) / 자동 워치독 (자가 복구)
- **SLA dashboard** / SLA 대시보드

### 🏢 Enterprise Ready / 엔터프라이즈 지원

- **Multi-tenant with user isolation** / 멀티테넌트 사용자 격리
- **Per-user quotas** (daily/monthly) / 사용자별 쿼터 (일/월)
- **Multi-agent routing** / 다중 에이전트 라우팅
- **Plugin architecture** / 플러그인 아키텍처
- **Event hooks system** / 이벤트 훅 시스템
- **Multi-persona** (SOUL.md) / 멀티 페르소나
- **Windows system tray** / Windows 시스템 트레이
- **Auto-update** / 자동 업데이트

---

## 🔧 Configuration / 설정

### Environment Variables / 환경변수

```bash
SALMALM_PORT=18800            # Server port / 서버 포트
SALMALM_BIND=127.0.0.1        # Bind address / 바인드 주소
SALMALM_WS_PORT=18801          # WebSocket port / 웹소켓 포트
SALMALM_LLM_TIMEOUT=30         # LLM timeout (seconds) / LLM 타임아웃 (초)
SALMALM_COST_CAP=0             # Cost cap (0=disabled) / 비용 상한 (0=비활성화)
SALMALM_VAULT_PW=...           # Auto-unlock vault / 볼트 자동 잠금 해제
SALMALM_TELEGRAM_WEBHOOK_URL=  # Telegram webhook URL / 텔레그램 웹훅 URL
```

### Telegram Setup / 텔레그램 설정

1. Create a bot via **@BotFather** → Get the token / BotFather에서 봇 생성 → 토큰 받기
2. Open Web UI **Settings** → Enter Telegram Bot Token / Web UI 설정 → 텔레그램 봇 토큰 입력
3. Enter your Chat ID (or set webhook URL) / Chat ID 입력 (또는 webhook URL 설정)

### Discord Setup / 디스코드 설정

1. Create an application at [Discord Developer Portal](https://discord.com/developers/applications) / 디스코드 개발자 포털에서 애플리케이션 생성
2. Create a Bot → Copy the token / 봇 생성 → 토큰 복사
3. Open Web UI **Settings** → Enter Discord Bot Token / Web UI 설정 → 디스코드 봇 토큰 입력

### Google Calendar & Gmail / 구글 캘린더 & 지메일

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → Create OAuth Client ID / 구글 클라우드 콘솔 → OAuth 클라이언트 ID 생성
2. Enable **Calendar API** + **Gmail API** / Calendar API + Gmail API 활성화
3. Open Web UI **Settings** → Enter Client ID/Secret → Connect / Web UI 설정 → Client ID/Secret 입력 → 연결

---

## 🏗️ Architecture / 아키텍처

```
Browser ──WebSocket──► SalmAlm Server ──► Anthropic / OpenAI / Google / xAI
   │                        │
   └──HTTP/SSE──►          ├── SQLite DB
                            ├── Plugin System
Telegram ──►                ├── Cron Scheduler
Discord  ──►                ├── RAG Engine
                            └── Tool Registry (56 tools)
```

---

## 📋 Commands / 명령어

| Command | Description / 설명 |
|---|---|
| `/help` | Show all commands / 모든 명령어 보기 |
| `/model <name>` | Switch model / 모델 변경 |
| `/think` | Toggle extended thinking / 확장 사고 모드 전환 |
| `/export` | Export conversation / 대화 내보내기 |
| `/remind <text>` | Set a reminder / 리마인더 설정 |
| `/briefing` | Daily briefing / 데일리 브리핑 |
| `/expense` | Expense tracker / 가계부 |
| `/note` | Notes / 메모 |
| `/translate` | Quick translate / 빠른 번역 |
| `/pomodoro` | Pomodoro timer / 포모도로 타이머 |
| `/vault` | Manage vault / 볼트 관리 |

---

## 🔌 Plugins / 플러그인

SalmAlm supports a plugin architecture for extending functionality.
SalmAlm은 기능 확장을 위한 플러그인 아키텍처를 지원합니다.

```
plugins/
  my_plugin/
    __init__.py    # Plugin entry point / 플러그인 진입점
    manifest.json  # Plugin metadata / 플러그인 메타데이터
```

Plugins can register tools, event hooks, and custom commands.
플러그인은 도구, 이벤트 훅, 커스텀 명령어를 등록할 수 있습니다.

---

## 🤝 Contributing / 기여

Contributions are welcome! / 기여를 환영합니다!

1. Fork the repository / 저장소 포크
2. Create a feature branch / 기능 브랜치 생성
3. Write tests / 테스트 작성
4. Submit a PR / PR 제출

```bash
# Run tests / 테스트 실행
python -m pytest tests/
```

---

## 📄 License / 라이선스

[MIT](LICENSE)
