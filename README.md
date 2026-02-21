<div align="center">

# 😈 SalmAlm (삶앎)

### Your Entire AI Life in One `pip install`

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)](https://pypi.org/project/salmalm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/hyunjun6928-netizen/salmalm/actions/workflows/ci.yml/badge.svg)](https://github.com/hyunjun6928-netizen/salmalm/actions)
[![Tests](https://img.shields.io/badge/tests-1%2C710%20passed-brightgreen)]()
[![Tools](https://img.shields.io/badge/tools-62-blueviolet)]()
[![Commands](https://img.shields.io/badge/commands-62+-orange)]()

**[한국어 README](README_KR.md)**

</div>

---

## What is SalmAlm?

SalmAlm is a **personal AI gateway** — one Python package that gives you a full-featured AI assistant with a web UI, Telegram/Discord bots, 62 tools, and 10 features you won't find anywhere else.

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
| 📦 | Zero dependencies* | ✅ | N/A | ❌ | ❌ |

*\*stdlib-only core; optional `cryptography` for vault, otherwise pure Python HMAC-CTR fallback*

---

## ⚡ Quick Start

```bash
# One-liner install (creates venv, installs, symlinks to ~/.local/bin)
curl -fsSL https://raw.githubusercontent.com/hyunjun6928-netizen/salmalm/main/scripts/install.sh | bash

# Or manual install
pip install salmalm

# Start (web UI at http://localhost:18800)
salmalm

# Auto-open browser on start
salmalm --open

# ⚠️ If you installed with install.sh before v0.17.24, remove the old PATH entry:
# Edit ~/.bashrc (or ~/.zshrc) and delete the line containing "salmalm-env/bin"

# Create desktop shortcut (double-click to launch!)
salmalm --shortcut

# Self-update to latest version
salmalm --update

# Custom port / external access
SALMALM_PORT=8080 salmalm
SALMALM_BIND=0.0.0.0 salmalm    # expose to LAN (see Security section)
```

### Desktop Shortcut

Run `salmalm --shortcut` once to create a desktop icon:

| Platform | What's created | How to use |
|---|---|---|
| **Windows** | `SalmAlm.bat` on Desktop | Double-click → server starts + browser opens |
| **Linux** | `salmalm.desktop` on Desktop | Double-click → server starts + browser opens |
| **macOS** | `SalmAlm.command` on Desktop | Double-click → server starts + browser opens |

The shortcut is **version-independent** — update SalmAlm anytime, the shortcut keeps working.

### Supported Providers

| Provider | Models | Env Variable |
|---|---|---|
| Anthropic | Claude Opus 4, Sonnet 4, Haiku 4.5 | `ANTHROPIC_API_KEY` |
| OpenAI | GPT-5.2, GPT-4.1, o3, o4-mini | `OPENAI_API_KEY` |
| Google | Gemini 3 Pro/Flash, 2.5 Pro/Flash | `GOOGLE_API_KEY` |
| xAI | Grok-4, Grok-3 | `XAI_API_KEY` |
| Ollama | Any local model | `OLLAMA_URL` |

Set keys via environment variables or the web UI **Settings → API Keys**.

---

## 🎯 Feature Overview

### Core AI
- **Intelligent model routing** — auto-selects model by complexity (simple→Haiku, moderate→Sonnet, complex→Opus), extracted to dedicated `model_selection` module with user-configurable routing
- **Extended Thinking** — deep reasoning mode with budget control
- **5-stage context compaction** — strip binary → trim tools → drop old → truncate → LLM summarize, with cross-session continuity via `compaction_summaries` DB table
- **Prompt caching** — Anthropic cache_control for 90% cost reduction on system prompts
- **Model failover** — exponential backoff + transient error retry (timeout/5xx/429) with 1.5s delay across providers
- **Message queue** — offline message queuing with FIFO ordering, 3-stage retry backoff, and dead letter handling; auto-drain on model recovery
- **Sub-agent system** — spawn/steer/collect background AI workers with isolated sessions; 8 actions (spawn, stop, list, log, info, steer, collect, status)
- **Streaming stability** — partial content preservation on abort; `AbortController` accumulates tokens and freezes on cancel
- **Cache-aware session pruning** — respects Anthropic prompt cache TTL (5min) with 60s cooldown

### 62 Built-in Tools
Web search (Brave), email (Gmail), calendar (Google), file I/O, shell exec, Python eval, image generation (DALL-E), TTS/STT, browser automation (Playwright), RAG search, QR codes, system monitor, OS-native sandbox, mesh networking, canvas preview, and more.

### Web UI
- Real-time streaming (WebSocket + SSE fallback)
- WebSocket reconnect with session resume (buffered message flush)
- Session branching, rollback, search (`Ctrl+K`)
- Command palette (`Ctrl+Shift+P`)
- Message edit/delete/regenerate
- Image paste/drag-drop with vision
- Code syntax highlighting
- Dark/Light themes (light default), EN/KR i18n
- PWA installable
- CSP-compatible — all JS in external `app.js`, no inline event handlers
- Compaction progress indicator (✨ Compacting context...)

### Infrastructure
- **OS-native sandbox** — bubblewrap (Linux) / sandbox-exec (macOS) / rlimit fallback; auto-detects strongest tier
- **Mesh networking** — P2P between SalmAlm instances (task delegation, clipboard sharing, LAN UDP discovery, HMAC auth)
- **Canvas** — local HTML/code/chart preview server at `:18803`
- **Browser automation** — Playwright snapshot/act pattern (`pip install salmalm[browser]`)

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

## 📋 Commands (62+)

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
| `/subagents` | Sub-agents (spawn, steer, collect, list, stop, log, info, status) |
| `/evolve` | Self-evolving prompt |
| `/mood` | Mood detection |
| `/split` | A/B split response |
| `/cron` | Cron jobs |
| `/bash <cmd>` | Shell command |
| `/screen` | Browser control |
| `/life` | Life dashboard |
| `/briefing` | Daily briefing |
| `/debug` | Real-time system diagnostics |
| `/security` | Security status overview |
| `/plugins` | Plugin management |
| `/export` | Export session data |
| `/soul` | View/edit AI personality file |
| `/config` | Configuration management |
| `/brave` | Brave search settings |
| `/approve` | Approve pending exec commands |
| `/agent` | Agent management |
| `/plan` | Create multi-step plans |
| `/compare` | Compare model responses |
| `/hooks` | Webhook management |
| `/health` | System health check |
| `/bookmarks` | View saved links |
| `/new` | New session |
| `/clear` | Clear current session |
| `/whoami` | Current user info |
| `/tools` | List available tools |
| `/prune` | Prune context manually |
| `/skill` | Skill management |
| `/oauth` | OAuth setup (Gmail, Calendar) |
| `/queue` | Message queue management |

</details>

---

## 🔒 Security

SalmAlm follows a **dangerous features default OFF** policy:

| Feature | Default | Opt-in |
|---|---|---|
| Network bind | `127.0.0.1` (loopback only) | `SALMALM_BIND=0.0.0.0` |
| Shell operators (pipe, redirect, chain) | Blocked | `SALMALM_ALLOW_SHELL=1` |
| Home directory file read | Workspace only | `SALMALM_ALLOW_HOME_READ=1` |
| Vault (without `cryptography`) | Disabled | `SALMALM_VAULT_FALLBACK=1` for HMAC-CTR |
| Interpreters in exec | Blocked | Use `/bash` or `python_eval` tool instead |
| Dangerous exec flags (find -exec, awk -f, etc.) | Blocked | N/A (security hardening, no override) |
| HTTP request headers | Allowlist only | `SALMALM_HEADER_PERMISSIVE=1` for blocklist mode |

### Header Security

HTTP request tool uses **allowlist mode** by default — only safe headers (Accept, Content-Type, Authorization, User-Agent, etc.) are permitted. Unknown headers are rejected.

Set `SALMALM_HEADER_PERMISSIVE=1` to switch to blocklist mode (blocks only dangerous headers like Proxy-Authorization, X-Forwarded-For).

### Route Security Middleware

Every HTTP route has a **security policy** (auth, audit, CSRF, rate limit) enforced automatically via `web/middleware.py`:

- **Public routes** (`/`, `/setup`, `/static/*`) — no auth required
- **API routes** (`/api/*`) — auth required, writes audited, CSRF enforced on POST
- **Sensitive routes** (`/api/vault/*`, `/api/admin/*`) — always require auth + CSRF

Developers can't accidentally skip auth — the middleware chain enforces it structurally.

### Tool Risk Tiers

Tools are classified by risk level, and **critical tools are blocked on external network exposure without authentication**:

| Tier | Tools | External (0.0.0.0) |
|---|---|---|
| 🔴 Critical | exec, bash, file_write, file_delete, python_eval, browser_action, sandbox_exec | Auth required |
| 🟡 High | http_request, send_email, file_read, mesh_task | Allowed with warning |
| 🟢 Normal | web_search, calendar, QR, etc. | Allowed |

### External Exposure Safety

When binding to `0.0.0.0`, SalmAlm automatically:
- ⚠️ Warns if no admin password is set
- ⚠️ Warns about dangerous tools being accessible
- Blocks critical tools for unauthenticated sessions

### Additional Hardening

- **SSRF defense** — private IP blocklist on every redirect hop, scheme allowlist, userinfo block, decimal IP normalization
- **Shell operator blocking** — pipe (`|`), redirect (`>`), chain (`&&`, `||`, `;`) blocked by default in exec
- **Exec argument blocklist** — dangerous flags blocked per command: `find -exec`, `awk system()`, `tar --to-command`, `git clone/push`, `sed -i`, `xargs -I`
- **Token security** — JWT with `kid` key rotation, `jti` revocation, PBKDF2-200K password hashing
- **Login lockout** — persistent DB-backed brute-force protection with auto-cleanup
- **Audit trail** — append-only checkpoint log with automated cron (every 6 hours) + cleanup (30 days)
- **Rate limiting** — in-memory per-IP rate limiter (60 req/min) for API routes
- **WebSocket origin validation** — prevents cross-site WebSocket hijacking
- **CSP-compatible UI** — no inline scripts or event handlers; external `app.js` with ETag caching; optional strict CSP via `SALMALM_CSP_NONCE=1`
- **Exec resource limits** — foreground exec: CPU timeout+5s, 1GB RAM, 100 fd, 50MB fsize (Linux/macOS)
- **Tool timeouts** — per-tool wall-clock limits (exec 120s, browser 90s, default 60s)
- **Tool result truncation** — per-tool output limits (exec 20K, browser 10K, HTTP 15K chars)
- **SQLite hardening** — WAL journal mode + 5s busy_timeout (prevents "database is locked")
- **46 security regression tests** — SSRF bypass, header injection, exec bypass, tool tiers, route policies

See [`SECURITY.md`](SECURITY.md) for full details.

---

## 🔧 Configuration

```bash
# Server
SALMALM_PORT=18800         # Web server port
SALMALM_BIND=127.0.0.1    # Bind address (default: loopback only)
SALMALM_WS_PORT=18801     # WebSocket port
SALMALM_HOME=~/SalmAlm    # Data directory (DB, vault, logs, memory)

# AI
SALMALM_LLM_TIMEOUT=30    # LLM request timeout (seconds)
SALMALM_COST_CAP=0        # Monthly cost cap (0=unlimited)
SALMALM_REFLECT=0          # Disable self-reflection pass (saves cost/latency)

# Security
SALMALM_VAULT_PW=...         # Auto-unlock vault on start
SALMALM_ALLOW_SHELL=1        # Enable shell operators in exec
SALMALM_ALLOW_HOME_READ=1    # Allow file read outside workspace
SALMALM_VAULT_FALLBACK=1     # Allow HMAC-CTR vault without cryptography
SALMALM_HEADER_PERMISSIVE=1  # HTTP headers: blocklist mode instead of allowlist
SALMALM_CSP_NONCE=1          # Strict CSP with nonce-based script-src
SALMALM_OPEN_BROWSER=1       # Auto-open browser on server start

# Mesh
SALMALM_MESH_SECRET=...   # HMAC secret for mesh peer authentication
```

All configuration is also available through the web UI.

---

## 🏗️ Architecture

```
Browser ──WebSocket──► SalmAlm ──► Anthropic / OpenAI / Google / xAI / Ollama
   │                     │
   └──HTTP/SSE──►       ├── SQLite (sessions, usage, memory, audit)
                         ├── Model Selection (complexity-based routing)
Telegram ──►             ├── Tool Registry (62 tools)
Discord  ──►             ├── Cron Scheduler + Audit Cron
                         ├── Sub-Agent Manager (spawn/steer/collect)
Mesh Peers ──►           ├── Message Queue (offline + retry + dead letter)
                         ├── RAG Engine (TF-IDF + cosine similarity)
                         ├── OS-native Sandbox (bwrap/unshare/rlimit)
                         ├── Canvas Server (:18803)
                         ├── Security Middleware (auth/audit/rate/CSRF per route)
                         ├── Plugin System
                         └── Vault (PBKDF2 encrypted)
```

- **231 modules**, **45K+ lines**, **82 test files**, **1,710 tests**
- Pure Python 3.10+ stdlib — no frameworks, no heavy dependencies
- Route-table architecture (59 GET + 63 POST registered handlers)
- Default bind `127.0.0.1` — explicit opt-in for network exposure
- Runtime data under `~/SalmAlm` (configurable via `SALMALM_HOME`)
- Cost estimation unified in `core/cost.py` with per-model pricing
- Slash commands extracted to `core/slash_commands.py` (engine.py: 2007→1221 lines)
- Model selection extracted to `core/model_selection.py`
- Web UI JS extracted to external `static/app.js` (index.html: 3016→661 lines)

### Version Management

```bash
# Bump version across all source files (pyproject.toml + __init__.py)
python scripts/bump_version.py 0.17.0

# CI automatically checks version consistency
```

---

## 🐳 Docker (Optional)

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
docker compose up -d
```

---

## 🔌 Plugins

Drop a `.py` file in the `plugins/` directory — auto-discovered on startup:

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

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for full guide including test execution, code style, and architecture overview.

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
pip install -e ".[dev]"

# Run tests (per-file, CI-style)
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
