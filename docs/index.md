# SalmAlm (삶앎)

**Your Personal AI Gateway — 43 Tools, 6 Providers, Zero Dependencies.**

```bash
pip install salmalm
salmalm
```

That's it. Open `http://localhost:18800` and start talking.

## What is SalmAlm?

SalmAlm is a personal AI assistant framework that runs entirely on your machine. It connects to multiple AI providers (Anthropic, OpenAI, Google, xAI, DeepSeek, local LLMs) and provides 43 built-in tools for coding, personal productivity, knowledge management, and more.

**삶앎** (SalmAlm) = **삶**(life) + **앎**(knowledge) — "knowing life."

## Key Features

- 🤖 **6 AI Providers** — Claude, GPT, Gemini, Grok, DeepSeek, Ollama/LM Studio
- 🔧 **43 Built-in Tools** — exec, web search, file ops, git, email, reminders, expenses, RAG...
- 💰 **Smart Cost Optimization** — Auto routing saves 83% vs always-Sonnet ($7.09→$1.23/day)
- 🔒 **Encrypted Vault** — API keys stored with AES-256, never in plaintext
- 📱 **Telegram & Discord** — Full bot integration with reactions, drafts, rich formatting
- 🧠 **RAG Knowledge Base** — Local vector search with Korean jamo support
- 🔌 **MCP Server** — Model Context Protocol for tool interoperability
- 📊 **Web Dashboard** — Real-time monitoring, session management, settings UI
- 🐍 **Pure Python** — Zero external dependencies, stdlib only

## Quick Start

```bash
# Install
pip install salmalm

# Run
salmalm

# Or with specific port
salmalm --port 8080
```

On first launch, the setup wizard guides you through API key configuration.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Telegram    │     │   Web UI     │     │  Discord    │
│  Bot         │────▶│  :18800      │◀────│  Bot        │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
                    ┌──────▼───────┐
                    │   Engine     │ ← Auto Routing
                    │  (Pipeline)  │ ← Context Mgmt
                    └──────┬───────┘ ← Tool Selection
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼───┐ ┌─────▼─────┐
        │ Anthropic  │ │OpenAI │ │  Google   │
        │ xAI       │ │DeepSk │ │  Local    │
        └───────────┘ └───────┘ └───────────┘
```

## Documentation

- [Getting Started](getting-started.md) — Installation and first setup
- [Commands](commands.md) — Slash commands reference
- [Tools](tools.md) — All 43 tools documented
- [Features](features/index.md) — Deep dive into each feature
- [Configuration](configuration.md) — Environment variables and settings
- [Architecture](architecture.md) — Internal design and module structure
- [API Reference](api/index.md) — HTTP API documentation
- [Deployment](deployment.md) — Production deployment guide
- [FAQ](FAQ_EN.md) — Frequently asked questions

## Project Stats

| Metric | Value |
|--------|-------|
| Python files | 266 |
| Total lines | 51K |
| Functions | 2,162 |
| Test count | 1,817 |
| Max cyclomatic complexity | 20 |
| Largest file | 778 lines |
| Docstring coverage | 99% |
| Type hint coverage | 81% |

## Links

- [PyPI](https://pypi.org/project/salmalm/)
- [GitHub](https://github.com/hyunjun6928-netizen/salmalm)
- [Changelog](changelog.md)
