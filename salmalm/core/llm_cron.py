"""LLM Cron Manager — scheduled AI tasks with error tracking and auto-disable."""

import json
import time
from datetime import datetime
from typing import Optional

from salmalm.constants import DATA_DIR, KST
from salmalm.security.crypto import log


def _get_heartbeat():
    """Lazy import to avoid circular dependency."""
    from salmalm.core.scheduler import heartbeat  # noqa: PLC0415
    return heartbeat


def _get_usage() -> dict:
    from salmalm.core.core import _usage  # noqa: PLC0415
    return _usage


def _get_tg_bot():
    from salmalm.core.session_store import _tg_bot  # noqa: PLC0415
    return _tg_bot


def _get_sessions() -> dict:
    from salmalm.core.session_store import _sessions  # noqa: PLC0415
    return _sessions


def _write_daily_log(entry: str) -> None:
    try:
        from salmalm.core.core import write_daily_log  # noqa: PLC0415
        write_daily_log(entry)
    except Exception as e:
        log.debug(f"[CRON] write_daily_log failed: {e}")


class LLMCronManager:
    """OpenClaw-style LLM cron with isolated session execution.

    Each cron job runs in its own isolated session (no cross-contamination).
    Completed tasks announce results to configured channels.
    """

    _JOBS_FILE = DATA_DIR / ".cron_jobs.json"  # noqa: F405

    def __init__(self) -> None:
        """Init  ."""
        self.jobs = []

    def load_jobs(self) -> None:
        """Load persisted cron jobs from file."""
        try:
            if self._JOBS_FILE.exists():
                self.jobs = json.loads(self._JOBS_FILE.read_text())
                log.info(f"[CRON] Loaded {len(self.jobs)} LLM cron jobs")
        except Exception as e:
            log.error(f"Failed to load cron jobs: {e}")
            self.jobs = []

    def save_jobs(self) -> None:
        """Persist cron jobs to file."""
        try:
            self._JOBS_FILE.write_text(json.dumps(self.jobs, ensure_ascii=False, indent=2))
        except Exception as e:
            log.error(f"Failed to save cron jobs: {e}")

    def add_job(
        self,
        name: str,
        schedule: dict,
        prompt: str,
        model: Optional[str] = None,
        notify=True,
    ) -> dict:
        """Add a new LLM cron job.
        schedule: {'kind': 'cron', 'expr': '0 6 * * *', 'tz': 'Asia/Seoul'}
                  {'kind': 'every', 'seconds': 3600}
        notify: True/False or dict e.g. {"channel":"telegram","chat_id":"123"}
                  {'kind': 'at', 'time': '2026-02-18T06:00:00+09:00'}
        """
        import uuid as _uuid

        job = {
            "id": str(_uuid.uuid4())[:8],
            "name": name,
            "schedule": schedule,
            "prompt": prompt,
            "model": model,
            "notify": notify,
            "enabled": True,
            "created": datetime.now(KST).isoformat(),  # noqa: F405
            "last_run": None,
            "run_count": 0,
        }
        self.jobs.append(job)
        self.save_jobs()
        log.info(f"[CRON] LLM cron job added: {name} ({job['id']})")
        return job

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled cron job by ID."""
        before = len(self.jobs)
        self.jobs = [j for j in self.jobs if j["id"] != job_id]
        if len(self.jobs) < before:
            self.save_jobs()
            return True
        return False

    @staticmethod
    def _schedule_display(sched: dict) -> str:
        """Human-readable schedule label for UI."""
        if not sched:
            return "—"
        kind = sched.get("kind", "")
        if not kind:
            if "every" in sched:
                kind, sched = "every", {"kind": "every", "seconds": int(sched["every"])}
            elif "expr" in sched:
                kind = "cron"
        if kind == "every":
            s = int(sched.get("seconds", 0))
            if s < 60:
                return f"매 {s}초"
            if s < 3600:
                return f"매 {s // 60}분"
            return f"매 {s // 3600}시간"
        if kind == "cron":
            return sched.get("expr", "cron")
        if kind == "at":
            return sched.get("time", "at")[:16]
        return str(sched)

    def list_jobs(self) -> list:
        """List all registered cron jobs with their schedules."""
        return [
            {
                "id": j["id"],
                "name": j["name"],
                "prompt": j.get("prompt", ""),
                "schedule": j["schedule"],
                "interval": self._schedule_display(j["schedule"]),
                "enabled": j["enabled"],
                "last_run": j["last_run"],
                "run_count": j["run_count"],
            }
            for j in self.jobs
        ]

    def _should_run(self, job: dict) -> bool:
        """Check if a job should run now."""
        if not job["enabled"]:
            return False
        sched = job["schedule"]
        now = datetime.now(KST)  # noqa: F405

        # Normalize legacy/LLM-generated formats: {"every":60} → {"kind":"every","seconds":60}
        if "kind" not in sched:
            if "every" in sched:
                sched = {"kind": "every", "seconds": int(sched["every"])}
                job["schedule"] = sched  # normalize in-place
            elif "expr" in sched:
                sched = {"kind": "cron", "expr": sched["expr"]}
                job["schedule"] = sched

        if sched["kind"] == "every":
            if not job["last_run"]:
                return True
            elapsed = (now - datetime.fromisoformat(job["last_run"])).total_seconds()
            return elapsed >= sched["seconds"]  # type: ignore[no-any-return]

        elif sched["kind"] == "cron":
            # Simple cron: minute hour day month weekday
            expr = sched["expr"].split()
            if len(expr) != 5:
                return False
            checks = [
                (expr[0], now.minute),
                (expr[1], now.hour),
                (expr[2], now.day),
                (expr[3], now.month),
                (expr[4], now.weekday()),  # 0=Monday
            ]
            for field, val in checks:
                if field == "*":
                    continue
                try:
                    if "," in field:
                        if val not in [int(x) for x in field.split(",")]:
                            return False
                    elif "-" in field:
                        lo, hi = field.split("-")
                        if not (int(lo) <= val <= int(hi)):
                            return False
                    elif int(field) != val:
                        return False
                except ValueError:
                    return False
            # Don't run twice in same minute
            if job["last_run"]:
                last = datetime.fromisoformat(job["last_run"])
                if (now - last).total_seconds() < 60:
                    return False
            return True

        elif sched["kind"] == "at":
            target = datetime.fromisoformat(sched["time"])
            # Normalize: make target timezone-aware if now is aware
            if now.tzinfo is not None and target.tzinfo is None:
                target = target.replace(tzinfo=now.tzinfo)
            if job["last_run"]:
                return False  # One-shot, already ran
            return now >= target

        return False

    def _notify_completion(self, job: dict, response: str) -> None:
        """Route cron job completion notification to configured channels."""
        notify_cfg = job.get("notify")
        summary = response[:800] + ("..." if len(response) > 800 else "")
        notify_text = f"⏰ **[크론] {job['name']}**\n\n{summary}"

        # 1. WS broadcast — via notify_ws_via_hook (no direct web.ws import from core)
        try:
            from salmalm.core.core import notify_ws_via_hook
            notify_ws_via_hook("", "cron_result", {
                "job_name": job["name"],
                "text": notify_text,
            })
        except Exception as e:
            log.debug(f"[CRON] WS broadcast failed: {e}")

        # 2. Telegram (if configured)
        if (_tg_bot_:=_get_tg_bot()) and _tg_bot_.token and _tg_bot_.owner_id:
            try:
                _tg_bot_.send_message(_tg_bot_.owner_id, notify_text)
            except Exception as e:
                log.warning(f"[CRON] Telegram notify failed: {e}")

        # 3. Explicit channel override
        if isinstance(notify_cfg, dict):
            self._send_to_channel(notify_cfg, notify_text, job["name"])

        # 4. Fallback: store in web session _notifications (polled every 30s)
        self._store_web_notification(job["name"], response)

    def _send_to_channel(self, notify_cfg: dict, text: str, job_name: str) -> bool:
        """Send notification to a specific channel. Returns True if sent."""
        ch = notify_cfg.get("channel", "")
        try:
            if ch == "telegram":
                chat_id = notify_cfg.get("chat_id", "")
                if chat_id and (_tg_bot_ch:=_get_tg_bot()) and _tg_bot_ch.token:
                    _tg_bot_ch.send_message(chat_id, text)
                    return True
            elif ch == "discord":
                channel_id = notify_cfg.get("channel_id", "")
                if channel_id:
                    import salmalm.channels.discord_bot as _dmod

                    dbot = getattr(_dmod, "_bot", None)
                    if dbot and hasattr(dbot, "send_message"):
                        dbot.send_message(channel_id, text)
                        return True
        except Exception as e:
            log.warning(f"[CRON] Notification routing failed for {job_name}: {e}")
        return False

    def _store_web_notification(self, job_name: str, response: str) -> None:
        """Store notification in web session for UI visibility."""
        # Try namespaced sessions first (web:{uid}), fall back to plain "web"
        web_session = None
        for key, sess in list(_get_sessions().items()):
            if key == "web" or key.startswith("web:"):
                web_session = sess
                break
        if not web_session:
            return
        if not hasattr(web_session, "_notifications"):
            web_session._notifications = []
        web_session._notifications.append({"time": time.time(), "text": f"⏰ Cron [{job_name}]: {response[:200]}"})

    def _handle_cron_failure(self, job: dict, error) -> None:
        """Handle cron job failure: notify owner, auto-disable after 5 failures."""
        error_text = f"⚠️ Cron job failed: {job['name']}\nError: {str(error)[:200]}"
        try:
            if (_tg_bot_err:=_get_tg_bot()) and _tg_bot_err.token and _tg_bot_err.owner_id:
                _tg_bot_err.send_message(_tg_bot_err.owner_id, error_text)
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        if job.get("error_count", 0) >= 5:
            job["enabled"] = False
            self.save_jobs()
            log.warning(f"[CRON] Job {job['name']} disabled after 5 consecutive failures")

    async def tick(self) -> None:
        """Check and execute due jobs. Also runs heartbeat if due."""
        # OpenClaw-style heartbeat check
        try:
            _hb = _get_heartbeat()
            if _hb.should_beat():
                await _hb.beat()
        except Exception as e:
            log.error(f"[HEARTBEAT] Tick error: {e}")

        for job in self.jobs:
            if not self._should_run(job):
                continue
            log.info(f"[CRON] LLM cron firing: {job['name']} ({job['id']})")
            try:
                import asyncio
                from salmalm.core.engine_pipeline import process_message

                # Track cost before/after to enforce per-cron-job cap
                _usage = _get_usage()
                cost_before = _usage.get("total_cost", 0)
                now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z")  # noqa: F405
                response = await asyncio.wait_for(
                    process_message(
                        f"cron-{job['id']}-{int(time.time()*1000)}",
                        job["prompt"],
                        model_override=job.get("model"),
                        system_suffix=f"[크론 작업] 현재 정확한 시각: {now_str}. 반드시 텍스트로만 응답하시오. TTS·음성·이미지 생성 도구는 절대 사용하지 마시오.",
                    ),
                    timeout=300,
                )
                cost_after = _get_usage().get("total_cost", 0)
                cron_cost = cost_after - cost_before
                MAX_CRON_JOB_COST = 2.0  # $2 max per cron execution
                if cron_cost > MAX_CRON_JOB_COST:
                    log.warning(f"[CRON] Job {job['name']} cost ${cron_cost:.2f} — exceeds ${MAX_CRON_JOB_COST} cap")
                job["last_run"] = datetime.now(KST).isoformat()  # noqa: F405
                job["run_count"] = job.get("run_count", 0) + 1
                job["error_count"] = 0  # Reset on success
                job.pop("last_error", None)
                self.save_jobs()
                log.info(f"[CRON] Cron completed: {job['name']} ({len(response)} chars)")

                self._notify_completion(job, response)
                _write_daily_log(f"[CRON] {job['name']}: {response[:150]}")
                if job["schedule"]["kind"] == "at":
                    job["enabled"] = False
                    self.save_jobs()

            except Exception as e:
                log.error(f"LLM cron error ({job['name']}): {e}")
                job["last_run"] = datetime.now(KST).isoformat()  # noqa: F405
                job["last_error"] = str(e)[:200]
                job["error_count"] = job.get("error_count", 0) + 1
                self.save_jobs()

                self._handle_cron_failure(job, e)


# ============================================================
# PLUGIN LOADER — Auto-load tools from plugins/ directory
