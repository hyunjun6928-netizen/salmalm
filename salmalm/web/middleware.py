"""Request middleware chain — auth, audit, rate limiting for all routes.

Every route handler passes through this chain. Security attributes are
declared per-route at registration time, so developers can't accidentally
skip auth or audit.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional

log = logging.getLogger(__name__)

# ── Route security metadata ──

# auth levels: "none" (public), "optional" (check if token present), "required"
# audit: True/False — log this request to audit trail
# rate: None or "user" or "ip" — rate limit scope


class RoutePolicy:
    """Security policy for a single route."""
    __slots__ = ('auth', 'audit', 'csrf', 'rate')

    def __init__(self, auth: str = 'required', audit: bool = True,
                 csrf: bool = False, rate: Optional[str] = None):
        self.auth = auth      # "none" | "optional" | "required"
        self.audit = audit    # log to audit trail
        self.csrf = csrf      # require CSRF token (POST)
        self.rate = rate      # None | "user" | "ip"


# Default policies by route pattern
_ROUTE_POLICIES: Dict[str, RoutePolicy] = {}

# Well-known public routes (no auth needed)
_PUBLIC_ROUTES = frozenset({
    '/', '/setup', '/unlock', '/health', '/api/health',
    '/static/app.js', '/static/index.html',
    '/icon-192.svg', '/icon-512.svg', '/manifest.json',
    '/api/auth/login', '/api/auth/status',
    '/favicon.ico',
})

# Routes that MUST have auth even on loopback
_SENSITIVE_ROUTES = frozenset({
    '/api/vault/unlock', '/api/vault/lock',
    '/api/admin/restart', '/api/admin/shutdown',
    '/bash',
})


def get_route_policy(path: str, method: str = 'GET') -> RoutePolicy:
    """Get security policy for a route. Returns sensible defaults."""
    if path in _ROUTE_POLICIES:
        return _ROUTE_POLICIES[path]

    # Public routes
    if path in _PUBLIC_ROUTES:
        return RoutePolicy(auth='none', audit=False, csrf=False)

    # Static files
    if path.startswith('/static/'):
        return RoutePolicy(auth='none', audit=False, csrf=False)

    # Sensitive routes — always require auth
    if path in _SENSITIVE_ROUTES:
        return RoutePolicy(auth='required', audit=True, csrf=True)

    # API routes default to auth required
    if path.startswith('/api/'):
        is_write = method in ('POST', 'PUT', 'DELETE', 'PATCH')
        return RoutePolicy(
            auth='required',
            audit=is_write,
            csrf=is_write,
            rate='user' if is_write else None,
        )

    # Default: require auth, audit writes
    return RoutePolicy(auth='required', audit=method != 'GET')


def register_route_policy(path: str, policy: RoutePolicy) -> None:
    """Register custom security policy for a route."""
    _ROUTE_POLICIES[path] = policy


# ── Rate limiter (in-memory, per-IP) ──

_rate_buckets: Dict[str, list] = {}  # key -> [timestamp, ...]
_RATE_WINDOW = 60  # seconds
_RATE_LIMIT = 60   # requests per window (per IP)


def check_rate_limit(key: str) -> bool:
    """Returns True if request is allowed, False if rate limited."""
    now = time.time()
    cutoff = now - _RATE_WINDOW
    bucket = _rate_buckets.get(key, [])
    bucket = [t for t in bucket if t > cutoff]
    if len(bucket) >= _RATE_LIMIT:
        _rate_buckets[key] = bucket
        return False
    bucket.append(now)
    _rate_buckets[key] = bucket
    return True


# ── External exposure safety checks ──

def check_external_exposure_safety(bind_addr: str, handler) -> list:
    """When binding to 0.0.0.0, verify safety requirements are met.
    Returns list of warning strings. Empty = safe."""
    if bind_addr == '127.0.0.1':
        return []

    warnings = []

    # Check if auth is configured
    import os
    from salmalm.constants import DATA_DIR
    db_path = DATA_DIR / 'salmalm.db'
    if db_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cur = conn.execute("SELECT COUNT(*) FROM users WHERE password_hash IS NOT NULL")
            count = cur.fetchone()[0]
            conn.close()
            if count == 0:
                warnings.append(
                    "⚠️  SECURITY: No admin password set! Run 'salmalm' and set a password "
                    "before exposing to network. Anyone can access all tools including /bash."
                )
        except Exception:
            pass
    else:
        warnings.append(
            "⚠️  SECURITY: No database found. First-time setup should be done on localhost "
            "before binding to 0.0.0.0."
        )

    # Check if dangerous tools should be restricted
    if not os.environ.get('SALMALM_EXTERNAL_TOOLS_OK'):
        warnings.append(
            "ℹ️  Dangerous tools (exec, bash, file_write, browser) require authentication "
            "when bound to 0.0.0.0. Set SALMALM_EXTERNAL_TOOLS_OK=1 to suppress this warning."
        )

    return warnings


# ── Tool risk tiers ──

TOOL_TIER_CRITICAL = frozenset({
    'exec', 'bash', 'file_write', 'file_delete', 'python_eval',
    'browser_action', 'sandbox_exec',
})
TOOL_TIER_HIGH = frozenset({
    'http_request', 'send_email', 'file_read',
    'mesh_task', 'mesh_broadcast',
})
TOOL_TIER_NORMAL = frozenset()  # everything else


def get_tool_tier(tool_name: str) -> str:
    """Get risk tier for a tool: 'critical', 'high', or 'normal'."""
    if tool_name in TOOL_TIER_CRITICAL:
        return 'critical'
    if tool_name in TOOL_TIER_HIGH:
        return 'high'
    return 'normal'


def is_tool_allowed_external(tool_name: str, is_authenticated: bool,
                             bind_addr: str) -> bool:
    """Check if a tool can be used given current context.
    Critical tools require auth when externally exposed."""
    if bind_addr == '127.0.0.1':
        return True  # Loopback = trusted
    tier = get_tool_tier(tool_name)
    if tier == 'critical' and not is_authenticated:
        return False
    return True
