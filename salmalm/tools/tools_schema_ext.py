"""Extended tool definitions (tools 32+).

Same design contract as tools.py:
- additionalProperties: false on all input_schemas
- Numeric limits (minimum/maximum) on all int/number fields
- Conditional required via allOf[if/then] for action-based tools
"""

TOOL_DEFINITIONS_EXT = [
    {
        "name": "gmail",
        "description": "Gmail: list, read, send, search emails. Requires Google OAuth in vault.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "read", "send", "search"]},
                "count": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                "message_id": {"type": "string"},
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "query": {"type": "string"},
                "label": {"type": "string", "default": "INBOX"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "read"}}},
                    "then": {"required": ["message_id"]},
                },
                {
                    "if": {"properties": {"action": {"const": "send"}}},
                    "then": {"required": ["to", "subject", "body"]},
                },
                {
                    "if": {"properties": {"action": {"const": "search"}}},
                    "then": {"required": ["query"]},
                },
            ],
        },
    },
    {
        "name": "calendar_list",
        "description": "List upcoming Google Calendar events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["today", "week", "month"], "default": "week"},
                "calendar_id": {"type": "string", "default": "primary"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "calendar_add",
        "description": "Add an event to Google Calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM (omit for all-day)"},
                "duration_minutes": {"type": "integer", "minimum": 1, "maximum": 1440, "default": 60},
                "description": {"type": "string"},
                "calendar_id": {"type": "string", "default": "primary"},
            },
            "required": ["title", "date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "calendar_delete",
        "description": "Delete a Google Calendar event by event_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "calendar_id": {"type": "string", "default": "primary"},
            },
            "required": ["event_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "email_inbox",
        "description": "List recent emails from Gmail inbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "email_read",
        "description": "Read a specific email by message_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
            },
            "required": ["message_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "email_send",
        "description": "Send an email via Gmail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
            "additionalProperties": False,
        },
    },
    {
        "name": "email_search",
        "description": 'Search emails using Gmail search syntax (e.g. "from:user@example.com is:unread").',
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "count": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "reminder",
        "description": "Set a reminder. Triggers notification via Telegram/desktop at specified time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["set", "list", "delete"]},
                "message": {"type": "string"},
                "time": {"type": "string", "description": 'ISO8601, relative ("30m", "2h"), or natural language'},
                "reminder_id": {"type": "string"},
                "repeat": {"type": "string", "description": "daily, weekly, monthly, or cron expression"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "set"}}},
                    "then": {"required": ["message", "time"]},
                },
                {
                    "if": {"properties": {"action": {"const": "delete"}}},
                    "then": {"required": ["reminder_id"]},
                },
            ],
        },
    },
    {
        "name": "tts_generate",
        "description": "Generate audio from text. Supports Google TTS (free) and OpenAI TTS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "provider": {"type": "string", "enum": ["google", "openai"], "default": "google"},
                "language": {"type": "string", "default": "ko-KR"},
                "voice": {"type": "string"},
                "output": {"type": "string"},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "workflow",
        "description": "Execute a predefined workflow (tool chain). Pipe outputs between steps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["run", "list", "save", "delete"]},
                "name": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "object"}},
                "variables": {"type": "object"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "save"}}},
                    "then": {"required": ["name", "steps"]},
                },
                {
                    "if": {"properties": {"action": {"enum": ["run", "delete"]}}},
                    "then": {"required": ["name"]},
                },
            ],
        },
    },
    {
        "name": "file_index",
        "description": "Index and search local files. Builds searchable index of workspace files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["search", "index", "status"]},
                "query": {"type": "string"},
                "path": {"type": "string"},
                "extensions": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "search"}}},
                    "then": {"required": ["query"]},
                },
            ],
        },
    },
    {
        "name": "notification",
        "description": "Send notification via configured channels (Telegram, desktop, webhook).",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "title": {"type": "string"},
                "channel": {"type": "string", "enum": ["telegram", "desktop", "webhook", "all"], "default": "all"},
                "url": {"type": "string", "description": "Webhook URL (for webhook channel)"},
                "priority": {"type": "string", "enum": ["low", "normal", "high"], "default": "normal"},
            },
            "required": ["message"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"channel": {"const": "webhook"}}},
                    "then": {"required": ["url"]},
                },
            ],
        },
    },
    {
        "name": "weather",
        "description": "Get current weather and forecast. No API key needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "format": {"type": "string", "enum": ["short", "full", "forecast"], "default": "full"},
                "lang": {"type": "string", "default": "ko"},
            },
            "required": ["location"],
            "additionalProperties": False,
        },
    },
    {
        "name": "rss_reader",
        "description": "Read RSS/Atom feeds. Subscribe, list, and fetch latest articles.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["fetch", "subscribe", "unsubscribe", "list"]},
                "url": {"type": "string"},
                "name": {"type": "string"},
                "count": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"enum": ["fetch", "subscribe"]}}},
                    "then": {"required": ["url"]},
                },
                {
                    "if": {"properties": {"action": {"const": "subscribe"}}},
                    "then": {"required": ["name"]},
                },
            ],
        },
    },
    {
        "name": "translate",
        "description": "Translate text between languages using Google Translate (free, no API key).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "target": {"type": "string"},
                "source": {"type": "string"},
            },
            "required": ["text", "target"],
            "additionalProperties": False,
        },
    },
    {
        "name": "qr_code",
        "description": "Generate QR code as SVG or text art.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "string"},
                "output": {"type": "string"},
                "format": {"type": "string", "enum": ["svg", "text"], "default": "svg"},
                "size": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
            },
            "required": ["data"],
            "additionalProperties": False,
        },
    },
    {
        "name": "note",
        "description": "Personal knowledge base — save, search, list, delete notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["save", "search", "list", "delete"]},
                "content": {"type": "string"},
                "tags": {"type": "string"},
                "query": {"type": "string"},
                "note_id": {"type": "string"},
                "count": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "save"}}},
                    "then": {"required": ["content"]},
                },
                {
                    "if": {"properties": {"action": {"const": "search"}}},
                    "then": {"required": ["query"]},
                },
                {
                    "if": {"properties": {"action": {"const": "delete"}}},
                    "then": {"required": ["note_id"]},
                },
            ],
        },
    },
    {
        "name": "expense",
        "description": "Expense tracker — add, view today/month, delete expenses.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "today", "month", "delete"]},
                "amount": {"type": "number", "minimum": 0},
                "category": {"type": "string"},
                "description": {"type": "string"},
                "date": {"type": "string"},
                "month": {"type": "string"},
                "expense_id": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "add"}}},
                    "then": {"required": ["amount", "description"]},
                },
                {
                    "if": {"properties": {"action": {"const": "delete"}}},
                    "then": {"required": ["expense_id"]},
                },
            ],
        },
    },
    {
        "name": "save_link",
        "description": "Save links/articles for later reading. Auto-fetches title and content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["save", "list", "search", "delete"]},
                "url": {"type": "string"},
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "tags": {"type": "string"},
                "query": {"type": "string"},
                "link_id": {"type": "string"},
                "count": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "save"}}},
                    "then": {"required": ["url"]},
                },
                {
                    "if": {"properties": {"action": {"const": "search"}}},
                    "then": {"required": ["query"]},
                },
                {
                    "if": {"properties": {"action": {"const": "delete"}}},
                    "then": {"required": ["link_id"]},
                },
            ],
        },
    },
    {
        "name": "pomodoro",
        "description": "Pomodoro timer — start focus session, break, stop, view stats.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["start", "break", "stop", "status"]},
                "duration": {"type": "integer", "minimum": 1, "maximum": 120},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
    {
        "name": "routine",
        "description": "Morning/evening routine automation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["morning", "evening", "list"]},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
    {
        "name": "briefing",
        "description": "Generate daily briefing — weather, calendar, email, tasks summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sections": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "apply_patch",
        "description": "Apply a multi-file patch (Add/Update/Delete files).",
        "input_schema": {
            "type": "object",
            "properties": {
                "patch_text": {"type": "string"},
                "base_dir": {"type": "string"},
            },
            "required": ["patch_text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ui_control",
        "description": "Control web UI settings: language, theme, model, panels, cron jobs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["set_lang", "set_theme", "set_model", "new_session", "show_panel", "add_cron", "toggle_debug"],
                },
                "value": {"type": "string"},
                "name": {"type": "string"},
                "interval": {"type": "integer", "minimum": 60, "maximum": 86400},
                "prompt": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "add_cron"}}},
                    "then": {"required": ["name", "interval", "prompt"]},
                },
                {
                    "if": {"properties": {"action": {"enum": ["set_lang", "set_theme", "set_model", "show_panel"]}}},
                    "then": {"required": ["value"]},
                },
            ],
        },
    },
    {
        "name": "mesh",
        "description": "SalmAlm Mesh — P2P networking between instances. Delegate tasks, share clipboard, discover peers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["status", "add", "remove", "ping", "task", "broadcast", "clipboard", "discover"]},
                "url": {"type": "string"},
                "name": {"type": "string"},
                "peer_id": {"type": "string"},
                "task": {"type": "string"},
                "text": {"type": "string"},
                "secret": {"type": "string"},
                "model": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "add"}}},
                    "then": {"required": ["url", "name"]},
                },
                {
                    "if": {"properties": {"action": {"enum": ["task", "remove", "ping"]}}},
                    "then": {"required": ["peer_id"]},
                },
                {
                    "if": {"properties": {"action": {"const": "task"}}},
                    "then": {"required": ["task"]},
                },
                {
                    "if": {"properties": {"action": {"const": "clipboard"}}},
                    "then": {"required": ["text"]},
                },
            ],
        },
    },
    {
        "name": "canvas",
        "description": "Render HTML, markdown, code, or charts on local preview (:18803).",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["status", "present", "markdown", "code", "list"]},
                "html": {"type": "string"},
                "text": {"type": "string"},
                "code": {"type": "string"},
                "language": {"type": "string"},
                "title": {"type": "string"},
                "open": {"type": "boolean", "default": False},
            },
            "required": ["action"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "present"}}},
                    "then": {"required": ["html"]},
                },
                {
                    "if": {"properties": {"action": {"const": "markdown"}}},
                    "then": {"required": ["text"]},
                },
                {
                    "if": {"properties": {"action": {"const": "code"}}},
                    "then": {"required": ["code"]},
                },
            ],
        },
    },
    {
        "name": "sandbox_exec",
        "description": "Execute in OS-native sandbox (bubblewrap/sandbox-exec/rlimit). Safer than exec.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30},
                "allow_network": {"type": "boolean", "default": False},
                "memory_mb": {"type": "integer", "minimum": 64, "maximum": 4096, "default": 512},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
]
