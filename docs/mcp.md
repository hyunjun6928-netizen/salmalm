# MCP Integration Guide

SalmAlm implements the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) — an open standard for connecting AI assistants to tools.

## What This Means

You can use SalmAlm's 32 tools (code execution, web search, file I/O, RAG, etc.) from **any MCP-compatible AI client**:

- **Claude Desktop** / **Claude Code**
- **Cursor** (AI code editor)
- **VS Code** (via Copilot MCP extension)
- **Gemini CLI**
- **Any MCP client**

## Quick Setup

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "salmalm": {
      "command": "python",
      "args": ["-m", "salmalm.mcp", "--server"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add salmalm -- python -m salmalm.mcp --server
```

### Cursor

Add to `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "salmalm": {
      "command": "python",
      "args": ["-m", "salmalm.mcp", "--server"]
    }
  }
}
```

### VS Code (Copilot MCP)

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "salmalm": {
      "command": "python",
      "args": ["-m", "salmalm.mcp", "--server"]
    }
  }
}
```

## Available Tools (32)

All SalmAlm tools are exposed via MCP:

| Tool | Description |
|------|-------------|
| `exec` | Execute shell commands (sandboxed) |
| `read_file` / `write_file` / `edit_file` | File operations |
| `web_search` | Brave Search API |
| `web_fetch` | Fetch URL content |
| `python_eval` | Execute Python code (sandboxed subprocess) |
| `http_request` | HTTP client (GET/POST/PUT/DELETE) |
| `system_monitor` | CPU, memory, disk, network stats |
| `image_generate` | xAI Aurora / OpenAI DALL-E |
| `image_analyze` | Vision AI analysis |
| `tts` / `stt` | Text-to-Speech / Speech-to-Text |
| `json_query` | jq-style JSON queries |
| `diff_files` | File comparison |
| `regex_test` | Regex testing |
| `hash_text` | Hashing + password/UUID generation |
| `rag_search` | Local BM25 search |
| `memory_read` / `memory_write` / `memory_search` | Persistent memory |
| `browser` | Chrome CDP automation |
| `node_manage` | Remote SSH/HTTP nodes |
| `cron_manage` | Scheduled tasks |
| `sub_agent` | Background task agents |
| `skill_manage` | Skill management |
| `plugin_manage` | Plugin management |
| `mcp_manage` | Manage external MCP servers |
| `health_check` | System diagnostics |
| `clipboard` | Cross-session clipboard |
| `screenshot` | Screen capture |
| `usage_report` | Token usage stats |

## Connecting TO External MCP Servers

SalmAlm can also act as an MCP **client** — importing tools from external MCP servers:

```
# In SalmAlm chat:
> Use the mcp_manage tool: add server "filesystem" with command "npx @modelcontextprotocol/server-filesystem /tmp"
```

Or via the `mcp_manage` tool:
- `list` — show connected MCP servers
- `add` — connect to a new MCP server
- `remove` — disconnect
- `tools` — list all imported tools

## Protocol Details

- **Transport**: stdio (JSON-RPC 2.0 over newline-delimited JSON)
- **Spec version**: 2025-03-26
- **Capabilities**: tools, resources, prompts
- **Resources**: Exposes `memory/*.md` and `MEMORY.md` as readable resources
