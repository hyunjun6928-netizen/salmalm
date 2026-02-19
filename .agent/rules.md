# SalmAlm — Agent Rules

## Philosophy
- **stdlib only** — no external dependencies. Use `urllib`, not `requests`.
- **Single process** — personal tool, not a team platform.
- **English for all docs/rules/readmes** — saves tokens on repeated reads.

## Domain Rules (SSOT)
Do NOT put detailed rules here. Read the domain-specific README when working in that area.

| Domain | When to read | Path |
|--------|-------------|------|
| Frontend/UX | UI changes, templates, CSS, client JS | `salmalm/frontend/README.md` |
| Backend/Engine | LLM calls, tools, engine logic, sessions | `salmalm/backend/README.md` |
| Security | Auth, vault, CSP, TLS, rate limiting | `salmalm/security/README.md` |
| Integrations | Telegram, Discord, MCP, nodes, browser | `salmalm/integrations/README.md` |
| Infrastructure | WebSocket, RAG, logging, cron, stability | `salmalm/infra/README.md` |
| Testing | Writing/running tests, coverage targets | `tests/README.md` |

## Universal Rules (apply everywhere)
1. All Python must pass `mypy --ignore-missing-imports` with 0 errors.
2. Never use `# type: ignore` without specifying the error code.
3. No secrets/keys in code. Use vault or env vars.
4. Error messages must not leak internals (paths, stack traces, keys).
5. Commit messages: `type: short description` (fix/feat/chore/test/docs).
6. Python triple-quote strings: double all JS regex backslashes (`\\w` not `\w`).
7. PyPI version bump required before every publish (can't re-upload same version).
8. `__version__` must match in both `pyproject.toml` and `salmalm/__init__.py`.
