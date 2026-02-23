"""LLM Cron Manager — scheduled AI tasks with error tracking and auto-disable."""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from salmalm.constants import BASE_DIR, DATA_DIR, KST, MEMORY_DIR
from salmalm.security.crypto import vault, log

class LLMCronManager:
    """OpenClaw-style LLM cron with isolated session execution.

    Each cron job runs in its own isolated session (no cross-contamination).
    Completed tasks announce results to configured channels.
    """

    _JOBS_FILE = BASE_DIR / ".cron_jobs.json"  # noqa: F405

    def __init__(self):
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

    def list_jobs(self) -> list:
        """List all registered cron jobs with their schedules."""
        return [
            {
                "id": j["id"],
                "name": j["name"],
                "schedule": j["schedule"],
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
            if job["last_run"]:
                return False  # One-shot, already ran
            return now >= target

        return False

    async def tick(self) -> None:
        """Check and execute due jobs. Also runs heartbeat if due."""
        # OpenClaw-style heartbeat check
        if heartbeat.should_beat():
            try:
                await heartbeat.beat()
            except Exception as e:
                log.error(f"[HEARTBEAT] Tick error: {e}")

        for job in self.jobs:
            if not self._should_run(job):
                continue
            log.info(f"[CRON] LLM cron firing: {job['name']} ({job['id']})")
            try:
                from salmalm.core.engine import process_message

                # Track cost before/after to enforce per-cron-job cap
                cost_before = _usage["total_cost"]
                response = await process_message(f"cron-{job['id']}", job["prompt"], model_override=job.get("model"))
                cost_after = _usage["total_cost"]
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

                # Notification routing
                notify_cfg = job.get("notify")
                notified = False
                summary = response[:800] + ("..." if len(response) > 800 else "")
                notify_text = f"⏰ SalmAlm scheduled task completed: {job['name']}\n\n{summary}"

                if isinstance(notify_cfg, dict):
                    ch = notify_cfg.get("channel", "")
                    try:
                        if ch == "telegram":
                            chat_id = notify_cfg.get("chat_id", "")
                            if chat_id and _tg_bot and _tg_bot.token:
                                _tg_bot.send_message(chat_id, notify_text)
                                notified = True
                        elif ch == "discord":
                            channel_id = notify_cfg.get("channel_id", "")
                            if channel_id:
                                try:
                                    import salmalm.channels.discord_bot as _dmod

                                    dbot = getattr(_dmod, "_bot", None)
                                    if dbot and hasattr(dbot, "send_message"):
                                        dbot.send_message(channel_id, notify_text)
                                        notified = True
                                except Exception as e:
                                    log.debug(f"Suppressed: {e}")
                    except Exception as e:
                        log.warning(f"[CRON] Notification routing failed for {job['name']}: {e}")
                elif notify_cfg:
                    if _tg_bot and _tg_bot.token and _tg_bot.owner_id:
                        try:
                            _tg_bot.send_message(_tg_bot.owner_id, notify_text)
                            notified = True
                        except Exception as e:
                            log.warning(f"[CRON] Telegram notify failed: {e}")

                # Fallback to web notification on failure, or always store for UI
                if notify_cfg:
                    web_session = _sessions.get("web")
                    if web_session:
                        if not notified or True:  # Always store in web for visibility
                            if not hasattr(web_session, "_notifications"):
                                web_session._notifications = []
                            web_session._notifications.append(
                                {
                                    "time": time.time(),
                                    "text": f"⏰ Cron [{job['name']}]: {response[:200]}",
                                }
                            )

                # Log to daily memory
                write_daily_log(f"[CRON] {job['name']}: {response[:150]}")

                # One-shot jobs: auto-disable
                if job["schedule"]["kind"] == "at":
                    job["enabled"] = False
                    self.save_jobs()

            except Exception as e:
                log.error(f"LLM cron error ({job['name']}): {e}")
                job["last_run"] = datetime.now(KST).isoformat()  # noqa: F405
                job["last_error"] = str(e)[:200]
                job["error_count"] = job.get("error_count", 0) + 1
                self.save_jobs()

                # Notify owner about cron failure
                error_text = f"⚠️ Cron job failed: {job['name']}\nError: {str(e)[:200]}"
                try:
                    if _tg_bot and _tg_bot.token and _tg_bot.owner_id:
                        _tg_bot.send_message(_tg_bot.owner_id, error_text)
                except Exception as e:
                    log.debug(f"Suppressed: {e}")

                # Auto-disable after 5 consecutive failures
                if job.get("error_count", 0) >= 5:
                    job["enabled"] = False
                    self.save_jobs()
                    log.warning(f"[CRON] Job {job['name']} disabled after 5 consecutive failures")


# ============================================================
# PLUGIN LOADER — Auto-load tools from plugins/ directory
