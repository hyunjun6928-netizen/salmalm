import logging
import sys

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("salmalm")
except Exception:
    __version__ = "0.0.0-dev"  # fallback — metadata missing

log = logging.getLogger("salmalm")
log.addHandler(logging.NullHandler())  # Prevent "No handlers" warning at import
app = None  # Will be set below if runtime (not during build)


def _register_services() -> None:
    """Register all service factories. Each registration is isolated so one
    failure does not prevent the others from loading."""
    if app is None:
        return
    import logging as _log
    _svc_log = _log.getLogger(__name__)
    _services = [
        ("vault", "salmalm.security.crypto", "vault"),
        ("router", "salmalm.core", "router"),
        ("auth_manager", "salmalm.auth", "auth_manager"),
        ("rate_limiter", "salmalm.auth", "rate_limiter"),
        ("rag_engine", "salmalm.rag", "rag_engine"),
        ("mcp_manager", "salmalm.mcp", "mcp_manager"),
        ("node_manager", "salmalm.nodes", "node_manager"),
        ("health_monitor", "salmalm.stability", "health_monitor"),
        ("telegram_bot", "salmalm.telegram", "telegram_bot"),
        ("user_manager", "salmalm.users", "user_manager"),
        ("discord_bot", "salmalm.discord_bot", "discord_bot"),
        ("ws_server", "salmalm.ws", "ws_server"),
    ]
    for svc_name, module_path, attr in _services:
        try:
            app.register(svc_name, lambda m=module_path, a=attr: getattr(__import__(m, fromlist=[a]), a))
        except Exception as _e:
            _svc_log.warning(f"[INIT] Failed to register service '{svc_name}': {_e}")


_logging_initialized = False


def init_logging() -> None:
    """Initialize file + console logging. Called once from entrypoint, not import."""
    global _logging_initialized
    if _logging_initialized:
        return
    # NullHandler doesn't count — it's a library default, not real logging
    if log.handlers and not all(isinstance(h, logging.NullHandler) for h in log.handlers):
        return
    _logging_initialized = True
    try:
        from .constants import LOG_FILE, DATA_DIR

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log.setLevel(logging.INFO)
        log.addHandler(logging.FileHandler(LOG_FILE, encoding="utf-8"))
        _sh = logging.StreamHandler(sys.stdout)
        _sh.encoding = "utf-8"  # type: ignore[attr-defined]
        log.addHandler(_sh)
        for h in log.handlers:
            h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    except Exception as e:  # noqa: broad-except
        log.debug(f"Suppressed: {e}")


import os as _os

_BUILDING = _os.environ.get("SALMALM_BUILDING") == "1"
if not _BUILDING:
    try:
        from .container import Container

        app = Container()
        _register_services()
    except Exception as e:
        log.debug(f"[INIT] Container setup failed (non-fatal at import): {e}")
