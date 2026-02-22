<div align="center">

# 😈 SalmAlm (삶앎)

### Your Entire AI Life in One `pip install`

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)](https://pypi.org/project/salmalm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/hyunjun6928-netizen/salmalm/actions/workflows/ci.yml/badge.svg)](https://github.com/hyunjun6928-netizen/salmalm/actions)
[![Tests](https://img.shields.io/badge/tests-1%2C817%20passed-brightgreen)]()
[![Tools](https://img.shields.io/badge/tools-66-blueviolet)]()

**[한국어 README](README_KR.md)**

</div>

---

## What is SalmAlm?

SalmAlm is a **personal AI gateway** — one Python package that gives you a full-featured AI assistant with a web UI, Telegram/Discord bots, 66 tools, and 10 features you won't find anywhere else.

No Docker. No Node.js. No config files. Just:

```bash
pip install salmalm
salmalm
# → http://localhost:18800
```

First launch opens a **Setup Wizard** — paste an API key, pick a model, done.

> ⚠️ **Don't run `salmalm` from inside a cloned repo directory** — Python will import the local source instead of the installed package. Run from `~` or any other directory.

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
| 🦙 | Local LLM (Ollama/LM Studio/vLLM) | ✅ | ❌ | ✅ | ✅ |
| 📦 | Zero dependencies* | ✅ | N/A | ❌ | ❌ |

*\*stdlib-only core; optional `cryptography` for AES-256-GCM vault, otherwise pure Python HMAC-CTR fallback*

---

## ⚡ Quick Start

```bash
# One-liner install
pip install salmalm

# Start (web UI at http://localhost:18800)
salmalm

# Auto-open browser
salmalm --open

# Desktop shortcut (double-click to launch!)
salmalm --shortcut

# Self-update
salmalm --update

# Custom port / external access
SALMALM_PORT=8080 salmalm
SALMALM_BIND=0.0.0.0 salmalm    # expose to LAN (see Security section)
```

### Supported Providers

| Provider | Models | Setup |
|---|---|---|
| Anthropic | Claude Opus 4, Sonnet 4, Haiku 4.5 | Web UI → Settings → API Keys |
| OpenAI | GPT-5.2, GPT-4.1, o3, o4-mini | Web UI → Settings → API Keys |
| Google | Gemini 3 Pro/Flash, 2.5 Pro/Flash | Web UI → Settings → API Keys |
| xAI | Grok-4, Grok-3 | Web UI → Settings → API Keys |
| **Local LLM** | Ollama / LM Studio / vLLM | Web UI → Settings → Local LLM |

**Local LLM endpoints**: Ollama `localhost:11434/v1` · LM Studio `localhost:1234/v1` · vLLM `localhost:8000/v1`

---

## 🎯 Feature Overview

### Core AI
- **Smart model routing** — auto-selects by complexity (simple→Haiku, moderate→Sonnet, complex→Opus)
- **Extended Thinking** — deep reasoning with budget control
- **5-stage context compaction** — strip binary → trim tools → drop old → truncate → LLM summarize
- **Prompt caching** — Anthropic cache_control for 90% cost reduction
- **Model failover** — exponential backoff + retry across providers
- **Sub-agent system** — spawn/steer/collect background AI workers
- **Infinite loop detection** — 3+ same (tool, args_hash) in last 6 iterations = auto-break
- **Irreversible action gate** — email send, calendar delete require explicit confirmation

### 66 Built-in Tools
Web search (Brave), email (Gmail), calendar (Google), file I/O, shell exec, Python eval, image generation (DALL-E/Aurora), TTS/STT, browser automation (Playwright), RAG search, QR codes, system monitor, OS-native sandbox, mesh networking, canvas preview, and more.

### Web UI
- Real-time streaming (WebSocket + SSE fallback)
- Session branching, rollback, search (`Ctrl+K`), command palette (`Ctrl+Shift+P`)
- Dark/Light themes, **EN/KR i18n** (language toggle in settings)
- Image paste/drag-drop with vision, code syntax highlighting
- PWA installable, CSP-compatible (all JS in external `app.js`)

### Channels
- **Web** — full SPA at `localhost:18800`
- **Telegram** — polling + webhook with inline buttons
- **Discord** — bot with thread support and mentions

### Admin Panels
📈 Dashboard · 📋 Sessions · ⏰ Cron Jobs · 🧠 Memory · 🔬 Debug · 📋 Logs · 📖 Docs

---

## ✨ 10 Unique Features

| # | Feature | What it does |
|---|---|---|
| 1 | **Self-Evolving Prompt** | AI auto-generates personality rules from your conversations |
| 2 | **Dead Man's Switch** | Emergency actions if you go inactive for N days |
| 3 | **Shadow Mode** | AI learns your style, replies as you when away |
| 4 | **Life Dashboard** | Unified health, finance, habits, calendar view |
| 5 | **Mood-Aware Response** | Detects emotional state, adjusts tone |
| 6 | **Encrypted Vault** | PBKDF2-200K + AES-256-GCM / HMAC-CTR for API keys |
| 7 | **Agent-to-Agent Protocol** | HMAC-SHA256 signed communication between instances |
| 8 | **A/B Split Response** | Two model perspectives on the same question |
| 9 | **Time Capsule** | Schedule messages to your future self |
| 10 | **Thought Stream** | Private journaling with hashtag search and mood tracking |

---

## 💰 Cost Optimization

SalmAlm is designed to minimize API costs without sacrificing quality:

| Feature | Effect |
|---|---|
| Dynamic tool loading | 66 tools → 0 (chat) or 7-12 (actions) per request |
| Smart model routing | Simple→Haiku ($1), Moderate→Sonnet ($3), Complex→Opus ($15) |
| Tool schema compression | 7,749 → 693 tokens (91% reduction) |
| System prompt compression | 762 → 310 tokens |
| Intent-based max_tokens | Chat 512, search 1024, code 4096 |
| Intent-based history trim | Chat 10 turns, code 20 turns |
| Cache TTL | Same question cached (30min–24h, configurable) |

**Result: $7.09/day → $1.23/day (83% savings at 100 calls/day)**

---

## 🔒 Security

SalmAlm follows a **dangerous features default OFF** policy:

| Feature | Default | Opt-in |
|---|---|---|
| Network bind | `127.0.0.1` (loopback only) | `SALMALM_BIND=0.0.0.0` |
| Shell operators | Blocked | `SALMALM_ALLOW_SHELL=1` |
| Home dir file read | Workspace only | `SALMALM_ALLOW_HOME_READ=1` |
| Vault fallback | Disabled | `SALMALM_VAULT_FALLBACK=1` |
| Plugin system | Disabled | `SALMALM_PLUGINS=1` |
| CLI OAuth reuse | Disabled | `SALMALM_CLI_OAUTH=1` |
| Elevated exec on external bind | Blocked | `SALMALM_ALLOW_ELEVATED=1` |
| Strict CSP (nonce mode) | Enabled | `SALMALM_CSP_COMPAT=1` for legacy |

### Tool Risk Tiers

Tools are classified by risk and **critical tools are blocked on external bind without authentication**:

| Tier | Tools | External (0.0.0.0) |
|---|---|---|
| 🔴 Critical | `exec`, `exec_session`, `write_file`, `edit_file`, `python_eval`, `sandbox_exec`, `browser`, `email_send`, `gmail`, `google_calendar`, `calendar_delete`, `calendar_add`, `node_manage`, `plugin_manage` | Auth required |
| 🟡 High | `http_request`, `read_file`, `memory_write`, `mesh`, `sub_agent`, `cron_manage`, `screenshot`, `tts`, `stt` | Allowed with warning |
| 🟢 Normal | `web_search`, `weather`, `translate`, etc. | Allowed |

### Security Hardening

- **SSRF defense** — DNS pinning + private IP block on every redirect hop (web tools AND browser)
- **Browser SSRF** — internal/private URL blocked on external bind
- **Irreversible action gate** — `gmail send`, `calendar delete/create` require `_confirmed=true`
- **Audit log redaction** — secrets scrubbed from tool args before logging (9 pattern types)
- **Memory scrubbing** — API keys/tokens auto-redacted before storage
- **Path validation** — `Path.is_relative_to()` for all file operations (no `startswith` bypass)
- **Write-path gate** — write tools blocked outside allowed roots even for non-existent paths
- **Session isolation** — `user_id` column in session_store, export scoped to own data
- **Vault export** — requires admin role
- **Secret isolation** — API keys stripped from subprocess environments
- **CSRF defense** — Origin validation + `X-Requested-With` custom header
- **Centralized auth gate** — all `/api/` routes require auth unless in `_PUBLIC_PATHS`
- **Node dispatch** — HMAC-SHA256 signed payloads with timestamp + nonce
- **142+ security regression tests** in CI

See [`SECURITY.md`](SECURITY.md) for full threat model and details.

---

## 🦙 Local LLM Setup

SalmAlm works with any OpenAI-compatible local LLM server:

| Server | Default Endpoint | Setup |
|---|---|---|
| **Ollama** | `http://localhost:11434/v1` | `ollama serve` then pick model in UI |
| **LM Studio** | `http://localhost:1234/v1` | Start server in LM Studio |
| **vLLM** | `http://localhost:8000/v1` | `vllm serve <model>` |

Settings → **Local LLM** → paste endpoint URL → Save. API key is optional (only if your server requires auth).

SalmAlm auto-discovers available models via `/models`, `/v1/models`, or `/api/tags` endpoints.

---

## 🔑 Google OAuth Setup (Gmail & Calendar)

1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → Create OAuth client
2. Enable **Gmail API** + **Google Calendar API**
3. Redirect URI: `http://localhost:18800/api/google/callback`
4. Save Client ID + Secret in Settings → API Keys
5. Run `/oauth` in chat → click Google sign-in link

---

## 🔧 Configuration

```bash
# Server
SALMALM_PORT=18800         # Web server port
SALMALM_BIND=127.0.0.1    # Bind address
SALMALM_HOME=~/SalmAlm    # Data directory

# AI
SALMALM_PLANNING=1         # Planning phase (opt-in)
SALMALM_REFLECT=1          # Reflection pass (opt-in)
SALMALM_MAX_TOOL_ITER=25   # Max tool iterations (999=unlimited)
SALMALM_COST_CAP=0         # Daily cost cap (0=unlimited)

# Security
SALMALM_PLUGINS=1           # Enable plugin system
SALMALM_CLI_OAUTH=1         # Allow CLI token reuse
SALMALM_ALLOW_SHELL=1       # Enable shell operators in exec
SALMALM_ALLOW_HOME_READ=1   # File read outside workspace
SALMALM_VAULT_FALLBACK=1    # HMAC-CTR vault without cryptography
```

All settings also available in the web UI → Settings panels.

---

## 🏗️ Architecture

```
Browser ──WebSocket──► SalmAlm ──► Anthropic / OpenAI / Google / xAI / Local LLM
   │                     │
   └──HTTP/SSE──►       ├── SQLite (sessions, usage, memory, audit)
                         ├── Smart Model Routing (complexity-based)
Telegram ──►             ├── Tool Registry (66 tools, risk-tiered)
Discord  ──►             ├── Security Middleware (auth/CSRF/audit/rate-limit)
                         ├── Sub-Agent Manager
Mesh Peers ──►           ├── Message Queue (offline + retry)
                         ├── Shared Secret Redaction (security/redact.py)
                         ├── OS-native Sandbox (bwrap/rlimit)
                         ├── Node Gateway (HMAC-signed dispatch)
                         ├── Plugin System (opt-in)
                         └── Vault (PBKDF2 + AES-256-GCM / HMAC-CTR)
```

- **233 modules**, **49K+ lines**, **82 test files**, **1,817 tests**
- Pure Python 3.10+ stdlib — no frameworks, no heavy dependencies
- Data stored under `~/SalmAlm` (configurable via `SALMALM_HOME`)

---

## 🔌 Plugins

> ⚠️ Plugins run arbitrary code. Enable with `SALMALM_PLUGINS=1`.

Drop a `.py` file in `~/SalmAlm/plugins/`:

```python
# plugins/my_plugin.py
TOOLS = [{
    'name': 'my_tool',
    'description': 'Says hello',
    'input_schema': {'type': 'object', 'properties': {'name': {'type': 'string'}}}
}]

def handle_my_tool(args):
    return f"Hello, {args.get('name', 'world')}!"
```

---

## 🤝 Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
pip install -e ".[dev]"
for f in tests/test_*.py; do python -m pytest "$f" -q --timeout=30; done
```

---

## 📄 License

[MIT](LICENSE)

---

<div align="center">

**SalmAlm** = 삶(Life) + 앎(Knowledge)

*Your life, understood by AI.*

</div>
