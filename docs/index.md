# 😈 SalmAlm

## Personal AI Gateway — Your AI Assistant in One Command

---

**SalmAlm** is a pure-Python personal AI gateway that turns any LLM API into a fully-featured AI assistant with 67 built-in tools, multi-channel support (Web, Telegram, Discord), and minimal dependencies.

## Quick Start

```bash
pip install salmalm
salmalm
```

Open **http://localhost:18800** — the Setup Wizard guides you through API key configuration.

## Key Features

| Feature | Description |
|---|---|
| 🤖 Smart model routing | Auto-selects by complexity: simple→Haiku, moderate→Sonnet, complex→Opus |
| 🧠 Extended thinking | Deep reasoning with budget control |
| 🔧 67 built-in tools | File, web, exec, email, calendar, RAG, TTS, image gen, browser, and more |
| 💬 30+ slash commands | Full control via Telegram/Discord |
| 🔗 Telegram & Discord | OpenClaw-style UX: ack reactions, reply-to, streaming preview, command menus |
| 💰 Cost optimization | $7/day → $1.2/day (83% savings at 100 calls/day) |
| 🔒 Security hardened | 150+ security tests, AES-256 vault, SSRF defense, tool risk tiers |
| 🦙 Local LLM | Ollama, LM Studio, vLLM support |
| 📱 PWA installable | Mobile-ready web UI with EN/KR i18n |
| 🧠 Memory system | Auto-curated long-term memory + daily logs + TF-IDF search |

## Supported Providers

| Provider | Models |
|---|---|
| **Anthropic** | Claude Opus 4, Sonnet 4, Haiku 4.5 |
| **OpenAI** | GPT-5.2, GPT-4.1, o3, o4-mini |
| **Google** | Gemini 3 Pro/Flash, 2.5 Pro/Flash |
| **xAI** | Grok-4, Grok-3 |
| **Local LLM** | Ollama, LM Studio, vLLM (any OpenAI-compatible endpoint) |

## Project Info

- **Version**: v0.18.73
- **License**: MIT
- **Python**: 3.10+
- **Tests**: 1,809 passing
- **Modules**: 234
- **Lines**: 49K+

## Links

- [GitHub](https://github.com/hyunjun6928-netizen/salmalm)
- [PyPI](https://pypi.org/project/salmalm/)
