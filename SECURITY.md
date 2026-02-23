# Security Policy

## Threat Model

SalmAlm is a **local single-user personal AI tool**. Default bind is `127.0.0.1` (loopback only). External exposure (`0.0.0.0`) requires explicit opt-in and triggers additional safety checks.

## Dangerous Features: Default OFF

| Feature | Env Variable | Default | Risk |
|---|---|---|---|
| Network bind | `SALMALM_BIND=0.0.0.0` | `127.0.0.1` | Network exposure |
| Shell operators (pipe, redirect, chain) | `SALMALM_ALLOW_SHELL=1` | OFF | Command injection |
| Home directory file read | `SALMALM_ALLOW_HOME_READ=1` | OFF | Data exfiltration |
| Vault fallback (HMAC-CTR) | `SALMALM_VAULT_FALLBACK=1` | OFF | Weaker encryption |
| Plugin system | `SALMALM_PLUGINS=1` | OFF | Arbitrary code execution |
| CLI OAuth token reuse | `SALMALM_CLI_OAUTH=1` | OFF | Third-party token access |
| Elevated exec on external bind | `SALMALM_ALLOW_ELEVATED=1` | OFF | Privilege escalation |
| Trusted proxy (XFF headers) | `SALMALM_TRUST_PROXY=1` | OFF | IP spoofing |
| Strict CSP (nonce mode) | Default ON | `SALMALM_CSP_COMPAT=1` for legacy | XSS surface |
| HTTP header permissive mode | `SALMALM_HEADER_PERMISSIVE=1` | OFF (allowlist) | Header injection |
| Dangerous exec flags | N/A (always blocked) | OFF | Code execution via allowed commands |

## Tool Risk Tiers

Tools are classified by risk level. **Critical tools are blocked on external bind without authentication:**

| Tier | Tools |
|---|---|
| 🔴 Critical | `exec`, `exec_session`, `write_file`, `edit_file`, `python_eval`, `sandbox_exec`, `browser`, `email_send`, `gmail`, `google_calendar`, `calendar_delete`, `calendar_add`, `node_manage`, `plugin_manage` |
| 🟡 High | `http_request`, `read_file`, `memory_write`, `mesh`, `sub_agent`, `cron_manage`, `screenshot`, `tts`, `stt` |
| 🟢 Normal | Everything else |

Tier names are verified against actual registered tool names via `TestToolTierAlignment` in CI.

## Irreversible Action Gate

Destructive operations require explicit `_confirmed=true` parameter:
- `gmail` (action: `send`, `delete`)
- `google_calendar` (action: `create`, `delete`)
- `email_send` (all actions)
- `calendar_delete` (all actions)
- `calendar_add` (all actions)

## SSRF Defense

- **Web tools** (`http_request`, `web_fetch`): DNS pinning + private IP block on every redirect hop + scheme allowlist
- **Browser tool**: `_is_internal_url()` DNS resolution check — blocks private/loopback/link-local/metadata IPs on external bind
- Both share the same private IP detection logic

## Authentication & Authorization

- **Centralized auth gate**: All `/api/` routes require authentication unless in `_PUBLIC_PATHS` set
- **CSRF defense**: Origin validation + `X-Requested-With: SalmAlm` custom header (CORS preflight enforcement)
- **JWT tokens**: `kid` key rotation, `jti` revocation support
- **Password hashing**: PBKDF2-200K iterations
- **Login lockout**: Persistent DB-backed brute-force protection
- **Rate limiting**: Token bucket per-IP rate limiter
- **Multi-user session isolation**: `session_store.user_id` column, queries filtered by user
- **Export security**: Vault export requires admin role

## Secret Protection

- **Audit log redaction**: 9 secret patterns (OpenAI, Anthropic, xAI, Google, Slack, GitHub, AWS, JWT, key=value) scrubbed from tool args before logging (`security/redact.py`)
- **Memory scrubbing**: Same patterns applied before memory write
- **Secret isolation**: API keys stripped from subprocess environments (`exec`, `python_eval`, background sessions)
- **Output redaction**: Tool outputs scanned for API key patterns, replaced with `[REDACTED]`

## Path Validation

- All file path checks use `Path.resolve()` + `Path.is_relative_to()` (not string `startswith`)
- Write tools blocked outside allowed roots even for non-existent paths
- Allowed roots: `WORKSPACE_DIR`, `DATA_DIR`, `/tmp`
- `..` traversal blocked at string level as secondary defense

## Node Security

- Gateway registration requires auth token (`_gateway_token`)
- Tool dispatch payloads are HMAC-SHA256 signed with timestamp + nonce
- Response size capped at 5MB, strict dict validation
- JSON decode errors caught separately

## Vault Encryption

- **Primary**: PBKDF2-HMAC-SHA256 (200K iterations) + AES-256-GCM (requires `cryptography` package)
- **Fallback**: PBKDF2-HMAC-SHA256 (200K iterations) + HMAC-CTR (pure Python, requires `SALMALM_VAULT_FALLBACK=1`)
- Password held in memory only while process runs, never written to disk
- `~/SalmAlm/.vault_auto` for keychain-less environments (WSL)

## Reporting Vulnerabilities

Please report security issues to: https://github.com/hyunjun6928-netizen/salmalm/issues

## Test Coverage

- 150+ security regression tests (`test_security_regression.py`, `test_security_p0p1.py`, `test_security.py`)
- Tool tier alignment verified against registry in CI
- Exec bypass vectors (find -exec, tar --to-command, awk system(), xargs bash, curl metadata) pinned in tests
