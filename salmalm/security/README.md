# Security Rules

## Files
- `auth.py` — AuthManager, TokenManager, RateLimiter, RBAC
- `crypto.py` — Vault (AES-256-GCM encryption), key derivation
- `tls.py` — Self-signed TLS certificate generation
- `web.py` — CSP headers, security headers, auth middleware

## Vault
- AES-256-GCM via `cryptography` library (only external dep, optional).
- Fallback: HMAC-CTR if `cryptography` not installed.
- `vault.get(key)` checks vault first, then env var fallback (`_ENV_MAP`).
- `vault.get()` uses `is not None` check (empty string is valid value).
- Vault password: never hardcode. Use `SALMALM_VAULT_PW` env var.
- `salmalm_local` is the default password for new installs — weak but intentional for localhost-only use.

## Authentication
- JWT tokens for web sessions. Secret rotates on server restart.
- First-run setup wizard: set password → unlock vault → enter API keys.
- Public endpoints (no auth): `/api/status`, `/api/check-update`, `/manifest.json`, icons, SW.
- All other endpoints require valid JWT or fail with 401.
- Rate limiter: per-IP, configurable max requests per window.

## CSP (see also frontend/README.md)
- Nonce generated per-request in `_html()` method.
- `_security_headers(nonce)` sets all headers.
- Additional headers: X-Content-Type-Options, X-Frame-Options, Referrer-Policy.
- `Permissions-Policy: microphone=(self)` — needed for STT.

## Error Handling
- Never leak internal paths, stack traces, or API keys in error responses.
- Generic error messages to client; detailed logs to server log only.
- `audit_log()` for security events (login, failed auth, tool execution).

## File Access
- Tool file operations restricted to `WORKSPACE_DIR` and `Path.home()`.
- Path traversal check: `path.resolve().relative_to(allowed_dir)`.
- Protected files list in `constants.py` — vault, audit DB, etc.

## Secrets in Code
- Zero secrets in source code. All via vault or env vars.
- `.gitignore` must exclude: `vault.enc`, `audit.db*`, `certs/`, `*.key`.
- PyPI tokens, API keys: never commit. If exposed, revoke immediately.
