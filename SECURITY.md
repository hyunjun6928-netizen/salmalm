# Security Policy

## Dangerous Features: Default OFF

SalmAlm ships with powerful tools that are **disabled by default**. Each requires explicit opt-in via environment variable or CLI flag.

| Feature | Env Variable | Default | Risk |
|---------|-------------|---------|------|
| Shell operators (pipe, redirect, chain) | `SALMALM_ALLOW_SHELL=1` | OFF | Command injection |
| Home directory file read | `SALMALM_ALLOW_HOME_READ=1` | OFF | Data exfiltration |
| Bind to all interfaces | `SALMALM_BIND=0.0.0.0` | `127.0.0.1` | Network exposure |
| Vault fallback (HMAC-CTR) | `SALMALM_VAULT_FALLBACK=1` | OFF | Weaker encryption |
| Trusted proxy (XFF headers) | `SALMALM_TRUST_PROXY=1` | OFF | IP spoofing |
| CSP nonce strict mode | `SALMALM_CSP_NONCE=1` | OFF (unsafe-inline) | XSS surface |
| HTTP header permissive mode | `SALMALM_HEADER_PERMISSIVE=1` | OFF (allowlist) | Header injection |

## Route Security Middleware

Every HTTP route has an enforced security policy via `web/middleware.py`:

- **RoutePolicy** per route: `auth`, `audit`, `csrf`, `rate` attributes
- Public routes (`/`, `/setup`, `/static/*`): no auth
- API routes (`/api/*`): auth required, writes audited, CSRF on POST
- Sensitive routes (`/api/vault/*`, `/api/admin/*`): always auth + CSRF
- **Rate limiting**: in-memory per-IP, 60 requests per 60-second window

## Tool Risk Tiers

| Tier | Tools | External (0.0.0.0) without auth |
|------|-------|---------------------------------|
| Critical | exec, bash, file_write, file_delete, python_eval, browser_action, sandbox_exec | **Blocked** |
| High | http_request, send_email, file_read, mesh_task | Warning logged |
| Normal | All others | Allowed |

When `SALMALM_BIND=0.0.0.0`, SalmAlm automatically warns if no admin password is configured and blocks critical tools for unauthenticated sessions.

## Blocked by Default

- **Interpreters** (`python`, `python3`, `node`, `bash`, `sh`, `ruby`, `perl`) are blocked from `exec` tool entirely via `EXEC_BLOCKED_INTERPRETERS`.
- **Elevated commands** (`pip`, `npm`, `docker`, `kubectl`, etc.) require user approval via `EXEC_ELEVATED`.
- **SSRF protection**: HTTP requests validate scheme (http/https only), block userinfo in URLs, re-validate on redirects, block dangerous headers.
- **Path traversal**: `Path.resolve()` + subpath check as primary defense. Sensitive system dirs (`/etc/`, `/var/`, `/root/`) unconditionally blocked.

## HTTP Request Header Security

The `http_request` tool enforces header security in two modes:

### Allowlist Mode (default)
Only explicitly safe headers are permitted:
- `Accept`, `Accept-Language`, `Accept-Encoding`, `Authorization`
- `Content-Type`, `Content-Length`, `Cookie`, `User-Agent`
- `Cache-Control`, `If-None-Match`, `If-Modified-Since`
- `Range`, `Referer`, `Origin`, `X-Requested-With`
- `X-API-Key`, `X-CSRF-Token`

Any header not in this list is rejected with an error message.

### Blocklist Mode (`SALMALM_HEADER_PERMISSIVE=1`)
All headers allowed except explicitly dangerous ones:
- `Host`, `Transfer-Encoding`, `TE`, `Upgrade`, `Connection`
- `Proxy-Authorization`, `Proxy-Connection`
- `X-Forwarded-For`, `X-Real-IP`, `Forwarded`
- `X-Forwarded-Host`, `X-Forwarded-Proto`

Additional blocked headers can be added via `SALMALM_BLOCKED_HEADERS` (comma-separated).

## Network Security

- **Default bind**: `127.0.0.1` (localhost only). Public exposure requires explicit opt-in.
- **XFF trust**: Only from private/loopback subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`). Public IPs cannot spoof XFF even with `SALMALM_TRUST_PROXY=1`.
- **Loopback admin bypass**: Only active when bound to `127.0.0.1`.
- **WebSocket**: Origin validation enforced. Same-session reconnection supported with message buffering (max 50).
- **OAuth**: Token XOR warning logged when misconfigured. PKCE enforced where supported.
- **Mesh networking**: HMAC-SHA256 authentication via `SALMALM_MESH_SECRET`. Peers must share the same secret.

## Authentication

- **Vault**: AES-256-GCM encryption with PBKDF2 key derivation (200,000 iterations). Requires `cryptography` package; fallback HMAC-CTR only via explicit opt-in.
- **Login lockout**: Persistent in SQLite. Exponential backoff after failed attempts.
- **Token rotation**: Multi-key `kid` ring system via `_SECRET_DIR`. Old keys remain valid for verification during rotation window.
- **Session tokens**: HMAC-SHA256 signed, expiry-checked.

## Sandbox

OS-native sandbox tiers (no Docker dependency):

| Level | Linux | macOS | Windows |
|-------|-------|-------|---------|
| Strong | bubblewrap (bwrap) | — | — |
| Moderate | unshare | sandbox-exec | — |
| Basic | rlimit (CPU/RAM/fd/fsize) | rlimit | rlimit |

Detection: `SandboxCapabilities.detect()` auto-selects the strongest available tier.

### Exec Resource Limits (foreground)
- CPU: command timeout + 5 seconds
- RAM: 1 GB
- File descriptors: 100
- File size: 50 MB
- Platform: Linux/macOS only (Windows skipped)

### Tool Timeouts
Per-tool wall-clock limits prevent runaway operations:
- `exec`: 120 seconds
- `browser`: 90 seconds
- Default: 60 seconds

### Tool Result Truncation
Per-tool output size limits prevent token flooding:
- `exec`: 20,000 characters
- `http_request`: 15,000 characters
- `browser`: 10,000 characters

## Audit

- All tool executions logged to `audit.db` (SQLite).
- Security-sensitive operations (exec, file write, HTTP requests) include full parameter logging.
- **Automated audit checkpoint**: runs every 6 hours via `audit_cron` module (Timer-based, graceful shutdown).
- **Audit log cleanup**: removes entries older than 30 days.
- Append-only checkpoint log for tamper evidence.

## CSP (Content Security Policy)

- **Default**: `unsafe-inline` for script-src (backward compatibility with older browsers).
- **Strict mode** (`SALMALM_CSP_NONCE=1`): nonce-based script-src. All JS is in external `app.js` served with ETag caching and security headers.
- No inline `onclick` or event handlers anywhere — all UI uses `data-action` delegation.

## Reporting Vulnerabilities

Please report security vulnerabilities via GitHub Issues with the `security` label, or email the maintainer directly. Do not open public issues for critical vulnerabilities — use responsible disclosure.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.17.x | ✅ Current (1,709 tests, 46 security regression tests) |
| 0.16.x | ✅ Security fixes |
| < 0.16 | ❌ Upgrade recommended |
