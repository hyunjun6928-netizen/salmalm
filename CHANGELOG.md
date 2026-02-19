# Changelog

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
