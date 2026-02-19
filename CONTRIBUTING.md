# Contributing to SalmAlm

First off, thanks for considering contributing! 🎉

## Getting Started

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
pip install -e ".[dev]"
python -m unittest discover tests/ -v
```

## Development Setup

SalmAlm has **zero external dependencies** (stdlib only). The only optional dependency is `cryptography` for AES-256-GCM vault encryption.

```bash
# Run the dev server
python server.py
# → http://localhost:18800

# Run tests
python -m unittest discover tests/ -v

# Quick import check
python -c "import salmalm; print('OK')"
```

## How to Contribute

### 🐛 Bug Reports

Open an issue with:
- Python version (`python --version`)
- OS (Windows/Mac/Linux)
- Steps to reproduce
- Error message or log (`salmalm.log`)

### 💡 Feature Requests

Open an issue describing:
- What you want to do
- Why it would be useful
- Any implementation ideas

### 🔧 Pull Requests

1. Fork the repo
2. Create a branch (`git checkout -b fix/my-fix`)
3. Make your changes
4. Run tests (`python -m unittest discover tests/ -v`)
5. Commit with a clear message
6. Push and open a PR

### 🧩 Plugins

The easiest way to contribute is writing a plugin! Drop a `.py` file in `plugins/`:

```python
# plugins/my_tool.py
TOOLS = [{
    "name": "my_tool",
    "description": "Does something cool",
    "parameters": {"type": "object", "properties": {}}
}]

def execute(name, params, context=None):
    return "Hello from my plugin!"
```

## Code Style

- Pure Python stdlib (no external dependencies in core)
- Functions over classes where possible
- Korean comments are fine (this is a bilingual project)
- Test your changes: `python -m unittest discover tests/`

## Good First Issues

Look for issues labeled `good first issue` — these are designed for newcomers.

## Architecture Overview

```
salmalm/
├── core.py          — session management, cron, caching
├── engine.py        — Intelligence Engine (classify → plan → execute → reflect)
├── llm.py           — LLM API calls (6 providers)
├── tools.py         — 30 tool definitions
├── tool_handlers.py — tool execution
├── web.py           — HTTP server + API
├── templates.py     — HTML templates
└── ...              — 25 modules total
```

## Questions?

Open a Discussion on GitHub or file an issue. We're friendly. 😈
