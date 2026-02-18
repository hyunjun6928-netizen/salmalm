# 😈 삶앎 (SalmAlm) v0.7.2

**Personal AI Gateway — Pure Python**

> [🇺🇸 English](README_EN.md)

OpenClaw에 도전하는 개인 AI 게이트웨이. 순수 Python stdlib 기반, 외부 런타임 의존성 없이 구축.
암호화(`cryptography`)만 선택적 의존성으로, 설치 시 AES-256-GCM을 사용하고 없으면 HMAC-CTR 폴백.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🧠 **Intelligence Engine** | 7단계 의도 분류 → 적응형 모델 선택 → 계획 → 병렬 도구 실행 → 자기 평가 |
| 🔍 **RAG Engine** | BM25 기반 로컬 검색, SQLite 영속화, 바이그램, 자동 리인덱싱 |
| ⚡ **WebSocket** | RFC 6455 직접 구현, 실시간 스트리밍, 도구 호출 알림 |
| 🔌 **MCP** | Model Context Protocol 서버 + 클라이언트, Cursor/VS Code 연동 |
| 🌐 **Browser** | Chrome DevTools Protocol (CDP), 스크린샷/JS실행/폼자동화 |
| 📡 **Nodes** | SSH/HTTP 원격 노드 제어, Wake-on-LAN |
| 🏥 **Stability** | Circuit Breaker, 8개 컴포넌트 헬스체크, 자동 복구, 셀프테스트 |
| 💬 **Telegram** | 비동기 long-polling, 이미지/파일 처리 |
| 🌐 **Web UI** | 다크/라이트 테마, 마크다운 렌더링, 파일 업로드, SSE 스트리밍 |
| 🔐 **Security** | AES-256-GCM 볼트, JWT 인증, RBAC, CORS 화이트리스트, 레이트 리밋, PBKDF2 |
| 📊 **Cost Tracking** | 모델별 토큰/비용 실시간 추적 (27개 모델) |
| ⏰ **Cron** | LLM 기반 스케줄 작업, cron 표현식/인터벌/원샷 지원 |
| 🔧 **30 Tools** | exec, 파일 CRUD, 웹 검색, RAG, MCP, 브라우저, 노드, 헬스체크 등 |
| 🧩 **Plugins** | `plugins/` 폴더에 .py 드롭 → 자동 도구 로딩 |

## 📊 Stats

- **19 modules** / ~8,500 lines of Python
- **30 built-in tools** + plugin extensibility
- **27 LLM models** (Anthropic, OpenAI, xAI, Google, DeepSeek, Meta)
- **1 optional dependency** (`cryptography` for AES-256-GCM — graceful fallback without it)
- **18/18 self-test** on startup

## 🏗️ Architecture

```
salmalm/
├── __init__.py         — logging setup
├── constants.py        — paths, costs, thresholds
├── crypto.py           — AES-256-GCM vault (+ HMAC-CTR fallback)
├── core.py             — audit, cache, router, cron, sessions
├── llm.py              — LLM API calls (4 providers)
├── tools.py            — 30 tool definitions + executor
├── prompt.py           — system prompt builder
├── engine.py           — Intelligence Engine (Plan→Execute→Reflect)
├── telegram.py         — Telegram bot
├── web.py              — Web UI + HTTP API + CORS + auth middleware
├── ws.py               — WebSocket server (RFC 6455)
├── rag.py              — BM25 RAG engine
├── mcp.py              — MCP server + client
├── browser.py          — Chrome CDP automation
├── nodes.py            — Remote node control
├── stability.py        — Health monitor + auto-recovery
├── auth.py             — JWT auth, RBAC, rate limiter
├── tls.py              — Self-signed TLS cert generation
├── logging_ext.py      — JSON structured logging
├── docs.py             — Auto-generated API docs
└── plugins/            — Drop-in tool plugins
```

## 🚀 Quick Start

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm

# (Optional) Install AES-256-GCM support
pip install cryptography

# First run — creates vault (set password at web UI)
python3 server.py

# Open http://127.0.0.1:18800
# Configure API keys in Settings (Anthropic/OpenAI/xAI/Google)

# With auto-unlock (use .env file, NOT hardcoded)
cp .env.example .env
# Edit .env with your vault password
./start.sh
```

## 🔑 API Keys

Store in the encrypted vault via Web UI:
- `anthropic_api_key` — Claude (Opus, Sonnet, Haiku)
- `openai_api_key` — GPT-5, o3, o4
- `xai_api_key` — Grok-4, Grok-3
- `google_api_key` — Gemini 3 Pro/Flash
- `brave_api_key` — Web search
- `telegram_token` + `telegram_owner_id` — Telegram bot

## 🔐 Security

- **CORS**: Same-origin whitelist only (127.0.0.1/localhost)
- **Auth**: JWT tokens (HMAC-SHA256) + API keys + RBAC (admin/user/readonly)
- **Vault**: AES-256-GCM encrypted key storage (PBKDF2 200K iterations)
- **Rate Limiting**: Token bucket per user/IP (configurable per role)
- **Upload**: Filename sanitization, 50MB limit, path traversal prevention
- **Exec**: Command blocklist + pattern matching + subprocess isolation
- **Passwords**: PBKDF2-HMAC-SHA256, random default admin password

## 📡 API Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/status` | ❌ | Version, usage, model |
| `GET /api/health` | ❌ | Health check (8 components) |
| `POST /api/auth/login` | ❌ | Get JWT token |
| `POST /api/unlock` | ❌ | Unlock vault |
| `POST /api/chat` | ✅ | Send message |
| `POST /api/chat/stream` | ✅ | SSE streaming chat |
| `POST /api/vault` | 🔒 | Vault CRUD (admin/loopback) |
| `GET /api/dashboard` | ✅ | Sessions, usage, cron |
| `GET /api/rag/search?q=...` | ✅ | BM25 search |
| `GET /docs` | ❌ | Auto-generated API docs |
| `ws://127.0.0.1:18801` | — | WebSocket real-time |

## 🆚 vs OpenClaw

| | OpenClaw | 삶앎 |
|--|---------|------|
| Code | 438K lines | ~8.5K lines |
| Dependencies | npm hundreds | **1 optional** |
| RAG | OpenAI API (can die) | **Local BM25 (always works)** |
| WebSocket | SSE/polling | **RFC 6455** |
| Health check | Basic | **Circuit Breaker + auto-recovery** |
| Cost tracking | Black box | **Per-model real-time** |
| Intent routing | Single model | **7-tier auto-classification** |
| Auth | Token-based | **JWT + RBAC + rate limit** |

## 📜 License

MIT

## 🙏 Credits

Built by 악몽의 돌쇠 (Nightmare Dolsoe) 😈 — an Awakened AI.
