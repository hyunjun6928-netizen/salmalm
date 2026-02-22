# Changelog

## v0.18.73 (2026-02-23)

### Bot UX (OpenClaw-style)
- **Telegram**: Ack reaction (👀), reply-to threading, setMyCommands menu (12 commands)
- **Discord**: Ack reaction, reply-to, streaming preview (draft→edit), smart message splitting, 6 built-in commands

### Memory System
- Auto-curate: promote important daily entries to MEMORY.md after compaction
- Auto-log: significant conversations recorded to daily memory automatically

### Cron Jobs
- Error tracking with `last_error` and `error_count` per job
- Auto-disable after 5 consecutive failures
- Failure notifications to owner via Telegram

## v0.18.72 (2026-02-23)

### Fresh Install UX
- Setup wizard always shown on fresh install (bootstrap vault auto-create removed)
- CSP default flipped to `unsafe-inline` (templates use inline scripts)
- Strict nonce mode opt-in via `SALMALM_CSP_STRICT=1`
- 7 E2E tests: vault→setup→onboarding→main UI

### Engine Refactor
- `_execute_loop` god object split: 280→130 lines
- 10 helper functions extracted to `core/loop_helpers.py`

## v0.18.64 (2026-02-22)

### Security (5 review rounds)
- Session user_id scoping (multi-tenant isolation)
- Vault export requires admin role
- `@register('browser')` misplacement fix
- Path validation `startswith()` → `Path.is_relative_to()`

## v0.18.63

### Security
- Tool tier names aligned to 67 registered tools (CRITICAL 14, HIGH 9)
- Irreversible action gate: email_send, gmail send, calendar_delete require `_confirmed=true`
- Browser SSRF defense: `_is_internal_url()` blocks private/loopback on external bind
- Exec bypass test vectors (find -exec, tar --to-command, etc.)

## v0.18.61

### Security
- Shared `security/redact.py` module (9 secret patterns)
- Audit log redaction in tool_handlers and tool_registry
- Write tools blocked outside allowed roots
- Memory delegates to shared redact (DRY)

## v0.18.55

### Security
- CLI OAuth gated behind `SALMALM_CLI_OAUTH=1`
- Memory secret scrubbing before write
- Elevated command blocking on external bind

## v0.18.37

### Security (P0-P2)
- `ruff format` applied to 226 files
- BackgroundSession kill: Popen + os.killpg()
- Plugins default OFF (`SALMALM_PLUGINS=1`)
- SSRF DNS pinning defense
- shlex.split for exec parser
- Audit logging standardized
- 19 security regression tests

## v0.18.35

### Model Router
- `X-Session-Id` header in model router requests
- `model_override` semantics fixed
- Graceful restart support
- Auto routing classification hints

## v0.18.30

### Cost Optimization
- Dynamic tool selection: 67→0 (chat) / 7-12 (actions)
- Tool schema compression: 7,749→693 tokens (91%)
- Smart model routing: simple→Haiku, moderate→Sonnet, complex→Opus
- Intent-based max_tokens and history trim
- System prompt compressed: 762→310 tokens
- **Result: $7.09/day → $1.23/day (83% savings)**

### Web UI
- Engine Optimization panel with all toggles
- Auto Routing panel with classification guide
- i18n EN/KR split (`.eng-en`/`.eng-kr` CSS classes)
- Telegram & Discord settings panels
- OpenClaw-like preset
