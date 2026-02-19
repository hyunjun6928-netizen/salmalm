# Testing Rules

## Running Tests
```bash
python -m unittest discover tests/          # all tests
python -m unittest tests/test_coverage.py   # specific file
python -m coverage run -m unittest discover tests/ && python -m coverage report --include='salmalm/*'
```

## Test Files
- `test_tools.py` — Tool definitions, constants, template validation
- `test_crypto.py` — Vault encrypt/decrypt, key derivation
- `test_api.py` — HTTP API endpoint integration tests
- `test_coverage.py` — Coverage boost: tool handlers, engine, core
- `test_coverage2.py` — Coverage boost: web routes, MCP, nodes, browser
- `test_coverage3.py` — Coverage boost: internals, edge cases, RAG
- `test_coverage4.py` — Coverage boost: all web routes, final push

## Coverage Targets
- Current: ~48% (370 tests)
- Target: 50%+ overall
- Hard-to-test modules: telegram.py (12%), discord_bot.py (19%) — external API dependent
- Well-tested: constants (100%), templates (100%), tools (100%), prompt (96%)

## Writing Tests
- Use `unittest.TestCase` (stdlib only — no pytest).
- Mock external APIs with `unittest.mock.patch`.
- HTTP tests: spin up `HTTPServer` in `setUpClass`, use port 0 for auto-assign.
- File tests: use workspace path (`constants.WORKSPACE_DIR / '_test_tmp'`), not `/tmp`.
- Async tests: `asyncio.new_event_loop()` + `run_until_complete()`, close in finally.
- Accept broad status codes for auth-dependent endpoints: `assertIn(s, (200, 401, ...))`.

## CI
- GitHub Actions: 12-matrix (Python 3.10-3.13 × ubuntu/windows/macos).
- All tests must pass on all platforms before merge.
- Windows-specific: no emoji in logs, UTF-8 stream handler, `resource` module unavailable.

## Known Limitations
- `python_eval` tool tests may behave differently on Windows (subprocess).
- Web server tests can have port conflicts when run in parallel — use port 0.
- Coverage for LLM calls requires mock (no real API calls in tests).
