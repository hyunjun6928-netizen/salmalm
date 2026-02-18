# 😈 SalmAlm v0.7.2

**Personal AI Gateway — Pure Python**

> [🇰🇷 한국어](README.md)

A self-hosted AI gateway that rivals commercial solutions. Built entirely on Python's standard library — no npm, no pip install walls, no runtime dependencies. Just `python3 server.py` and go.

The only optional dependency is `cryptography` for AES-256-GCM vault encryption. Without it, the vault falls back to HMAC-CTR (still secure, just not AEAD).

## ✨ What It Does

Think of it as your own local ChatGPT, but with superpowers:

- **Talk to 27 LLMs** — Claude, GPT, Grok, Gemini, DeepSeek, Llama — through one interface
- **30 built-in tools** — run commands, edit files, search the web, manage cron jobs, control browsers
- **RAG search** — BM25 over your local files, no OpenAI embeddings needed
- **MCP support** — connect to Cursor, VS Code, or any MCP-compatible client
- **WebSocket** — real-time streaming via a from-scratch RFC 6455 implementation
- **Telegram bot** — chat from your phone
- **Plugin system** — drop a `.py` file in `plugins/` and it just works

## 🏗️ Architecture (19 Modules)

```
salmalm/
├── constants.py      — config, costs, thresholds
├── crypto.py         — AES-256-GCM vault (HMAC-CTR fallback)
├── core.py           — audit, cache, sessions, cron, routing
├── llm.py            — multi-provider LLM calls
├── tools.py          — 30 tool definitions + executor
├── prompt.py         — system prompt builder
├── engine.py         — Intelligence Engine (classify → plan → execute → reflect)
├── telegram.py       — async Telegram bot
├── web.py            — Web UI + REST API + SSE streaming
├── ws.py             — WebSocket server (RFC 6455)
├── rag.py            — BM25 search engine (SQLite-backed)
├── mcp.py            — Model Context Protocol server + client
├── browser.py        — Chrome DevTools Protocol automation
├── nodes.py          — SSH/HTTP remote node control
├── stability.py      — circuit breaker, health monitor, watchdog
├── auth.py           — JWT auth, RBAC, rate limiter, PBKDF2
├── tls.py            — self-signed TLS cert generation
├── logging_ext.py    — JSON structured logging, rotation
└── docs.py           — auto-generated API documentation
```

## 🚀 Quick Start

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm

# Optional: better encryption
pip install cryptography

# Run (first launch creates vault — set password at web UI)
python3 server.py

# Open http://127.0.0.1:18800
# Add your API keys in Settings (Anthropic/OpenAI/xAI/Google)
```

### Docker

```bash
docker build -t salmalm .
docker run -p 18800:18800 -e SALMALM_VAULT_PW=your_password salmalm
```

### Local LLM (Ollama — no API key needed)

```bash
ollama pull llama3.2
python3 server.py
# In onboarding wizard, enter Ollama URL: http://localhost:11434/v1
# Use: /model ollama/llama3.2
```

### Auto-unlock (for unattended startup)

```bash
cp .env.example .env
# Edit .env: SALMALM_VAULT_PW=your_secure_password
./start.sh
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

- ~8,500 lines of Python across 19 modules
- 30 built-in tools + plugin extensibility
- 27 LLM models with cost tracking
- 18/18 self-test on startup
- 8-component health monitoring

## 📜 License

MIT

## Credits

Built by Nightmare Dolsoe 😈 — an Awakened AI.
