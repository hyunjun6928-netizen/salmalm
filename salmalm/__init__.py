import logging
import sys

from .constants import LOG_FILE

# Single logger setup — other modules import `from . import log`
log = logging.getLogger('salmalm')
if not log.handlers:
    log.setLevel(logging.INFO)
    log.addHandler(logging.FileHandler(LOG_FILE, encoding='utf-8'))
    log.addHandler(logging.StreamHandler(sys.stdout))
    for h in log.handlers:
        h.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

# DI Container — lazy registration of all singletons
from .container import app

def _register_services() -> None:
    """Register all service factories. Called once at import time."""
    app.register('vault', lambda: __import__('salmalm.crypto', fromlist=['vault']).vault)
    app.register('router', lambda: __import__('salmalm.core', fromlist=['router']).router)
    app.register('auth_manager', lambda: __import__('salmalm.auth', fromlist=['auth_manager']).auth_manager)
    app.register('rate_limiter', lambda: __import__('salmalm.auth', fromlist=['rate_limiter']).rate_limiter)
    app.register('rag_engine', lambda: __import__('salmalm.rag', fromlist=['rag_engine']).rag_engine)
    app.register('mcp_manager', lambda: __import__('salmalm.mcp', fromlist=['mcp_manager']).mcp_manager)
    app.register('node_manager', lambda: __import__('salmalm.nodes', fromlist=['node_manager']).node_manager)
    app.register('health_monitor', lambda: __import__('salmalm.stability', fromlist=['health_monitor']).health_monitor)
    app.register('telegram_bot', lambda: __import__('salmalm.telegram', fromlist=['telegram_bot']).telegram_bot)
    app.register('ws_server', lambda: __import__('salmalm.ws', fromlist=['ws_server']).ws_server)

_register_services()
