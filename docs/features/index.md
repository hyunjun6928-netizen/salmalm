# Features Overview

SalmAlm packs 43 tools and 11 feature systems into a single `pip install` — zero external dependencies.

## Feature Map

| Feature | Description | Key Tools |
|---------|-------------|-----------|
| [Multi-Model Routing](multi-model.md) | 6 providers, auto complexity routing | — |
| [Extended Thinking](thinking.md) | Chain-of-thought reasoning (4 levels) | — |
| [RAG & Knowledge Base](rag.md) | Local vector search, Korean support | `rag_search`, `file_index` |
| [MCP Integration](mcp.md) | Model Context Protocol server | — |
| [Session Management](sessions.md) | Auto-compaction, per-user scoping | — |
| [Security & Vault](security.md) | Encrypted key storage, OWASP hardening | — |
| [Personal Assistant](personal.md) | Expenses, habits, reminders, notes | `expense`, `habit`, `reminder` |
| [Telegram & Discord](channels.md) | Bot integration with rich UX | — |
| [Self-Evolution](self-evolve.md) | Auto memory curation, prompt evolution | `memory_write` |
| [SLA & Monitoring](sla.md) | Latency tracking, uptime, cost metrics | — |

## Tool Categories

### Core (6 tools — always available)
`exec`, `exec_session`, `web_search`, `web_fetch`, `read_file`, `write_file`

### Code & System (8 tools)
`system_monitor`, `git`, `code_review`, `file_index`, `project_init`

### Personal (9 tools)
`reminder`, `note`, `expense`, `habit`, `journal`, `save_link`, `rss_reader`, `weather`, `qr_code`

### Communication (4 tools)
`email`, `translate`, `tts_generate`, `web_screenshot`

### AI & Knowledge (6 tools)
`rag_search`, `memory_write`, `memory_search`, `soul_edit`, `sub_agent`, `mesh`

### Configuration (4 tools)
`switch_model`, `manage_sessions`, `system_config`, `dashboard`

## Cost Optimization

SalmAlm's engine optimization reduces token usage by up to 83%:

| Optimization | Savings |
|-------------|---------|
| Dynamic tool selection | 91% tool schema reduction |
| Auto model routing | 12x cheaper for simple tasks |
| Context compaction | 50% threshold reduction |
| Tool result truncation | 50% per-tool limit reduction |
| Intent-based history | Fewer messages in context |

See [Engine Optimization](../configuration.md) for details.
