# Contributing to SalmAlm

## Quick Start

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
pip install -e ".[dev]"
```

## Running Tests

### ⚠️ Important: Do NOT run `pytest tests/` directly

The full test suite hangs when run in a single process due to test-file-level state pollution (HTTP servers, asyncio loops, `os.execv` in `/restart` command). This is a known issue.

### Recommended: Per-file execution (CI-style)

```bash
# Run all tests safely (same as CI)
for f in tests/test_*.py; do
    echo "--- $f ---"
    python -m pytest "$f" -q --timeout=30
done
```

### Alternative: pytest-forked

```bash
pip install pytest-forked
python -m pytest tests/ --forked --timeout=30
```

This forks each test into a separate process. Slower (~2min) but avoids all state pollution.

### Run a specific test file

```bash
python -m pytest tests/test_tools.py -v --timeout=30
```

### Run a specific test

```bash
python -m pytest tests/test_e2e.py::TestE2ECommandRouting::test_command_routing -v
```

## Code Style

- **Max line length**: 120 characters
- **Linting**: `flake8 salmalm/ --max-line-length=120 --ignore=E501,W503,E402,E203,F405`
- **No new dependencies**: SalmAlm is stdlib-only. New features must use only Python standard library.
  - Exception: Optional extras (`pip install salmalm[browser]` for Playwright)
- **Imports**: Use direct imports (`from salmalm.core.engine import ...`), not shim imports (`from salmalm import engine`). Shims are deprecated (see `DEPRECATIONS.md`).

## Architecture

```
salmalm/
├── core/           # Engine, session, LLM routing, compaction, cost
├── features/       # Commands, agents, mood, hooks, plugins, mesh, canvas
├── security/       # Crypto, sandbox, exec approvals, audit
├── tools/          # 62 built-in tools (exec, browser, web, file, etc.)
├── web/            # HTTP server, WebSocket, OAuth, templates
├── channels/       # Telegram, Slack integrations
├── utils/          # Chunker, migration, markdown
└── static/         # Web UI (HTML/CSS/JS)
```

### Key Design Decisions

- **DATA_DIR** (`~/SalmAlm` or `$SALMALM_HOME`): All runtime data (DB, vault, memory, logs). BASE_DIR is code only.
- **Security defaults**: Dangerous features OFF. See `SECURITY.md`.
- **OS-native sandbox**: No Docker dependency. bubblewrap → unshare → rlimit fallback.
- **Cost estimation**: Single source in `core/cost.py`.

## Adding a New Tool

1. Create handler in `tools/tools_yourmodule.py`
2. Register in `tools/tool_registry.py`
3. Add tool definition in `tools/tools.py`
4. Add i18n strings (EN + KR) in your module
5. Write tests in `tests/test_yourmodule.py`
6. Update tool count in `README.md` and `README_KR.md`

## Adding a Slash Command

1. Add handler function in `core/engine.py` (in the slash commands section)
2. Register in `_SLASH_COMMANDS` dict (exact match) or `_SLASH_PREFIX_COMMANDS` list (prefix match)
3. Add help text in `features/commands.py`
4. Write tests

## Pull Request Checklist

- [ ] Tests pass: `python -m pytest tests/test_yourfile.py -v --timeout=30`
- [ ] No new dependencies (stdlib only)
- [ ] i18n: Both EN and KR strings provided
- [ ] Security: Dangerous features default OFF with env var opt-in
- [ ] Lint: `flake8 salmalm/ --max-line-length=120 --ignore=E501,W503,E402,E203,F405`
