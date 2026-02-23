"""Health Endpoint — K8s readiness/liveness probe compatible.

GET /health → JSON with LLM status, memory, active sessions, uptime, disk, version.
200 = healthy, 503 = unhealthy.
stdlib-only.
"""

from __future__ import annotations

import os
import threading
import time

try:
    import resource as _resource
except ImportError:
    _resource = None  # type: ignore[assignment]

from salmalm.constants import VERSION, BASE_DIR
import logging

log = logging.getLogger(__name__)

_start_time = time.time()


def get_health_report() -> dict:
    """Build comprehensive health report.

    Returns dict with:
      - status: 'healthy' | 'degraded' | 'unhealthy'
      - version, uptime_seconds, uptime_human
      - llm: connection status
      - memory_mb: RSS memory
      - active_sessions: count
      - disk: free/total MB
      - threads: active thread count
    """
    report: dict = {
        "status": "healthy",
        "version": VERSION,
        "uptime_seconds": round(time.time() - _start_time),
        "uptime_human": _format_uptime(),
    }
    issues = []

    # LLM connectivity (cached probe, not real API call on every check)
    report["llm"] = _check_llm_status()
    if not report["llm"].get("connected"):
        issues.append("llm")

    # Memory
    mem_mb = _get_memory_mb()
    report["memory_mb"] = mem_mb
    if mem_mb > 500:
        issues.append("memory")

    # Active sessions
    try:
        from salmalm.core.core import _sessions

        report["active_sessions"] = len(_sessions)
    except Exception as e:  # noqa: broad-except
        report["active_sessions"] = 0

    # Disk
    disk = _get_disk_info()
    report["disk"] = disk
    if disk.get("free_mb", 9999) < 100:
        issues.append("disk")

    # Threads
    report["threads"] = threading.active_count()

    # Determine status
    if len(issues) >= 2 or "disk" in issues:
        report["status"] = "unhealthy"
    elif issues:
        report["status"] = "degraded"

    if issues:
        report["issues"] = issues

    return report


def _format_uptime() -> str:
    """Format uptime."""
    secs = int(time.time() - _start_time)
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m"


def _get_memory_mb() -> float:
    """Get RSS memory in MB."""
    if _resource is not None:
        try:
            usage = _resource.getrusage(_resource.RUSAGE_SELF)
            return round(usage.ru_maxrss / 1024, 1)  # Linux: KB → MB
        except Exception as e:
            log.debug(f"Suppressed: {e}")
    # Fallback: /proc/self/status
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    return 0.0


def _get_disk_info() -> dict:
    """Get disk usage for BASE_DIR."""
    try:
        stat = os.statvfs(str(BASE_DIR))
        return {
            "free_mb": round(stat.f_bavail * stat.f_frsize / (1024 * 1024), 1),
            "total_mb": round(stat.f_blocks * stat.f_frsize / (1024 * 1024), 1),
            "usage_pct": round(100 * (1 - stat.f_bavail / max(stat.f_blocks, 1)), 1),
        }
    except Exception as e:  # noqa: broad-except
        return {}


# Simple LLM status cache (avoid hitting API on every health check)
_llm_status_cache: dict = {}
_llm_status_ts: float = 0.0
_LLM_CHECK_INTERVAL = 60.0  # Re-check every 60s


def _check_llm_status() -> dict:
    """Check LLM availability. Uses circuit breaker status, not live API."""
    global _llm_status_cache, _llm_status_ts
    now = time.time()
    if now - _llm_status_ts < _LLM_CHECK_INTERVAL and _llm_status_cache:
        return _llm_status_cache

    result: dict = {"connected": False}
    try:
        from salmalm.features.stability import health_monitor

        breaker = health_monitor.circuit_breaker.get_status()
        llm_breaker = breaker.get("llm", {})
        if llm_breaker.get("tripped"):
            result["connected"] = False
            result["error"] = llm_breaker.get("last_error", "circuit breaker tripped")
        else:
            # Check if any API key is configured
            from salmalm.security.crypto import vault

            providers = ["anthropic_api_key", "openai_api_key", "xai_api_key", "google_api_key"]
            has_key = any(vault.get(k) for k in providers)
            has_ollama = bool(vault.get("ollama_url"))
            result["connected"] = has_key or has_ollama
            if not result["connected"]:
                result["error"] = "no API keys configured"
    except Exception as e:
        result["error"] = str(e)[:100]

    _llm_status_cache = result
    _llm_status_ts = now
    return result
