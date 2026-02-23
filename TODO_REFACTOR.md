# Refactor / Tech Debt Queue

Priority order. Not features — structural improvements.

1. **sys.modules proxy removal** — `core/__init__.py` `_PkgProxy` → simple re-exports
2. **exec allowlist tiering** — split into basic/network/db tiers; network/db require explicit opt-in
3. **cooldown error-type policy** — 401/403 provider-wide, 429/5xx model-only + backoff, timeout short retry
4. **vault fallback warning** — doctor + UI banner when running HMAC-CTR without `cryptography`
5. **CLI OAuth UI confirmation** — add 2-step approval in web UI (not just env var)
