"""SalmAlm tool definitions — schema for all 32 tools."""

TOOL_DEFINITIONS = [
    {
        'name': 'exec',
        'description': 'Execute shell commands. Supports background=true for async, yieldMs for auto-background. Dangerous commands require approval.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'command': {'type': 'string', 'description': 'Shell command to execute'},
                'timeout': {'type': 'integer', 'description': 'Timeout in seconds (default 30, max 1800 fg / 7200 bg)'},
                'background': {'type': 'boolean', 'description': 'Run in background, return immediately'},
                'yieldMs': {'type': 'integer', 'description': 'Wait N ms then auto-background if not finished'},
                'notifyOnExit': {'type': 'boolean', 'description': 'Notify on completion (background only)'},
                'env': {'type': 'object', 'description': 'Environment variables (PATH/LD_*/DYLD_* blocked)'}
            },
            'required': ['command']
        }
    },
    {
        'name': 'exec_session',
        'description': 'Manage background exec sessions: list, poll status, kill.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list | poll | kill', 'enum': ['list', 'poll', 'kill']},
                'session_id': {'type': 'string', 'description': 'Background session ID (for poll/kill)'}
            },
            'required': ['action']
        }
    },
    {
        'name': 'read_file',
        'description': 'Read file contents.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'File path'},
                'offset': {'type': 'integer', 'description': 'Start line number (1-based)'},
                'limit': {'type': 'integer', 'description': 'Number of lines to read'}
            },
            'required': ['path']
        }
    },
    {
        'name': 'write_file',
        'description': 'Write content to a file. Creates if not exists.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'File path'},
                'content': {'type': 'string', 'description': 'File content'}
            },
            'required': ['path', 'content']
        }
    },
    {
        'name': 'edit_file',
        'description': 'Find and replace text in a file.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'File path'},
                'old_text': {'type': 'string', 'description': 'Text to find'},
                'new_text': {'type': 'string', 'description': 'Replacement text'}
            },
            'required': ['path', 'old_text', 'new_text']
        }
    },
    {
        'name': 'web_search',
        'description': 'Perform web search.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'Search query'},
                'count': {'type': 'integer', 'description': 'Number of results', 'default': 5}
            },
            'required': ['query']
        }
    },
    {
        'name': 'web_fetch',
        'description': 'Fetch content from a URL.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'url': {'type': 'string', 'description': 'URL'},
                'max_chars': {'type': 'integer', 'description': 'Max characters', 'default': 10000}
            },
            'required': ['url']
        }
    },
    {
        'name': 'memory_read',
        'description': 'Read MEMORY.md or memory/ files.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'file': {'type': 'string', 'description': 'Filename (e.g., MEMORY.md, 2026-02-18.md)'}
            },
            'required': ['file']
        }
    },
    {
        'name': 'memory_write',
        'description': 'Write to MEMORY.md or memory/ files.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'file': {'type': 'string', 'description': 'Filename'},
                'content': {'type': 'string', 'description': 'Content'}
            },
            'required': ['file', 'content']
        }
    },
    {
        'name': 'usage_report',
        'description': 'Show token usage and cost for current session.',
        'input_schema': {'type': 'object', 'properties': {}}
    },
    {
        'name': 'memory_search',
        'description': 'Search MEMORY.md and memory/*.md by keyword.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'Keyword or phrase to search'},
                'max_results': {'type': 'integer', 'description': 'Max results', 'default': 5}
            },
            'required': ['query']
        }
    },
    {
        'name': 'image_generate',
        'description': 'Generate images using xAI Aurora or OpenAI DALL-E.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'prompt': {'type': 'string', 'description': 'Image generation prompt (English recommended)'},
                'provider': {'type': 'string', 'description': 'xai or openai', 'default': 'xai'},
                'size': {'type': 'string', 'description': 'Image size', 'default': '1024x1024'}
            },
            'required': ['prompt']
        }
    },
    {
        'name': 'image_analyze',
        'description': 'Analyze an image using vision AI (GPT-4o/Claude). Describe, OCR, or answer questions about images.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'image_path': {'type': 'string', 'description': 'Path to local image file or URL'},
                'question': {'type': 'string', 'description': 'What to analyze (e.g., "describe this image", "read the text", "what color is the car")', 'default': 'Describe this image in detail.'}
            },
            'required': ['image_path']
        }
    },
    {
        'name': 'tts',
        'description': 'Convert text to speech (OpenAI TTS).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'text': {'type': 'string', 'description': 'Text to convert'},
                'voice': {'type': 'string', 'description': 'alloy, echo, fable, onyx, nova, shimmer', 'default': 'nova'}
            },
            'required': ['text']
        }
    },
    {
        'name': 'stt',
        'description': 'Transcribe audio to text (OpenAI Whisper). Accepts file path or base64 audio.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'audio_path': {'type': 'string', 'description': 'Path to audio file'},
                'audio_base64': {'type': 'string', 'description': 'Base64-encoded audio data'},
                'language': {'type': 'string', 'description': 'Language code (e.g. ko, en, ja)', 'default': 'ko'}
            }
        }
    },
    {
        'name': 'python_eval',
        'description': 'Execute Python code. Useful for math, data processing, analysis. Set _result to return output.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'code': {'type': 'string', 'description': 'Python code to execute. Assign result to _result variable.'},
                'timeout': {'type': 'integer', 'description': 'Timeout in seconds', 'default': 15}
            },
            'required': ['code']
        }
    },
    {
        'name': 'system_monitor',
        'description': 'Monitor system status (CPU, memory, disk, processes).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'detail': {'type': 'string', 'description': 'overview, cpu, memory, disk, processes, or network', 'default': 'overview'}
            },
            'required': []
        }
    },
    {
        'name': 'http_request',
        'description': 'Send HTTP requests (GET/POST/PUT/DELETE). Useful for API calls.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'method': {'type': 'string', 'description': 'GET, POST, PUT, DELETE', 'default': 'GET'},
                'url': {'type': 'string', 'description': 'Request URL'},
                'headers': {'type': 'object', 'description': 'Request headers (JSON)'},
                'body': {'type': 'string', 'description': 'Request body (for POST/PUT)'},
                'timeout': {'type': 'integer', 'description': 'Timeout in seconds', 'default': 15}
            },
            'required': ['url']
        }
    },
    {
        'name': 'screenshot',
        'description': 'Capture a screenshot of the current screen.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'region': {'type': 'string', 'description': 'full (entire screen) or WxH+X+Y (region)', 'default': 'full'}
            },
            'required': []
        }
    },
    {
        'name': 'json_query',
        'description': 'Query JSON data with jq-style syntax.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'data': {'type': 'string', 'description': 'JSON string or file path'},
                'query': {'type': 'string', 'description': 'jq filter expression (e.g., .items[].name)'},
                'from_file': {'type': 'boolean', 'description': 'true if data is a file path', 'default': False}
            },
            'required': ['data', 'query']
        }
    },
    {
        'name': 'diff_files',
        'description': 'Compare differences between two files or texts.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'file1': {'type': 'string', 'description': 'First file path or text'},
                'file2': {'type': 'string', 'description': 'Second file path or text'},
                'context_lines': {'type': 'integer', 'description': 'Context lines', 'default': 3}
            },
            'required': ['file1', 'file2']
        }
    },
    {
        'name': 'sub_agent',
        'description': 'Run long tasks in background. Returns immediately, notifies on completion.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'spawn, list, result, or send', 'enum': ['spawn', 'list', 'result', 'send']},
                'task': {'type': 'string', 'description': 'Task description (for spawn)'},
                'model': {'type': 'string', 'description': 'Model to use (optional)'},
                'agent_id': {'type': 'string', 'description': 'Agent ID (for result/send)'},
                'message': {'type': 'string', 'description': 'Message to send to agent (for send)'}
            },
            'required': ['action']
        }
    },
    {
        'name': 'skill_manage',
        'description': 'List and load skills from skills/ directory.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list, load, match, install, or uninstall', 'enum': ['list', 'load', 'match', 'install', 'uninstall']},
                'skill_name': {'type': 'string', 'description': 'Skill directory name (for load/uninstall)'},
                'query': {'type': 'string', 'description': 'Query to match (for match)'},
                'url': {'type': 'string', 'description': 'Git URL or GitHub shorthand user/repo (for install)'}
            },
            'required': ['action']
        }
    },
    {
        'name': 'clipboard',
        'description': 'Text clipboard. Quick copy/paste between sessions. Max 50 slots.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'copy, paste, list, or clear', 'enum': ['copy', 'paste', 'list', 'clear']},
                'slot': {'type': 'string', 'description': 'Slot name (default: default)'},
                'content': {'type': 'string', 'description': 'Text to save (for copy)'}
            },
            'required': ['action']
        }
    },
    {
        'name': 'hash_text',
        'description': 'Hash text (SHA256/MD5/SHA1) or generate random password/UUID/token.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'hash, password, uuid, or token', 'enum': ['hash', 'password', 'uuid', 'token']},
                'text': {'type': 'string', 'description': 'Text to hash (for hash)'},
                'algorithm': {'type': 'string', 'description': 'sha256, md5, sha1, sha512, sha384 (default: sha256)'},
                'length': {'type': 'integer', 'description': 'Password/token length (default: 16)'}
            },
            'required': ['action']
        }
    },
    {
        'name': 'regex_test',
        'description': 'Test regular expressions. Match, replace, extract patterns.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'pattern': {'type': 'string', 'description': 'Regex pattern'},
                'text': {'type': 'string', 'description': 'Target text'},
                'action': {'type': 'string', 'description': 'match, find, replace, or split', 'enum': ['match', 'find', 'replace', 'split']},
                'replacement': {'type': 'string', 'description': 'Replacement text (for replace)'},
                'flags': {'type': 'string', 'description': 'Flags: i(case-insensitive), m(multiline), s(dotall)'}
            },
            'required': ['pattern', 'text']
        }
    },
    {
        'name': 'cron_manage',
        'description': 'Manage scheduled tasks. Auto-run LLM tasks on a schedule.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list, add, remove, or toggle', 'enum': ['list', 'add', 'remove', 'toggle']},
                'name': {'type': 'string', 'description': 'Job name (for add)'},
                'prompt': {'type': 'string', 'description': 'LLM prompt (for add)'},
                'schedule': {'type': 'object', 'description': 'Schedule: {"kind":"cron","expr":"0 6 * * *"} or {"kind":"every","seconds":3600} or {"kind":"at","time":"ISO8601"}'},
                'model': {'type': 'string', 'description': 'Model to use (optional, default: current)'},
                'job_id': {'type': 'string', 'description': 'Job ID (for remove/toggle)'}
            },
            'required': ['action']
        }
    },
    {
        'name': 'plugin_manage',
        'description': 'Manage plugins. Auto-load .py files from plugins/ to extend tools.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list or reload', 'enum': ['list', 'reload']}
            },
            'required': ['action']
        }
    },
    {
        'name': 'mcp_manage',
        'description': 'Manage MCP (Model Context Protocol) servers.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list, add, remove, or tools', 'enum': ['list', 'add', 'remove', 'tools']},
                'name': {'type': 'string', 'description': 'Server name (for add/remove)'},
                'command': {'type': 'string', 'description': 'Server command (for add, space-separated)'},
                'env': {'type': 'object', 'description': 'Environment variables (for add, optional)'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'rag_search',
        'description': 'Local RAG (BM25) search across MEMORY.md, memory/, uploads/.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'Search query'},
                'max_results': {'type': 'integer', 'description': 'Max results (default 5)', 'default': 5},
            },
            'required': ['query']
        }
    },
    {
        'name': 'browser',
        'description': 'Browser automation via Chrome CDP. Navigate, screenshot, execute JS.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'navigate/screenshot/text/html/evaluate/click/type/tabs/pdf/status', 'enum': ['navigate', 'screenshot', 'text', 'html', 'evaluate', 'click', 'type', 'tabs', 'pdf', 'status', 'connect', 'console']},
                'url': {'type': 'string', 'description': 'URL (for navigate)'},
                'selector': {'type': 'string', 'description': 'CSS selector (for click/type)'},
                'expression': {'type': 'string', 'description': 'JavaScript code (for evaluate)'},
                'text': {'type': 'string', 'description': 'Input text (for type)'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'node_manage',
        'description': 'Remote node management via SSH/HTTP.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list/add/remove/run/status/upload/wake', 'enum': ['list', 'add', 'remove', 'run', 'status', 'upload', 'wake']},
                'name': {'type': 'string', 'description': 'Node name'},
                'command': {'type': 'string', 'description': 'Command to run (for run)'},
                'host': {'type': 'string', 'description': 'Host address (for add)'},
                'user': {'type': 'string', 'description': 'SSH user (default: root)'},
                'port': {'type': 'integer', 'description': 'SSH port (default: 22)'},
                'key': {'type': 'string', 'description': 'SSH key path'},
                'type': {'type': 'string', 'description': 'Node type: ssh/http'},
                'url': {'type': 'string', 'description': 'HTTP agent URL (for add type=http)'},
                'mac': {'type': 'string', 'description': 'MAC address (for wake)'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'health_check',
        'description': 'System health check. Comprehensive diagnosis of all components.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'check, selftest, or recover', 'enum': ['check', 'selftest', 'recover'], 'default': 'check'},
            },
        }
    },
    # ── v0.12 New Tools ──────────────────────────────────────────
    {
        'name': 'google_calendar',
        'description': 'Google Calendar: list upcoming events, create/delete events. Requires Google API credentials in vault.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list, create, delete', 'enum': ['list', 'create', 'delete']},
                'days': {'type': 'integer', 'description': 'Days ahead to list (default: 7)'},
                'title': {'type': 'string', 'description': 'Event title (for create)'},
                'start': {'type': 'string', 'description': 'Start time ISO8601 (for create)'},
                'end': {'type': 'string', 'description': 'End time ISO8601 (for create)'},
                'description': {'type': 'string', 'description': 'Event description'},
                'event_id': {'type': 'string', 'description': 'Event ID (for delete)'},
                'calendar_id': {'type': 'string', 'description': 'Calendar ID (default: primary)'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'gmail',
        'description': 'Gmail: list recent emails, read specific email, send email. Requires Google API credentials in vault.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list, read, send, search', 'enum': ['list', 'read', 'send', 'search']},
                'count': {'type': 'integer', 'description': 'Number of emails to list (default: 10)'},
                'message_id': {'type': 'string', 'description': 'Message ID (for read)'},
                'to': {'type': 'string', 'description': 'Recipient email (for send)'},
                'subject': {'type': 'string', 'description': 'Email subject (for send)'},
                'body': {'type': 'string', 'description': 'Email body (for send)'},
                'query': {'type': 'string', 'description': 'Search query (Gmail search syntax)'},
                'label': {'type': 'string', 'description': 'Label filter (default: INBOX)'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'calendar_list',
        'description': 'List upcoming Google Calendar events. Use period="today" for today, "week" for this week, "month" for this month.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'period': {'type': 'string', 'description': 'today, week, month (default: week)', 'enum': ['today', 'week', 'month']},
                'calendar_id': {'type': 'string', 'description': 'Calendar ID (default: primary)'},
            },
        }
    },
    {
        'name': 'calendar_add',
        'description': 'Add an event to Google Calendar.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'title': {'type': 'string', 'description': 'Event title'},
                'date': {'type': 'string', 'description': 'Date in YYYY-MM-DD format'},
                'time': {'type': 'string', 'description': 'Start time HH:MM (omit for all-day)'},
                'duration_minutes': {'type': 'integer', 'description': 'Duration in minutes (default: 60)'},
                'description': {'type': 'string', 'description': 'Event description'},
                'calendar_id': {'type': 'string', 'description': 'Calendar ID (default: primary)'},
            },
            'required': ['title', 'date']
        }
    },
    {
        'name': 'calendar_delete',
        'description': 'Delete an event from Google Calendar by event_id.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'event_id': {'type': 'string', 'description': 'Event ID to delete'},
                'calendar_id': {'type': 'string', 'description': 'Calendar ID (default: primary)'},
            },
            'required': ['event_id']
        }
    },
    {
        'name': 'email_inbox',
        'description': 'List recent emails from Gmail inbox.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'count': {'type': 'integer', 'description': 'Number of messages (default: 10, max: 30)'},
            },
        }
    },
    {
        'name': 'email_read',
        'description': 'Read a specific email by message_id.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'message_id': {'type': 'string', 'description': 'Gmail message ID'},
            },
            'required': ['message_id']
        }
    },
    {
        'name': 'email_send',
        'description': 'Send an email via Gmail.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'to': {'type': 'string', 'description': 'Recipient email address'},
                'subject': {'type': 'string', 'description': 'Email subject'},
                'body': {'type': 'string', 'description': 'Email body text'},
            },
            'required': ['to', 'subject']
        }
    },
    {
        'name': 'email_search',
        'description': 'Search emails using Gmail search syntax (e.g. "from:user@example.com", "is:unread", "subject:keyword").',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'Gmail search query'},
                'count': {'type': 'integer', 'description': 'Max results (default: 10)'},
            },
            'required': ['query']
        }
    },
    {
        'name': 'reminder',
        'description': 'Set a reminder. Triggers notification via configured channel (Telegram/desktop) at specified time.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'set, list, delete', 'enum': ['set', 'list', 'delete']},
                'message': {'type': 'string', 'description': 'Reminder message'},
                'time': {'type': 'string', 'description': 'When to remind: ISO8601, relative (e.g. "30m", "2h", "1d"), or natural language'},
                'reminder_id': {'type': 'string', 'description': 'Reminder ID (for delete)'},
                'repeat': {'type': 'string', 'description': 'Repeat interval: daily, weekly, monthly, or cron expression'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'tts_generate',
        'description': 'Text-to-Speech: generate audio from text. Returns audio file path. Supports Google TTS (free) and OpenAI TTS.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'text': {'type': 'string', 'description': 'Text to convert to speech'},
                'provider': {'type': 'string', 'description': 'TTS provider: google, openai (default: google)', 'enum': ['google', 'openai']},
                'language': {'type': 'string', 'description': 'Language code (default: ko-KR)'},
                'voice': {'type': 'string', 'description': 'Voice name (provider-specific)'},
                'output': {'type': 'string', 'description': 'Output file path (default: auto-generated)'},
            },
            'required': ['text']
        }
    },
    {
        'name': 'workflow',
        'description': 'Execute a predefined workflow (tool chain). Define workflows with steps that pipe outputs.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'run, list, save, delete', 'enum': ['run', 'list', 'save', 'delete']},
                'name': {'type': 'string', 'description': 'Workflow name'},
                'steps': {'type': 'array', 'description': 'Workflow steps: [{tool, args, output_var}]',
                          'items': {'type': 'object'}},
                'variables': {'type': 'object', 'description': 'Input variables for the workflow'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'file_index',
        'description': 'Index and search local files. Builds searchable index of workspace files for fast retrieval.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'search, index, status', 'enum': ['search', 'index', 'status']},
                'query': {'type': 'string', 'description': 'Search query'},
                'path': {'type': 'string', 'description': 'Directory to index (default: workspace)'},
                'extensions': {'type': 'string', 'description': 'File extensions to include (comma-separated, e.g. "py,md,txt")'},
                'limit': {'type': 'integer', 'description': 'Max results (default: 10)'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'notification',
        'description': 'Send notification via configured channels (Telegram, desktop, webhook).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'description': 'Notification message'},
                'title': {'type': 'string', 'description': 'Notification title'},
                'channel': {'type': 'string', 'description': 'Channel: telegram, desktop, webhook, all', 'enum': ['telegram', 'desktop', 'webhook', 'all']},
                'url': {'type': 'string', 'description': 'Webhook URL (for webhook channel)'},
                'priority': {'type': 'string', 'description': 'Priority: low, normal, high', 'enum': ['low', 'normal', 'high']},
            },
            'required': ['message']
        }
    },
    # ── v0.12.1 Additional Tools ─────────────────────────────────
    {
        'name': 'weather',
        'description': 'Get current weather and forecast for a location. No API key needed.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'location': {'type': 'string', 'description': 'City name or coordinates (e.g. "Seoul", "Tokyo", "37.5,127.0")'},
                'format': {'type': 'string', 'description': 'Output format: short, full, forecast', 'enum': ['short', 'full', 'forecast'], 'default': 'full'},
                'lang': {'type': 'string', 'description': 'Language code (default: ko)', 'default': 'ko'},
            },
            'required': ['location']
        }
    },
    {
        'name': 'rss_reader',
        'description': 'Read RSS/Atom feeds. Subscribe, list, and fetch latest articles from news sources.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'fetch, subscribe, unsubscribe, list', 'enum': ['fetch', 'subscribe', 'unsubscribe', 'list']},
                'url': {'type': 'string', 'description': 'RSS feed URL (for fetch/subscribe)'},
                'name': {'type': 'string', 'description': 'Feed name (for subscribe)'},
                'count': {'type': 'integer', 'description': 'Number of articles to fetch (default: 5)'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'translate',
        'description': 'Translate text between languages using Google Translate (free, no API key).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'text': {'type': 'string', 'description': 'Text to translate'},
                'target': {'type': 'string', 'description': 'Target language code (e.g. "en", "ko", "ja", "zh", "es", "fr")'},
                'source': {'type': 'string', 'description': 'Source language code (default: auto-detect)'},
            },
            'required': ['text', 'target']
        }
    },
    {
        'name': 'qr_code',
        'description': 'Generate QR code as SVG or text art. Pure stdlib, no dependencies.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'data': {'type': 'string', 'description': 'Data to encode in QR code (URL, text, etc.)'},
                'output': {'type': 'string', 'description': 'Output file path (default: auto-generated SVG)'},
                'format': {'type': 'string', 'description': 'Output format: svg, text', 'enum': ['svg', 'text'], 'default': 'svg'},
                'size': {'type': 'integer', 'description': 'Module size in pixels (SVG, default: 10)'},
            },
            'required': ['data']
        }
    },
    # ── Personal Assistant Tools ──────────────────────────────
    {
        'name': 'note',
        'description': 'Personal knowledge base — save, search, list, delete notes. 개인 메모/지식 베이스.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'Action: save, search, list, delete', 'enum': ['save', 'search', 'list', 'delete']},
                'content': {'type': 'string', 'description': 'Note content (for save)'},
                'tags': {'type': 'string', 'description': 'Comma-separated tags (for save)'},
                'query': {'type': 'string', 'description': 'Search query (for search)'},
                'note_id': {'type': 'string', 'description': 'Note ID (for delete)'},
                'count': {'type': 'integer', 'description': 'Number of results (for list)', 'default': 10},
            },
            'required': ['action']
        }
    },
    {
        'name': 'expense',
        'description': 'Expense tracker — add, view today/month, delete expenses. 가계부/지출 추적.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'Action: add, today, month, delete', 'enum': ['add', 'today', 'month', 'delete']},
                'amount': {'type': 'number', 'description': 'Amount in KRW (for add)'},
                'category': {'type': 'string', 'description': 'Category: 식비,교통,쇼핑,구독,의료,생활,기타 (auto-detected if empty)'},
                'description': {'type': 'string', 'description': 'Description (for add)'},
                'date': {'type': 'string', 'description': 'Date YYYY-MM-DD (default: today)'},
                'month': {'type': 'string', 'description': 'Month YYYY-MM (for month summary)'},
                'expense_id': {'type': 'string', 'description': 'Expense ID (for delete)'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'save_link',
        'description': 'Save links/articles for later reading. Auto-fetches title and content. 링크/아티클 저장.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'Action: save, list, search, delete', 'enum': ['save', 'list', 'search', 'delete']},
                'url': {'type': 'string', 'description': 'URL to save'},
                'title': {'type': 'string', 'description': 'Title (auto-detected if empty)'},
                'summary': {'type': 'string', 'description': '3-line summary'},
                'tags': {'type': 'string', 'description': 'Comma-separated tags'},
                'query': {'type': 'string', 'description': 'Search query'},
                'link_id': {'type': 'string', 'description': 'Link ID (for delete)'},
                'count': {'type': 'integer', 'description': 'Number of results', 'default': 10},
            },
            'required': ['action']
        }
    },
    {
        'name': 'pomodoro',
        'description': 'Pomodoro timer — start focus session, break, stop, view stats. 포모도로 타이머.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'Action: start, break, stop, status', 'enum': ['start', 'break', 'stop', 'status']},
                'duration': {'type': 'integer', 'description': 'Duration in minutes (default: 25 for focus, 5 for break)'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'routine',
        'description': 'Morning/evening routine automation. 아침/저녁 루틴 자동화.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'Routine name: morning, evening, list'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'briefing',
        'description': 'Generate daily briefing — weather, calendar, email, tasks summary. 데일리 브리핑.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'sections': {'type': 'string', 'description': 'Comma-separated sections: weather,calendar,email,tasks,notes,expenses'},
            },
        }
    },
    {
        'name': 'apply_patch',
        'description': 'Apply a multi-file patch (Add/Update/Delete files). 멀티 파일 패치 적용.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patch_text': {'type': 'string', 'description': 'Patch text in *** Begin Patch / *** End Patch format'},
                'base_dir': {'type': 'string', 'description': 'Base directory for patch operations (default: cwd)'},
            },
            'required': ['patch_text'],
        }
    },
    {
        'name': 'ui_control',
        'description': 'Control the web UI settings. Change language, theme, model, navigate panels, or create cron jobs. '
                       'UI 설정 제어: 언어, 테마, 모델 변경, 패널 이동, 크론 작업 생성.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {
                    'type': 'string',
                    'enum': ['set_lang', 'set_theme', 'set_model', 'new_session', 'show_panel', 'add_cron', 'toggle_debug'],
                    'description': 'Action to perform'
                },
                'value': {
                    'type': 'string',
                    'description': 'Value for the action. set_lang: en/ko, set_theme: light/dark, set_model: model name, show_panel: chat/settings/dashboard/sessions/cron/memory/docs'
                },
                'name': {'type': 'string', 'description': 'For add_cron: job name'},
                'interval': {'type': 'integer', 'description': 'For add_cron: interval in seconds'},
                'prompt': {'type': 'string', 'description': 'For add_cron: AI prompt to execute'},
            },
            'required': ['action'],
        }
    },
]


# Re-export handler for backward compatibility
from salmalm.tool_handlers import execute_tool, _resolve_path, _is_safe_command, _is_subpath  # noqa: F401
