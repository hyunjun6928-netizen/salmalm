"""Tool registry — decorator-based tool dispatch replacing if-elif chain."""

import json
from salmalm.security.crypto import log
from salmalm.core import audit_log

_HANDLERS = {}
_DYNAMIC_TOOLS = []  # dynamically registered tool definitions
_modules_loaded = False


def _ensure_modules():
    """Lazy-load all tools_*.py modules so @register decorators run."""
    global _modules_loaded
    if _modules_loaded:
        return
    _modules_loaded = True
    from salmalm import (  # noqa: F401
        tools_file,
        tools_web,
        tools_exec,
        tools_memory,  # noqa: F401
        tools_misc,
        tools_system,
        tools_util,
        tools_agent,
        tools_browser,
        tools_google,
        tools_media,
        tools_calendar,
        tools_email,
        tools_personal,
    )
    from salmalm.tools import tools_brave, tools_mesh, tools_sandbox, tools_ui  # noqa: F401

    # Register apply_patch tool
    from salmalm.tools.tools_patch import apply_patch as _apply_patch_fn

    _HANDLERS["apply_patch"] = lambda args: _apply_patch_fn(args.get("patch_text", ""), args.get("base_dir", "."))


def register(name):
    """Decorator to register a tool handler function."""

    def decorator(fn):
        _HANDLERS[name] = fn
        return fn

    return decorator


def register_dynamic(name: str, handler, tool_def: dict = None):
    """Dynamically register a tool at runtime (for plugins).

    플러그인에서 런타임에 도구를 동적으로 등록합니다.
    """
    _HANDLERS[name] = handler
    if tool_def:
        # Avoid duplicates
        _DYNAMIC_TOOLS[:] = [t for t in _DYNAMIC_TOOLS if t.get("name") != name]
        _DYNAMIC_TOOLS.append(tool_def)
    log.info(f"[TOOL] Dynamic tool registered: {name}")


def unregister_dynamic(name: str):
    """Remove a dynamically registered tool."""
    _HANDLERS.pop(name, None)
    _DYNAMIC_TOOLS[:] = [t for t in _DYNAMIC_TOOLS if t.get("name") != name]


def get_dynamic_tools() -> list:
    """Return all dynamically registered tool definitions."""
    return list(_DYNAMIC_TOOLS)


def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return result string. Auto-dispatches to remote node if available."""
    import os as _os

    audit_log("tool_exec", f"{name}: {json.dumps(args, ensure_ascii=False)[:200]}")

    # Defense-in-depth: tool tier re-verification at registry level
    # (supplements web middleware check — catches internal call paths)
    bind = _os.environ.get("SALMALM_BIND", "127.0.0.1")
    if bind != "127.0.0.1":
        try:
            from salmalm.web.middleware import is_tool_allowed_external

            if not is_tool_allowed_external(name, is_authenticated=False, bind_addr=bind):
                log.warning(f"[SECURITY] Tool '{name}' blocked: external bind + restricted tier")
                return f'❌ Tool "{name}" is restricted on externally-exposed instances'
        except ImportError:
            pass

    # Try remote node dispatch first (if gateway has registered nodes)
    try:
        from salmalm.features.nodes import gateway

        if gateway._nodes:
            result = gateway.dispatch_auto(name, args)
            if result and "error" not in result:
                return result.get("result", str(result))
    except Exception:
        pass  # Fall through to local execution

    _ensure_modules()

    try:
        handler = _HANDLERS.get(name)
        if handler:
            return handler(args)

        # Try legacy plugin tools as fallback
        from salmalm.core import PluginLoader

        result = PluginLoader.execute(name, args)
        if result is not None:
            return result

        # Try directory-based plugins (new plugin architecture)
        try:
            from salmalm.features.plugin_manager import plugin_manager

            result = plugin_manager._execute_plugin_tool(name, args)
            if result is not None:
                return result
        except Exception:
            pass

        # Try MCP tools as last fallback
        if name.startswith("mcp_"):
            from salmalm.features.mcp import mcp_manager

            mcp_result = mcp_manager.call_tool(name, args)
            if mcp_result is not None:
                return mcp_result

        return f"❌ Unknown tool: {name}"

    except PermissionError as e:
        return f"❌ Permission denied: {e}"
    except Exception as e:
        log.error(f"Tool error ({name}): {e}")
        return f"❌ Tool error: {str(e)[:200]}"
