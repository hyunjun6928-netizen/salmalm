# Architecture
# 아키텍처

## Project Structure / 프로젝트 구조

SalmAlm is organized into several subpackages, each responsible for a specific domain.

SalmAlm은 여러 서브패키지로 구성되어 있으며, 각각 특정 도메인을 담당합니다.

```
salmalm/
├── __init__.py          # Package init, version
├── __main__.py          # Entry point (python -m salmalm)
├── cli.py               # CLI argument parser
├── constants.py         # Global constants
├── engine.py            # Main engine (legacy shim)
│
├── core/                # Core engine modules / 코어 엔진 모듈
│   ├── core.py          # Central SalmAlm class
│   ├── engine.py        # LLM orchestration engine
│   ├── llm.py           # LLM provider abstraction
│   ├── llm_loop.py      # Conversation loop handler
│   ├── llm_task.py      # Async LLM task runner
│   ├── prompt.py        # System prompt builder
│   ├── session_manager.py # Session lifecycle
│   ├── memory.py        # Memory management
│   ├── health.py        # Health check endpoints
│   ├── shutdown.py      # Graceful shutdown
│   ├── export.py        # Session export (JSON/Markdown)
│   ├── image_resize.py  # Image preprocessing
│   ├── plugin_watcher.py # Plugin hot-reload
│   └── exceptions.py    # Custom exceptions
│
├── tools/               # Tool system / 도구 시스템
│   ├── tool_registry.py # Decorator-based tool dispatch
│   ├── tools.py         # Tool definitions (58+ schemas)
│   ├── tools_file.py    # File operations
│   ├── tools_web.py     # Web search & fetch
│   ├── tools_exec.py    # Shell execution
│   ├── tools_memory.py  # Memory tools
│   ├── tools_system.py  # System monitoring
│   ├── tools_personal.py # Personal assistant tools
│   ├── tools_calendar.py # Calendar tools
│   ├── tools_email.py   # Email tools
│   ├── tools_google.py  # Google integration
│   ├── tools_media.py   # Image/audio tools
│   ├── tools_browser.py # Browser automation
│   ├── tools_agent.py   # Sub-agent spawning
│   ├── tools_misc.py    # Miscellaneous utilities
│   ├── tools_patch.py   # Patch/diff tools
│   ├── tools_common.py  # Shared tool utilities
│   ├── tools_reaction.py # Reaction tools
│   ├── tools_reminder.py # Reminder tools
│   └── tools_util.py    # Utility tools
│
├── features/            # Feature modules / 기능 모듈
│   ├── commands.py      # Slash command handler (30+)
│   ├── rag.py           # RAG vector search
│   ├── mcp.py           # MCP server/client
│   ├── mcp_marketplace.py # MCP marketplace
│   ├── a2a.py           # Agent-to-agent protocol
│   ├── agents.py        # Multi-agent management
│   ├── briefing.py      # Daily briefing
│   ├── bookmarks.py     # Session bookmarks
│   ├── compare.py       # Response comparison
│   ├── dashboard_life.py # Life dashboard
│   ├── deadman.py       # Dead man switch
│   ├── doctor.py        # System diagnostics
│   ├── heartbeat.py     # Heartbeat monitoring
│   ├── hooks.py         # Event hooks
│   ├── mood.py          # Mood tracking
│   ├── nodes.py         # Node management
│   ├── plugin_manager.py # Plugin lifecycle
│   ├── presence.py      # Online presence
│   ├── self_evolve.py   # Self-evolution
│   ├── shadow.py        # Shadow mode
│   ├── sla.py           # SLA monitoring
│   ├── stt.py           # Speech-to-text
│   ├── stability.py     # Stability features
│   ├── thoughts.py      # Thought tracking
│   ├── timecapsule.py   # Time capsule
│   ├── transcript_hygiene.py # Transcript cleanup
│   ├── tray.py          # System tray
│   ├── users.py         # User management
│   ├── vault_chat.py    # Vault chat
│   ├── watcher.py       # File watcher
│   └── workflow.py      # Workflow engine
│
├── channels/            # Chat channels / 채팅 채널
│   ├── channel_router.py # Multi-channel routing
│   ├── telegram.py      # Telegram bot
│   ├── discord_bot.py   # Discord bot
│   └── slack_bot.py     # Slack bot (experimental)
│
├── security/            # Security layer / 보안 레이어
│   ├── security.py      # OWASP protection
│   ├── crypto.py        # AES-256-GCM encryption
│   ├── sandbox.py       # Sandboxed execution
│   ├── container.py     # Container isolation
│   └── exec_approvals.py # Dangerous command approval
│
├── web/                 # Web server / 웹 서버
│   ├── web.py           # HTTP request handler
│   ├── ws.py            # WebSocket handler
│   ├── auth.py          # Web authentication
│   ├── oauth.py         # Google OAuth flow
│   └── templates.py     # HTML templates
│
├── utils/               # Utilities / 유틸리티
│   ├── async_http.py    # Async HTTP client
│   ├── browser.py       # Browser utilities
│   ├── chunker.py       # Message chunking
│   ├── dedup.py         # Deduplication
│   ├── file_logger.py   # File-based logging
│   ├── logging_ext.py   # Logging extensions
│   ├── markdown_ir.py   # Markdown IR processor
│   ├── migration.py     # Data migration
│   ├── queue.py         # Async queue
│   ├── retry.py         # Retry with backoff
│   └── tls.py           # TLS certificate generation
│
├── infra/               # Infrastructure / 인프라
├── integrations/        # External integrations / 외부 통합
├── plugins/             # Plugin directory / 플러그인 디렉토리
├── static/              # Static assets (HTML, CSS, JS)
├── frontend/            # Frontend assets
└── default_skills/      # Built-in skill definitions
```

## Data Flow / 데이터 흐름

```
User Input → Channel (Web/Telegram/Discord)
    → channel_router → core.engine
    → prompt builder → LLM API
    → tool_registry (if tool call) → tool_handler
    → response → channel → User
```

## Key Design Decisions / 주요 설계 결정

1. **Zero dependencies** — stdlib only for core; `cryptography` optional for vault / 코어는 표준 라이브러리만 사용
2. **Decorator-based tool registry** — `@register("tool_name")` pattern / 데코레이터 기반 도구 등록
3. **Lazy module loading** — tools loaded on first use / 첫 사용 시 모듈 로딩
4. **Multi-channel abstraction** — single engine, multiple frontends / 단일 엔진, 다중 프론트엔드
5. **Feature isolation** — each feature is a standalone module / 각 기능은 독립 모듈
