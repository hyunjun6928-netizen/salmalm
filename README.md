# SalmAlm — Private AI Gateway

> Self-hosted, privacy-first AI gateway. Your data never leaves your machine.

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Quick Start
```bash
pip install salmalm
salmalm start
# Open http://localhost:8000
```

## Features
- 🔒 **100% Local** — no data sent to third parties
- 🤖 **Multi-LLM** — Claude, GPT, Gemini in one interface
- 📚 **RAG** — chat with your own documents
- 🛠️ **62 built-in tools** — web search, file ops, code execution
- 🔐 **Vault encryption** for sensitive data
- 🐳 **Docker ready**

## Docker
```bash
docker-compose up -d
```

## Requirements
- Python 3.10+
- API key for at least one LLM provider

---

<div align="center">

# 😈 SalmAlm

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/pypi/pyversions/salmalm)](https://pypi.org/project/salmalm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/hyunjun6928-netizen/salmalm/actions/workflows/ci.yml/badge.svg)](https://github.com/hyunjun6928-netizen/salmalm/actions)
[![Tests](https://img.shields.io/badge/tests-1%2C908%20passed-brightgreen)]()

**Self-hosted personal AI gateway — one `pip install`, no Docker, no Node.js.**

[Documentation](https://hyunjun6928-netizen.github.io/salmalm/) · [Korean README](README_KR.md) · [Changelog](CHANGELOG.md)

</div>

---

## Features

- **Multi-provider LLM routing** — OpenAI, Anthropic, Google, xAI, Ollama with 3-tier auto-routing (simple / moderate / complex)
- **Automatic failover + circuit breaker** — transparent retry across providers; unhealthy endpoints are isolated
- **RAG** — BM25 + semantic search with Reciprocal Rank Fusion (RRF); indexes your local files automatically
- **Vault encryption** — AES-256-GCM with PBKDF2-200K key derivation; opt-in per secret
- **OAuth2** — Google and Anthropic social login flows
- **WebSocket streaming** — real-time token streaming to the web UI
- **Multi-user auth** — JWT-based session management with per-user quotas
- **Cost tracking + daily quotas** — per-model token accounting with configurable daily spend caps
- **Prometheus metrics** — `/metrics` endpoint; drop-in for any Grafana stack
- **SQLite audit log** — WAL mode; every request, tool call, and auth event is logged
- **62 built-in tools** — shell exec, file I/O, web search (Brave), browser automation, TTS/STT, image gen, cron, and more

---

## Quick Start

```bash
pip install salmalm
salmalm start
# → http://localhost:18800
```

A **Setup Wizard** opens on first launch. Paste an API key, pick a model — done.

> **Recommended:** use `pipx install salmalm` to avoid dependency conflicts.

---

## Configuration

All configuration is via environment variables. No config files required.

| Variable | Default | Description |
|---|---|---|
| `SALMALM_PORT` | `18800` | HTTP listen port |
| `SALMALM_BIND` | `127.0.0.1` | Bind address (`0.0.0.0` for LAN access) |
| `SALMALM_SECRET` | *(none)* | Master secret for Vault + JWT signing (set this!) |
| `SALMALM_ALLOW_SHELL` | `0` | Enable shell operators in tool exec (`1` to opt in) |
| `SALMALM_PYTHON_EVAL` | `0` | Enable Python eval tool (`1` to opt in) |
| `SALMALM_DAILY_BUDGET` | *(none)* | Daily spend cap in USD, e.g. `2.00` |

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Send a message; returns SSE stream |
| `GET` | `/api/sessions` | List chat sessions |
| `DELETE` | `/api/sessions/{id}` | Delete a session |
| `GET` | `/api/tools` | List available tools and their schemas |
| `GET` | `/api/models` | List discovered models across all providers |
| `GET` | `/api/costs` | Cost summary (today / 30-day) |
| `GET` | `/metrics` | Prometheus metrics endpoint |
| `GET` | `/api/vault` | List vault entries (values redacted) |
| `POST` | `/api/vault` | Store an encrypted secret |
| `GET` | `/api/audit` | Recent audit log entries |

---

## Architecture

```
Client (Browser / Telegram / Discord)
        │
        ▼  HTTP + WebSocket
┌───────────────────────────────────────────┐
│                 SalmAlm                   │
│                                           │
│  ┌─────────────┐   ┌───────────────────┐  │
│  │ 3-Tier      │   │  Engine Pipeline  │  │
│  │ LLM Router  │──▶│  classify → route │  │
│  │ + Failover  │   │  → context → exec │  │
│  └─────────────┘   └───────────────────┘  │
│         │                                 │
│  ┌──────▼──────────────────────────────┐  │
│  │  Providers                          │  │
│  │  OpenAI · Anthropic · Google · xAI  │  │
│  │  Ollama · LM Studio · vLLM          │  │
│  └─────────────────────────────────────┘  │
│                                           │
│  RAG (BM25 + Semantic + RRF)              │
│  Vault (AES-256-GCM)                      │
│  JWT Auth · OAuth2                        │
│  62 Tools · Cron · Sub-Agents             │
│  SQLite Audit (WAL) · Prometheus /metrics │
└───────────────────────────────────────────┘
```

---

## Development

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
pip install -e ".[dev]"
pytest tests/ -q --timeout=30 -x \
  --ignore=tests/test_multi_tenant.py \
  --ignore=tests/test_fresh_install_e2e.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

[MIT](LICENSE) © 2024 hyunjun6928-netizen

---

<div align="center">

**SalmAlm** = 삶 (Life) + 앎 (Knowledge)

*Your life, understood by AI.*

</div>

---

# SalmAlm — Private AI Gateway

> Self-hosted, privacy-first AI gateway. Your data never leaves your machine.

## Quick Start
```bash
pip install salmalm
salmalm start
# Open http://localhost:8000
```

## Features
- 🔒 100% local — no data sent to third parties
- 🤖 Multi-LLM — Claude, GPT, Gemini in one place
- 📚 RAG — chat with your documents
- 🛠️ 62 built-in tools
- 🔐 Vault encryption for sensitive data

## Docker
```bash
docker-compose up -d
```
