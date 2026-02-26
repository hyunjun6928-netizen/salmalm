"""SalmAlm tool definitions — schema for all built-in tools.

Design contract:
- Every input_schema has additionalProperties: false (typo guard)
- Numeric fields carry minimum/maximum (timeout/limit/count)
- Action-based tools use allOf[if/then] for conditional required
- anyOf used where exactly one of N inputs is required (stt)
- Risk metadata lives in TOOL_RISK_METADATA (separate from API schema)
"""

TOOL_DEFINITIONS = [
    {
        "name": "exec",
        "description": "Execute shell commands. Dangerous commands require approval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1, "maximum": 1800, "default": 30},
                "background": {"type": "boolean", "default": False},
                "yieldMs": {"type": "integer", "minimum": 0, "maximum": 600000},
                "notifyOnExit": {"type": "boolean", "default": False},
                "env": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            "required": ["command"],
            "additionalProperties": False,
            # notifyOnExit only valid with background=true — enforced at runtime
        },
    },
    {
        "name": "exec_session",
        "description": "Manage background exec sessions: list, poll status, kill.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "poll", "kill"]},
                "session_id": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"enum": ["poll", "kill"]}}},
                    "then": {"required": ["session_id"]},
                }
            ],
        },
    },
    {
        "name": "read_file",
        "description": "Read file contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10000},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates if not exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "edit_file",
        "description": "Find and replace text in a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "web_search",
        "description": "Perform web search.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "count": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "web_fetch",
        "description": "Fetch content from a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 200000, "default": 10000},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "memory_read",
        "description": "Read MEMORY.md or memory/ files.",
        "input_schema": {
            "type": "object",
            "properties": {"file": {"type": "string"}},
            "required": ["file"],
            "additionalProperties": False,
        },
    },
    {
        "name": "memory_write",
        "description": "Write to MEMORY.md or memory/ files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "usage_report",
        "description": "Show token usage and cost for current session.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "memory_search",
        "description": "Search MEMORY.md and memory/*.md by keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "image_generate",
        "description": "Generate images using xAI Aurora or OpenAI DALL-E.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "provider": {"type": "string", "enum": ["xai", "openai"], "default": "xai"},
                "size": {"type": "string", "default": "1024x1024"},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
    {
        "name": "image_analyze",
        "description": "Analyze an image using vision AI (GPT-4o/Claude). Describe, OCR, or answer questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string"},
                "question": {"type": "string", "default": "Describe this image in detail."},
            },
            "required": ["image_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "tts",
        "description": "Convert text to speech (OpenAI TTS).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "voice": {"type": "string", "enum": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"], "default": "nova"},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "stt",
        "description": "Transcribe audio to text (OpenAI Whisper). Provide audio_path OR audio_base64.",
        "input_schema": {
            "type": "object",
            "properties": {
                "audio_path": {"type": "string"},
                "audio_base64": {"type": "string"},
                "language": {"type": "string", "default": "ko"},
            },
            "anyOf": [
                {"required": ["audio_path"]},
                {"required": ["audio_base64"]},
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "python_eval",
        "description": "Execute Python code (disabled by default; set SALMALM_PYTHON_EVAL=1). Assign result to _result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1, "maximum": 300, "default": 15},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "system_monitor",
        "description": "Monitor system status (CPU, memory, disk, processes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "detail": {
                    "type": "string",
                    "enum": ["overview", "cpu", "memory", "disk", "processes", "network"],
                    "default": "overview",
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "http_request",
        "description": "Send HTTP requests (GET/POST/PUT/DELETE). For API calls.",
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"], "default": "GET"},
                "url": {"type": "string"},
                "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                "body": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1, "maximum": 120, "default": 15},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "screenshot",
        "description": "Capture a screenshot of the current screen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {"type": "string", "default": "full"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "json_query",
        "description": "Query JSON data with jq-style syntax.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "string"},
                "query": {"type": "string"},
                "from_file": {"type": "boolean", "default": False},
            },
            "required": ["data", "query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "diff_files",
        "description": "Compare differences between two files or texts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file1": {"type": "string"},
                "file2": {"type": "string"},
                "context_lines": {"type": "integer", "minimum": 0, "maximum": 20, "default": 3},
            },
            "required": ["file1", "file2"],
            "additionalProperties": False,
        },
    },
    {
        "name": "sub_agent",
        "description": "Run long tasks in background sub-agent. Returns immediately, notifies on completion.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["spawn", "list", "result", "send", "stop", "log", "info", "steer"]},
                "task": {"type": "string"},
                "model": {"type": "string"},
                "agent_id": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "spawn"}}},
                    "then": {"required": ["task"]},
                },
                {
                    "if": {"properties": {"action": {"enum": ["result", "send", "stop", "log", "steer"]}}},
                    "then": {"required": ["agent_id"]},
                },
                {
                    "if": {"properties": {"action": {"const": "send"}}},
                    "then": {"required": ["message"]},
                },
            ],
        },
    },
    {
        "name": "skill_manage",
        "description": "List and load skills from skills/ directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "load", "match", "install", "uninstall"]},
                "skill_name": {"type": "string"},
                "query": {"type": "string"},
                "url": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"enum": ["load", "uninstall"]}}},
                    "then": {"required": ["skill_name"]},
                },
                {
                    "if": {"properties": {"action": {"const": "match"}}},
                    "then": {"required": ["query"]},
                },
                {
                    "if": {"properties": {"action": {"const": "install"}}},
                    "then": {"required": ["url"]},
                },
            ],
        },
    },
    {
        "name": "clipboard",
        "description": "Text clipboard. Quick copy/paste between sessions. Max 50 slots.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["copy", "paste", "list", "clear"]},
                "slot": {"type": "string", "default": "default"},
                "content": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "copy"}}},
                    "then": {"required": ["content"]},
                }
            ],
        },
    },
    {
        "name": "hash_text",
        "description": "Hash text (SHA256/MD5/SHA1) or generate random password/UUID/token.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["hash", "password", "uuid", "token"]},
                "text": {"type": "string"},
                "algorithm": {"type": "string", "enum": ["sha256", "md5", "sha1", "sha512", "sha384"], "default": "sha256"},
                "length": {"type": "integer", "minimum": 8, "maximum": 256, "default": 16},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "hash"}}},
                    "then": {"required": ["text"]},
                }
            ],
        },
    },
    {
        "name": "regex_test",
        "description": "Test regular expressions. Match, replace, extract patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "text": {"type": "string"},
                "action": {"type": "string", "enum": ["match", "find", "replace", "split"], "default": "find"},
                "replacement": {"type": "string"},
                "flags": {"type": "string"},
            },
            "required": ["pattern", "text"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "replace"}}},
                    "then": {"required": ["replacement"]},
                }
            ],
        },
    },
    {
        "name": "cron_manage",
        "description": "Manage scheduled tasks. Auto-run LLM tasks on a schedule.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "add", "remove", "toggle"]},
                "name": {"type": "string"},
                "prompt": {"type": "string"},
                "schedule": {
                    "type": "object",
                    "description": '{"kind":"cron","expr":"0 6 * * *"} or {"kind":"every","seconds":3600} or {"kind":"at","time":"ISO8601"}',
                },
                "model": {"type": "string"},
                "job_id": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "add"}}},
                    "then": {"required": ["name", "prompt", "schedule"]},
                },
                {
                    "if": {"properties": {"action": {"enum": ["remove", "toggle"]}}},
                    "then": {"required": ["job_id"]},
                },
            ],
        },
    },
    {
        "name": "plugin_manage",
        "description": "Manage plugins. Auto-load .py files from plugins/ to extend tools.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "reload"]},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mcp_manage",
        "description": "Manage MCP (Model Context Protocol) servers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "add", "remove", "tools"]},
                "name": {"type": "string"},
                "command": {"type": "string"},
                "env": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "add"}}},
                    "then": {"required": ["name", "command"]},
                },
                {
                    "if": {"properties": {"action": {"enum": ["remove", "tools"]}}},
                    "then": {"required": ["name"]},
                },
            ],
        },
    },
    {
        "name": "rag_search",
        "description": "Local RAG (BM25) search across MEMORY.md, memory/, uploads/.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "browser",
        "description": "Browser automation (Playwright). snapshot→act→verify pattern. Requires: pip install salmalm[browser].",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["status", "snapshot", "act", "screenshot", "navigate"]},
                "url": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["click", "type", "press", "navigate", "evaluate", "screenshot"],
                },
                "selector": {"type": "string"},
                "text": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1000, "maximum": 120000, "default": 30000},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "act"}}},
                    "then": {"required": ["kind"]},
                },
                {
                    "if": {"properties": {"action": {"const": "navigate"}}},
                    "then": {"required": ["url"]},
                },
            ],
        },
    },
    {
        "name": "node_manage",
        "description": "Remote node management via SSH/HTTP.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "add", "remove", "run", "status", "upload", "wake"]},
                "name": {"type": "string"},
                "command": {"type": "string"},
                "host": {"type": "string"},
                "user": {"type": "string", "default": "root"},
                "port": {"type": "integer", "minimum": 1, "maximum": 65535, "default": 22},
                "key": {"type": "string"},
                "type": {"type": "string", "enum": ["ssh", "http"]},
                "url": {"type": "string"},
                "mac": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "add"}}},
                    "then": {"required": ["name", "host"]},
                },
                {
                    "if": {"properties": {"action": {"const": "run"}}},
                    "then": {"required": ["name", "command"]},
                },
                {
                    "if": {"properties": {"action": {"enum": ["remove", "status", "wake"]}}},
                    "then": {"required": ["name"]},
                },
            ],
        },
    },
    {
        "name": "health_check",
        "description": "System health check. Comprehensive diagnosis of all components.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["check", "selftest", "recover"], "default": "check"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "google_calendar",
        "description": "Google Calendar: list, create, delete events. Requires Google OAuth in vault.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "create", "delete"]},
                "days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 7},
                "title": {"type": "string"},
                "start": {"type": "string", "description": "ISO8601 datetime"},
                "end": {"type": "string", "description": "ISO8601 datetime"},
                "description": {"type": "string"},
                "event_id": {"type": "string"},
                "calendar_id": {"type": "string", "default": "primary"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "create"}}},
                    "then": {"required": ["title", "start", "end"]},
                },
                {
                    "if": {"properties": {"action": {"const": "delete"}}},
                    "then": {"required": ["event_id"]},
                },
            ],
        },
    },
]

# ── Risk metadata (separate from API schema — not sent to LLM) ────────────
# Used by tool_selector and validate_tool_calls for approval gating.
TOOL_RISK_METADATA: dict[str, dict] = {
    "exec":           {"risk": "high",   "approval_required": True},
    "sandbox_exec":   {"risk": "medium", "approval_required": False},
    "write_file":     {"risk": "medium", "approval_required": False},
    "edit_file":      {"risk": "medium", "approval_required": False},
    "http_request":   {"risk": "medium", "approval_required": False},
    "node_manage":    {"risk": "high",   "approval_required": True},
    "plugin_manage":  {"risk": "high",   "approval_required": True},
    "mcp_manage":     {"risk": "high",   "approval_required": True},
    "cron_manage":    {"risk": "medium", "approval_required": False},
    "google_calendar":{"risk": "medium", "approval_required": False},
    "gmail":          {"risk": "medium", "approval_required": False},
}

# Extended tools (split for file size)
from salmalm.tools.tools_schema_ext import TOOL_DEFINITIONS_EXT  # noqa: E402

TOOL_DEFINITIONS.extend(TOOL_DEFINITIONS_EXT)


def _validate_tool_definitions(defns: list) -> None:
    """Startup sanity check: no name duplicates, schema basics OK."""
    seen: dict[str, int] = {}
    errors: list[str] = []
    for i, tool in enumerate(defns):
        name = tool.get("name", f"<unnamed@{i}>")
        if name in seen:
            errors.append(f"Duplicate tool name '{name}' (indices {seen[name]} and {i})")
        seen[name] = i
        schema = tool.get("input_schema", {})
        if schema.get("type") == "object":
            if "additionalProperties" not in schema:
                errors.append(f"Tool '{name}': missing additionalProperties")
            for req in schema.get("required", []):
                if req not in schema.get("properties", {}):
                    errors.append(f"Tool '{name}': required field '{req}' not in properties")
    if errors:
        import logging
        log = logging.getLogger(__name__)
        for e in errors:
            log.warning(f"[TOOLS] Schema issue: {e}")


_validate_tool_definitions(TOOL_DEFINITIONS)


# Re-export handler for backward compatibility
from salmalm.tools.tool_handlers import execute_tool, _resolve_path, _is_safe_command, _is_subpath  # noqa: F401
