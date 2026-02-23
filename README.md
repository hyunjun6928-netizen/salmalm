<div align="center">

# 😈 SalmAlm (삶앎)

### Your Entire AI Life in One `pip install`

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)](https://pypi.org/project/salmalm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/hyunjun6928-netizen/salmalm/actions/workflows/ci.yml/badge.svg)](https://github.com/hyunjun6928-netizen/salmalm/actions)
[![Tests](https://img.shields.io/badge/tests-1%2C878%20passed-brightgreen)]()
[![Tools](https://img.shields.io/badge/tools-62-blueviolet)]()
[![Coverage](https://img.shields.io/badge/docstrings-99%25-blue)]()

**[한국어 README](README_KR.md)** · **[Documentation](https://hyunjun6928-netizen.github.io/salmalm/)**

</div>

---

## What is SalmAlm?

SalmAlm is a **personal AI gateway** — one Python package that gives you a full-featured AI assistant with a web UI, Telegram/Discord bots, 62 tools, browser automation, sub-agents, and memory system.

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
| 🤖 | Multi-provider routing | ✅ Auto 3-tier | ❌ | ✅ | ✅ |
| 🧠 | Memory (2-layer + auto-recall) | ✅ | ❌ | ✅ | ❌ |
| 🤖 | Sub-agents (spawn/steer/notify) | ✅ | ❌ | ✅ | ❌ |
| 🌐 | Browser automation (Playwright) | ✅ | ❌ | ✅ | ❌ |
| 🧠 | Extended Thinking (4 levels) | ✅ | ❌ | ✅ | ❌ |
| 🔐 | Encrypted Vault (AES-256-GCM) | ✅ | ❌ | ❌ | ❌ |
| 📱 | Telegram + Discord | ✅ | ❌ | ✅ | ❌ |
| 🧩 | MCP (Model Context Protocol) | ✅ | ❌ | ❌ | ✅ |
| 🦙 | Local LLM (Ollama/LM Studio/vLLM) | ✅ | ❌ | ✅ | ✅ |
| 📦 | Zero dependencies* | ✅ | N/A | ❌ | ❌ |
| 💰 | Cost optimization (83% savings) | ✅ | ❌ | ❌ | ❌ |

*\*stdlib-only core; optional `cryptography` for AES-256-GCM vault*

---

## ⚡ Quick Start (5분이면 충분합니다)

### Step 1: 설치 (30초)
```bash
pip install salmalm
```

### Step 2: 실행 (10초)
```bash
salmalm --open
# → 브라우저가 자동으로 열립니다 (http://localhost:18800)

# 또는 (editable install에서 console_script가 안 될 때):
python3 -m salmalm --open
```

### Step 3: API 키 입력 (2분)
1. 웹 UI의 **Setup Wizard**가 자동으로 뜹니다
2. AI 제공사의 API 키를 붙여넣기 하세요:
   - [Anthropic Console](https://console.anthropic.com/) → API Keys
   - [OpenAI Platform](https://platform.openai.com/api-keys) → API Keys
   - 또는 [Google AI Studio](https://aistudio.google.com/apikey) → API Keys
3. "Save" 클릭 → 끝!

### Step 4: 대화 시작 (바로!)
```
"오늘 날씨 어때?"          → 웹 검색 + 답변
"이 코드 리뷰해줘"         → 파일 읽기 + 분석
"/model sonnet"            → 모델 변경
"/help"                    → 전체 명령어 보기
```

> 💡 **자연어로 말하면 됩니다.** 62개 도구를 AI가 알아서 선택합니다.
> 명령어를 외울 필요 없이, 하고 싶은 걸 그냥 말하세요.

### 고급 옵션
```bash
salmalm --shortcut          # 바탕화면 바로가기 생성
salmalm doctor              # 자가진단
salmalm --update            # 자동 업데이트
SALMALM_PORT=8080 salmalm   # 포트 변경
```

### Supported Providers (Auto-Routing)

| Provider | Models | Tier |
|---|---|---|
| Anthropic | Claude Opus 4.6, Sonnet 4.6, Haiku 4.5 | Complex / Moderate / Simple |
| OpenAI | GPT-5.2, GPT-5, o4-mini | Complex / Moderate |
| Google | Gemini 3.1 Pro, 2.5 Flash | Moderate / Simple |
| xAI | Grok-4, Grok-3-mini | Complex / Simple |
| DeepSeek | R1, Chat | Via OpenRouter |
| **Local LLM** | Ollama / LM Studio / vLLM | Auto-detected |

---

## 🧠 Architecture

```
Browser ──WebSocket──► SalmAlm ──► Anthropic / OpenAI / Google / xAI / Local
   │                     │
   └──HTTP/SSE──►       ├── Smart Model Router (3-tier: simple/moderate/complex)
                         ├── Engine Pipeline (classify → route → context → execute)
Telegram ──►             ├── Memory System (2-layer + auto-recall + TF-IDF RAG)
Discord  ──►             ├── Sub-Agent Manager (spawn/steer/kill/notify)
                         ├── Tool Registry (62 tools, risk-tiered)
                         ├── Browser Automation (Playwright subprocess)
                         ├── Security Middleware (auth/CSRF/CSP/rate-limit/audit)
                         ├── Vault (PBKDF2-200K + AES-256-GCM)
                         └── Cron / Backup / Self-Diagnostics
```

### Codebase Metrics

| Metric | Value |
|---|---|
| Python files | 192 |
| Total lines | ~52,450 |
| Functions | ~1,800 |
| Max cyclomatic complexity | 20 (all functions) |
| Largest file | 778 lines |
| Files > 800 lines | 0 |
| Docstring coverage | 99% |
| Return type hints | 81% |
| Tests | 1,878 passing |

---

## 🎯 Feature Overview

### Core AI Engine
- **3-tier auto-routing** — simple→Haiku ($1/M), moderate→Sonnet ($3/M), complex→GPT-5.2/Sonnet ($2-3/M)
- **Extended Thinking** — 4 levels (low/medium/high/xhigh) with budget control
- **Cross-provider message sanitization** — seamless model switching mid-conversation
- **5-stage context compaction** — strip binary → trim tools → drop old → truncate → LLM summarize
- **Prompt caching** — Anthropic cache_control for 90% cost reduction
- **Model failover** — exponential backoff + retry across providers
- **Infinite loop detection** — 3+ same (tool, args_hash) in last 6 iterations = auto-break

### Memory System (OpenClaw-style)
- **2-layer architecture** — `MEMORY.md` (curated long-term) + `memory/YYYY-MM-DD.md` (daily logs)
- **Auto-recall** — searches memory before each response, injects relevant context
- **Auto-curation** — promotes important daily entries to long-term memory
- **TF-IDF + cosine similarity search** across all memory files
- **Memory scrubbing** — API keys/secrets auto-redacted before storage

### Sub-Agent System
- **Spawn** background AI workers with independent sessions
- **Thinking level** per agent (low/medium/high/xhigh)
- **Labels** for human-readable naming
- **Steer** running agents with mid-task guidance
- **Auto-notify** on completion (WebSocket + Telegram push)
- **Collect** results (push-style, like OpenClaw)

```
/subagents spawn Review this PR --model sonnet --thinking high --label pr-review
/subagents list
/subagents steer abc123 Focus on security issues
/subagents kill abc123
/subagents collect
```

### 62 Built-in Tools
Web search (Brave), email (Gmail), calendar (Google), file I/O, shell exec, Python eval (opt-in), image generation (DALL-E/Aurora), TTS/STT, **browser automation (Playwright)**, RAG search, QR codes, system monitor, OS-native sandbox, mesh networking, and more.

### Web UI
- Real-time streaming (SSE-first, WebSocket for typing indicators)
- Embedding RAG — hybrid vector search (OpenAI/Google embeddings + BM25 fallback)
- Agent steer — `/agent steer <label> <message>` to control running sub-agents
- Browser aria-ref compression — 10x token savings for browser automation
- Thinking stream UI — real-time collapsible thinking display
- Session branching, rollback, search (`Ctrl+K`), command palette (`Ctrl+Shift+P`)
- Dark/Light themes, **EN/KR i18n**
- Image paste/drag-drop with vision, code syntax highlighting
- Settings panels: Engine, Routing, Telegram, Discord, Memory, Cron, Backup
- PWA installable

### Channels
- **Web** — full SPA at `localhost:18800`
- **Telegram** — polling + webhook with inline buttons
- **Discord** — bot with thread support and mentions

---

## ✨ Unique Features

| Feature | What it does |
|---|---|
| **Self-Evolving Prompt** | AI auto-generates personality rules from conversations |
| **Dead Man's Switch** | Emergency actions if you go inactive for N days |
| **Shadow Mode** | AI learns your style, replies as you when away |
| **Life Dashboard** | Unified health, finance, habits, calendar view |
| **Mood-Aware Response** | Detects emotional state, adjusts tone |
| **A/B Split Response** | Two model perspectives on the same question |
| **Time Capsule** | Schedule messages to your future self |
| **Thought Stream** | Private journaling with hashtag search and mood tracking |

---

## 💰 Cost Optimization

SalmAlm is designed to minimize API costs without sacrificing quality:

| Feature | Effect |
|---|---|
| Dynamic tool loading | 62 tools → 0 (chat) or 7-12 (actions) per request |
| 3-tier auto-routing | Simple→$1/M, Moderate→$3/M, Complex→$3/M (no Opus needed) |
| Tool schema compression | 7,749 → 693 tokens (91% reduction) |
| System prompt compression | 762 → 310 tokens |
| Intent-based max_tokens | Chat 512, search 1024, code 4096 |
| Intent-based history trim | Chat 10 turns, code 20 turns |
| Cache TTL | Same question cached (30min–24h, configurable) |
| Cross-provider failover | Falls back to cheaper model on rate limit |

**Result: $7.09/day → $1.23/day (83% savings at 100 calls/day)**

---

## 🔒 Security

**Dangerous features default OFF** — everything requires explicit opt-in:

| Feature | Default | Opt-in |
|---|---|---|
| Network bind | `127.0.0.1` | `SALMALM_BIND=0.0.0.0` |
| Shell operators | Blocked | `SALMALM_ALLOW_SHELL=1` |
| Python eval | **Disabled** | `SALMALM_PYTHON_EVAL=1` |
| Home dir file read | Workspace only | `SALMALM_ALLOW_HOME_READ=1` |
| Plugin system | Disabled | `SALMALM_PLUGINS=1` |

### Security Hardening
- **SSRF defense** — DNS pinning + private IP block on every redirect hop
- **Tool risk tiers** — Critical tools blocked on external bind without auth
- **CSRF** — Origin validation + `X-Requested-With` header
- **CSP** — Strict nonce mode available
- **Audit log** — secrets scrubbed before logging (9 pattern types)
- **Memory scrubbing** — API keys auto-redacted before storage
- **Path validation** — `Path.is_relative_to()` for all file operations
- **Session isolation** — user_id scoped, export restricted to own data
- **Node dispatch** — HMAC-SHA256 signed payloads
- **150+ security regression tests** in CI

See [`SECURITY.md`](SECURITY.md) for full threat model.

---

## 🦙 Local LLM Setup

| Server | Endpoint | Setup |
|---|---|---|
| **Ollama** | `http://localhost:11434/v1` | `ollama serve` |
| **LM Studio** | `http://localhost:1234/v1` | Start server in LM Studio |
| **vLLM** | `http://localhost:8000/v1` | `vllm serve <model>` |

Settings → **Local LLM** → paste endpoint → Save. Models auto-discovered.

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
SALMALM_MAX_TOOL_ITER=25   # Max tool iterations
SALMALM_COST_CAP=0         # Daily cost cap (0=unlimited)

# Security
SALMALM_PYTHON_EVAL=1       # Enable python_eval tool
SALMALM_PLUGINS=1           # Enable plugin system
SALMALM_ALLOW_SHELL=1       # Enable shell operators
```

All settings also available in **Web UI → Settings**.

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

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## 📄 License

[MIT](LICENSE)

---

<div align="center">

**SalmAlm** = 삶(Life) + 앎(Knowledge)

*Your life, understood by AI.*

</div>
