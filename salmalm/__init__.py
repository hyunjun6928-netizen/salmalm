import logging
import sys

try:
    __version__ = "0.18.51"
except Exception:
    __version__ = "0.18.51"

log = logging.getLogger("salmalm")
log.addHandler(logging.NullHandler())  # Prevent "No handlers" warning at import
app = None  # Will be set below if runtime (not during build)


def _register_services() -> None:
    """Register all service factories. Called once at import time."""
    if app is None:
        return
    app.register("vault", lambda: __import__("salmalm.crypto", fromlist=["vault"]).vault)
    app.register("router", lambda: __import__("salmalm.core", fromlist=["router"]).router)
    app.register("auth_manager", lambda: __import__("salmalm.auth", fromlist=["auth_manager"]).auth_manager)
    app.register("rate_limiter", lambda: __import__("salmalm.auth", fromlist=["rate_limiter"]).rate_limiter)
    app.register("rag_engine", lambda: __import__("salmalm.rag", fromlist=["rag_engine"]).rag_engine)
    app.register("mcp_manager", lambda: __import__("salmalm.mcp", fromlist=["mcp_manager"]).mcp_manager)
    app.register("node_manager", lambda: __import__("salmalm.nodes", fromlist=["node_manager"]).node_manager)
    app.register("health_monitor", lambda: __import__("salmalm.stability", fromlist=["health_monitor"]).health_monitor)
    app.register("telegram_bot", lambda: __import__("salmalm.telegram", fromlist=["telegram_bot"]).telegram_bot)
    app.register("user_manager", lambda: __import__("salmalm.users", fromlist=["user_manager"]).user_manager)
    app.register("discord_bot", lambda: __import__("salmalm.discord_bot", fromlist=["discord_bot"]).discord_bot)
    app.register("ws_server", lambda: __import__("salmalm.ws", fromlist=["ws_server"]).ws_server)


_logging_initialized = False


def init_logging():
    """Initialize file + console logging. Called once from entrypoint, not import."""
    global _logging_initialized
    if _logging_initialized or log.handlers:
        return
    _logging_initialized = True
    try:
        from .constants import LOG_FILE, DATA_DIR

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log.setLevel(logging.INFO)
        log.addHandler(logging.FileHandler(LOG_FILE, encoding="utf-8"))
        _sh = logging.StreamHandler(sys.stdout)
        _sh.setStream(open(sys.stdout.fileno(), "w", encoding="utf-8", errors="replace", closefd=False))
        log.addHandler(_sh)
        for h in log.handlers:
            h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    except Exception:
        pass


try:
    from .container import Container

    app = Container()
    _register_services()
except Exception:
    # During pip build / isolated environments, constants may fail.
    pass
