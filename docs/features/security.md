# Security

SalmAlm follows a **dangerous features default OFF** policy.

## Defaults

| Feature | Default | Opt-in |
|---|---|---|
| Network bind | `127.0.0.1` (loopback only) | `SALMALM_BIND=0.0.0.0` |
| Shell operators | Blocked | `SALMALM_ALLOW_SHELL=1` |
| Home dir file read | Workspace only | `SALMALM_ALLOW_HOME_READ=1` |
| Plugin system | Disabled | `SALMALM_PLUGINS=1` |
| CLI OAuth reuse | Disabled | `SALMALM_CLI_OAUTH=1` |
| Strict CSP (nonce) | Disabled | `SALMALM_CSP_STRICT=1` |

## Tool Risk Tiers

| Tier | Tools | External (0.0.0.0) |
|---|---|---|
| 🔴 Critical (14) | exec, exec_session, write_file, edit_file, python_eval, sandbox_exec, browser, email_send, gmail, google_calendar, calendar_delete, calendar_add, node_manage, plugin_manage | Auth required |
| 🟡 High (9) | http_request, read_file, memory_write, mesh, sub_agent, cron_manage, screenshot, tts, stt | Allowed with warning |
| 🟢 Normal | web_search, weather, translate, etc. | Allowed |

## Vault

API keys are encrypted at rest:

- **Primary**: PBKDF2-200K iterations + AES-256-GCM (requires `cryptography` package)
- **Fallback**: HMAC-SHA256-CTR (pure Python, enabled via `SALMALM_VAULT_FALLBACK=1`)
- **Storage**: `~/SalmAlm/.vault.enc`
- **Auto-unlock**: `.vault_auto` file for WSL/no-keychain environments

## SSRF Defense

- DNS pinning eliminates TOCTOU gap in redirects
- Private/loopback/link-local IPs blocked on external bind
- Browser tool: `_is_internal_url()` DNS resolution check
- Applied to all outbound HTTP (web tools + browser)

## Irreversible Action Gate

These tools require `_confirmed=true` parameter:

- `email_send` — send email
- `gmail` (action: send) — send via Gmail
- `calendar_delete` — delete calendar event

Without confirmation, a preview is shown instead.

## Secret Protection

- **Shared redact module** (`security/redact.py`): 9 regex patterns (OpenAI, Anthropic, xAI, Google, Slack, GitHub, AWS, JWT, key=value)
- **Memory scrubbing**: secrets auto-redacted before storage
- **Audit log redaction**: tool args scrubbed before logging
- **Subprocess isolation**: API keys stripped from child environments

## Auth & CSRF

- Centralized auth gate: all `/api/` routes require auth unless in `_PUBLIC_PATHS`
- CSRF: Origin validation + `X-Requested-With` custom header
- Session cookies with secure flags

## Node Communication

- HMAC-SHA256 signed payloads (`X-Signature` header)
- Timestamp + nonce for replay prevention
- 5MB response cap
- Strict dict validation

## Tests

- **150+ security regression tests** across 3 test files
- Covers: path traversal, exec bypass vectors, SSRF, tool tier enforcement, irreversible gates, secret scrubbing
