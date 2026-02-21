# Deprecation Timeline / 지원 종료 일정

## Backward Compatibility Shims / 하위 호환 심

SalmAlm v0.14+ restructured the codebase from flat modules into organized packages:
- `salmalm/core/` — engine, LLM, routing, sessions
- `salmalm/tools/` — all tool handlers
- `salmalm/features/` — plugins, cron, agents, etc.
- `salmalm/security/` — auth, crypto, sandbox
- `salmalm/web/` — HTTP server, WebSocket, OAuth

**81 shim files** in `salmalm/` maintain backward compatibility for external plugins
and scripts that import from the old flat paths (e.g., `from salmalm import engine`).

### Timeline / 일정

| Version | Action | Date |
|---------|--------|------|
| v0.16.x | Shims emit `DeprecationWarning` on import | Current |
| v0.18.0 | Shims emit `FutureWarning` (visible by default) | 2026 Q2 |
| v0.20.0 | Shims removed — direct imports only | 2026 Q3 |

### Migration / 마이그레이션

Replace old imports with new direct paths:

```python
# Old (deprecated) / 이전 (지원 종료 예정)
from salmalm import engine
from salmalm import tools_exec

# New (recommended) / 신규 (권장)
from salmalm.core.engine import process_message
from salmalm.tools.tools_exec import handle_exec
```

### How to find deprecated imports / 지원 종료 import 찾기

```bash
python -W all -c "import salmalm.engine"
# → DeprecationWarning: engine is a shim; use salmalm.core.engine directly
```

Or run with `PYTHONWARNINGS=default` to see all warnings:

```bash
PYTHONWARNINGS=default python -m salmalm
```
