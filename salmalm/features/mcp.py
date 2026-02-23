from __future__ import annotations

"""SalmAlm MCP (Model Context Protocol) — Server + Client.

Implements MCP 2025-03-26 spec (simplified):
  - **MCP Server**: Exposes SalmAlm tools to external MCP clients (Cursor, VS Code, etc.)
    Transport: stdio (subprocess) or SSE (HTTP)
  - **MCP Client**: Connects to external MCP servers to import their tools
    Transport: stdio (subprocess) or SSE (HTTP)

Protocol: JSON-RPC 2.0 over newline-delimited JSON (stdio) or SSE (HTTP).

Usage:
  # As server (stdio) — run by MCP host:
  python -m salmalm.mcp --server --stdio

  # As client — connect to external MCP server:
  from salmalm.features.mcp import mcp_manager
  mcp_manager.add_server("filesystem", command=["npx", "@modelcontextprotocol/server-filesystem", "/tmp"])
  tools = mcp_manager.list_tools()
"""


import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from salmalm.constants import VERSION, BASE_DIR
from salmalm.security.crypto import log

# ── JSON-RPC helpers ──────────────────────────────────────────

_rpc_id = 0


def _next_id() -> int:
    """Next id."""
    global _rpc_id
    _rpc_id += 1
    return _rpc_id


def _rpc_request(method: str, params: Optional[dict] = None, id: Optional[int] = None) -> dict:
    """Rpc request."""
    msg = {"jsonrpc": "2.0", "method": method}
    if params:
        msg["params"] = params  # type: ignore[assignment]
    if id is not None:
        msg["id"] = id  # type: ignore[assignment]
    return msg


def _rpc_response(id: int, result: Optional[Any] = None, error: Optional[dict] = None) -> dict:
    """Rpc response."""
    msg = {"jsonrpc": "2.0", "id": id}
    if error:
        msg["error"] = error
    else:
        msg["result"] = result if result is not None else {}
    return msg


# ══════════════════════════════════════════════════════════════
#  MCP SERVER — expose SalmAlm tools to external clients
# ══════════════════════════════════════════════════════════════


class MCPServer:
    """MCP Server that exposes SalmAlm tools via JSON-RPC 2.0."""

    SERVER_INFO = {
        "name": "salmalm",
        "version": VERSION,
    }
    CAPABILITIES = {
        "tools": {"listChanged": False},
        "resources": {"subscribe": False, "listChanged": False},
        "prompts": {"listChanged": False},
    }

    def __init__(self) -> None:
        """Init  ."""
        self._tools: List[dict] = []
        self._tool_executor = None  # async fn(name, args) -> result
        self._resources: List[dict] = []
        self._initialized = False

    def set_tools(self, tools: list, executor) -> None:
        """Register tools and their executor function."""
        self._tools = tools
        self._tool_executor = executor

    def _convert_tool_to_mcp(self, tool: dict) -> dict:
        """Convert SalmAlm tool definition to MCP tool format."""
        return {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "inputSchema": tool.get("input_schema", {"type": "object", "properties": {}}),
        }

    def _list_resources(self) -> list:
        """List available MCP resources (memory files)."""
        resources = []
        mem_dir = BASE_DIR / "memory"
        if mem_dir.exists():
            for f in sorted(mem_dir.glob("*.md"))[-10:]:
                resources.append({"uri": f"file://memory/{f.name}", "name": f.name, "mimeType": "text/markdown"})
        mem_file = BASE_DIR / "MEMORY.md"
        if mem_file.exists():
            resources.append({"uri": "file://MEMORY.md", "name": "MEMORY.md", "mimeType": "text/markdown"})
        return resources

    async def _handle_tool_call(self, msg_id, params: dict):
        """Handle tools/call MCP request."""
        name = params.get("name", "")
        args = params.get("arguments", {})
        if not self._tool_executor:
            return _rpc_response(msg_id, error={"code": -32603, "message": "No tool executor configured"})
        try:
            result = await self._tool_executor(name, args)
            return _rpc_response(msg_id, {"content": [{"type": "text", "text": str(result)}], "isError": False})
        except Exception as e:
            return _rpc_response(msg_id, {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True})

    async def handle_message(self, msg: dict) -> Optional[dict]:
        """Handle a single JSON-RPC message. Returns response or None for notifications."""
        method = msg.get("method", "")
        params = msg.get("params", {})
        msg_id = msg.get("id")

        # ── Lifecycle ──
        if method == "initialize":
            self._initialized = True
            return _rpc_response(
                msg_id,
                {  # type: ignore[arg-type]
                    "protocolVersion": "2025-03-26",
                    "capabilities": self.CAPABILITIES,
                    "serverInfo": self.SERVER_INFO,
                },
            )

        if method == "notifications/initialized":
            return None  # No response for notifications

        if method == "ping":
            return _rpc_response(msg_id, {})  # type: ignore[arg-type]

        # ── Tools ──
        if method == "tools/list":
            tools = [self._convert_tool_to_mcp(t) for t in self._tools]
            _cursor = params.get("cursor")  # noqa: F841
            # Simple pagination: return all (SalmAlm has ~30 tools, no pagination needed)
            return _rpc_response(msg_id, {"tools": tools})  # type: ignore[arg-type]

        if method == "tools/call":
            return await self._handle_tool_call(msg_id, params)

        # ── Resources ──
        if method == "resources/list":
            return _rpc_response(msg_id, {"resources": self._list_resources()})  # type: ignore[arg-type]

        if method == "resources/read":
            uri = params.get("uri", "")
            if uri.startswith("file://"):
                rel_path = uri[7:]
                full_path = (BASE_DIR / rel_path).resolve()
                # Path traversal protection
                try:
                    full_path.relative_to(BASE_DIR.resolve())
                except ValueError:
                    return _rpc_response(
                        msg_id,
                        error={  # type: ignore[arg-type]
                            "code": -32602,
                            "message": "Path traversal denied",
                        },
                    )
                if full_path.exists() and full_path.is_file():
                    try:
                        content = full_path.read_text(encoding="utf-8", errors="replace")[:50000]
                        return _rpc_response(
                            msg_id,
                            {  # type: ignore[arg-type]
                                "contents": [
                                    {
                                        "uri": uri,
                                        "mimeType": "text/markdown",
                                        "text": content,
                                    }
                                ]
                            },
                        )
                    except Exception as e:
                        return _rpc_response(
                            msg_id,
                            error={  # type: ignore[arg-type]
                                "code": -32603,
                                "message": str(e),
                            },
                        )
            return _rpc_response(
                msg_id,
                error={  # type: ignore[arg-type]
                    "code": -32602,
                    "message": f"Unknown resource: {uri}",
                },
            )

        # ── Prompts ──
        if method == "prompts/list":
            return _rpc_response(
                msg_id,
                {
                    "prompts": [  # type: ignore[arg-type]
                        {
                            "name": "analyze",
                            "description": "Analysis request prompt",
                            "arguments": [{"name": "topic", "description": "Topic to analyze", "required": True}],
                        },
                        {
                            "name": "code_review",
                            "description": "Code review prompt",
                            "arguments": [
                                {"name": "file_path", "description": "File path to review", "required": True}
                            ],
                        },
                    ]
                },
            )

        if method == "prompts/get":
            name = params.get("name", "")
            args = params.get("arguments", {})
            if name == "analyze":
                topic = args.get("topic", "unknown")
                return _rpc_response(
                    msg_id,
                    {  # type: ignore[arg-type]
                        "description": f"'{topic}' Analysis",
                        "messages": [
                            {"role": "user", "content": {"type": "text", "text": f"Deep analysis of topic: {topic}"}}
                        ],
                    },
                )
            if name == "code_review":
                fp = args.get("file_path", "")
                return _rpc_response(
                    msg_id,
                    {  # type: ignore[arg-type]
                        "description": f"'{fp}' Code review",
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": f"Review this file for security/performance/readability: {fp}",
                                },
                            }
                        ],
                    },
                )
            return _rpc_response(
                msg_id,
                error={  # type: ignore[arg-type]
                    "code": -32602,
                    "message": f"Unknown prompt: {name}",
                },
            )

        # ── Unknown method ──
        if msg_id is not None:
            return _rpc_response(msg_id, error={"code": -32601, "message": f"Method not found: {method}"})
        return None

    async def run_stdio(self) -> None:
        """Run MCP server on stdin/stdout (for subprocess transport)."""
        log.info("[CONN] MCP Server starting (stdio transport)")
        loop = asyncio.get_event_loop()

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

        w_transport, w_protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout.buffer)
        writer = asyncio.StreamWriter(w_transport, w_protocol, reader, loop)

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                response = await self.handle_message(msg)
                if response:
                    out = json.dumps(response, ensure_ascii=False) + "\n"
                    writer.write(out.encode("utf-8"))
                    await writer.drain()
        except (EOFError, ConnectionError, BrokenPipeError):
            pass
        log.info("[CONN] MCP Server stopped (stdio)")


# ══════════════════════════════════════════════════════════════
#  MCP CLIENT — connect to external MCP servers
# ══════════════════════════════════════════════════════════════


class MCPClientConnection:
    """A connection to a single external MCP server (stdio transport)."""

    def __init__(
        self, name: str, command: List[str], env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None
    ) -> None:
        """Init  ."""
        self.name = name
        self.command = command
        self.env = env or {}
        self.cwd = cwd
        self._process: Optional[subprocess.Popen] = None
        self._tools: List[dict] = []
        self._resources: List[dict] = []
        self._lock = threading.Lock()
        self._connected = False
        self._rpc_responses: Dict[int, dict] = {}
        self._reader_thread: Optional[threading.Thread] = None

    def connect(self) -> bool:
        """Start the MCP server subprocess and initialize."""
        try:
            full_env = {**os.environ, **self.env}
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=full_env,
                cwd=self.cwd,
                bufsize=0,
            )

            # Start reader thread
            self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._reader_thread.start()

            # Initialize
            resp = self._send_request(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "salmalm", "version": VERSION},
                },
            )
            if not resp or "error" in resp:
                log.error(f"MCP init failed ({self.name}): {resp}")
                self.disconnect()
                return False

            # Send initialized notification
            self._send_notification("notifications/initialized")

            # List tools
            tools_resp = self._send_request("tools/list")
            if tools_resp and "result" in tools_resp:
                self._tools = tools_resp["result"].get("tools", [])

            # List resources
            res_resp = self._send_request("resources/list")
            if res_resp and "result" in res_resp:
                self._resources = res_resp["result"].get("resources", [])

            self._connected = True
            log.info(
                f"[CONN] MCP client connected: {self.name} ({len(self._tools)} tools, {len(self._resources)} resources)"
            )
            return True

        except Exception as e:
            log.error(f"MCP connect failed ({self.name}): {e}")
            self.disconnect()
            return False

    def disconnect(self) -> None:
        """Disconnect from an MCP server."""
        self._connected = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception as e:  # noqa: broad-except
                try:
                    self._process.kill()
                except Exception as e:  # noqa: broad-except
                    log.debug(f"Suppressed: {e}")
            self._process = None

    def _read_loop(self):
        """Background thread: read JSON-RPC responses from stdout."""
        try:
            while self._process and self._process.poll() is None:
                line = self._process.stdout.readline()  # type: ignore[union-attr]
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if "id" in msg:
                        self._rpc_responses[msg["id"]] = msg
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        self._connected = False

    def _send_request(self, method: str, params: Optional[dict] = None, timeout: float = 30) -> Optional[dict]:
        """Send JSON-RPC request and wait for response."""
        if not self._process or self._process.poll() is not None:
            return None
        rid = _next_id()
        msg = _rpc_request(method, params, rid)
        try:
            data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
            self._process.stdin.write(data)  # type: ignore[union-attr]
            self._process.stdin.flush()  # type: ignore[union-attr]
        except Exception as e:
            log.error(f"MCP send error ({self.name}): {e}")
            return None

        # Wait for response
        deadline = time.time() + timeout
        while time.time() < deadline:
            if rid in self._rpc_responses:
                return self._rpc_responses.pop(rid)
            time.sleep(0.05)
        log.warning(f"MCP timeout ({self.name}): {method}")
        return None

    def _send_notification(self, method: str, params: Optional[dict] = None):
        """Send JSON-RPC notification (no id, no response expected)."""
        if not self._process or self._process.poll() is not None:
            return
        msg = _rpc_request(method, params)
        try:
            data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
            self._process.stdin.write(data)  # type: ignore[union-attr]
            self._process.stdin.flush()  # type: ignore[union-attr]
        except Exception as e:
            log.debug(f"Suppressed: {e}")

    @property
    def tools(self) -> List[dict]:
        """List all available tools from connected MCP servers."""
        return self._tools

    def call_tool(self, name: str, arguments: Optional[dict] = None, timeout: float = 60) -> Optional[str]:
        """Call a tool on the remote MCP server."""
        if not self._connected:
            return None
        resp = self._send_request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments or {},
            },
            timeout=timeout,
        )
        if resp and "result" in resp:
            result = resp["result"]
            contents = result.get("content", [])
            texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
            return "\n".join(texts) if texts else str(result)
        if resp and "error" in resp:
            return f"MCP Error: {resp['error'].get('message', 'unknown')}"
        return None

    def read_resource(self, uri: str) -> Optional[str]:
        """Read a resource from the remote MCP server."""
        if not self._connected:
            return None
        resp = self._send_request("resources/read", {"uri": uri})
        if resp and "result" in resp:
            contents = resp["result"].get("contents", [])
            texts = [c.get("text", "") for c in contents]
            return "\n".join(texts) if texts else None
        return None


class MCPManager:
    """Manages multiple MCP client connections + the server instance."""

    def __init__(self) -> None:
        """Init  ."""
        self._clients: Dict[str, MCPClientConnection] = {}
        self._server = MCPServer()
        self._config_path = BASE_DIR / "mcp_servers.json"

    @property
    def server(self) -> MCPServer:
        """Get connection info for a specific MCP server."""
        return self._server

    def add_server(
        self,
        name: str,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        auto_connect: bool = True,
    ) -> bool:
        """Add and optionally connect to an external MCP server."""
        if name in self._clients:
            self._clients[name].disconnect()

        client = MCPClientConnection(name, command, env, cwd)
        self._clients[name] = client

        if auto_connect:
            return client.connect()
        return True

    def remove_server(self, name: str) -> None:
        """Disconnect and remove an MCP server."""
        if name in self._clients:
            self._clients[name].disconnect()
            del self._clients[name]

    def list_servers(self) -> List[dict]:
        """List all configured MCP servers and their status."""
        return [
            {
                "name": name,
                "connected": client._connected,
                "tools": len(client.tools),
                "command": client.command,
            }
            for name, client in self._clients.items()
        ]

    def get_all_tools(self) -> List[dict]:
        """Get all tools from all connected MCP servers (for LLM tool lists)."""
        tools = []
        for name, client in self._clients.items():
            if not client._connected:
                continue
            for tool in client.tools:
                # Prefix tool names with server name to avoid collisions
                tools.append(
                    {
                        "name": f"mcp_{name}_{tool['name']}",
                        "description": f"[MCP:{name}] {tool.get('description', '')}",
                        "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}}),
                        "_mcp_server": name,
                        "_mcp_tool": tool["name"],
                    }
                )
        return tools

    def call_tool(self, prefixed_name: str, arguments: Optional[dict] = None) -> Optional[str]:
        """Call an MCP tool by its prefixed name (mcp_servername_toolname)."""
        # Parse: mcp_{server}_{tool}
        if not prefixed_name.startswith("mcp_"):
            return None
        rest = prefixed_name[4:]
        for name, client in self._clients.items():
            prefix = f"{name}_"
            if rest.startswith(prefix):
                tool_name = rest[len(prefix) :]
                return client.call_tool(tool_name, arguments)
        return f"Unknown MCP tool: {prefixed_name}"

    def save_config(self) -> None:
        """Save server configurations to JSON."""
        config = {}
        for name, client in self._clients.items():
            config[name] = {
                "command": client.command,
                "env": client.env,
                "cwd": client.cwd,
            }
        self._config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info(f"[CONN] MCP config saved ({len(config)} servers)")

    def load_config(self) -> None:
        """Load and auto-connect configured MCP servers."""
        if not self._config_path.exists():
            return
        try:
            config = json.loads(self._config_path.read_text(encoding="utf-8"))
            for name, cfg in config.items():
                self.add_server(
                    name, command=cfg.get("command", []), env=cfg.get("env"), cwd=cfg.get("cwd"), auto_connect=True
                )
        except Exception as e:
            log.error(f"MCP config load error: {e}")

    def shutdown(self) -> None:
        """Disconnect all clients."""
        for client in self._clients.values():
            client.disconnect()
        self._clients.clear()


# ── Module-level instance ──────────────────────────────────────

mcp_manager = MCPManager()


# ── CLI entry point for stdio server mode ──────────────────────


async def _run_server_stdio():
    """Entry point for `python -m salmalm.mcp --server --stdio`."""
    import logging

    # Redirect all logging to stderr so stdout is clean JSON-RPC
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    from salmalm.tools import TOOL_DEFINITIONS, execute_tool

    server = MCPServer()

    async def executor(name: str, args):
        """Get the tool executor callable for MCP tools."""
        return execute_tool(name, args)

    server.set_tools(TOOL_DEFINITIONS, executor)
    await server.run_stdio()


if __name__ == "__main__":
    if "--server" in sys.argv:
        # Ensure ALL logging goes to stderr before any imports trigger log output
        import logging

        for h in logging.root.handlers[:]:
            logging.root.removeHandler(h)
        logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        asyncio.run(_run_server_stdio())
