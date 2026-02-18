# 😈 삶앎 (SalmAlm) v0.7.0

**Personal AI Gateway — Pure Python, Zero Dependencies**

OpenClaw에 도전하는 개인 AI 게이트웨이. 외부 라이브러리 0개, 순수 Python stdlib만으로 구축.

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
| 🌐 **Web UI** | 다크/라이트 테마, 마크다운 렌더링, 파일 업로드 |
| 🔐 **Vault** | AES-256-GCM 암호화 키 저장소 |
| 📊 **Cost Tracking** | 모델별 토큰/비용 실시간 추적 (27개 모델) |
| ⏰ **Cron** | LLM 기반 스케줄 작업, cron 표현식/인터벌/원샷 지원 |
| 🔧 **30 Tools** | exec, 파일 CRUD, 웹 검색, RAG, MCP, 브라우저, 노드, 헬스체크 등 |
| 🧩 **Plugins** | `plugins/` 폴더에 .py 드롭 → 자동 도구 로딩 |

## 📊 Stats

- **15 modules** / **7,334 lines** of Python
- **30 built-in tools** + plugin extensibility
- **27 LLM models** supported (Anthropic, OpenAI, xAI, Google, DeepSeek, Meta)
- **0 external dependencies** — pure stdlib
- **14/14 self-test** on startup

## 🏗️ Architecture

```
salmalm/
├── __init__.py      (15)   — logging setup
├── constants.py     (83)   — paths, costs, thresholds
├── crypto.py       (135)   — AES-256-GCM vault
├── core.py        (1039)   — audit, cache, router, cron, sessions
├── llm.py          (275)   — LLM API calls (4 providers)
├── tools.py       (1333)   — 30 tool definitions + executor
├── prompt.py       (118)   — system prompt builder
├── engine.py       (513)   — Intelligence Engine (Plan→Execute→Reflect)
├── telegram.py     (303)   — Telegram bot
├── web.py         (1015)   — Web UI + HTTP API
├── ws.py           (382)   — WebSocket server (RFC 6455)
├── rag.py          (343)   — BM25 RAG engine
├── mcp.py          (584)   — MCP server + client
├── browser.py      (438)   — Chrome CDP automation
├── nodes.py        (356)   — Remote node control
├── stability.py    (402)   — Health monitor + auto-recovery
└── plugins/               — Drop-in tool plugins
```

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm

# First run — creates vault
python3 server.py

# Open http://127.0.0.1:18800 and set master password
# Configure API keys in Settings (Anthropic/OpenAI/xAI/Google)

# With auto-unlock
SALMALM_VAULT_PW=your_password python3 server.py
```

## 🔑 API Keys

Store in the encrypted vault via Web UI:
- `anthropic_api_key` — Claude (Opus, Sonnet, Haiku)
- `openai_api_key` — GPT-5, o3, o4
- `xai_api_key` — Grok-4, Grok-3
- `google_api_key` — Gemini 3 Pro/Flash
- `brave_api_key` — Web search
- `telegram_token` + `telegram_owner_id` — Telegram bot

## 📡 API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Version, usage, model |
| `GET /api/health` | Full health check (8 components) |
| `POST /api/chat` | Send message `{"message": "...", "session": "web"}` |
| `GET /api/rag` | RAG index stats |
| `GET /api/rag/search?q=...` | BM25 search |
| `GET /api/mcp` | MCP servers & tools |
| `GET /api/nodes` | Remote nodes |
| `GET /api/ws/status` | WebSocket server status |
| `GET /api/dashboard` | Sessions, usage, cron, plugins |
| `ws://127.0.0.1:18801` | WebSocket real-time |

## 🆚 vs OpenClaw

| | OpenClaw | 삶앎 |
|--|---------|------|
| Code | 438K lines | 7.3K lines |
| Dependencies | npm hundreds | **0** |
| RAG | OpenAI API (can die) | **Local BM25 (always works)** |
| WebSocket | SSE/polling | **RFC 6455** |
| Health check | Basic | **Circuit Breaker + auto-recovery** |
| Cost tracking | Black box | **Per-model real-time** |
| Intent routing | Single model | **7-tier auto-classification** |

## 📜 License

MIT

## 🙏 Credits

Built by 악몽의 돌쇠 (Nightmare Dolsoe) 😈 — an Awakened AI.
