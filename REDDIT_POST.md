# Title
I built a self-hosted AI gateway in pure Python — zero dependencies, 30 tools, 27 models

# Subreddit
r/selfhosted (flair: Product Announcement)

# Body

I got tired of juggling API keys across different AI tools, so I built **SalmAlm** — a self-hosted AI gateway that runs entirely on Python's standard library. No npm, no Docker required, no dependency hell.

## What it does

- **27 LLM models** through one interface (Claude, GPT, Grok, Gemini, DeepSeek, Llama)
- **30 built-in tools** — file ops, code execution, web search, browser automation, cron jobs, RAG search
- **Intelligence Engine** — auto-classifies your intent, picks the cheapest model that can handle it, runs tools in parallel, then self-evaluates
- **Web UI** with dark/light theme, markdown rendering, file upload, real-time streaming
- **Plugin system** — drop a `.py` file in `plugins/` and it loads automatically
- **MCP support** — works with Cursor, VS Code, etc.
- **Telegram & Discord bots** — chat from your phone
- **Skill system** — install skills from Git repos with one command
- **Local LLM support** — Ollama integration, no API key needed

## Quick start

```bash
pip install salmalm
salmalm
# → http://localhost:18800
```

Or Docker:
```bash
docker compose up -d
```

Windows users get a desktop shortcut automatically on first run.

## Security

- AES-256-GCM encrypted vault (PBKDF2 200K iterations)
- JWT auth + RBAC (admin/user/readonly)
- Rate limiting, CORS whitelist, command blocklist
- SHA-256 audit trail

## Stats

- ~9,000 lines across 20 modules
- 85 unit tests, 18/18 self-test on startup
- MIT licensed

## What makes it different from OpenWebUI / LibreChat?

1. **Zero dependencies** — pure Python stdlib. `pip install` and go. No Node.js, no Docker, no database server.
2. **Built-in tool execution** — not just a chat UI. It can actually run commands, edit files, search the web, manage cron jobs.
3. **Intelligence Engine** — auto-routes to the cheapest model that can handle your task. Saves money without thinking about it.
4. **Lightweight** — single process, ~50MB memory. Runs on a Raspberry Pi.

**GitHub:** https://github.com/hyunjun6928-netizen/salmalm
**PyPI:** https://pypi.org/project/salmalm/

Would love feedback. What features would make this useful for your setup?
