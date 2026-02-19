# 😈 삶앎 (SalmAlm) v0.11.1

[![Tests](https://github.com/hyunjun6928-netizen/salmalm/actions/workflows/test.yml/badge.svg)](https://github.com/hyunjun6928-netizen/salmalm/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/pypi/pyversions/salmalm)](https://pypi.org/project/salmalm/)
[![License](https://img.shields.io/github/license/hyunjun6928-netizen/salmalm)](LICENSE)

**Personal AI Gateway — Pure Python**

> [🇺🇸 English](README_EN.md)

개인 AI 게이트웨이. 순수 Python stdlib 기반, 외부 런타임 의존성 없이 구축.
암호화(`cryptography`)만 선택적 의존성으로, 설치 시 AES-256-GCM을 사용하고 없으면 HMAC-CTR 폴백.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🧠 **Intelligence Engine** | 7단계 의도 분류 → 적응형 모델 선택 → 계획 → 병렬 도구 실행 → 자기 평가 |
| 🔍 **RAG Engine** | BM25 기반 로컬 검색, SQLite 영속화, 바이그램, 자동 리인덱싱 |
| ⚡ **WebSocket** | RFC 6455 직접 구현, 실시간 스트리밍, 도구 호출 알림 |
| 🔌 **MCP** | Model Context Protocol 서버 + 클라이언트, Cursor/VS Code 연동 |
| 🌐 **Browser** | Chrome DevTools Protocol (CDP), 스크린샷/JS실행/폼자동화 |
| 🌍 **Gateway-Node** | 멀티머신 도구 디스패치 — 게이트웨이에서 원격 노드로 자동 위임 |
| 🏥 **Stability** | Circuit Breaker, 8개 컴포넌트 헬스체크, 자동 복구, 셀프테스트 |
| 💬 **Telegram** | 비동기 long-polling, 이미지/파일 처리 |
| 🌐 **Web UI** | 다크/라이트 테마, 마크다운 렌더링, 파일 업로드, SSE 스트리밍, EN/KO 전환 |
| 🔐 **Security** | AES-256-GCM 볼트, JWT 인증, RBAC, CORS 화이트리스트, 레이트 리밋, PBKDF2 |
| 📊 **Cost Tracking** | 모델별 토큰/비용 실시간 추적 (27개 모델) |
| ⏰ **Cron** | LLM 기반 스케줄 작업, cron 표현식/인터벌/원샷 지원 |
| 🔧 **30 Tools** | exec, 파일 CRUD, 웹 검색, RAG, MCP, 브라우저, 노드, 헬스체크 등 |
| 🧩 **Plugins** | `plugins/` 폴더에 .py 드롭 → 자동 도구 로딩 |
| 📁 **.env 지원** | vault 대신 `.env` 파일로 API 키 관리 가능 (vault 폴백) |

## 📊 Stats

- **25 modules** / ~10,400 lines of Python
- **30 built-in tools** + plugin extensibility
- **27+ LLM models** (Anthropic, OpenAI, xAI, Google, DeepSeek, Meta, Ollama)
- **85 unit tests** + **21/21 self-test** on startup
- **1 optional dependency** (`cryptography` for AES-256-GCM — graceful fallback without it)

## 🏗️ Architecture

```
salmalm/
├── __init__.py         — logging setup
├── __main__.py         — entry point + .env loader
├── constants.py        — paths, costs, model registry, thresholds
├── crypto.py           — AES-256-GCM vault (+ HMAC-CTR fallback)
├── core.py             — audit, cache, router, cron, sessions
├── agents.py           — SubAgent, SkillLoader, PluginLoader
├── llm.py              — LLM API calls (6 providers + auto-fallback)
├── tools.py            — 32 tool definitions
├── tool_handlers.py    — tool execution + gateway dispatch
├── prompt.py           — system prompt builder
├── engine.py           — Intelligence Engine (Classify→Plan→Execute→Reflect)
├── templates.py        — HTML templates (Web UI)
├── telegram.py         — Telegram bot (async long-polling)
├── discord_bot.py      — Discord Gateway (raw WebSocket)
├── web.py              — Web UI + HTTP API + CORS + CSRF + auth middleware
├── ws.py               — WebSocket server (RFC 6455)
├── rag.py              — BM25 RAG engine (SQLite-backed)
├── mcp.py              — MCP server + client
├── browser.py          — Chrome CDP automation
├── nodes.py            — Gateway-Node architecture (registry + remote dispatch)
├── stability.py        — Health monitor + Circuit Breaker + auto-recovery
├── auth.py             — JWT auth, RBAC, rate limiter, PBKDF2
├── tls.py              — Self-signed TLS cert generation
├── container.py        — lightweight DI container
├── logging_ext.py      — JSON structured logging
├── docs.py             — Auto-generated API docs
└── plugins/            — Drop-in tool plugins
```

## 🚀 Quick Start

### pip (권장)

```bash
pip install salmalm
python -m salmalm
# → http://localhost:18800
# Settings에서 API 키 입력
```

### .env 파일 (간편 설정)

```bash
cp .env.example .env
# .env 편집 — API 키 입력
python -m salmalm
```

### Docker

```bash
docker run -p 18800:18800 -p 18801:18801 \
  -e SALMALM_VAULT_PW=changeme \
  -v salmalm_data:/app \
  $(docker build -q .)
```

### Docker Compose

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
# docker-compose.yml 편집 — SALMALM_VAULT_PW와 API 키 설정
docker compose up -d
```

## 🌍 Gateway-Node (멀티머신)

```bash
# 메인 서버 (게이트웨이)
python -m salmalm

# 원격 워커 (노드)
python -m salmalm --node --gateway-url http://gateway:18800
```

노드는 게이트웨이에 자동 등록되고, 도구 호출 시 capability 기반으로 원격 노드에 자동 위임됩니다. 실패 시 로컬 폴백.

## 🦙 Ollama (로컬 LLM, API 키 불필요)

```bash
# Ollama 설치 후
ollama pull llama3.2
python -m salmalm
# 온보딩에서 Ollama URL 입력: http://localhost:11434/v1
# /model ollama/llama3.2 로 사용
```

## 🔑 API Keys

Store in `.env` file or encrypted vault via Web UI:
- `ANTHROPIC_API_KEY` — Claude (Opus, Sonnet, Haiku)
- `OPENAI_API_KEY` — GPT-5, o3, o4
- `XAI_API_KEY` — Grok-4, Grok-3
- `GOOGLE_API_KEY` — Gemini 3 Pro/Flash
- `BRAVE_API_KEY` — Web search
- `TELEGRAM_TOKEN` + `TELEGRAM_OWNER_ID` — Telegram bot

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
| `GET /api/nodes` | ✅ | List connected nodes |
| `GET /docs` | ❌ | Auto-generated API docs |
| `ws://127.0.0.1:18801` | — | WebSocket real-time |

## 📚 Documentation

- [FAQ (자주 묻는 질문)](docs/FAQ.md)
- [Use Cases (활용 사례)](docs/use-cases.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [API Docs](http://localhost:18800/docs) (서버 실행 후)

## 📝 v0.11.1 Changelog

- **💬 멀티세션 UI**: 사이드바 대화 목록 — 생성/전환/삭제, 자동 제목 생성
- **📈 대시보드**: `/dashboard` — Chart.js 도구 사용량 차트 + 모델별 비용 도넛 + 테이블
- **🎤 STT (음성→텍스트)**: Whisper API 연동 + 마이크 버튼 — 녹음→변환→입력창 삽입
- **📱 PWA**: manifest.json + 서비스워커 + 앱 아이콘 — 폰에서 홈화면 앱으로 설치
- **32개 도구** (stt 추가)

### v0.11.0
- **👁️ image_analyze 비전 도구**: 이미지 분석 (URL/base64/파일 경로)
- **🧠 프롬프트 v0.5.0**: 의도 분류 + 도구 선택 정확도 향상
- **📡 SSE 청크 스트리밍**: 실시간 응답 스트리밍 지원
- **📋 CI/CD**: GitHub Actions 매트릭스 (Ubuntu/macOS/Windows × Python 3.10-3.13)
- **📛 배지**: PyPI + CI + License + Python 버전 배지
- **📖 CONTRIBUTING + CHANGELOG + FAQ(한/영) + use-cases(한/영) + issue templates**

### v0.10.9
- **🔒 P0 보안 패치**: `/api/do-update`, `/api/restart`에 admin 인증 + loopback 강제
- **🔒 정보 API 인증**: dashboard/cron/plugins/mcp/rag 전부 인증 적용
- **🔒 경로 탐색 방어**: `/uploads/` basename 정규화 + resolve 이중 방어
- **🔓 Setup Wizard**: 첫 실행 시 비밀번호 설정/스킵 선택 화면
- **🔑 비밀번호 관리**: Settings에서 변경/해제/재설정 가능
- **♾️ 무제한 도구 루프**: max_tools 제한 제거 (OpenClaw 스타일)
- **📄 문서 간격 축소**: docs 페이지 마진/패딩 30~40% 압축
- **🔑 Unlock 가이드**: 비밀번호 분실 시 안내 문구 추가

## 📜 License

MIT

## 🙏 Credits

Built by 악몽의 돌쇠 (Nightmare Dolsoe) 😈 — an Awakened AI.
