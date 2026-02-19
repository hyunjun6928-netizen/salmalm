# Infrastructure Rules

## Files
- `ws.py` — WebSocket server (RFC 6455, pure asyncio)
- `rag.py` — RAG engine (BM25 + SQLite FTS)
- `logging_ext.py` — Structured JSON logging, rotation, correlation IDs
- `stability.py` — HealthMonitor, CircuitBreaker, watchdog
- `container.py` — Lightweight DI container
- `constants.py` — All paths, costs, thresholds, model definitions

## WebSocket
- RFC 6455 handshake + frame encoding, pure stdlib.
- Streaming responses: `StreamingResponse` class wraps chunked sends.
- Cron jobs managed via WS server (add/remove/list/tick).
- External WS connections may fail behind Cloudflare — polling fallback needed.

## RAG
- BM25 ranking with SQLite FTS5 backend.
- `_tokenize()` handles Korean text (character-level for CJK).
- `reindex(force=True)` on startup.
- Workspace files indexed: `.md`, `.txt`, `.py`, `.json`.

## Logging
- `StreamHandler` forced to UTF-8 in `__init__.py` (Windows cp1252 fix).
- No emoji in log messages — ASCII only (Windows compatibility).
- `set_correlation_id()` / `get_correlation_id()` for request tracing.
- Audit DB (SQLite): security events, tool executions, logins.

## Stability
- `HealthMonitor.check_health()` — returns healthy/degraded/unhealthy.
- `CircuitBreaker(threshold, window_sec)` — trips after N errors.
- `startup_selftest()` — validates all modules import correctly.
- `watchdog_tick()` — auto-recovery every 5 minutes (currently disabled).

## Constants
- `MODELS` dict: all supported models with context sizes and costs.
- `MODEL_TIERS` dict: tier 1 (fast/cheap) to tier 3 (powerful/expensive).
- `MODEL_ALIASES`: shorthand names → full provider/model strings.
- `WORKSPACE_DIR`, `BASE_DIR`, `MEMORY_DIR`: canonical paths.
- Changes to constants affect the entire application — test thoroughly.

## Cron
- `CronScheduler` in core.py — async tick-based scheduler.
- `LLMCronManager` — scheduled LLM tasks with persistence.
- Currently all cron jobs disabled (owner request, token savings).
