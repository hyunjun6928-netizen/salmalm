<div align="center">

# 😈 SalmAlm (삶앎)

### Your Entire AI Life in One `pip install`

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)](https://pypi.org/project/salmalm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/hyunjun6928-netizen/salmalm/actions/workflows/ci.yml/badge.svg)](https://github.com/hyunjun6928-netizen/salmalm/actions)
[![Tools](https://img.shields.io/badge/tools-62-blueviolet)]()
[![Commands](https://img.shields.io/badge/commands-32-orange)]()

**[한국어 README](README_KR.md)**

</div>

---

## What is SalmAlm?

SalmAlm is a **personal AI gateway** — one Python package that gives you a full-featured AI assistant with a web UI, Telegram/Discord bots, 62 tools, and 10 features you won't find anywhere else.

No Docker. No Node.js. No config files. Just:

```bash
pip install salmalm
salmalm start
# → http://localhost:18800
```

First launch opens a **Setup Wizard** — paste an API key, pick a model, done.

---

## Why SalmAlm?

| | Feature | SalmAlm | ChatGPT | OpenClaw | Open WebUI |
|---|---|:---:|:---:|:---:|:---:|
| 🔧 | Install complexity | `pip install` | N/A | npm + config | Docker |
| 🤖 | Multi-provider routing | ✅ | ❌ | ✅ | ✅ |
| 🧠 | Self-Evolving Prompt | ✅ | ❌ | ❌ | ❌ |
| 👻 | Shadow Mode | ✅ | ❌ | ❌ | ❌ |
| 💀 | Dead Man's Switch | ✅ | ❌ | ❌ | ❌ |
| 🔐 | Encrypted Vault | ✅ | ❌ | ❌ | ❌ |
| 📱 | Telegram + Discord | ✅ | ❌ | ✅ | ❌ |
| 🧩 | MCP Marketplace | ✅ | ❌ | ❌ | ✅ |
| 📦 | Zero dependencies* | ✅ | N/A | ❌ | ❌ |

*\*stdlib-only core; optional integrations use standard protocols*

---

## ⚡ Quick Start

```bash
# Install
pip install salmalm

# Start (opens web UI automatically)
salmalm start

# Or with options
salmalm start --port 8080 --no-browser
```

### Supported Providers

| Provider | Models | Env Variable |
|---|---|---|
| Anthropic | Claude Opus 4, Sonnet 4, Haiku 4.5 | `ANTHROPIC_API_KEY` |
| OpenAI | GPT-5.2, GPT-4.1, o3, o4-mini | `OPENAI_API_KEY` |
| Google | Gemini 2.5 Pro/Flash | `GOOGLE_API_KEY` |
| xAI | Grok-4, Grok-3 | `XAI_API_KEY` |
| Ollama | Any local model | `OLLAMA_URL` |

Set keys via environment variables or the web UI Settings → API Keys.

---

## 🎯 Feature Overview

### Core AI
- **Multi-model auto-routing** — routes simple→Haiku, moderate→Sonnet, complex→Opus
- **Extended Thinking** — deep reasoning mode with budget control
- **Context compaction** — auto-summarizes at 80K tokens
- **Prompt caching** — Anthropic cache_control for 90% cost reduction on system prompts
- **Model failover** — exponential backoff across providers

### 62 Built-in Tools
Web search (Brave), email (Gmail), calendar (Google), file I/O, shell exec, Python eval, image generation (DALL-E), TTS/STT, browser automation, RAG search, QR codes, system monitor, and more.

### Web UI
- Real-time streaming (WebSocket + SSE fallback)
- Session branching, rollback, search (`Ctrl+K`)
- Command palette (`Ctrl+Shift+P`)
- Message edit/delete/regenerate
- Image paste/drag-drop with vision
- Code syntax highlighting
- Dark/Light themes, EN/KR i18n
- PWA installable

### Channels
- **Web** — full-featured SPA at `localhost:18800`
- **Telegram** — polling + webhook with inline buttons
- **Discord** — bot with thread support

### Admin Panels
- **📈 Dashboard** — token usage, cost tracking, daily trends with date filters
- **📋 Sessions** — full session management with search, delete, branch indicators
- **⏰ Cron Jobs** — scheduled AI tasks with CRUD management
- **🧠 Memory** — file browser for agent memory/personality files
- **🔬 Debug** — real-time system diagnostics (5 cards, auto-refresh)
- **📋 Logs** — server log viewer with level filter
- **📖 Docs** — built-in reference for all 32 commands and 10 unique features

---

## ✨ 10 Unique Features

These are SalmAlm-only — not found in ChatGPT, OpenClaw, Open WebUI, or any other gateway:

| # | Feature | What it does |
|---|---|---|
| 1 | **Self-Evolving Prompt** | AI auto-generates personality rules from your conversations (FIFO, max 20) |
| 2 | **Dead Man's Switch** | Automated emergency actions if you go inactive for N days |
| 3 | **Shadow Mode** | AI silently learns your communication style, replies as you when away |
| 4 | **Life Dashboard** | Unified view of health, finance, habits, calendar in one command |
| 5 | **Mood-Aware Response** | Detects emotional state and adjusts tone automatically |
| 6 | **Encrypted Vault** | PBKDF2-200K + HMAC-authenticated stream cipher for private conversations |
| 7 | **Agent-to-Agent Protocol** | HMAC-SHA256 signed communication between SalmAlm instances |
| 8 | **A/B Split Response** | Get two different model perspectives on the same question |
| 9 | **Time Capsule** | Schedule messages to your future self |
| 10 | **Thought Stream** | Private journaling timeline with hashtag search and mood tracking |

---

## 📋 Commands (32)

<details>
<summary>Click to expand full command list</summary>

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/status` | Session status |
| `/model <name>` | Switch model (opus/sonnet/haiku/gpt/auto) |
| `/think [level]` | Extended thinking (low/medium/high) |
| `/compact` | Compress context |
| `/context` | Token count breakdown |
| `/usage` | Token & cost tracking |
| `/persona <name>` | Switch persona |
| `/branch` | Branch conversation |
| `/rollback [n]` | Undo last n messages |
| `/remind <time> <msg>` | Set reminder |
| `/expense <amt> <desc>` | Track expense |
| `/pomodoro` | Focus timer |
| `/note <text>` | Quick note |
| `/link <url>` | Save link |
| `/routine` | Daily routines |
| `/shadow` | Shadow mode |
| `/vault` | Encrypted vault |
| `/capsule` | Time capsule |
| `/deadman` | Dead man's switch |
| `/a2a` | Agent-to-agent |
| `/workflow` | Workflow engine |
| `/mcp` | MCP management |
| `/subagents` | Sub-agents |
| `/evolve` | Self-evolving prompt |
| `/mood` | Mood detection |
| `/split` | A/B split response |
| `/cron` | Cron jobs |
| `/bash <cmd>` | Shell command |
| `/screen` | Browser control |
| `/life` | Life dashboard |
| `/briefing` | Daily briefing |

</details>

---

## 🔧 Configuration

```bash
# Environment variables (all optional)
SALMALM_PORT=18800         # Web server port
SALMALM_BIND=127.0.0.1    # Bind address
SALMALM_WS_PORT=18801     # WebSocket port
SALMALM_LLM_TIMEOUT=30    # LLM request timeout
SALMALM_COST_CAP=0        # Monthly cost cap (0=unlimited)
SALMALM_VAULT_PW=...      # Auto-unlock vault on start
```

All configuration is also available through the web UI.

---

## 🏗️ Architecture

```
Browser ──WebSocket──► SalmAlm ──► Anthropic / OpenAI / Google / xAI / Ollama
   │                     │
   └──HTTP/SSE──►       ├── SQLite (sessions, usage, memory)
                         ├── Tool Registry (62 tools)
Telegram ──►             ├── Cron Scheduler
Discord  ──►             ├── RAG Engine (TF-IDF + cosine similarity)
                         ├── Plugin System
                         └── Vault (PBKDF2 encrypted)
```

- **218 modules**, **42K+ lines**, **80 test files**, **1,649 tests**
- Pure Python 3.10+ stdlib — no frameworks, no heavy dependencies
- Single `pip install`, runs anywhere Python runs
- Route-table architecture (85 GET + 59 POST handlers)
- Default bind `127.0.0.1` (explicit opt-in for network exposure)

---

## 🐳 Docker (Optional)

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
docker compose up -d
```

---

## 🔌 Plugins

```python
# plugins/my_plugin/__init__.py
def register(app):
    @app.tool("my_tool")
    def my_tool(args):
        return "Hello from my plugin!"
```

---

## 🤝 Contributing

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
pip install -e ".[dev]"
python -m pytest tests/ --timeout=30
```

---

## 📄 License

[MIT](LICENSE)

---

<div align="center">

**SalmAlm** = 삶(Life) + 앎(Knowledge)

*Your life, understood by AI.*

</div>
