# Integrations Rules

## Files
- `telegram.py` — Telegram bot (long-polling, pure stdlib)
- `discord_bot.py` — Discord bot (Gateway WebSocket + HTTP API)
- `mcp.py` — Model Context Protocol server + client (JSON-RPC 2.0)
- `nodes.py` — Remote node control (SSH + HTTP agents)
- `browser.py` — Chrome DevTools Protocol (CDP) automation
- `agents.py` — SkillLoader, PluginLoader, SubAgent

## Telegram
- Long-polling via `getUpdates` (not webhook).
- Must use `asyncio.to_thread()` for polling (sync urllib in async context).
- Start polling LAST — after all other initialization.
- Can't share bot token with another service (e.g., OpenClaw) — message conflicts.
- Owner ID check: only respond to configured owner.

## Discord
- Pure stdlib Gateway (WebSocket) — no discord.py library.
- Heartbeat required to maintain connection.
- Message handler registered via `@discord_bot.on_message` decorator.

## MCP (Model Context Protocol)
- JSON-RPC 2.0 over stdio or HTTP.
- Server exposes SalmAlm's 32 tools to external MCP clients.
- Client connects to external MCP servers for additional tools.
- Config persisted in `mcp_config.json`.

## Nodes
- Lightweight remote agent management.
- SSH nodes: command execution via subprocess ssh.
- HTTP nodes: REST API calls to remote SalmAlm instances.
- Config persisted in `nodes_config.json`.

## Browser (CDP)
- Chrome DevTools Protocol over WebSocket.
- Requires Chrome/Chromium running with `--remote-debugging-port`.
- Async methods: `connect()`, `evaluate()`, `click()`, `get_text()`, `get_tabs()`.
- Not available in headless environments without Chrome installed.

## Plugins
- `plugins/*.py` scanned on startup.
- Files starting with `_` are skipped.
- Each plugin must export `TOOLS` list + `execute()` function.
- Hot-reload via `/plugins reload` command.

## Skills
- Markdown-based skill files in `skills/` directory.
- SkillLoader.match() finds relevant skill for a query.
- Skills provide context/instructions, not executable code.
