<div align="center">

# 😈 SalmAlm (삶앎)

### Your Entire AI Life in One `pip install`

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)](https://pypi.org/project/salmalm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/hyunjun6928-netizen/salmalm/actions/workflows/ci.yml/badge.svg)](https://github.com/hyunjun6928-netizen/salmalm/actions)
[![Tests](https://img.shields.io/badge/tests-1%2C908%20passed-brightgreen)]()
[![Tools](https://img.shields.io/badge/tools-66-blueviolet)]()

**[한국어 README](README_KR.md)** · **[Documentation](https://hyunjun6928-netizen.github.io/salmalm/)**

</div>

---

## What is SalmAlm?

SalmAlm is a **self-hosted personal AI gateway** — one Python package that gives you a full-featured AI assistant with web UI, Telegram/Discord bots, 66 tools, memory system, sub-agents, and multi-provider model routing.

No Docker. No Node.js. No config files. Just:

```bash
pip install salmalm
python3 -m salmalm
# → http://localhost:18800
```

First launch opens a **Setup Wizard** — paste an API key, pick a model, done.

---

## ⚡ Quick Start

```bash
# Install (recommended)
pipx install salmalm

# Or with pip (in a venv)
python3 -m venv ~/.salmalm-env && ~/.salmalm-env/bin/pip install salmalm

# Run
salmalm --open
# → Browser opens http://localhost:18800

# Setup Wizard appears → paste API key → done!
```

### Supported Providers

| Provider | Models | Tier |
|---|---|---|
| Anthropic | Claude Opus 4.6, Sonnet 4.6, Haiku 4.5 | Complex / Moderate / Simple |
| OpenAI | GPT-5.2, GPT-5.1, o3 | Complex / Moderate |
| Google | Gemini 3 Pro, 3 Flash | Moderate / Simple |
| xAI | Grok-4, Grok-3-mini | Complex / Simple |
| **Local** | Ollama / LM Studio / vLLM | Auto-detected |

---

## 🧠 Architecture

```
Browser ──SSE/WS──► SalmAlm ──► Anthropic / OpenAI / Google / xAI / Ollama
Telegram ──►           ├── 3-Tier Model Router (simple/moderate/complex)
Discord  ──►           ├── Engine Pipeline (classify → route → context → execute)
                       ├── Memory (MEMORY.md + daily logs + auto-recall + RAG)
                       ├── Sub-Agent Manager (spawn/steer/kill/notify)
                       ├── 62 Tools (risk-tiered, dynamic loading)
                       ├── Vault (PBKDF2-200K + AES-256-GCM)
                       └── Cron / Backup / Self-Diagnostics
```

---

## 🎯 Features

### AI Engine
- **3-tier auto-routing** — simple→Haiku, moderate→Sonnet, complex→Opus/GPT-5 (cost-optimized)
- **Extended Thinking** — 4 levels (low/medium/high/xhigh) with budget control
- **5-stage context compaction** — keeps conversations going without losing context
- **Prompt caching** — Anthropic cache_control for cost reduction
- **Model failover** — automatic retry across providers
- **Tier momentum** — prevents model downgrade mid-complex-task

### Memory System
- **2-layer** — `MEMORY.md` (curated long-term) + `memory/YYYY-MM-DD.md` (daily logs)
- **Auto-recall** — searches memory before each response, injects relevant context
- **Auto-curation** — promotes important daily entries to long-term memory
- **TF-IDF RAG** — cosine similarity search across all files

### Sub-Agents
- Spawn background AI workers with independent sessions
- Thinking level per agent, labels, mid-task steering
- Auto-notify on completion (WebSocket + Telegram)

### 62 Built-in Tools
Shell exec, file I/O, web search (Brave), web fetch, Python eval (opt-in), image gen (DALL-E), TTS/STT, browser automation (Playwright), RAG search, cron jobs, system monitor, and more.

### Unique Features

| Feature | What it does |
|---|---|
| **Self-Evolving Prompt** | AI auto-generates personality rules from conversations (max 20, FIFO) |
| **Dead Man's Switch** | Automated actions (email, commands) if you go inactive for N days |
| **Shadow Mode** | AI learns your communication style, can reply as you when away |
| **Life Dashboard** | Unified view: expenses, habits, calendar, mood, routines |
| **Mood-Aware Response** | Detects emotional state from NLP signals, adjusts tone |
| **A/B Split Response** | Two model perspectives on the same question, side-by-side |
| **Time Capsule** | Schedule encrypted messages to your future self |
| **Thought Stream** | Private journaling with hashtag search and mood tracking |
| **Agent-to-Agent** | HMAC-SHA256 signed communication between SalmAlm instances |
| **Workflow Engine** | Multi-step AI workflows with conditions and loops |
| **Message Queue** | 5 modes: collect, steer, followup, steer-backlog, interrupt |
| **MCP Marketplace** | Install/manage Model Context Protocol tool servers |

### Web UI
- SSE streaming with real-time thinking display
- Multi-file upload (drag-drop, paste, clip button)
- Session management (branch, rollback, search)
- Command palette (`Ctrl+Shift+P`), dark/light themes, EN/KR i18n
- Settings: Engine, Routing, Channels, Memory, Cron, Backup
- PWA installable

### Channels
- **Web** — SPA at `localhost:18800`
- **Telegram** — polling + webhook with inline buttons
- **Discord** — bot with thread support

---

## 💰 Cost Optimization

| Technique | Effect |
|---|---|
| 3-tier auto-routing | Simple→$1/M, Complex→$3/M |
| Dynamic tool loading | 62 → 0-12 tools per request |
| Tool schema compression | 91% token reduction |
| Intent-based max_tokens | Chat 512, code 4096 |
| Response caching | Same question cached 30min-24h |

**$7/day → $1.2/day at 100 calls/day (83% savings)**

---

## 🔒 Security

All dangerous features **default OFF**:

| Feature | Default | Opt-in |
|---|---|---|
| Network bind | `127.0.0.1` | `SALMALM_BIND=0.0.0.0` |
| Shell operators | Blocked | `SALMALM_ALLOW_SHELL=1` |
| Python eval | Disabled | `SALMALM_PYTHON_EVAL=1` |

Plus: SSRF defense, CSRF protection, CSP, audit logging, memory scrubbing, path validation, 150+ security tests.

See [`SECURITY.md`](SECURITY.md) for details.

---

## 🦙 Local LLM

```bash
# Ollama
ollama serve
# → Settings → Local LLM → http://localhost:11434/v1 → models auto-discovered
```

Also supports LM Studio (`localhost:1234/v1`) and vLLM (`localhost:8000/v1`).

---

## 📊 Codebase

| Metric | Value |
|---|---|
| Python files | 192 |
| Lines of code | ~52,760 |
| Tools | 62 |
| Tests | 1,908 passing |
| Max cyclomatic complexity | ≤20 (all but 1 function) |
| Files > 800 lines | 0 |

---

## 🤝 Contributing

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
pip install -e ".[dev]"
python -m pytest tests/ -q --timeout=30 -x \
  --ignore=tests/test_multi_tenant.py \
  --ignore=tests/test_fresh_install_e2e.py
```

---

## 📄 License

[MIT](LICENSE)

---

<div align="center">

**SalmAlm** = 삶(Life) + 앎(Knowledge)

*Your life, understood by AI.*

</div>
