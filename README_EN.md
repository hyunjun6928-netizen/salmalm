# 😈 SalmAlm v0.11.1

[![Tests](https://github.com/hyunjun6928-netizen/salmalm/actions/workflows/test.yml/badge.svg)](https://github.com/hyunjun6928-netizen/salmalm/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/pypi/pyversions/salmalm)](https://pypi.org/project/salmalm/)
[![License](https://img.shields.io/github/license/hyunjun6928-netizen/salmalm)](LICENSE)

**Personal AI Gateway — Pure Python, Zero Dependencies**

> [🇰🇷 한국어](README.md)

A self-hosted AI gateway built entirely on Python's standard library. No npm, no dependency hell, no Docker required. One command and you're running your own AI assistant with 32 tools.

The only optional dependency is `cryptography` for AES-256-GCM vault encryption. Without it, the vault falls back to HMAC-CTR (still secure, just not AEAD).

## 🚀 Quick Start

### pip (Recommended)

```bash
python -m pip install salmalm && python -m salmalm
```
Install → server starts → browser auto-opens → `SalmAlm.bat` created on Desktop (double-click next time)

### .env File (Simple Config)

```bash
cp .env.example .env
# Edit .env — add your API keys
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
# Edit docker-compose.yml — set SALMALM_VAULT_PW and API keys
docker compose up -d
# → http://localhost:18800
```

### Local LLM (Ollama — no API key needed)

```bash
ollama pull llama3.2
python -m salmalm
# In Settings, enter Ollama URL: http://localhost:11434/v1
# Use: /model ollama/llama3.2
```

## ✨ What It Does

Think of it as your own local ChatGPT, but with superpowers:

- **Talk to 27 LLMs** — Claude, GPT, Grok, Gemini, DeepSeek, Llama — through one interface
- **30 built-in tools** — run commands, edit files, search the web, manage cron jobs, control browsers
- **RAG search** — BM25 over your local files, no OpenAI embeddings needed
- **MCP support** — connect to Cursor, VS Code, or any MCP-compatible client
- **WebSocket** — real-time streaming via a from-scratch RFC 6455 implementation
- **Gateway-Node** — distribute tool execution across multiple machines
- **Telegram bot** — chat from your phone
- **Plugin system** — drop a `.py` file in `plugins/` and it just works
- **.env support** — configure API keys via `.env` file or encrypted vault
- **EN/KO i18n** — switch language in Settings (English default)
- **One-click update** — upgrade from Settings UI

## 🌍 Gateway-Node Architecture

Scale tool execution across multiple machines:

```bash
# Main server (gateway)
python -m salmalm

# Remote worker (node)
python -m salmalm --node --gateway-url http://gateway:18800
```

Nodes auto-register with the gateway. Tool calls are dispatched to remote nodes based on capabilities. Falls back to local execution on failure.

## 🏗️ Architecture (25 Modules, ~10,400 lines)

```
salmalm/
├── __init__.py         — logging setup
├── __main__.py         — entry point + .env loader
├── constants.py        — config, costs, model registry, thresholds
├── crypto.py           — AES-256-GCM vault (HMAC-CTR fallback)
├── core.py             — audit, cache, sessions, cron, routing
├── agents.py           — SubAgent, SkillLoader, PluginLoader
├── llm.py              — multi-provider LLM calls (6 providers + auto-fallback)
├── tools.py            — 32 tool definitions
├── tool_handlers.py    — tool execution + gateway dispatch
├── prompt.py           — system prompt builder
├── engine.py           — Intelligence Engine (classify → plan → execute → reflect)
├── templates.py        — HTML templates (Web UI)
├── telegram.py         — async Telegram bot
├── discord_bot.py      — Discord Gateway (raw WebSocket)
├── web.py              — Web UI + REST API + SSE streaming + CSRF
├── ws.py               — WebSocket server (RFC 6455)
├── rag.py              — BM25 search engine (SQLite-backed)
├── mcp.py              — Model Context Protocol server + client
├── browser.py          — Chrome DevTools Protocol automation
├── nodes.py            — Gateway-Node architecture (registry + remote dispatch)
├── stability.py        — circuit breaker, health monitor, watchdog
├── auth.py             — JWT auth, RBAC, rate limiter, PBKDF2
├── tls.py              — self-signed TLS cert generation
├── container.py        — lightweight DI container
├── logging_ext.py      — JSON structured logging, rotation
├── docs.py             — auto-generated API documentation
└── plugins/            — Drop-in tool plugins
```

## 🔐 Security

| Layer | Implementation |
|-------|---------------|
| **Vault** | AES-256-GCM (or HMAC-CTR fallback), PBKDF2 200K iterations |
| **Auth** | JWT tokens (HMAC-SHA256), API keys, PBKDF2 password hashing |
| **RBAC** | admin / user / readonly roles with permission matrix |
| **CORS** | Same-origin whitelist only (127.0.0.1, localhost) |
| **Rate Limit** | Token bucket per user + per IP, configurable per role |
| **Upload** | Filename sanitization, 50MB limit, path traversal prevention |
| **Exec** | Command blocklist + regex pattern matching + subprocess isolation |
| **Audit** | SHA-256 hash chain, tamper-evident log |

## 📡 API

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/status` | No | Version, usage stats |
| `GET /api/health` | No | Component health (8 checks) |
| `POST /api/auth/login` | No | Get JWT token |
| `POST /api/unlock` | No | Unlock vault |
| `POST /api/chat` | Yes | Send message |
| `POST /api/chat/stream` | Yes | SSE streaming response |
| `POST /api/vault` | Admin | Key CRUD |
| `GET /api/dashboard` | Yes | Sessions, costs, cron |
| `GET /api/rag/search?q=...` | Yes | BM25 search |
| `GET /api/nodes` | Yes | List connected nodes |
| `GET /docs` | No | Auto-generated API docs |
| `ws://127.0.0.1:18801` | — | WebSocket |

## 🔑 Supported Models

| Provider | Models |
|----------|--------|
| Anthropic | Claude Opus 4, Sonnet 4, Haiku 3.5 |
| OpenAI | GPT-5.3 Codex, GPT-4.1, o3, o4-mini |
| xAI | Grok-4, Grok-3, Grok-3 Mini |
| Google | Gemini 3 Pro/Flash, Gemini 2.5 Pro/Flash |
| DeepSeek | R1, Chat |
| Meta | Llama 4 Maverick, Scout |

All with per-model cost tracking (input + output tokens → USD).

## 🧠 Intelligence Engine

Not just a chat proxy. Every message goes through:

1. **Intent Classification** — 7 tiers (trivial → emergency) with keyword + length analysis
2. **Model Selection** — cheapest model that can handle the task
3. **Tool Planning** — which tools to call, in what order
4. **Parallel Execution** — independent tool calls run concurrently
5. **Self-Reflection** — checks output quality, retries if needed

## 📊 Stats

- ~10,400 lines of Python across 25 modules
- 30 built-in tools + plugin extensibility
- 27+ LLM models with cost tracking (including Ollama local models)
- 85 unit tests
- 21/21 self-test on startup
- 8-component health monitoring

## 📝 v0.11.1 Changelog

- **💬 Multi-session UI**: sidebar chat list — create/switch/delete conversations, auto-titling
- **📈 Dashboard**: `/dashboard` — Chart.js tool usage bar chart + model cost doughnut + stats table
- **🎤 STT (Speech-to-Text)**: Whisper API + mic button — record → transcribe → insert into input
- **📱 PWA**: manifest.json + service worker + app icon — install as home screen app
- **32 tools** (added `stt`)

### v0.11.0
- **👁️ `image_analyze` vision tool**: image analysis (URL/base64/local file/OCR)
- **🧠 Prompt v0.5.0**: improved intent classification + tool selection accuracy
- **📡 SSE chunk streaming**: real-time response streaming with tool counters
- **📋 CI/CD**: GitHub Actions matrix (Ubuntu/macOS/Windows × Python 3.10–3.13)
- **📛 Badges**: PyPI + CI + License + Python version
- **📖 CONTRIBUTING + CHANGELOG + FAQ (KR+EN) + use-cases (KR+EN) + issue templates**

### v0.10.9
- **🔒 P0 Security**: admin auth + loopback enforcement on sensitive endpoints
- **🔓 Setup Wizard**: first-run password setup/skip screen
- **🔑 Password Management**: change/remove/set password anytime from Settings
- **♾️ Unlimited tool loop**: no artificial cap (OpenClaw-style)

Full history: [CHANGELOG.md](CHANGELOG.md)

## 📜 License

MIT
