"""Tool registry — decorator-based tool dispatch replacing if-elif chain."""
import json
from .crypto import log
from .core import audit_log

_HANDLERS = {}
_modules_loaded = False


def _ensure_modules():
    """Lazy-load all tools_*.py modules so @register decorators run."""
    global _modules_loaded
    if _modules_loaded:
        return
    _modules_loaded = True
    from . import (tools_file, tools_web, tools_exec, tools_memory,
                   tools_misc, tools_system, tools_util, tools_agent,
                   tools_browser, tools_google, tools_media,
                   tools_calendar, tools_email)  # noqa: F401


def register(name):
    """Decorator to register a tool handler function."""
    def decorator(fn):
        _HANDLERS[name] = fn
        return fn
    return decorator


def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return result string. Auto-dispatches to remote node if available."""
    audit_log('tool_exec', f'{name}: {json.dumps(args, ensure_ascii=False)[:200]}')

    # Try remote node dispatch first (if gateway has registered nodes)
    try:
        from .nodes import gateway
        if gateway._nodes:
            result = gateway.dispatch_auto(name, args)
            if result and 'error' not in result:
                return result.get('result', str(result))
    except Exception:
        pass  # Fall through to local execution

    _ensure_modules()

    try:
        handler = _HANDLERS.get(name)
        if handler:
            return handler(args)

        # Try plugin tools as fallback
        from .core import PluginLoader
        result = PluginLoader.execute(name, args)
        if result is not None:
            return result

        # Try MCP tools as last fallback
        if name.startswith('mcp_'):
            from .mcp import mcp_manager
            mcp_result = mcp_manager.call_tool(name, args)
            if mcp_result is not None:
                return mcp_result

        return f'❌ Unknown tool: {name}'

    except PermissionError as e:
        return f'❌ Permission denied: {e}'
    except Exception as e:
        log.error(f"Tool error ({name}): {e}")
        return f'❌ Tool error: {str(e)[:200]}'
