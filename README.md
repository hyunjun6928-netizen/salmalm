<div align="center">

# 😈 SalmAlm

### Personal AI Gateway — Your AI Assistant in One Command
### 개인 AI 게이트웨이 — 한 줄로 시작하는 AI 비서

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://pypi.org/project/salmalm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-586%20passing-brightgreen)]()
[![Tools](https://img.shields.io/badge/tools-56%20built--in-blue)]()

</div>

---

## ⚡ Quick Start

```bash
pip install salmalm
python -m salmalm start
# → Open http://localhost:18800
```

First run launches the **Setup Wizard** automatically — enter an API key, pick a model, and start chatting!

---

## 🌟 Feature Highlights

| | Feature | Description |
|---|---|---|
| 🤖 | **Multi-Model Routing** | Auto-selects Opus/Sonnet/Haiku/GPT/Gemini per task |
| 🧠 | **Extended Thinking** | Deep reasoning mode for complex problems |
| 🎭 | **Setup Wizard** | Guided onboarding with API key test, model & persona selection |
| 💬 | **Real-time Streaming** | WebSocket-native with inline buttons & code highlighting |
| 🔌 | **Plugin Architecture** | Extend with custom tools, hooks, and commands |
| 📱 | **Telegram + Discord** | Full bot integration with polling & webhook |
| 🔐 | **Vault Encryption** | AES-256-GCM encrypted secrets storage |
| 📊 | **SLA Dashboard** | Uptime, response time P50/P95/P99, self-healing watchdog |
| 🧩 | **MCP Marketplace** | Install Model Context Protocol servers with one command |
| 🎯 | **56 Built-in Tools** | Web search, email, calendar, file ops, exec, and more |

---

## ✨ Features (v0.16.0)

### 🤖 AI Engine

- **Multi-model routing** — Opus/Sonnet/Haiku auto-select / 멀티모델 자동 라우팅
- **Extended thinking mode** / 확장 사고 모드
- **Context compaction** — auto at 80K tokens / 컨텍스트 자동 압축
- **Session pruning** — tool result cleanup / 세션 프루닝
- **Model failover** — exponential backoff / 모델 자동 전환
- **56 built-in tools** / 56개 내장 도구

### 💬 Chat & UI

- **WebSocket real-time streaming** / 웹소켓 실시간 스트리밍
- **Image drag & drop + Vision** / 이미지 드래그앤드롭 + 비전
- **Inline buttons** (web + Telegram) / 인라인 버튼
- **Session branching & rollback** / 세션 분기 및 롤백
- **Message edit/delete** / 메시지 편집/삭제
- **Conversation search** (`Ctrl+K`) / 대화 검색
- **Command palette** (`Ctrl+Shift+P`) / 커맨드 팔레트
- **Code syntax highlighting** / 코드 구문 강조
- **PWA installable + Mobile responsive** / PWA + 모바일 반응형
- **Dark/Light theme** / 다크/라이트 테마
- **Export** (JSON/Markdown/HTML) / 내보내기
- **TTS** (Web Speech + OpenAI) / 음성 합성
- **Session groups & bookmarks** / 세션 그룹 및 북마크

### 🔗 Integrations

- **Telegram** (polling + webhook) / 텔레그램
- **Discord** / 디스코드
- **Google Calendar & Gmail** / 구글 캘린더 & 지메일
- **Google OAuth** / 구글 OAuth
- **MCP Marketplace** / MCP 마켓플레이스

### 🆕 New in v0.16.0

- 🎭 **Setup Wizard** — Guided multi-step onboarding with API test & persona selection
- 🧩 **MCP Marketplace** — Browse & install MCP servers (`/mcp catalog`)
- 📊 **Provider Health Monitor** — Real-time API provider status tracking
- 🔀 **Response Comparison** — Compare outputs from different models side-by-side
- 📋 **Summary Cards** — Auto-generated conversation summaries
- 🎯 **Quick Actions** — Context-aware suggested actions
- 📎 **Smart Paste** — Intelligent paste handling for code, URLs, images
- 🗂️ **Session Groups** — Organize conversations into folders
- 🕰️ **Time Capsule** — Schedule messages to your future self
- 🔍 **Web Clip** — Save & summarize web pages with one command

### 🔒 Security & Reliability

- **OWASP Top 10 compliant** / OWASP Top 10 준수
- **Rate limiting** (IP-based) / 요청 빈도 제한
- **AES-256-GCM vault encryption** / AES-256-GCM 볼트 암호화
- **SSRF protection** / SSRF 방지
- **Audit logging** / 감사 로깅
- **Graceful shutdown** / 안전한 종료

### 🏢 Enterprise Ready

- **Multi-tenant with user isolation** / 멀티테넌트 사용자 격리
- **Per-user quotas** (daily/monthly) / 사용자별 쿼터
- **Multi-agent routing** / 다중 에이전트 라우팅
- **Plugin architecture** / 플러그인 아키텍처
- **Event hooks system** / 이벤트 훅 시스템

---

## 🔧 Configuration

### Environment Variables

```bash
SALMALM_PORT=18800            # Server port
SALMALM_BIND=127.0.0.1        # Bind address
SALMALM_WS_PORT=18801          # WebSocket port
SALMALM_LLM_TIMEOUT=30         # LLM timeout (seconds)
SALMALM_COST_CAP=0             # Cost cap (0=disabled)
SALMALM_VAULT_PW=...           # Auto-unlock vault
```

---

## 📋 Commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/setup` | Re-run setup wizard |
| `/model <name>` | Switch model |
| `/think` | Toggle extended thinking |
| `/export` | Export conversation |
| `/mcp catalog` | Browse MCP marketplace |
| `/remind <text>` | Set a reminder |
| `/briefing` | Daily briefing |
| `/vault` | Manage vault |
| `/status` | Server status |

---

## 🐳 Docker

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
export ANTHROPIC_API_KEY=sk-ant-...
docker compose up -d
curl http://localhost:18800/api/health
```

---

## 🏗️ Architecture

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

## 🔌 Plugins

```
plugins/
  my_plugin/
    __init__.py    # Plugin entry point
    manifest.json  # Plugin metadata
```

Plugins can register tools, event hooks, and custom commands.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests: `python -m pytest tests/`
4. Submit a PR

---

## 📄 License

[MIT](LICENSE)
