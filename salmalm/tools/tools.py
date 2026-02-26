"""SalmAlm tool definitions — schema for all built-in tools."""

TOOL_DEFINITIONS = [
    {
        "name": "exec",
        "description": "Execute shell commands. Supports background=true for async, yieldMs for auto-background. Dangerous commands require approval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30, max 1800 fg / 7200 bg)"},
                "background": {"type": "boolean", "description": "Run in background, return immediately"},
                "yieldMs": {"type": "integer", "description": "Wait N ms then auto-background if not finished"},
                "notifyOnExit": {"type": "boolean", "description": "Notify on completion (background only)"},
                "env": {"type": "object", "description": "Environment variables (PATH/LD_*/DYLD_* blocked)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "exec_session",
        "description": "Manage background exec sessions: list, poll status, kill.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "list | poll | kill", "enum": ["list", "poll", "kill"]},
                "session_id": {"type": "string", "description": "Background session ID (for poll/kill)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "read_file",
        "description": "Read file contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "offset": {"type": "integer", "description": "Start line number (1-based)"},
                "limit": {"type": "integer", "description": "Number of lines to read"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates if not exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "File content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Find and replace text in a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "old_text": {"type": "string", "description": "Text to find"},
                "new_text": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "web_search",
        "description": "Perform web search.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "count": {"type": "integer", "description": "Number of results", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": "Fetch content from a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL"},
                "max_chars": {"type": "integer", "description": "Max characters", "default": 10000},
            },
            "required": ["url"],
        },
    },
    {
        "name": "memory_read",
        "description": "Read MEMORY.md or memory/ files.",
        "input_schema": {
            "type": "object",
            "properties": {"file": {"type": "string", "description": "Filename (e.g., MEMORY.md, 2026-02-18.md)"}},
            "required": ["file"],
        },
    },
    {
        "name": "memory_write",
        "description": "Write to MEMORY.md or memory/ files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Filename"},
                "content": {"type": "string", "description": "Content"},
            },
            "required": ["file", "content"],
        },
    },
    {
        "name": "usage_report",
        "description": "Show token usage and cost for current session.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "memory_search",
        "description": "Search MEMORY.md and memory/*.md by keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword or phrase to search"},
                "max_results": {"type": "integer", "description": "Max results", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "image_generate",
        "description": "Generate images using xAI Aurora or OpenAI DALL-E.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Image generation prompt (English recommended)"},
                "provider": {"type": "string", "description": "xai or openai", "default": "xai"},
                "size": {"type": "string", "description": "Image size", "default": "1024x1024"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "image_analyze",
        "description": "Analyze an image using vision AI (GPT-4o/Claude). Describe, OCR, or answer questions about images.",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Path to local image file or URL"},
                "question": {
                    "type": "string",
                    "description": 'What to analyze (e.g., "describe this image", "read the text", "what color is the car")',
                    "default": "Describe this image in detail.",
                },
            },
            "required": ["image_path"],
        },
    },
    {
        "name": "tts",
        "description": "Convert text to speech (OpenAI TTS).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to convert"},
                "voice": {
                    "type": "string",
                    "description": "alloy, echo, fable, onyx, nova, shimmer",
                    "default": "nova",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "stt",
        "description": "Transcribe audio to text (OpenAI Whisper). Accepts file path or base64 audio. You MUST provide either audio_path OR audio_base64.",
        "input_schema": {
            "type": "object",
            "properties": {
                "audio_path": {"type": "string", "description": "Path to audio file (provide this OR audio_base64)"},
                "audio_base64": {"type": "string", "description": "Base64-encoded audio data (provide this OR audio_path)"},
                "language": {"type": "string", "description": "Language code (e.g. ko, en, ja)", "default": "ko"},
            },
            "required": [],  # At least one of audio_path / audio_base64 is required (enforced at runtime)
        },
    },
    {
        "name": "python_eval",
        "description": "Execute Python code. Useful for math, data processing, analysis. Set _result to return output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute. Assign result to _result variable."},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 15},
            },
            "required": ["code"],
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
                    "description": "overview, cpu, memory, disk, processes, or network",
                    "default": "overview",
                }
            },
            "required": [],
        },
    },
    {
        "name": "http_request",
        "description": "Send HTTP requests (GET/POST/PUT/DELETE). Useful for API calls.",
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "GET, POST, PUT, DELETE", "default": "GET"},
                "url": {"type": "string", "description": "Request URL"},
                "headers": {"type": "object", "description": "Request headers (JSON)"},
                "body": {"type": "string", "description": "Request body (for POST/PUT)"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 15},
            },
            "required": ["url"],
        },
    },
    {
        "name": "screenshot",
        "description": "Capture a screenshot of the current screen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "full (entire screen) or WxH+X+Y (region)",
                    "default": "full",
                }
            },
            "required": [],
        },
    },
    {
        "name": "json_query",
        "description": "Query JSON data with jq-style syntax.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "JSON string or file path"},
                "query": {"type": "string", "description": "jq filter expression (e.g., .items[].name)"},
                "from_file": {"type": "boolean", "description": "true if data is a file path", "default": False},
            },
            "required": ["data", "query"],
        },
    },
    {
        "name": "diff_files",
        "description": "Compare differences between two files or texts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file1": {"type": "string", "description": "First file path or text"},
                "file2": {"type": "string", "description": "Second file path or text"},
                "context_lines": {"type": "integer", "description": "Context lines", "default": 3},
            },
            "required": ["file1", "file2"],
        },
    },
    {
        "name": "sub_agent",
        "description": "Run long tasks in background. Returns immediately, notifies on completion.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "spawn, list, result, send, stop, log, info, or steer",
                    "enum": ["spawn", "list", "result", "send", "stop", "log", "info", "steer"],
                },
                "task": {"type": "string", "description": "Task description (for spawn)"},
                "model": {"type": "string", "description": "Model to use (optional)"},
                "agent_id": {"type": "string", "description": "Agent ID (for result/send)"},
                "message": {"type": "string", "description": "Message to send to agent (for send)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "skill_manage",
        "description": "List and load skills from skills/ directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "list, load, match, install, or uninstall",
                    "enum": ["list", "load", "match", "install", "uninstall"],
                },
                "skill_name": {"type": "string", "description": "Skill directory name (for load/uninstall)"},
                "query": {"type": "string", "description": "Query to match (for match)"},
                "url": {"type": "string", "description": "Git URL or GitHub shorthand user/repo (for install)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "clipboard",
        "description": "Text clipboard. Quick copy/paste between sessions. Max 50 slots.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "copy, paste, list, or clear",
                    "enum": ["copy", "paste", "list", "clear"],
                },
                "slot": {"type": "string", "description": "Slot name (default: default)"},
                "content": {"type": "string", "description": "Text to save (for copy)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "hash_text",
        "description": "Hash text (SHA256/MD5/SHA1) or generate random password/UUID/token.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "hash, password, uuid, or token",
                    "enum": ["hash", "password", "uuid", "token"],
                },
                "text": {"type": "string", "description": "Text to hash (for hash)"},
                "algorithm": {"type": "string", "description": "sha256, md5, sha1, sha512, sha384 (default: sha256)"},
                "length": {"type": "integer", "description": "Password/token length (default: 16)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "regex_test",
        "description": "Test regular expressions. Match, replace, extract patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern"},
                "text": {"type": "string", "description": "Target text"},
                "action": {
                    "type": "string",
                    "description": "match, find, replace, or split",
                    "enum": ["match", "find", "replace", "split"],
                },
                "replacement": {"type": "string", "description": "Replacement text (for replace)"},
                "flags": {"type": "string", "description": "Flags: i(case-insensitive), m(multiline), s(dotall)"},
            },
            "required": ["pattern", "text"],
        },
    },
    {
        "name": "cron_manage",
        "description": "Manage scheduled tasks. Auto-run LLM tasks on a schedule.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "list, add, remove, or toggle",
                    "enum": ["list", "add", "remove", "toggle"],
                },
                "name": {"type": "string", "description": "Job name (for add)"},
                "prompt": {"type": "string", "description": "LLM prompt (for add)"},
                "schedule": {
                    "type": "object",
                    "description": 'Schedule: {"kind":"cron","expr":"0 6 * * *"} or {"kind":"every","seconds":3600} or {"kind":"at","time":"ISO8601"}',
                },
                "model": {"type": "string", "description": "Model to use (optional, default: current)"},
                "job_id": {"type": "string", "description": "Job ID (for remove/toggle)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "plugin_manage",
        "description": "Manage plugins. Auto-load .py files from plugins/ to extend tools.",
        "input_schema": {
            "type": "object",
            "properties": {"action": {"type": "string", "description": "list or reload", "enum": ["list", "reload"]}},
            "required": ["action"],
        },
    },
    {
        "name": "mcp_manage",
        "description": "Manage MCP (Model Context Protocol) servers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "list, add, remove, or tools",
                    "enum": ["list", "add", "remove", "tools"],
                },
                "name": {"type": "string", "description": "Server name (for add/remove)"},
                "command": {"type": "string", "description": "Server command (for add, space-separated)"},
                "env": {"type": "object", "description": "Environment variables (for add, optional)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "rag_search",
        "description": "Local RAG (BM25) search across MEMORY.md, memory/, uploads/.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Max results (default 5)", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "browser",
        "description": "Browser automation (Playwright). Snapshot/act pattern: snapshot → reason → act → verify. Requires: pip install salmalm[browser].",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "status/snapshot/act/screenshot",
                    "enum": ["status", "snapshot", "act", "screenshot"],
                },
                "url": {"type": "string", "description": "URL to navigate to"},
                "kind": {
                    "type": "string",
                    "description": "Action kind for act: click/type/press/navigate/evaluate/screenshot",
                    "enum": ["click", "type", "press", "navigate", "evaluate", "screenshot"],
                },
                "selector": {"type": "string", "description": "CSS selector (for click/type)"},
                "text": {"type": "string", "description": "Input text (for type/press/evaluate/navigate)"},
                "timeout": {"type": "integer", "description": "Timeout in ms (default 30000)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "node_manage",
        "description": "Remote node management via SSH/HTTP.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "list/add/remove/run/status/upload/wake",
                    "enum": ["list", "add", "remove", "run", "status", "upload", "wake"],
                },
                "name": {"type": "string", "description": "Node name"},
                "command": {"type": "string", "description": "Command to run (for run)"},
                "host": {"type": "string", "description": "Host address (for add)"},
                "user": {"type": "string", "description": "SSH user (default: root)"},
                "port": {"type": "integer", "description": "SSH port (default: 22)"},
                "key": {"type": "string", "description": "SSH key path"},
                "type": {"type": "string", "description": "Node type: ssh/http"},
                "url": {"type": "string", "description": "HTTP agent URL (for add type=http)"},
                "mac": {"type": "string", "description": "MAC address (for wake)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "health_check",
        "description": "System health check. Comprehensive diagnosis of all components.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "check, selftest, or recover",
                    "enum": ["check", "selftest", "recover"],
                    "default": "check",
                },
            },
        },
    },
    # ── v0.12 New Tools ──────────────────────────────────────────
    {
        "name": "google_calendar",
        "description": "Google Calendar: list upcoming events, create/delete events. Requires Google API credentials in vault.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "list, create, delete",
                    "enum": ["list", "create", "delete"],
                },
                "days": {"type": "integer", "description": "Days ahead to list", "default": 7},
                "title": {"type": "string", "description": "Event title (for create)"},
                "start": {"type": "string", "description": "Start time ISO8601 (for create)"},
                "end": {"type": "string", "description": "End time ISO8601 (for create)"},
                "description": {"type": "string", "description": "Event description"},
                "event_id": {"type": "string", "description": "Event ID (for delete)"},
                "calendar_id": {"type": "string", "description": "Calendar ID (default: primary)"},
            },
            "required": ["action"],
        },
    },
]

# Extended tools (split for file size).
# Wrapped in try/except: a broken tools_schema_ext must not silently
# truncate TOOL_DEFINITIONS — it raises so the operator sees the error.
try:
    from salmalm.tools.tools_schema_ext import TOOL_DEFINITIONS_EXT  # noqa: E402
    TOOL_DEFINITIONS.extend(TOOL_DEFINITIONS_EXT)
except ImportError as _ext_err:
    import logging as _log
    _log.getLogger(__name__).error(
        "[TOOLS] tools_schema_ext import failed — extended tools unavailable: %s", _ext_err
    )


# Re-export handler for backward compatibility
# execute_tool and path helpers live in tool_handlers / tools_common.
# Import them directly: from salmalm.tools.tool_handlers import execute_tool
