# MCP Integration

SalmAlm implements the [Model Context Protocol](https://modelcontextprotocol.io/) (MCP), enabling interoperability with any MCP-compatible client.

## What is MCP?

MCP is an open protocol for connecting AI assistants to external tools and data sources. SalmAlm acts as an **MCP server**, exposing its 43 tools and memory resources over JSON-RPC.

## Capabilities

### Tools

All SalmAlm tools are exposed as MCP tools with full JSON Schema:

```json
{
  "method": "tools/list",
  "result": {
    "tools": [
      {"name": "exec", "description": "Execute shell commands", "inputSchema": {...}},
      {"name": "web_search", "description": "Search the web", "inputSchema": {...}}
    ]
  }
}
```

### Resources

Memory files are exposed as MCP resources:

```json
{
  "method": "resources/list",
  "result": {
    "resources": [
      {"uri": "file://MEMORY.md", "name": "MEMORY.md", "mimeType": "text/markdown"},
      {"uri": "file://memory/2025-01-15.md", "name": "2025-01-15.md"}
    ]
  }
}
```

### Prompts

System prompts are available as MCP prompt templates.

## Connection

### WebSocket

```
ws://localhost:18800/mcp
```

Messages follow JSON-RPC 2.0 format:

```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "my-client"}}}
```

### Supported Methods

| Method | Description |
|--------|-------------|
| `initialize` | Handshake with capabilities |
| `tools/list` | List available tools |
| `tools/call` | Execute a tool |
| `resources/list` | List memory resources |
| `resources/read` | Read a resource |
| `prompts/list` | List prompt templates |

## Web UI

The **MCP** panel in Settings shows:

- Connection status
- Connected clients
- Tool call history
- Resource access log

## Use Cases

- **Claude Desktop** → Connect SalmAlm as an MCP tool server
- **VS Code extensions** → Use SalmAlm tools from your editor
- **Custom clients** → Build your own MCP client against SalmAlm
