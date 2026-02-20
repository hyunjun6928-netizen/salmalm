"""SalmAlm DI Container — Lightweight service registry.

Provides a central registry for all singleton services,
replacing scattered global instances. Supports:
  - Lazy initialization
  - Service replacement (for testing)
  - Type-safe access via properties
  - Startup validation

Usage:
    from salmalm.security.container import app
    vault = app.vault
    router = app.router
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, TypeVar

T = TypeVar('T')


class Container:
    """Lightweight DI container with lazy initialization."""

    def __init__(self) -> None:
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._lock = threading.Lock()

    def register(self, name: str, factory: Callable[[], T]) -> None:
        """Register a lazy factory for a service."""
        with self._lock:
            self._factories[name] = factory

    def set(self, name: str, instance: Any) -> None:
        """Set an already-created service instance."""
        with self._lock:
            self._services[name] = instance

    def get(self, name: str) -> Any:
        """Get a service, creating it lazily if needed."""
        if name in self._services:
            return self._services[name]
        with self._lock:
            # Double-check after acquiring lock
            if name in self._services:
                return self._services[name]
            if name in self._factories:
                instance = self._factories[name]()
                self._services[name] = instance
                return instance
        raise KeyError(f"Service not registered: {name}")

    def replace(self, name: str, instance: Any) -> Any:
        """Replace a service (for testing). Returns old instance."""
        with self._lock:
            old = self._services.get(name)
            self._services[name] = instance
            return old

    def has(self, name: str) -> bool:
        """Check if a service is registered."""
        return name in self._services or name in self._factories

    def reset(self) -> None:
        """Clear all services (for testing)."""
        with self._lock:
            self._services.clear()
            self._factories.clear()

    # ── Typed properties for IDE autocomplete ────────────────

    @property
    def vault(self) -> Any:
        """Get the Vault service instance."""
        return self.get('vault')

    @property
    def router(self) -> Any:
        """Get the ModelRouter service instance."""
        return self.get('router')

    @property
    def auth_manager(self) -> Any:
        """Get the AuthManager service instance."""
        return self.get('auth_manager')

    @property
    def rate_limiter(self) -> Any:
        """Get the RateLimiter service instance."""
        return self.get('rate_limiter')

    @property
    def rag_engine(self) -> Any:
        """Get the RAGEngine service instance."""
        return self.get('rag_engine')

    @property
    def mcp_manager(self) -> Any:
        """Get the MCPManager service instance."""
        return self.get('mcp_manager')

    @property
    def node_manager(self) -> Any:
        """Get the NodeManager service instance."""
        return self.get('node_manager')

    @property
    def health_monitor(self) -> Any:
        """Get the HealthMonitor service instance."""
        return self.get('health_monitor')

    @property
    def telegram_bot(self) -> Any:
        """Get the TelegramBot service instance."""
        return self.get('telegram_bot')

    @property
    def ws_server(self) -> Any:
        """Get the WebSocketServer service instance."""
        return self.get('ws_server')

    def validate(self) -> Dict[str, bool]:
        """Check all expected services are registered."""
        expected = [
            'vault', 'router', 'auth_manager', 'rate_limiter',
            'rag_engine', 'mcp_manager', 'node_manager',
            'health_monitor', 'telegram_bot', 'ws_server',
        ]
        return {name: self.has(name) for name in expected}


# ── Global container instance ────────────────────────────────
app = Container()
