# Contributing to SalmAlm

## Quick Start

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
pip install -e ".[dev]"
```

## Running Tests

### ⚠️ Important: Do NOT run `pytest tests/` directly in a single process

The full test suite may have cross-file state pollution (HTTP servers, asyncio loops). Per-file execution is the safe default.

### Recommended: Per-file execution (CI-style)

```bash
# Run all tests safely (same as CI)
for f in tests/test_*.py; do
    echo "--- $f ---"
    python -m pytest "$f" -q --timeout=30
done
```

### Alternative: Full suite (works reliably)

```bash
# Also works — the os.execv hang has been fixed
python -m pytest tests/ -q --timeout=30
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
├── core/               # Engine, session, LLM routing, compaction, cost, model selection, slash commands
│   ├── engine.py       # Intelligence engine + process_message (1,221 lines)
│   ├── core.py         # Session management, compaction, audit
│   ├── cost.py         # Unified cost estimation + MODEL_PRICING
│   ├── model_selection.py  # Complexity-based model routing (single authority)
│   ├── slash_commands.py   # All 32 slash command handlers
│   ├── compaction.py   # Compaction facade (re-exports from core.py)
│   ├── llm_loop.py     # LLM call loop, failover, retry, streaming
│   ├── llm_router.py   # Provider detection, API key management, LLMRouter
│   ├── session_manager.py  # Pruning, cache-aware trimming
│   └── prompt.py       # System prompt builder
├── features/           # Commands, agents, mood, hooks, plugins, mesh, canvas, audit cron
│   ├── audit_cron.py   # Automated audit checkpoint (Timer-based, start/stop)
│   ├── canvas.py       # Local HTML preview server (:18803)
│   ├── mesh.py         # P2P networking (task delegation, LAN discovery)
│   ├── message_queue.py # Offline message queue with retry + dead letter
│   ├── subagents.py    # Sub-agent manager (spawn/steer/collect)
│   └── ...
├── security/           # Crypto, sandbox, exec approvals, audit
│   ├── sandbox.py      # OS-native sandbox (bwrap/unshare/sandbox-exec/rlimit)
│   └── ...
├── tools/              # 62 built-in tools (exec, browser, web, file, etc.)
│   ├── tools_browser.py # Playwright automation (snapshot/act)
│   ├── tools_mesh.py   # Mesh networking tools
│   ├── tools_sandbox.py # Sandbox exec tool
│   └── ...
├── web/                # HTTP server, WebSocket, OAuth, templates
│   ├── web.py          # Route-table HTTP server (59 GET + 63 POST)
│   ├── ws.py           # WebSocket server with reconnect/resume
│   ├── middleware.py   # Route security policies, rate limiter, tool tiers
│   └── ...
├── channels/           # Telegram, Slack integrations
├── utils/              # Chunker, migration, markdown
├── static/             # Web UI
│   ├── index.html      # Main SPA (661 lines, CSP-compatible)
│   ├── app.js          # Extracted JS (2,355 lines, ETag cached)
│   └── icon.svg        # Desktop shortcut icon
└── cli.py              # CLI: --shortcut, --open, --update, --version, --node, --tray
```

### Key Design Decisions

- **DATA_DIR** (`~/SalmAlm` or `$SALMALM_HOME`): All runtime data (DB, vault, memory, logs). BASE_DIR is code only.
- **Security defaults**: Dangerous features OFF. See `SECURITY.md`.
- **OS-native sandbox**: No Docker dependency. bubblewrap → unshare → rlimit fallback.
- **Cost estimation**: Single source in `core/cost.py`.
- **Model selection**: Single authority in `core/model_selection.py`. LLMRouter handles provider availability only.
- **Slash commands**: Extracted to `core/slash_commands.py` with lazy `_get_engine()` for circular dep avoidance.
- **Web UI JS**: External `static/app.js` — no inline scripts, CSP-compatible.
- **Audit cron**: `features/audit_cron.py` — Timer-based, auto-starts on boot, stops on graceful shutdown.
- **Header security**: Allowlist mode by default, blocklist via opt-in.

### Version Management

Version is synchronized across `pyproject.toml` and `salmalm/__init__.py`. Use the bump script:

```bash
python scripts/bump_version.py 0.17.0
```

CI automatically checks version consistency between these files.

## Adding a New Tool

1. Create handler in `tools/tools_yourmodule.py`
2. Register in `tools/tool_registry.py`
3. Add tool definition in `tools/tools.py`
4. Add i18n strings (EN + KR) in your module
5. Write tests in `tests/test_yourmodule.py`
6. Update tool count in `README.md` and `README_KR.md`

## Adding a Slash Command

1. Add handler function in `core/slash_commands.py`
2. Register in `_SLASH_COMMANDS` dict (exact match) or `_SLASH_PREFIX_COMMANDS` list (prefix match)
3. Add help text in `features/commands.py`
4. Write tests

## Pull Request Checklist

- [ ] Tests pass: `python -m pytest tests/test_yourfile.py -v --timeout=30`
- [ ] Full suite: `python -m pytest tests/ -q --timeout=30` (1,709 tests expected)
- [ ] No new dependencies (stdlib only)
- [ ] i18n: Both EN and KR strings provided
- [ ] Security: Dangerous features default OFF with env var opt-in
- [ ] Lint: `flake8 salmalm/ --max-line-length=120 --ignore=E501,W503,E402,E203,F405`
- [ ] Version: Run `python scripts/bump_version.py` if releasing
