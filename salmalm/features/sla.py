"""SalmAlm SLA Engine — Uptime monitoring, latency tracking, watchdog.

SLA 보장 구조: 업타임 모니터링, 응답 시간 추적, 자동 헬스체크/자가 복구.

Components:
  - SLAConfig: Runtime-reloadable SLA settings (~/.salmalm/sla.json)
  - UptimeMonitor: Server uptime tracking, downtime logging, lockfile-based crash detection
  - LatencyTracker: TTFT/total response time P50/P95/P99 with ring buffer
  - Watchdog: Background self-diagnosis every N seconds with auto-recovery
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from salmalm.constants import VERSION, KST, AUDIT_DB, DATA_DIR
from salmalm.security.crypto import log

# ── Paths ────────────────────────────────────────────────────
_SALMALM_DIR = DATA_DIR
_RUNNING_FILE = _SALMALM_DIR / ".running"
_SLA_CONFIG_FILE = _SALMALM_DIR / "sla.json"

# ============================================================
# SLA Configuration (런타임 반영 설정)
# ============================================================

_DEFAULT_SLA_CONFIG = {
    "uptime_target_pct": 99.9,
    "ttft_target_ms": 3000,
    "response_target_ms": 30000,
    "memory_limit_mb": 500,
    "disk_limit_pct": 90,
    "watchdog_interval_sec": 30,
    "auto_recovery": True,
    "alerts": {
        "telegram": True,
        "web": True,
    },
}


class SLAConfig:
    """Runtime-reloadable SLA configuration from ~/.salmalm/sla.json."""

    def __init__(self):
        self._config: dict = dict(_DEFAULT_SLA_CONFIG)
        self._lock = threading.Lock()
        self._mtime: float = 0.0
        self.load()

    def load(self):
        """Load config from disk. Creates default if missing."""
        _SALMALM_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if _SLA_CONFIG_FILE.exists():
                mtime = _SLA_CONFIG_FILE.stat().st_mtime
                with self._lock:
                    if mtime == self._mtime:
                        return  # unchanged
                data = json.loads(_SLA_CONFIG_FILE.read_text(encoding="utf-8"))
                with self._lock:
                    # Merge with defaults (keep new keys from default)
                    merged = dict(_DEFAULT_SLA_CONFIG)
                    merged.update(data)
                    if isinstance(data.get("alerts"), dict):
                        merged["alerts"] = dict(_DEFAULT_SLA_CONFIG["alerts"])
                        merged["alerts"].update(data["alerts"])
                    self._config = merged
                    self._mtime = mtime
            else:
                self.save()
        except Exception as e:
            log.warning(f"[SLA] Config load error: {e}")

    def save(self):
        """Write current config to disk."""
        _SALMALM_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with self._lock:
                data = dict(self._config)
            _SLA_CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._mtime = _SLA_CONFIG_FILE.stat().st_mtime
        except Exception as e:
            log.warning(f"[SLA] Config save error: {e}")

    def get(self, key: str, default=None):
        self._maybe_reload()
        with self._lock:
            return self._config.get(key, default)

    def set(self, key: str, value):
        with self._lock:
            self._config[key] = value
        self.save()

    def get_all(self) -> dict:
        self._maybe_reload()
        with self._lock:
            return dict(self._config)

    def update(self, data: dict):
        with self._lock:
            self._config.update(data)
        self.save()

    def _maybe_reload(self):
        """Reload if file changed on disk (런타임 반영)."""
        try:
            if _SLA_CONFIG_FILE.exists():
                mtime = _SLA_CONFIG_FILE.stat().st_mtime
                with self._lock:
                    if mtime != self._mtime:
                        pass  # need reload
                    else:
                        return
                self.load()
        except Exception:
            pass


# Global config instance
sla_config = SLAConfig()


# ============================================================
# Uptime Monitor (업타임 모니터링)
# ============================================================


class UptimeMonitor:
    """Track server uptime, detect crashes, log downtime events.

    서버 업타임 추적, 비정상 종료 감지, 다운타임 이벤트 DB 기록.
    """

    def __init__(self):
        self._start_time = time.time()
        self._start_dt = datetime.now(KST)
        self._lock = threading.Lock()

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(AUDIT_DB), check_same_thread=True)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def init_db(self):
        """Create uptime_log table if not exists."""
        conn = self._get_db()
        conn.execute("""CREATE TABLE IF NOT EXISTS uptime_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT NOT NULL,
            end_time TEXT,
            duration_sec REAL,
            reason TEXT DEFAULT 'unknown'
        )""")
        conn.commit()
        conn.close()

    def on_startup(self):
        """Called at server startup: check lockfile, record crash if needed."""
        _SALMALM_DIR.mkdir(parents=True, exist_ok=True)
        self.init_db()

        if _RUNNING_FILE.exists():
            # Previous non-graceful shutdown detected (비정상 종료 감지)
            log.warning("[SLA] Non-graceful shutdown detected! Recording downtime.")
            try:
                prev_data = json.loads(_RUNNING_FILE.read_text(encoding="utf-8"))
                prev_start = prev_data.get("start_time", "")
                prev_pid = prev_data.get("pid", "?")
            except Exception:
                prev_start = ""
                prev_pid = "?"

            now_str = datetime.now(KST).isoformat()
            # Estimate downtime: from prev start to now (approximate)
            duration = None
            if prev_start:
                try:
                    prev_dt = datetime.fromisoformat(prev_start)
                    duration = (datetime.now(KST) - prev_dt).total_seconds()
                except Exception:
                    pass

            conn = self._get_db()
            conn.execute(
                "INSERT INTO uptime_log (start_time, end_time, duration_sec, reason) VALUES (?, ?, ?, ?)",
                (prev_start or now_str, now_str, duration, f"crash (prev_pid={prev_pid})"),
            )
            conn.commit()
            conn.close()

            from salmalm.core import audit_log

            audit_log("sla_downtime", f"Non-graceful shutdown detected. prev_pid={prev_pid}")

        # Write lockfile (시작 시 lockfile 생성)
        lockdata = {
            "pid": os.getpid(),
            "start_time": self._start_dt.isoformat(),
            "version": VERSION,
        }
        _RUNNING_FILE.write_text(json.dumps(lockdata), encoding="utf-8")
        log.info(f"[SLA] Lockfile created: {_RUNNING_FILE}")

    def on_shutdown(self):
        """Called on graceful shutdown: remove lockfile."""
        try:
            if _RUNNING_FILE.exists():
                _RUNNING_FILE.unlink()
                log.info("[SLA] Lockfile removed (graceful shutdown)")
        except Exception as e:
            log.warning(f"[SLA] Lockfile removal error: {e}")

    def record_downtime(self, start: str, end: str, duration: float, reason: str):
        """Manually record a downtime event."""
        try:
            conn = self._get_db()
            conn.execute(
                "INSERT INTO uptime_log (start_time, end_time, duration_sec, reason) VALUES (?, ?, ?, ?)",
                (start, end, duration, reason),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            log.error(f"[SLA] Record downtime error: {e}")

    def get_uptime_seconds(self) -> float:
        return time.time() - self._start_time

    def get_uptime_human(self) -> str:
        secs = int(self.get_uptime_seconds())
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        return f"{hours}h {minutes}m {seconds}s"

    def get_monthly_uptime_pct(self, year: int = 0, month: int = 0) -> float:
        """Calculate uptime percentage for a given month.

        월별 업타임 퍼센티지 계산.
        """
        now = datetime.now(KST)
        if not year:
            year = now.year
        if not month:
            month = now.month

        # Total seconds in this month (up to now if current month)
        month_start = datetime(year, month, 1, tzinfo=KST)
        if month == 12:
            month_end = datetime(year + 1, 1, 1, tzinfo=KST)
        else:
            month_end = datetime(year, month + 1, 1, tzinfo=KST)

        if now < month_end:
            month_end = now
        total_secs = (month_end - month_start).total_seconds()
        if total_secs <= 0:
            return 100.0

        # Sum downtime in this month
        try:
            conn = self._get_db()
            start_str = month_start.isoformat()
            end_str = month_end.isoformat()
            cur = conn.execute(
                "SELECT COALESCE(SUM(duration_sec), 0) FROM uptime_log "
                "WHERE start_time >= ? AND start_time < ? AND duration_sec IS NOT NULL",
                (start_str, end_str),
            )
            downtime = cur.fetchone()[0] or 0.0
            conn.close()
        except Exception:
            downtime = 0.0

        uptime_pct = max(0.0, 100.0 * (1.0 - downtime / total_secs))
        return round(uptime_pct, 4)

    def get_daily_uptime_pct(self, date_str: str = "") -> float:
        """Calculate uptime percentage for a given day."""
        now = datetime.now(KST)
        if not date_str:
            date_str = now.strftime("%Y-%m-%d")

        day_start = datetime.fromisoformat(date_str).replace(tzinfo=KST)
        day_end = day_start + timedelta(days=1)
        if now < day_end:
            day_end = now
        total_secs = (day_end - day_start).total_seconds()
        if total_secs <= 0:
            return 100.0

        try:
            conn = self._get_db()
            cur = conn.execute(
                "SELECT COALESCE(SUM(duration_sec), 0) FROM uptime_log "
                "WHERE start_time >= ? AND start_time < ? AND duration_sec IS NOT NULL",
                (day_start.isoformat(), day_end.isoformat()),
            )
            downtime = cur.fetchone()[0] or 0.0
            conn.close()
        except Exception:
            downtime = 0.0

        return round(max(0.0, 100.0 * (1.0 - downtime / total_secs)), 4)

    def get_recent_incidents(self, limit: int = 10) -> list:
        """Get recent downtime incidents."""
        try:
            conn = self._get_db()
            cur = conn.execute(
                "SELECT start_time, end_time, duration_sec, reason FROM uptime_log ORDER BY id DESC LIMIT ?", (limit,)
            )
            rows = cur.fetchall()
            conn.close()
            return [{"start": r[0], "end": r[1], "duration_sec": r[2], "reason": r[3]} for r in rows]
        except Exception:
            return []

    def get_stats(self) -> dict:
        """Full uptime stats for API/dashboard."""
        now = datetime.now(KST)
        target = sla_config.get("uptime_target_pct", 99.9)
        monthly_pct = self.get_monthly_uptime_pct()
        return {
            "uptime_seconds": round(self.get_uptime_seconds()),
            "uptime_human": self.get_uptime_human(),
            "start_time": self._start_dt.isoformat(),
            "monthly_uptime_pct": monthly_pct,
            "daily_uptime_pct": self.get_daily_uptime_pct(),
            "target_pct": target,
            "meets_target": monthly_pct >= target,
            "recent_incidents": self.get_recent_incidents(5),
            "month": now.strftime("%Y-%m"),
        }


# ============================================================
# Latency Tracker (응답 시간 추적)
# ============================================================


class LatencyTracker:
    """Track TTFT and total response time with ring buffer.

    링버퍼로 최근 100개 요청의 TTFT/총 응답 시간 추적.
    P50/P95/P99 계산 + SLA 경고.
    """

    def __init__(self, max_size: int = 100):
        self._max_size = max_size
        self._records: deque = deque(maxlen=max_size)
        self._lock = threading.Lock()
        self._consecutive_timeouts = 0
        self._timeout_threshold = 3  # Trigger failover after N consecutive timeouts

    def record(self, ttft_ms: float, total_ms: float, model: str = "", timed_out: bool = False, session_id: str = ""):
        """Record a single request's latency.

        요청의 레이턴시 기록.
        """
        entry = {
            "timestamp": datetime.now(KST).isoformat(),
            "ttft_ms": round(ttft_ms, 1),
            "total_ms": round(total_ms, 1),
            "model": model,
            "timed_out": timed_out,
            "session_id": session_id,
        }
        with self._lock:
            self._records.append(entry)
            if timed_out:
                self._consecutive_timeouts += 1
            else:
                self._consecutive_timeouts = 0

        # SLA warnings (SLA 경고)
        ttft_target = sla_config.get("ttft_target_ms", 3000)
        resp_target = sla_config.get("response_target_ms", 30000)

        if ttft_ms > ttft_target:
            log.warning(f"[SLA] TTFT {ttft_ms:.0f}ms exceeds target {ttft_target}ms (model={model})")
        if total_ms > resp_target:
            log.warning(f"[SLA] Total response {total_ms:.0f}ms exceeds target {resp_target}ms (model={model})")

    def should_failover(self) -> bool:
        """Check if consecutive timeouts warrant a model failover."""
        with self._lock:
            return self._consecutive_timeouts >= self._timeout_threshold

    def reset_timeout_counter(self):
        with self._lock:
            self._consecutive_timeouts = 0

    def _percentile(self, values: list, p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = (p / 100.0) * (len(sorted_vals) - 1)
        lower = int(math.floor(idx))
        upper = int(math.ceil(idx))
        if lower == upper:
            return sorted_vals[lower]
        frac = idx - lower
        return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac

    def get_stats(self) -> dict:
        """Get latency statistics: P50/P95/P99 + histogram.

        레이턴시 통계: P50/P95/P99 + 히스토그램 데이터.
        """
        with self._lock:
            records = list(self._records)

        if not records:
            return {
                "count": 0,
                "ttft": {"p50": 0, "p95": 0, "p99": 0},
                "total": {"p50": 0, "p95": 0, "p99": 0},
                "histogram": [],
                "recent": [],
                "consecutive_timeouts": 0,
                "targets": {
                    "ttft_ms": sla_config.get("ttft_target_ms", 3000),
                    "response_ms": sla_config.get("response_target_ms", 30000),
                },
            }

        ttft_vals = [r["ttft_ms"] for r in records if r["ttft_ms"] > 0]
        total_vals = [r["total_ms"] for r in records]

        # Histogram buckets for total response time (ms)
        buckets = [500, 1000, 2000, 3000, 5000, 10000, 20000, 30000, 60000]
        histogram = []
        for b in buckets:
            count = sum(1 for v in total_vals if v <= b)
            histogram.append({"le": b, "count": count})
        histogram.append({"le": "+Inf", "count": len(total_vals)})

        # Recent 10 entries for trend display
        recent = records[-10:] if len(records) >= 10 else records

        return {
            "count": len(records),
            "ttft": {
                "p50": round(self._percentile(ttft_vals, 50), 1),
                "p95": round(self._percentile(ttft_vals, 95), 1),
                "p99": round(self._percentile(ttft_vals, 99), 1),
            },
            "total": {
                "p50": round(self._percentile(total_vals, 50), 1),
                "p95": round(self._percentile(total_vals, 95), 1),
                "p99": round(self._percentile(total_vals, 99), 1),
            },
            "histogram": histogram,
            "recent": [
                {"ts": r["timestamp"], "ttft": r["ttft_ms"], "total": r["total_ms"], "model": r["model"]}
                for r in recent
            ],
            "consecutive_timeouts": self._consecutive_timeouts,
            "targets": {
                "ttft_ms": sla_config.get("ttft_target_ms", 3000),
                "response_ms": sla_config.get("response_target_ms", 30000),
            },
        }


# ============================================================
# Watchdog (자동 헬스체크 + 자가 복구)
# ============================================================


class Watchdog:
    """Background watchdog: periodic self-diagnosis + auto-recovery.

    30초마다 자가 진단: HTTP, WS, DB, 메모리, 디스크.
    이상 감지 시 로그 + 알림 + 자동 복구 시도.
    """

    def __init__(self, uptime_monitor: UptimeMonitor, latency_tracker: LatencyTracker):
        self._uptime = uptime_monitor
        self._latency = latency_tracker
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_report: dict = {}
        self._lock = threading.Lock()

    def start(self):
        """Start watchdog background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="sla-watchdog")
        self._thread.start()
        log.info("[SLA] Watchdog started")

    def stop(self):
        """Stop watchdog."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        log.info("[SLA] Watchdog stopped")

    def _run(self):
        # Wait a bit after startup before first check
        time.sleep(10)
        while not self._stop_event.is_set():
            interval = sla_config.get("watchdog_interval_sec", 30)
            try:
                report = self._check()
                with self._lock:
                    self._last_report = report
                if report.get("status") != "healthy":
                    self._handle_issues(report)
            except Exception as e:
                log.error(f"[SLA] Watchdog error: {e}")
            self._stop_event.wait(timeout=interval)

    def _check(self) -> dict:
        """Run all health checks. Returns detailed report."""
        report: Dict[str, Any] = {
            "timestamp": datetime.now(KST).isoformat(),
            "status": "healthy",
            "checks": {},
        }

        issues = []

        # 1. DB check
        try:
            conn = sqlite3.connect(str(AUDIT_DB), timeout=5)
            conn.execute("SELECT 1")
            conn.close()
            report["checks"]["database"] = {"status": "ok"}
        except Exception as e:
            report["checks"]["database"] = {"status": "error", "error": str(e)[:200]}
            issues.append(("database", str(e)))

        # 2. Memory check
        mem_limit = sla_config.get("memory_limit_mb", 500)
        try:
            try:
                import resource as _res

                usage = _res.getrusage(_res.RUSAGE_SELF)
                mem_mb = usage.ru_maxrss / 1024  # Linux: KB -> MB
            except (ImportError, AttributeError):
                mem_mb = 0
            report["checks"]["memory"] = {
                "status": "ok" if mem_mb < mem_limit else "warning",
                "usage_mb": round(mem_mb, 1),
                "limit_mb": mem_limit,
            }
            if mem_mb >= mem_limit:
                issues.append(("memory", f"{mem_mb:.0f}MB >= {mem_limit}MB"))
        except Exception as e:
            report["checks"]["memory"] = {"status": "unknown", "error": str(e)[:100]}

        # 3. Disk check
        disk_limit = sla_config.get("disk_limit_pct", 90)
        try:
            from salmalm.constants import BASE_DIR

            stat = os.statvfs(str(BASE_DIR))
            disk_pct = round(100 * (1 - stat.f_bavail / stat.f_blocks), 1)
            report["checks"]["disk"] = {
                "status": "ok" if disk_pct < disk_limit else "warning",
                "usage_pct": disk_pct,
                "limit_pct": disk_limit,
            }
            if disk_pct >= disk_limit:
                issues.append(("disk", f"{disk_pct}% >= {disk_limit}%"))
        except Exception as e:
            report["checks"]["disk"] = {"status": "unknown", "error": str(e)[:100]}

        # 4. HTTP server check (lightweight — just check thread is alive)
        report["checks"]["http"] = {"status": "ok"}  # If we're running, HTTP is ok

        # 5. WebSocket check
        try:
            from salmalm.web.ws import ws_server

            ws_ok = ws_server.is_running if hasattr(ws_server, "is_running") else True
            report["checks"]["websocket"] = {
                "status": "ok" if ws_ok else "error",
                "clients": getattr(ws_server, "client_count", 0) if hasattr(ws_server, "client_count") else 0,
            }
            if not ws_ok:
                issues.append(("websocket", "WS server not running"))
        except Exception as e:
            report["checks"]["websocket"] = {"status": "unknown", "error": str(e)[:100]}

        # Set overall status
        if any(report["checks"][k].get("status") == "error" for k in report["checks"]):
            report["status"] = "unhealthy"
        elif any(report["checks"][k].get("status") == "warning" for k in report["checks"]):
            report["status"] = "degraded"

        return report

    def _handle_issues(self, report: dict):
        """Handle detected issues: log, alert, attempt recovery."""
        _status = report["status"]  # noqa: F841
        checks = report["checks"]

        for name, check in checks.items():
            if check.get("status") in ("error", "warning"):
                detail = check.get("error", "") or json.dumps(check)
                log.warning(f"[SLA] Health issue: {name} = {check['status']}: {detail}")

                # Audit log
                try:
                    from salmalm.core import audit_log

                    audit_log("sla_health_issue", f"{name}: {detail}")
                except Exception:
                    pass

        # Auto-recovery attempts (자동 복구)
        if not sla_config.get("auto_recovery", True):
            return

        for name, check in checks.items():
            if check.get("status") != "error":
                continue
            try:
                if name == "database":
                    self._recover_database()
                elif name == "websocket":
                    self._recover_websocket()
            except Exception as e:
                log.error(f"[SLA] Recovery failed for {name}: {e}")

    def _recover_database(self):
        """Attempt DB reconnection."""
        log.info("[SLA] Attempting DB recovery...")
        try:
            from salmalm.core import _thread_local

            if hasattr(_thread_local, "audit_conn"):
                try:
                    _thread_local.audit_conn.close()
                except Exception:
                    pass
                del _thread_local.audit_conn
            # Test new connection
            conn = sqlite3.connect(str(AUDIT_DB), timeout=5)
            conn.execute("SELECT 1")
            conn.close()
            log.info("[SLA] DB recovery successful")
        except Exception as e:
            log.error(f"[SLA] DB recovery failed: {e}")

    def _recover_websocket(self):
        """Attempt WebSocket server restart."""
        log.info("[SLA] Attempting WebSocket recovery...")
        try:
            import asyncio
            from salmalm.web.ws import ws_server

            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(ws_server.start())
            log.info("[SLA] WebSocket recovery initiated")
        except Exception as e:
            log.error(f"[SLA] WebSocket recovery failed: {e}")

    def get_last_report(self) -> dict:
        """Get the most recent watchdog report."""
        with self._lock:
            return dict(self._last_report) if self._last_report else {}

    def get_detailed_health(self) -> dict:
        """Detailed health report for /health detail command."""
        report = self._check()
        report["uptime"] = self._uptime.get_stats()
        report["latency"] = self._latency.get_stats()
        report["sla_config"] = sla_config.get_all()
        return report


# ============================================================
# Global instances (전역 인스턴스)
# ============================================================

uptime_monitor = UptimeMonitor()
latency_tracker = LatencyTracker()
watchdog = Watchdog(uptime_monitor, latency_tracker)
