# Security Policy

## Dangerous Features: Default OFF

SalmAlm ships with powerful tools that are **disabled by default**. Each requires explicit opt-in via environment variable or CLI flag.

| Feature | Env Variable | Default | Risk |
|---------|-------------|---------|------|
| Shell operators (pipe, redirect, chain) | `SALMALM_ALLOW_SHELL=1` | OFF | Command injection |
| Home directory file read | `SALMALM_ALLOW_HOME_READ=1` | OFF | Data exfiltration |
| Bind to all interfaces | `SALMALM_BIND=0.0.0.0` or `--host 0.0.0.0` | `127.0.0.1` | Network exposure |
| Vault fallback (HMAC-CTR) | `SALMALM_VAULT_FALLBACK=1` | OFF | Weaker encryption |
| Trusted proxy (XFF headers) | `SALMALM_TRUST_PROXY=1` | OFF | IP spoofing |
| CSP nonce strict mode | `SALMALM_CSP_NONCE=1` | OFF (unsafe-inline) | XSS surface |

## Blocked by Default

- **Interpreters** (`python`, `python3`, `node`, `bash`, `sh`, `ruby`, `perl`) are blocked from `exec` tool entirely via `EXEC_BLOCKED_INTERPRETERS`.
- **Elevated commands** (`pip`, `npm`, `docker`, `kubectl`, etc.) require user approval via `EXEC_ELEVATED`.
- **SSRF protection**: HTTP requests validate scheme (http/https only), block userinfo in URLs, re-validate on redirects, block dangerous headers.
- **Path traversal**: `Path.resolve()` + subpath check as primary defense. Sensitive system dirs (`/etc/`, `/var/`, `/root/`) unconditionally blocked.

## Network Security

- **Default bind**: `127.0.0.1` (localhost only). Public exposure requires explicit opt-in.
- **XFF trust**: Only from private/loopback subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`). Public IPs cannot spoof XFF even with `SALMALM_TRUST_PROXY=1`.
- **Loopback admin bypass**: Only active when bound to `127.0.0.1`.
- **WebSocket**: Origin validation enforced. Same-session reconnection supported with message buffering.
- **OAuth**: Token XOR warning logged when misconfigured. PKCE enforced where supported.

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

## Audit

- All tool executions logged to `audit.db` (SQLite).
- Security-sensitive operations (exec, file write, HTTP requests) include full parameter logging.
- Audit checkpoint system for periodic review.

## Reporting Vulnerabilities

Please report security vulnerabilities via GitHub Issues with the `security` label, or email the maintainer directly. Do not open public issues for critical vulnerabilities — use responsible disclosure.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.16.x | ✅ Current |
| < 0.16 | ❌ Upgrade recommended |
