"""Patch web.py: extract simple GET/POST handlers into methods with route dispatch."""

with open('salmalm/web.py', 'r') as f:
    content = f.read()

# Strategy: For _do_get_inner, extract the simple one-liner API routes as methods
# and add a route dispatch. Keep complex routes (/, prefix routes) in the if/elif chain.

# For _do_post_inner, same approach but for the POST body-parsing routes.

# Step 1: Add simple GET handler methods before _do_get_inner
# Step 2: Add route dispatch at top of _do_get_inner
# Step 3: Remove the corresponding elif blocks from _do_get_inner

# Let's identify the simple GET handlers that can be extracted:
# These are ones like: elif self.path == '/api/X': ... self._json(...)

# For GET, simple handlers:
get_handlers = '''
    # ── Extracted GET handlers ────────────────────────────────
    def _get_uptime(self):
        from .sla import uptime_monitor
        self._json(uptime_monitor.get_stats())

    def _get_latency(self):
        from .sla import latency_tracker
        self._json(latency_tracker.get_stats())

    def _get_sla(self):
        from .sla import uptime_monitor, latency_tracker, watchdog, sla_config
        self._json({
            'uptime': uptime_monitor.get_stats(),
            'latency': latency_tracker.get_stats(),
            'health': watchdog.get_last_report(),
            'config': sla_config.get_all(),
        })

    def _get_sla_config(self):
        from .sla import sla_config
        self._json(sla_config.get_all())

    def _get_nodes(self):
        from .nodes import node_manager
        self._json({'nodes': node_manager.list_nodes()})

    def _get_gateway_nodes(self):
        from .nodes import gateway
        self._json({'nodes': gateway.list_nodes()})

    def _get_status(self):
        self._json({'app': APP_NAME, 'version': VERSION,
                    'unlocked': vault.is_unlocked,
                    'usage': get_usage_report(),
                    'model': router.force_model or 'auto'})

    def _get_metrics(self):
        from .core import _metrics
        usage = get_usage_report()
        _metrics['total_cost'] = usage.get('total_cost', 0.0)
        merged = {**request_logger.get_metrics(), **_metrics}
        self._json(merged)

    def _get_cert(self):
        from .tls import get_cert_info
        self._json(get_cert_info())

    def _get_ws_status(self):
        from .ws import ws_server
        self._json({
            'running': ws_server._running,
            'clients': ws_server.client_count,
            'port': ws_server.port,
        })

    def _get_usage_daily(self):
        if not self._require_auth('user'): return
        from .edge_cases import usage_tracker
        self._json({'report': usage_tracker.daily_report()})

    def _get_usage_monthly(self):
        if not self._require_auth('user'): return
        from .edge_cases import usage_tracker
        self._json({'report': usage_tracker.monthly_report()})

    def _get_usage_models(self):
        if not self._require_auth('user'): return
        from .edge_cases import usage_tracker
        self._json({'breakdown': usage_tracker.model_breakdown()})

    def _get_groups(self):
        if not self._require_auth('user'): return
        from .edge_cases import session_groups
        self._json({'groups': session_groups.list_groups()})

    def _get_models(self):
        if not self._require_auth('user'): return
        from .edge_cases import model_detector
        force = '?force' in self.path
        models = model_detector.detect_all(force=force)
        self._json({'models': models, 'count': len(models)})

    def _get_soul(self):
        if not self._require_auth('user'): return
        from .prompt import get_user_soul, USER_SOUL_FILE
        self._json({'content': get_user_soul(), 'path': str(USER_SOUL_FILE)})

    def _get_routing(self):
        if not self._require_auth('user'): return
        from .engine import get_routing_config
        from .constants import MODELS
        self._json({'config': get_routing_config(), 'available_models': MODELS})

    def _get_failover(self):
        if not self._require_auth('user'): return
        from .engine import get_failover_config, _load_cooldowns
        self._json({'config': get_failover_config(), 'cooldowns': _load_cooldowns()})

    def _get_cron(self):
        if not self._require_auth('user'): return
        from .core import _llm_cron
        self._json({'jobs': _llm_cron.list_jobs() if _llm_cron else []})

    def _get_mcp(self):
        if not self._require_auth('user'): return
        from .mcp import mcp_manager
        servers = mcp_manager.list_servers()
        all_tools = mcp_manager.get_all_tools()
        self._json({'servers': servers, 'total_tools': len(all_tools)})

    def _get_rag(self):
        if not self._require_auth('user'): return
        from .rag import rag_engine
        self._json(rag_engine.get_stats())

    def _get_personas(self):
        from .prompt import list_personas, get_active_persona
        session_id = self.headers.get('X-Session-Id', 'web')
        personas = list_personas()
        active = get_active_persona(session_id)
        self._json({'personas': personas, 'active': active})

    # ── GET Route Table (exact path → method) ──
    _GET_ROUTES = {
        '/api/uptime': '_get_uptime',
        '/api/latency': '_get_latency',
        '/api/sla': '_get_sla',
        '/api/sla/config': '_get_sla_config',
        '/api/nodes': '_get_nodes',
        '/api/gateway/nodes': '_get_gateway_nodes',
        '/api/status': '_get_status',
        '/api/metrics': '_get_metrics',
        '/api/cert': '_get_cert',
        '/api/ws/status': '_get_ws_status',
        '/api/usage/daily': '_get_usage_daily',
        '/api/usage/monthly': '_get_usage_monthly',
        '/api/usage/models': '_get_usage_models',
        '/api/groups': '_get_groups',
        '/api/models': '_get_models',
        '/api/soul': '_get_soul',
        '/api/routing': '_get_routing',
        '/api/failover': '_get_failover',
        '/api/cron': '_get_cron',
        '/api/mcp': '_get_mcp',
        '/api/rag': '_get_rag',
        '/api/personas': '_get_personas',
    }

'''

# Insert before _do_get_inner
marker = '    def _do_get_inner(self):'
pos = content.index(marker)
content = content[:pos] + get_handlers + '\n' + content[pos:]

# Add dispatch at top of _do_get_inner
old_get = '    def _do_get_inner(self):\n        if self.path'
new_get = '''    def _do_get_inner(self):
        # Route table dispatch for simple API endpoints
        _clean_path = self.path.split('?')[0]
        _handler_name = self._GET_ROUTES.get(_clean_path)
        if _handler_name:
            return getattr(self, _handler_name)()
        if self.path'''
content = content.replace(old_get, new_get)

# Now remove the elif blocks that are now handled by route table
# We need to remove each extracted handler's elif block from _do_get_inner
paths_to_remove = [
    '/api/soul', '/api/routing', '/api/failover', '/api/cron', '/api/mcp',
    '/api/rag', '/api/ws/status', '/api/usage/daily', '/api/usage/monthly',
    '/api/usage/models', '/api/groups', '/api/models', '/api/uptime',
    '/api/latency', '/api/sla/config', '/api/nodes', '/api/gateway/nodes',
    '/api/status', '/api/personas', '/api/metrics', '/api/cert',
]

# For /api/sla - special case, it's exact match but needs care
# Let's also handle it

# Remove each extracted elif block
import re

for path in paths_to_remove:
    # Match: elif self.path == '/api/X':\n            ...(until next elif or else)
    # This is tricky due to indentation. Let's do it carefully.
    escaped = re.escape(path)
    # Find the elif for this exact path
    pattern = f"        elif self\\.path == '{escaped}':\n"
    idx = content.find(f"        elif self.path == '{path}':\n")
    if idx == -1:
        # Try without quotes variation
        print(f"  SKIP: {path} (not found as elif)")
        continue

    # Find the next elif/else at same indentation
    search_from = idx + 1
    next_elif = content.find('\n        elif ', search_from)
    next_else = content.find('\n        else:', search_from)

    candidates = [x for x in [next_elif, next_else] if x != -1]
    if candidates:
        end = min(candidates)
    else:
        end = len(content)

    block = content[idx:end]
    # Only remove if it looks like a simple handler (not too many lines)
    lines = block.count('\n')
    if lines <= 15:
        content = content[:idx] + content[end:]
        print(f"  REMOVED: {path} ({lines} lines)")
    else:
        print(f"  SKIP: {path} (complex: {lines} lines)")

# Also handle /api/sla (exact) separately since it may conflict with /api/sla/config
idx = content.find("        elif self.path == '/api/sla':\n")
if idx != -1:
    search_from = idx + 1
    next_elif = content.find('\n        elif ', search_from)
    next_else = content.find('\n        else:', search_from)
    candidates = [x for x in [next_elif, next_else] if x != -1]
    end = min(candidates) if candidates else len(content)
    block = content[idx:end]
    if block.count('\n') <= 15:
        content = content[:idx] + content[end:]
        print(f"  REMOVED: /api/sla")

with open('salmalm/web.py', 'w') as f:
    f.write(content)

print(f"\nDone. web.py patched.")
