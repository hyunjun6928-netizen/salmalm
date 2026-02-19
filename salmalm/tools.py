"""SalmAlm tool definitions — schema for all 32 tools."""

TOOL_DEFINITIONS = [
    {
        'name': 'exec',
        'description': 'Execute shell commands. Dangerous commands are blocked.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'command': {'type': 'string', 'description': 'Shell command to execute'},
                'timeout': {'type': 'integer', 'description': 'Timeout in seconds', 'default': 30}
            },
            'required': ['command']
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
]



# Re-export handler for backward compatibility
from .tool_handlers import execute_tool, _resolve_path, _is_safe_command, _is_subpath
