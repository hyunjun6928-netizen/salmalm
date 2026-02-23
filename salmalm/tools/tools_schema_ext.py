"""Extended tool definitions (tools 32-62)."""

TOOL_DEFINITIONS_EXT = [
    {
        "name": "gmail",
        "description": "Gmail: list recent emails, read specific email, send email. Requires Google API credentials in vault.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "list, read, send, search",
                    "enum": ["list", "read", "send", "search"],
                },
                "count": {"type": "integer", "description": "Number of emails to list (default: 10)"},
                "message_id": {"type": "string", "description": "Message ID (for read)"},
                "to": {"type": "string", "description": "Recipient email (for send)"},
                "subject": {"type": "string", "description": "Email subject (for send)"},
                "body": {"type": "string", "description": "Email body (for send)"},
                "query": {"type": "string", "description": "Search query (Gmail search syntax)"},
                "label": {"type": "string", "description": "Label filter (default: INBOX)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "calendar_list",
        "description": 'List upcoming Google Calendar events. Use period="today" for today, "week" for this week, "month" for this month.',
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "today, week, month (default: week)",
                    "enum": ["today", "week", "month"],
                },
                "calendar_id": {"type": "string", "description": "Calendar ID (default: primary)"},
            },
        },
    },
    {
        "name": "calendar_add",
        "description": "Add an event to Google Calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Event title"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "time": {"type": "string", "description": "Start time HH:MM (omit for all-day)"},
                "duration_minutes": {"type": "integer", "description": "Duration in minutes (default: 60)"},
                "description": {"type": "string", "description": "Event description"},
                "calendar_id": {"type": "string", "description": "Calendar ID (default: primary)"},
            },
            "required": ["title", "date"],
        },
    },
    {
        "name": "calendar_delete",
        "description": "Delete an event from Google Calendar by event_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "Event ID to delete"},
                "calendar_id": {"type": "string", "description": "Calendar ID (default: primary)"},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "email_inbox",
        "description": "List recent emails from Gmail inbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "Number of messages (default: 10, max: 30)"},
            },
        },
    },
    {
        "name": "email_read",
        "description": "Read a specific email by message_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID"},
            },
            "required": ["message_id"],
        },
    },
    {
        "name": "email_send",
        "description": "Send an email via Gmail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body text"},
            },
            "required": ["to", "subject"],
        },
    },
    {
        "name": "email_search",
        "description": 'Search emails using Gmail search syntax (e.g. "from:user@example.com", "is:unread", "subject:keyword").',
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail search query"},
                "count": {"type": "integer", "description": "Max results (default: 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "reminder",
        "description": "Set a reminder. Triggers notification via configured channel (Telegram/desktop) at specified time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "set, list, delete", "enum": ["set", "list", "delete"]},
                "message": {"type": "string", "description": "Reminder message"},
                "time": {
                    "type": "string",
                    "description": 'When to remind: ISO8601, relative (e.g. "30m", "2h", "1d"), or natural language',
                },
                "reminder_id": {"type": "string", "description": "Reminder ID (for delete)"},
                "repeat": {
                    "type": "string",
                    "description": "Repeat interval: daily, weekly, monthly, or cron expression",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "tts_generate",
        "description": "Text-to-Speech: generate audio from text. Returns audio file path. Supports Google TTS (free) and OpenAI TTS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to convert to speech"},
                "provider": {
                    "type": "string",
                    "description": "TTS provider: google, openai (default: google)",
                    "enum": ["google", "openai"],
                },
                "language": {"type": "string", "description": "Language code (default: ko-KR)"},
                "voice": {"type": "string", "description": "Voice name (provider-specific)"},
                "output": {"type": "string", "description": "Output file path (default: auto-generated)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "workflow",
        "description": "Execute a predefined workflow (tool chain). Define workflows with steps that pipe outputs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "run, list, save, delete",
                    "enum": ["run", "list", "save", "delete"],
                },
                "name": {"type": "string", "description": "Workflow name"},
                "steps": {
                    "type": "array",
                    "description": "Workflow steps: [{tool, args, output_var}]",
                    "items": {"type": "object"},
                },
                "variables": {"type": "object", "description": "Input variables for the workflow"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "file_index",
        "description": "Index and search local files. Builds searchable index of workspace files for fast retrieval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "search, index, status",
                    "enum": ["search", "index", "status"],
                },
                "query": {"type": "string", "description": "Search query"},
                "path": {"type": "string", "description": "Directory to index (default: workspace)"},
                "extensions": {
                    "type": "string",
                    "description": 'File extensions to include (comma-separated, e.g. "py,md,txt")',
                },
                "limit": {"type": "integer", "description": "Max results (default: 10)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "notification",
        "description": "Send notification via configured channels (Telegram, desktop, webhook).",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Notification message"},
                "title": {"type": "string", "description": "Notification title"},
                "channel": {
                    "type": "string",
                    "description": "Channel: telegram, desktop, webhook, all",
                    "enum": ["telegram", "desktop", "webhook", "all"],
                },
                "url": {"type": "string", "description": "Webhook URL (for webhook channel)"},
                "priority": {
                    "type": "string",
                    "description": "Priority: low, normal, high",
                    "enum": ["low", "normal", "high"],
                },
            },
            "required": ["message"],
        },
    },
    # ── v0.12.1 Additional Tools ─────────────────────────────────
    {
        "name": "weather",
        "description": "Get current weather and forecast for a location. No API key needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": 'City name or coordinates (e.g. "Seoul", "Tokyo", "37.5,127.0")',
                },
                "format": {
                    "type": "string",
                    "description": "Output format: short, full, forecast",
                    "enum": ["short", "full", "forecast"],
                    "default": "full",
                },
                "lang": {"type": "string", "description": "Language code (default: ko)", "default": "ko"},
            },
            "required": ["location"],
        },
    },
    {
        "name": "rss_reader",
        "description": "Read RSS/Atom feeds. Subscribe, list, and fetch latest articles from news sources.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "fetch, subscribe, unsubscribe, list",
                    "enum": ["fetch", "subscribe", "unsubscribe", "list"],
                },
                "url": {"type": "string", "description": "RSS feed URL (for fetch/subscribe)"},
                "name": {"type": "string", "description": "Feed name (for subscribe)"},
                "count": {"type": "integer", "description": "Number of articles to fetch (default: 5)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "translate",
        "description": "Translate text between languages using Google Translate (free, no API key).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to translate"},
                "target": {
                    "type": "string",
                    "description": 'Target language code (e.g. "en", "ko", "ja", "zh", "es", "fr")',
                },
                "source": {"type": "string", "description": "Source language code (default: auto-detect)"},
            },
            "required": ["text", "target"],
        },
    },
    {
        "name": "qr_code",
        "description": "Generate QR code as SVG or text art. Pure stdlib, no dependencies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "Data to encode in QR code (URL, text, etc.)"},
                "output": {"type": "string", "description": "Output file path (default: auto-generated SVG)"},
                "format": {
                    "type": "string",
                    "description": "Output format: svg, text",
                    "enum": ["svg", "text"],
                    "default": "svg",
                },
                "size": {"type": "integer", "description": "Module size in pixels (SVG, default: 10)"},
            },
            "required": ["data"],
        },
    },
    # ── Personal Assistant Tools ──────────────────────────────
    {
        "name": "note",
        "description": "Personal knowledge base — save, search, list, delete notes. 개인 메모/지식 베이스.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: save, search, list, delete",
                    "enum": ["save", "search", "list", "delete"],
                },
                "content": {"type": "string", "description": "Note content (for save)"},
                "tags": {"type": "string", "description": "Comma-separated tags (for save)"},
                "query": {"type": "string", "description": "Search query (for search)"},
                "note_id": {"type": "string", "description": "Note ID (for delete)"},
                "count": {"type": "integer", "description": "Number of results (for list)", "default": 10},
            },
            "required": ["action"],
        },
    },
    {
        "name": "expense",
        "description": "Expense tracker — add, view today/month, delete expenses. 가계부/지출 추적.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: add, today, month, delete",
                    "enum": ["add", "today", "month", "delete"],
                },
                "amount": {"type": "number", "description": "Amount in KRW (for add)"},
                "category": {
                    "type": "string",
                    "description": "Category: 식비,교통,쇼핑,구독,의료,생활,기타 (auto-detected if empty)",
                },
                "description": {"type": "string", "description": "Description (for add)"},
                "date": {"type": "string", "description": "Date YYYY-MM-DD (default: today)"},
                "month": {"type": "string", "description": "Month YYYY-MM (for month summary)"},
                "expense_id": {"type": "string", "description": "Expense ID (for delete)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "save_link",
        "description": "Save links/articles for later reading. Auto-fetches title and content. 링크/아티클 저장.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: save, list, search, delete",
                    "enum": ["save", "list", "search", "delete"],
                },
                "url": {"type": "string", "description": "URL to save"},
                "title": {"type": "string", "description": "Title (auto-detected if empty)"},
                "summary": {"type": "string", "description": "3-line summary"},
                "tags": {"type": "string", "description": "Comma-separated tags"},
                "query": {"type": "string", "description": "Search query"},
                "link_id": {"type": "string", "description": "Link ID (for delete)"},
                "count": {"type": "integer", "description": "Number of results", "default": 10},
            },
            "required": ["action"],
        },
    },
    {
        "name": "pomodoro",
        "description": "Pomodoro timer — start focus session, break, stop, view stats. 포모도로 타이머.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: start, break, stop, status",
                    "enum": ["start", "break", "stop", "status"],
                },
                "duration": {
                    "type": "integer",
                    "description": "Duration in minutes (default: 25 for focus, 5 for break)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "routine",
        "description": "Morning/evening routine automation. 아침/저녁 루틴 자동화.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Routine name: morning, evening, list"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "briefing",
        "description": "Generate daily briefing — weather, calendar, email, tasks summary. 데일리 브리핑.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sections": {
                    "type": "string",
                    "description": "Comma-separated sections: weather,calendar,email,tasks,notes,expenses",
                },
            },
        },
    },
    {
        "name": "apply_patch",
        "description": "Apply a multi-file patch (Add/Update/Delete files). 멀티 파일 패치 적용.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patch_text": {"type": "string", "description": "Patch text in *** Begin Patch / *** End Patch format"},
                "base_dir": {"type": "string", "description": "Base directory for patch operations (default: cwd)"},
            },
            "required": ["patch_text"],
        },
    },
    {
        "name": "ui_control",
        "description": "Control the web UI settings. Change language, theme, model, navigate panels, or create cron jobs. "
        "UI 설정 제어: 언어, 테마, 모델 변경, 패널 이동, 크론 작업 생성.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "set_lang",
                        "set_theme",
                        "set_model",
                        "new_session",
                        "show_panel",
                        "add_cron",
                        "toggle_debug",
                    ],
                    "description": "Action to perform",
                },
                "value": {
                    "type": "string",
                    "description": "Value for the action. set_lang: en/ko, set_theme: light/dark, set_model: model name, show_panel: chat/settings/dashboard/sessions/cron/memory/docs",
                },
                "name": {"type": "string", "description": "For add_cron: job name"},
                "interval": {"type": "integer", "description": "For add_cron: interval in seconds"},
                "prompt": {"type": "string", "description": "For add_cron: AI prompt to execute"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "mesh",
        "description": "SalmAlm Mesh — P2P networking between instances. Delegate tasks, share clipboard, discover LAN peers. / 인스턴스 간 P2P 네트워킹. 작업 위임, 클립보드 공유, LAN 피어 탐색.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "status/add/remove/ping/task/broadcast/clipboard/discover",
                    "enum": ["status", "add", "remove", "ping", "task", "broadcast", "clipboard", "discover"],
                },
                "url": {"type": "string", "description": "Peer URL (for add)"},
                "name": {"type": "string", "description": "Peer display name"},
                "peer_id": {"type": "string", "description": "Peer ID (for remove/task)"},
                "task": {"type": "string", "description": "Task to delegate (for task/broadcast)"},
                "text": {"type": "string", "description": "Clipboard text (for clipboard)"},
                "secret": {"type": "string", "description": "Shared secret for auth"},
                "model": {"type": "string", "description": "Model override for delegated task"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "canvas",
        "description": "Canvas — render HTML, markdown, code, or charts on a local preview server (:18803). / 로컬 프리뷰 서버에서 HTML, 마크다운, 코드, 차트 렌더링.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "status/present/markdown/code/list",
                    "enum": ["status", "present", "markdown", "code", "list"],
                },
                "html": {"type": "string", "description": "HTML content (for present)"},
                "text": {"type": "string", "description": "Markdown text (for markdown)"},
                "code": {"type": "string", "description": "Source code (for code)"},
                "language": {"type": "string", "description": "Programming language (for code)"},
                "title": {"type": "string", "description": "Page title"},
                "open": {"type": "boolean", "description": "Open in browser (default false)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "sandbox_exec",
        "description": "Execute in OS-native sandbox (bubblewrap/sandbox-exec/rlimit). Safer than exec. / OS 기본 샌드박스에서 실행. exec보다 안전.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute in sandbox"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
                "allow_network": {"type": "boolean", "description": "Allow network access (default false)"},
                "memory_mb": {"type": "integer", "description": "Memory limit in MB (default 512)"},
            },
            "required": ["command"],
        },
    },
]
