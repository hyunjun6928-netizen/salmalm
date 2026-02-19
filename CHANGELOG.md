# Changelog

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
