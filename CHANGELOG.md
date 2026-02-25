# Changelog

## v0.27.6 (2026-02-25)
### Bug Fix
- Session delete now also removes on-disk JSON file (`~/SalmAlm/sessions/{id}.json`) — previously deleted sessions would resurrect on every server restart

## v0.27.5 (2026-02-25)
### Packaging Fix
- `static/dist/*.js` (agent-panel.js) now included in PyPI wheel — Agents tab no longer shows "not built yet"

## v0.27.2 (2026-02-25)
### Stability Hardening (OpenClaw patterns)
- **SSE 중복 응답 방지 (Idempotency)** — 클라이언트가 send마다 `req_id` 생성, SSE 완료 시 서버가 5분 캐시 저장. HTTP POST fallback 시 캐시 히트 → 재처리 없이 즉시 반환. `❌ 응답 2개` 버그 근본 해결
- **Billing 전용 장기 쿨다운** — `insufficient_quota`, `billing`, `out of credits` 등 15개 패턴 감지. 잔액 부족 시 5h→12h→24h 쿨다운 (rate limit 1m→5m→1h와 구분). `_BILLING_COOLDOWN_STEPS`, `_BILLING_PATTERNS` 추가
- **Queue debounce 800ms + coalesce** — 연속 전송 메시지를 800ms 대기 후 한 번에 합쳐 처리. LLM 중복 응답 방지 + 문맥 통합 효과
- `_RESP_CACHE` TTL 5분, 만료 항목 자동 prune

## v0.27.1 (2026-02-25)
### Stability + Keyword
- **SSE per-chunk stall timeout (60s)** — 서버가 접속 유지하면서 데이터 안 보낼 때 60초 후 자동 abort → HTTP POST fallback. 기존 180초 전체 타이머만으론 청크 단위 stall 감지 불가
- **URL/링크 컨텍스트 키워드** — `this link`, `this url`, `what's this`, `summarize this`, `링크 내용`, `링크 요약`, `이 글`, `이 영상`, `this video` 등 12개 추가 (OpenClaw summarize 스킬 trigger phrases 참조)
- **이모지 3종 추가** — 🧾→web_fetch/rag_search (summarize), 🧩→exec/python_eval (coding-agent), 🐙→exec/web_fetch (github)

## v0.27.0 (2026-02-25)
### UX Convenience Upgrade
- **Emoji intent injection** — 80 emoji (📸📅🔍🎵⏰🌤️📧💻 등) → 해당 tool 자동 inject
- **Time-pattern tool injection** — "5분 후", "내일 오전", "in 3 hours", "at 3pm" → reminder/cron_manage 자동 inject
- **Question-word web search** — "어떻게", "왜", "what is", "how do" 등 의문형 질문 → web_search 자동 inject
- **Slash command autocomplete** — 채팅 입력창에 `/` 타이핑 시 Discord 스타일 드롭다운 (Arrow키 탐색, Tab/Enter 선택)
- **Model badge quick-switch** — 모델 뱃지 클릭 시 최근 3개 모델 팝업 + "All models" 링크
- `get_extra_tools()` 함수 추출 — classifier.py → tool_selector.py에서 호출
- app.js: 39 → 41 모듈 (3628 lines)

> **Note:** Versions v0.10.x through v0.18.x were rapid iteration releases during initial development (2026-02-19 ~ 2026-02-23). Daily version bumps reflect active development, not production releases. Stable releases begin from v0.19.x.

## v0.19.48 (2026-02-24)
- **24-item external review complete** — all findings addressed
- SSE-first architecture (tab-switch-safe message delivery)
- Embedding RAG with hybrid vector search (OpenAI/Google embeddings + BM25 fallback)
- Agent steer command (`/agent steer <label> <message>`)
- Browser aria-ref compression (10x token savings)
- Thinking stream UI (real-time collapsible display)
- Documentation updated to match v0.19.48 reality

## v0.19.47 (2026-02-24)
- Thinking stream UI — collapsible real-time thinking display

## v0.19.46 (2026-02-24)
- Browser aria-ref compression — 10x token savings

## v0.19.45 (2026-02-24)
- Agent steer command for sub-agent control

## v0.19.44 (2026-02-24)
- Embedding RAG — hybrid vector search with BM25 fallback

## v0.19.43 (2026-02-24)
- SSE-first transport architecture

## v0.19.42 (2026-02-24)
- Fix SSE reconnection edge cases

## v0.19.41 (2026-02-24)
- WebSocket demoted to typing indicators only

## v0.19.40 (2026-02-24)
- External review round 3 — remaining P2/P3 fixes

## v0.19.39 (2026-02-24)
- Detailed explanations for temperature & max tokens settings

## v0.19.38 (2026-02-24)
- Fix slider labels not updating (duplicate id EN/KR)

## v0.19.37 (2026-02-24)
- Fix cross-thread SQLite crash in weakref cleanup

## v0.19.36 (2026-02-24)
- P0-P3 second review round — 15 fixes

## v0.19.35 (2026-02-24)
- Revert max_tokens to cost-efficient defaults — users configure via Settings

## v0.19.34 (2026-02-24)
- Token budget hint injection — LLM self-structures to fit max_tokens

## v0.19.33 (2026-02-24)
- Increase max_tokens defaults — chat 512→4096, code 4096→8192

## v0.19.32 (2026-02-24)
- Auto-continuation for truncated responses

## v0.19.31 (2026-02-24)
- Fix stop button stuck after WS response completes

## v0.19.30 (2026-02-24)
- P1-P3 code review fixes — security, quality, documentation

## v0.19.29 (2026-02-24)
- Fix P0 bootstrap bugs + import paths + SO_REUSEADDR

## v0.19.28 (2026-02-24)
- Fix logging (init_logging skipped due to NullHandler)
- Fix model_override persistence — session meta DB column
- Telegram model pass-through
- Weakref DB connections

## v0.19.27 (2026-02-24)
- Discord WebSocket — websockets lib with raw SSL fallback

## v0.19.26 (2026-02-24)
- Complete 13-point review — all issues addressed

## v0.19.25 (2026-02-24)
- 13-point review fixes — audit atexit, compaction imports, docs cleanup

## v0.19.24 (2026-02-24)
### ✨ Features
- **PWA Service Worker** — offline cache + install prompt for mobile
- **Cloudflare Tunnel** — `salmalm --tunnel` for external access with QR code
- **Desktop Launcher** — PyInstaller one-file build, double-click to run
- **Max Tokens UI** — configurable per-intent (Chat/Code), 0 = Auto dynamic allocation
- **Friendly Error Messages** — bilingual KR/EN user-facing errors instead of tracebacks
- **`/help` Categories** — 7 organized sections (Chat, Reasoning, Status, Security, Agents, Personalization, Tools)
- **Beginners Guide** — `docs/beginners-guide.md` for non-developers

### 🐛 Fixes
- `web_fetch` / `web_search` HTTP errors no longer crash circuit breaker
- `shell=True` removed from 2 exec paths → `shlex.split` + `shell=False`
- Security approval failure now **denies** exec (fail-closed)
- `engine.py` 827→795 lines (under 800 limit)
- Flaky `test_loop_stops_at_max_iterations` fixed
- `compaction.py` missing `datetime`/`KST` imports fixed
- Audit log buffer now flushes on exit via `atexit` (crash data loss prevention)
- DB connection list capped at 100 (memory leak prevention)
- Tool count comments updated (32→67)
- PyPI description: "56+ tools" → "67 tools"

### 📝 Changes
- README/README_KR 5-minute quickstart rewritten
- Feature comparison table updated (12 items)
- MkDocs nav includes beginners guide
- OpenClaw comparison on every Engine setting

## v0.12.4 (2026-02-19)

### ✨ Features
- **Google OAuth2 Setup Wizard** — `/api/google/auth` redirects to Google consent screen, `/api/google/callback` exchanges code for refresh token and saves to vault automatically
- **Google Connect UI** — Settings page now has a Google Account card with Client ID/Secret inputs and one-click "Connect Google" button
- **43 tools** with categorized system prompt — AI now knows all available tools including gmail, google_calendar, reminder, workflow, weather, rss_reader, translate, qr_code, etc.

### 🐛 Fixes
- **Global fetch error handler** — all fetch() calls now show toast notifications on network errors (no more silent failures)
- **Toast notification system** — replaces browser alert() with styled, auto-dismissing toast messages
- **Unlock page try/catch** — prevents unhandled promise rejection on network error
- **CI fix** — `test_http_request_get` mocked to avoid httpbin.org 502 flakiness

### 📝 Changes
- System prompt updated: 31 → 43 tools with categorized descriptions
- Manifest description updated to 43 tools

## v0.12.2 (2026-02-19)

### ✨ Features
- **4 new tools** (43 total): `weather` (wttr.in), `rss_reader` (stdlib XML), `translate` (Google free API), `qr_code` (QR generation)
- **Korean natural language time parsing** — "내일 오전 9시", "30분 후", "다음주 월요일" for reminders
- **i18n labels** for all new tools (EN/KO)

## v0.12.0 (2026-02-19)

### ✨ Features
- **MCP Server + Client** — JSON-RPC 2.0 stdio transport, tools/resources/prompts endpoints
- **7 new tools** (39 total): `google_calendar`, `gmail`, `reminder`, `tts_generate`, `workflow`, `file_index`, `notification`
- **412 tests** passing
- **Dockerfile** + Ollama onboarding support

## v0.11.12 (2026-02-19)

### 🐛 Fixes
- i18n for setup/unlock pages (JS localStorage)
- Service worker version-aware caching
- VERSION scope bug in do_GET

## v0.11.6 (2026-02-19)

### 🐛 Fixes
- **Python 3.14 SyntaxError** — 36 invalid escape sequences doubled in templates.py JS
- **CSP Google Fonts** — added fonts.googleapis.com/fonts.gstatic.com to style-src

## v0.11.5 (2026-02-19)

### ✨ Quality
- **CSP nonce** — removed unsafe-inline from script-src; 49 inline handlers converted to data-action event delegation
- **98% docstring coverage**
- **375 tests**, mypy 0 errors, 48% coverage
- Accessibility: aria-labels on interactive elements

## v0.11.1 (2026-02-19)

### ✨ Features
- **Multi-session UI** — sidebar conversation list with create/switch/delete + auto-title from first message
- **Dashboard** (`/dashboard`) — Chart.js bar chart (tool calls 24h) + doughnut (cost by model) + model stats table + cron/plugin status + 60s auto-refresh
- **STT (Speech-to-Text)** — `stt` tool using OpenAI Whisper API; 🎤 mic button in web UI records audio → transcribes → inserts text
- **PWA** — `manifest.json`, SVG app icons, service worker (standalone mode only), installable from mobile
- **32 tools** (added `stt`)
- **FAQ + use-cases English versions** (`docs/FAQ_EN.md`, `docs/use-cases_EN.md`)

## v0.11.0 (2026-02-19)

### ✨ Features
- **`image_analyze` vision tool** — analyze images via GPT-4o/Claude Vision (URL, base64, local file, OCR)
- **Prompt v0.5.0** — improved intent classification + tool selection accuracy
- **SSE chunk streaming** — real-time response streaming with tool counters and status messages
- **CI/CD** — GitHub Actions matrix (Ubuntu/macOS/Windows × Python 3.10–3.13)
- **Badges** — PyPI, CI, License, Python version
- **Docs** — CONTRIBUTING, CHANGELOG, FAQ (KR+EN), use-cases (KR+EN), issue templates

## v0.10.9 (2026-02-19)

### 🔒 Security
- `/api/do-update`, `/api/restart`: admin auth + loopback-only enforcement
- `/api/dashboard`, `/api/cron`, `/api/plugins`, `/api/mcp`, `/api/rag`, `/api/notifications`: require user auth
- `/uploads/` directory traversal prevention (basename normalization + resolve)

### ✨ Features
- **Setup Wizard**: first-run screen asking password preference (set or skip)
- **Password management**: change, remove, or set password anytime from Settings
- **Unlimited tool loop**: removed max_tools cap (OpenClaw-style, model decides when to stop)
- **Unlock screen guide**: detailed instructions for first-time users + password recovery

### 🐛 Fixes
- Empty vault password (`""`) now correctly saves and unlocks (`_save()` falsiness fix)
- Docs page spacing reduced 30-40% (tighter margins, padding, line-height)

## v0.10.8 (2026-02-19)

### ✨ Features
- Unlimited tool loop (initial implementation)
- Friendlier Korean error messages for tool limit

## v0.10.7 (2026-02-19)

### 🔒 Security
- P0 auth hardening: all sensitive API endpoints now require authentication
- Path traversal fix on `/uploads/` serving

## v0.10.6 (2026-02-19)

### ✨ Features
- **Model registry centralized** in `constants.py` (MODELS, MODEL_TIERS, FALLBACK_MODELS, TEST_MODELS, MODEL_ALIASES)
- **Stdlib multipart parser** — replaced manual boundary-split with `email.parser.BytesParser`
- **Cache session isolation** — `ResponseCache._key()` includes session_id
- **Ollama tier routing + aliases**
- **Bind address configurable** — `--host` / `--port` CLI args
- **EXEC RBAC tiers** — allowlist / elevated / blocklist separation

### 🔒 Security
- Admin password stderr only (never in log files)
- API key SHA-256 hashed storage (raw key shown once, never stored)
- CSRF Origin validation on all POST /api/* endpoints
- `except Exception:` + undefined `{e}` bugs fixed (3 locations)
- `datetime` import fix in agents.py
- COMPLEX_INDICATORS deduplication
- SQLite WAL mode + thread-local connections
- `compact_messages` import fix
- Eval blocklist hardened

### 🐛 Fixes
- Token secret persisted to file (survives restarts)
- Rate limiter auto-cleanup (stale buckets purged every 10min)
- Session memory cleanup (8hr TTL, 200 session hard cap)

## v0.10.5 (2026-02-19)

### 🔒 Security
- 5 `except Exception:` + `{e}` reference bugs fixed
- Admin password output to stderr only
- API key storage changed to SHA-256 hash
- CSRF Origin validation added

## v0.10.4 (2026-02-19)

### ✨ Features
- Code split into 25 modules (from monolithic server.py)
  - `templates.py` — HTML extracted
  - `tool_handlers.py` — tool execution separated
  - `agents.py` — SubAgent, SkillLoader, PluginLoader extracted
  - `nodes.py` — Gateway-Node architecture
- `.env` as primary config, vault as option
- Korean intent classifier keywords
- Gateway-node architecture for multi-machine dispatch

## v0.10.0 (2026-02-19)

### ✨ Features
- 85 unit tests + 21/21 selftest
- Backward compatibility verification
- Vault/.env fallback system

## v0.9.x (2026-02-18)

### ✨ Features
- Intelligence Engine (7-intent classifier → adaptive routing → plan → execute → reflect)
- RAG Engine (BM25 + SQLite)
- WebSocket server (RFC 6455)
- MCP server + client
- Browser automation (Chrome CDP)
- Discord bot (raw WebSocket)
- Telegram bot (async long-polling)
- Cron scheduler
- 30 built-in tools
- Plugin system
- Cost tracking (27 models)
- Health monitor + Circuit Breaker

## v0.8.0 (2026-02-19)

### ✨ Features
- Initial PyPI release
- 20 modules, 30 tools, 84 tests
- pip install ready
