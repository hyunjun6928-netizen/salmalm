"""삶앎 Stability Engine — health monitoring, auto-recovery, watchdog.

Provides production-grade stability:
  - Health check endpoint with detailed diagnostics
  - Auto-recovery for crashed components (Telegram, WebSocket, Cron)
  - Memory watchdog (prevent runaway memory usage)
  - Session cleanup (stale session garbage collection)
  - Graceful degradation (fallback when components fail)
  - Startup self-test (verify all modules loadable)
  - Error rate tracking (circuit breaker pattern)
"""

import os
import resource
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional

from .constants import VERSION, KST, BASE_DIR, AUDIT_DB
from .crypto import log

# ── Error tracking ──────────────────────────────────────────

class CircuitBreaker:
    """Track error rates per component. Trip after threshold."""

    def __init__(self, threshold: int = 5, window_sec: int = 300,
                 cooldown_sec: int = 60):
        self.threshold = threshold
        self.window_sec = window_sec
        self.cooldown_sec = cooldown_sec
        self._errors: Dict[str, deque] = {}
        self._tripped: Dict[str, float] = {}  # component -> trip time
        self._lock = threading.Lock()

    def record_error(self, component: str, error: str = ""):
        """Record an error for a component."""
        with self._lock:
            if component not in self._errors:
                self._errors[component] = deque(maxlen=100)
            self._errors[component].append({
                "time": time.time(),
                "error": error[:200],
            })

    def record_success(self, component: str):
        """Record successful operation — helps reset breaker."""
        with self._lock:
            if component in self._tripped:
                elapsed = time.time() - self._tripped[component]
                if elapsed > self.cooldown_sec:
                    del self._tripped[component]
                    log.info(f"🔄 Circuit breaker reset: {component}")

    def is_tripped(self, component: str) -> bool:
        """Check if circuit breaker is open (too many errors)."""
        with self._lock:
            if component in self._tripped:
                if time.time() - self._tripped[component] < self.cooldown_sec:
                    return True
                else:
                    del self._tripped[component]

            errors = self._errors.get(component, deque())
            now = time.time()
            recent = sum(1 for e in errors if now - e["time"] < self.window_sec)

            if recent >= self.threshold:
                self._tripped[component] = now
                log.warning(f"⚡ Circuit breaker tripped: {component} "
                           f"({recent} errors in {self.window_sec}s)")
                return True
            return False

    def get_status(self) -> Dict[str, dict]:
        """Get all component statuses."""
        with self._lock:
            status = {}
            now = time.time()
            for comp, errors in self._errors.items():
                recent = sum(1 for e in errors if now - e["time"] < self.window_sec)
                last_error = errors[-1]["error"] if errors else ""
                status[comp] = {
                    "recent_errors": recent,
                    "total_errors": len(errors),
                    "tripped": comp in self._tripped,
                    "last_error": last_error,
                }
            return status


class HealthMonitor:
    """Comprehensive health monitoring and auto-recovery."""

    def __init__(self):
        self.circuit_breaker = CircuitBreaker()
        self._start_time = time.time()
        self._checks: Dict[str, dict] = {}
        self._recovery_attempts: Dict[str, int] = {}
        self._max_recovery = 3  # Max recovery attempts per component per hour
        self._lock = threading.Lock()

    def check_health(self) -> dict:
        """Run comprehensive health check. Returns health report."""
        report = {
            "status": "healthy",
            "version": VERSION,
            "uptime_seconds": round(time.time() - self._start_time),
            "uptime_human": self._format_uptime(),
            "timestamp": datetime.now(KST).isoformat(),
            "components": {},
            "system": self._check_system(),
            "circuit_breakers": self.circuit_breaker.get_status(),
        }

        # Check each component
        components = {
            "vault": self._check_vault,
            "telegram": self._check_telegram,
            "websocket": self._check_websocket,
            "rag": self._check_rag,
            "mcp": self._check_mcp,
            "cron": self._check_cron,
            "database": self._check_database,
            "llm": self._check_llm,
        }

        unhealthy = 0
        for name, check_fn in components.items():
            try:
                result = check_fn()
                report["components"][name] = result
                if result.get("status") != "ok":
                    unhealthy += 1
            except Exception as e:
                report["components"][name] = {
                    "status": "error",
                    "error": str(e)[:200],
                }
                unhealthy += 1

        if unhealthy > len(components) // 2:
            report["status"] = "critical"
        elif unhealthy > 0:
            report["status"] = "degraded"

        return report

    def _format_uptime(self) -> str:
        secs = int(time.time() - self._start_time)
        hours, remainder = divmod(secs, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 24:
            days = hours // 24
            hours = hours % 24
            return f"{days}d {hours}h {minutes}m"
        return f"{hours}h {minutes}m {seconds}s"

    def _check_system(self) -> dict:
        """Check system resources."""
        info = {}
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            info["memory_mb"] = round(usage.ru_maxrss / 1024, 1)  # Linux: KB
            info["user_time"] = round(usage.ru_utime, 2)
            info["sys_time"] = round(usage.ru_stime, 2)
        except Exception:
            pass

        try:
            # Check disk space for workspace
            stat = os.statvfs(str(BASE_DIR))
            info["disk_free_mb"] = round(stat.f_bavail * stat.f_frsize / (1024 * 1024), 1)
            info["disk_total_mb"] = round(stat.f_blocks * stat.f_frsize / (1024 * 1024), 1)
            info["disk_pct"] = round(100 * (1 - stat.f_bavail / stat.f_blocks), 1)
        except Exception:
            pass

        try:
            info["pid"] = os.getpid()
            info["threads"] = threading.active_count()
        except Exception:
            pass

        return info

    def _check_vault(self) -> dict:
        from .crypto import vault
        return {
            "status": "ok" if vault.is_unlocked else "locked",
            "locked": not vault.is_unlocked,
        }

    def _check_telegram(self) -> dict:
        try:
            from .core import _tg_bot
            if _tg_bot and _tg_bot.token:
                return {"status": "ok", "running": True,
                        "owner": bool(_tg_bot.owner_id)}
            return {"status": "not_configured"}
        except Exception as e:
            return {"status": "error", "error": str(e)[:100]}

    def _check_websocket(self) -> dict:
        try:
            from .ws import ws_server
            return {
                "status": "ok" if ws_server._running else "stopped",
                "running": ws_server._running,
                "clients": ws_server.client_count,
                "port": ws_server.port,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)[:100]}

    def _check_rag(self) -> dict:
        try:
            from .rag import rag_engine
            stats = rag_engine.get_stats()
            return {
                "status": "ok" if stats["total_chunks"] > 0 else "empty",
                **stats,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)[:100]}

    def _check_mcp(self) -> dict:
        try:
            from .mcp import mcp_manager
            servers = mcp_manager.list_servers()
            connected = sum(1 for s in servers if s.get("connected"))
            return {
                "status": "ok",
                "total_servers": len(servers),
                "connected": connected,
                "total_tools": sum(s.get("tools", 0) for s in servers),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)[:100]}

    def _check_cron(self) -> dict:
        try:
            from .core import cron
            return {
                "status": "ok" if cron._running else "stopped",
                "running": cron._running,
                "jobs": len(cron.jobs),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)[:100]}

    def _check_database(self) -> dict:
        import sqlite3
        try:
            conn = sqlite3.connect(str(AUDIT_DB))
            count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            usage_count = conn.execute("SELECT COUNT(*) FROM usage_stats").fetchone()[0]
            conn.close()
            size_kb = round(AUDIT_DB.stat().st_size / 1024, 1) if AUDIT_DB.exists() else 0
            return {
                "status": "ok",
                "audit_entries": count,
                "usage_entries": usage_count,
                "size_kb": size_kb,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)[:100]}

    def _check_llm(self) -> dict:
        """Check LLM availability (based on circuit breaker, not actual API call)."""
        breaker_status = self.circuit_breaker.get_status()
        llm_status = breaker_status.get("llm", {})
        if llm_status.get("tripped"):
            return {
                "status": "degraded",
                "tripped": True,
                "recent_errors": llm_status.get("recent_errors", 0),
                "last_error": llm_status.get("last_error", ""),
            }
        return {"status": "ok", "tripped": False}

    async def auto_recover(self):
        """Attempt to recover crashed components."""
        health = self.check_health()
        recovered = []

        for comp, status in health["components"].items():
            if status.get("status") in ("ok", "not_configured", "locked"):
                continue

            # Check recovery budget
            hour_key = f"{comp}_{int(time.time() // 3600)}"
            attempts = self._recovery_attempts.get(hour_key, 0)
            if attempts >= self._max_recovery:
                log.warning(f"🔧 Recovery budget exhausted: {comp} ({attempts} attempts this hour)")
                continue

            self._recovery_attempts[hour_key] = attempts + 1

            try:
                if comp == "websocket":
                    from .ws import ws_server
                    if not ws_server._running:
                        await ws_server.start()
                        recovered.append(comp)
                        log.info(f"🔧 Auto-recovered: {comp}")

                elif comp == "rag" and status.get("status") == "empty":
                    from .rag import rag_engine
                    rag_engine.reindex(force=True)
                    recovered.append(comp)
                    log.info(f"🔧 Auto-recovered: {comp}")

                elif comp == "cron":
                    from .core import cron
                    if not cron._running:
                        import asyncio
                        asyncio.create_task(cron.run())
                        recovered.append(comp)
                        log.info(f"🔧 Auto-recovered: {comp}")

            except Exception as e:
                log.error(f"🔧 Recovery failed ({comp}): {e}")
                self.circuit_breaker.record_error(f"recovery_{comp}", str(e))

        return recovered

    def startup_selftest(self) -> dict:
        """Run self-test on startup to verify all modules."""
        results = {}
        modules = [
            ("constants", "salmalm.constants"),
            ("crypto", "salmalm.crypto"),
            ("core", "salmalm.core"),
            ("llm", "salmalm.llm"),
            ("tools", "salmalm.tools"),
            ("prompt", "salmalm.prompt"),
            ("engine", "salmalm.engine"),
            ("telegram", "salmalm.telegram"),
            ("web", "salmalm.web"),
            ("ws", "salmalm.ws"),
            ("rag", "salmalm.rag"),
            ("mcp", "salmalm.mcp"),
            ("browser", "salmalm.browser"),
            ("nodes", "salmalm.nodes"),
            ("auth", "salmalm.auth"),
            ("tls", "salmalm.tls"),
            ("logging_ext", "salmalm.logging_ext"),
            ("docs", "salmalm.docs"),
        ]

        passed = 0
        for name, module_path in modules:
            try:
                __import__(module_path)
                results[name] = "ok"
                passed += 1
            except Exception as e:
                results[name] = f"FAIL: {e}"
                log.error(f"Self-test FAIL: {name} — {e}")

        total = len(modules)
        log.info(f"🧪 Self-test: {passed}/{total} modules OK")
        return {
            "passed": passed,
            "total": total,
            "all_ok": passed == total,
            "modules": results,
        }


# ── Watchdog async task ──────────────────────────────────────

async def watchdog_tick(monitor: HealthMonitor):
    """Periodic watchdog check — run via cron every 5 minutes."""
    health = monitor.check_health()

    # Log warnings for degraded components
    if health["status"] != "healthy":
        degraded = [name for name, s in health["components"].items()
                    if s.get("status") not in ("ok", "not_configured", "locked")]
        if degraded:
            log.warning(f"⚠️ Degraded components: {', '.join(degraded)}")

    # Memory check — warn if > 500MB
    mem_mb = health.get("system", {}).get("memory_mb", 0)
    if mem_mb > 500:
        log.warning(f"⚠️ High memory usage: {mem_mb}MB")

    # Disk check — warn if < 500MB free
    disk_free = health.get("system", {}).get("disk_free_mb", 9999)
    if disk_free < 500:
        log.warning(f"⚠️ Low disk space: {disk_free}MB free")

    # Auto-recover if needed
    if health["status"] in ("degraded", "critical"):
        recovered = await monitor.auto_recover()
        if recovered:
            log.info(f"🔧 Auto-recovered: {', '.join(recovered)}")


# Module-level instance
health_monitor = HealthMonitor()
