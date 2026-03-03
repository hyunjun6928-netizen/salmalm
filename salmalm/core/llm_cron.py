"""LLM Cron Manager — scheduled AI tasks with error tracking and auto-disable."""

import json
import time
from datetime import datetime
from typing import Optional

from salmalm.constants import BASE_DIR, KST
from salmalm.config.paths import DATA_DIR as _CRON_DATA_DIR
from salmalm.security.crypto import log



def _get_tg_bot():
    try:
        from salmalm.core import _tg_bot as _b
        return _b
    except Exception:
        pass
    try:
        from salmalm.features.channels import _tg_bot as _b2
        return _b2
    except Exception:
        return None

class LLMCronManager:
    """OpenClaw-style LLM cron with isolated session execution.

    Each cron job runs in its own isolated session (no cross-contamination).
    Completed tasks announce results to configured channels.
    """

    _JOBS_FILE = _CRON_DATA_DIR / ".cron_jobs.json"  # noqa: F405

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

    def list_jobs(self) -> list:
        """List all registered cron jobs with their schedules."""
        return [
            {
                "id": j["id"],
                "name": j["name"],
                "prompt": j.get("prompt", ""),
                "schedule": j["schedule"],
                "enabled": j["enabled"],
                "last_run": j["last_run"],
                "run_count": j.get("run_count", 0),
                "error_count": j.get("error_count", 0),
                "last_result": j.get("last_result", ""),
                "last_error": j.get("last_error"),
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

    def _notify_completion(self, job: dict, response: str) -> None:
        """Route cron job completion notification to configured channels."""
        notify_cfg = job.get("notify")
        if not notify_cfg:
            return
        summary = response[:800] + ("..." if len(response) > 800 else "")
        notify_text = f"⏰ SalmAlm scheduled task completed: {job['name']}\n\n{summary}"
        notified = False
        if isinstance(notify_cfg, dict):
            notified = self._send_to_channel(notify_cfg, notify_text, job["name"])
        elif (_tb := _get_tg_bot()) and _tb.token and _tb.owner_id:
            try:
                _tb.send_message(_tb.owner_id, notify_text)
                notified = True
            except Exception as e:
                log.warning(f"[CRON] Telegram notify failed: {e}")
        # Always store in web for visibility
        self._store_web_notification(job["name"], response)

    def _send_to_channel(self, notify_cfg: dict, text: str, job_name: str) -> bool:
        """Send notification to a specific channel. Returns True if sent."""
        ch = notify_cfg.get("channel", "")
        try:
            if ch == "telegram":
                chat_id = notify_cfg.get("chat_id", "")
                if chat_id and (_tb2 := _get_tg_bot()) and _tb2.token:
                    _tb2.send_message(chat_id, text)
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
        try:
            from salmalm.core import get_session as _gs
            web_session = _gs("web")
        except Exception:
            web_session = None
        if not web_session:
            return
        if not hasattr(web_session, "_notifications"):
            web_session._notifications = []
        web_session._notifications.append({"time": time.time(), "text": f"⏰ Cron [{job_name}]: {response[:200]}"})
        if len(web_session._notifications) > 200:
            web_session._notifications = web_session._notifications[-200:]

    def _handle_cron_failure(self, job: dict, error) -> None:
        """Handle cron job failure: notify owner, auto-disable after 5 failures."""
        error_text = f"⚠️ Cron job failed: {job['name']}\nError: {str(error)[:200]}"
        try:
            if (_tb3 := _get_tg_bot()) and _tb3.token and _tb3.owner_id:
                _tb3.send_message(_tb3.owner_id, error_text)
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        if job.get("error_count", 0) >= 5:
            job["enabled"] = False
            self.save_jobs()
            log.warning(f"[CRON] Job {job['name']} disabled after 5 consecutive failures")

    # Main asyncio event loop — captured by tick() on first async call so that
    # _execute_job (which runs in a daemon thread) can dispatch coroutines onto it.
    _main_loop = None

    def _execute_job(self, job: dict) -> None:
        """Execute a single cron job synchronously (runs in a background thread).

        Called from web_cron._post_api_cron_run via threading.Thread so it must
        be a plain (non-async) method.  Dispatches onto the captured main loop
        via run_coroutine_threadsafe so all async resources (DB, sessions, etc.)
        are accessed from the correct event loop.
        """
        import asyncio as _asyncio_cron

        async def _run():
            from salmalm.core.engine import process_message

            log.info(f"[CRON] Manual run: {job['name']} ({job['id']})")
            try:
                from salmalm.features.edge_cases import _usage as _u
                cost_before = _u.get("total_cost", 0)
            except Exception:
                cost_before = 0
            try:
                response = await process_message(
                    f"cron-{job['id']}", job["prompt"], model_override=job.get("model")
                )
                try:
                    from salmalm.features.edge_cases import _usage as _u2
                    cron_cost = _u2.get("total_cost", 0) - cost_before
                    MAX_CRON_JOB_COST = 2.0
                    if cron_cost > MAX_CRON_JOB_COST:
                        log.warning(f"[CRON] Job {job['name']} cost ${cron_cost:.2f} — exceeds ${MAX_CRON_JOB_COST} cap")
                except Exception:
                    pass
                job["last_run"] = datetime.now(KST).isoformat()  # noqa: F405
                job["run_count"] = job.get("run_count", 0) + 1
                job["error_count"] = 0
                job["last_result"] = response[:120] if response else ""
                job.pop("last_error", None)
                self.save_jobs()
                log.info(f"[CRON] Cron completed: {job['name']} ({len(response)} chars)")
                self._notify_completion(job, response)
                # Push result to web chat session + WS broadcast
                try:
                    from salmalm.core.session_store import get_session as _gs
                    _web_sess = _gs("web")
                    _cron_msg = f"⏰ **[크론]** `{job['name']}`\n\n{response}"
                    _web_sess.add_assistant(_cron_msg)
                    _cloop = LLMCronManager._main_loop
                    if _cloop and _cloop.is_running():
                        import asyncio as _aio2
                        from salmalm.web.ws import ws_server as _ws
                        async def _push():
                            await _ws.broadcast({
                                "type": "chat",
                                "role": "assistant",
                                "content": _cron_msg,
                                "session": "web",
                                "source": "cron",
                            })
                        _aio2.run_coroutine_threadsafe(_push(), _cloop)
                        log.debug(f"[CRON] WS push queued for '{job['name']}'")
                except Exception as _pe:
                    log.debug(f"[CRON] Web push failed: {_pe}")
                try:
                    from salmalm.core.memory import write_daily_log as _wdl; _wdl(f"[CRON] {job['name']}: {response[:150]}")
                except Exception: pass
                if job["schedule"]["kind"] == "at":
                    job["enabled"] = False
                    self.save_jobs()
            except Exception as e:
                log.error(f"[CRON] cron error ({job['name']}): {e}", exc_info=True)
                job["last_run"] = datetime.now(KST).isoformat()  # noqa: F405
                job["last_error"] = str(e)[:200]
                job["error_count"] = job.get("error_count", 0) + 1
                self.save_jobs()
                self._handle_cron_failure(job, e)

        loop = LLMCronManager._main_loop
        if loop and loop.is_running():
            try:
                fut = _asyncio_cron.run_coroutine_threadsafe(_run(), loop)
                fut.result(timeout=300)
                return
            except Exception as _e:
                log.error(f"[CRON] run_coroutine_threadsafe failed: {_e}", exc_info=True)
                return
        # Fallback: no main loop captured yet — spin a fresh loop (limited functionality)
        log.warning(f"[CRON] Main loop not captured; running {job['name']} in isolated loop")
        _loop = _asyncio_cron.new_event_loop()
        try:
            _loop.run_until_complete(_run())
        finally:
            _loop.close()

    async def tick(self) -> None:
        """Check and execute due jobs. Also runs heartbeat if due."""
        # Capture running event loop so _execute_job (daemon thread) can dispatch onto it
        import asyncio as _aio_tick
        try:
            LLMCronManager._main_loop = _aio_tick.get_running_loop()
        except RuntimeError:
            pass

        # OpenClaw-style heartbeat check
        try:
            from salmalm.core import heartbeat as _hb
            if _hb.should_beat():
                try:
                    await _hb.beat()
                except Exception as e:
                    log.error(f"[HEARTBEAT] Tick error: {e}")
        except Exception: pass

        for job in self.jobs:
            if not self._should_run(job):
                continue
            log.info(f"[CRON] LLM cron firing: {job['name']} ({job['id']})")
            try:
                from salmalm.core.engine import process_message

                # Track cost before/after to enforce per-cron-job cap
                try:
                    from salmalm.features.edge_cases import _usage as _u_tick
                    cost_before = _u_tick.get("total_cost", 0)
                except Exception:
                    cost_before = 0
                # Fresh session per run — clears orphan tool_calls from prior runs
                _cron_sid = f"cron-{job['id']}"
                try:
                    from salmalm.core.core import get_session as _gs_cron
                    _cs = _gs_cron(_cron_sid)
                    _cs.messages = [m for m in _cs.messages if m.get("role") == "system"]
                except Exception:
                    pass
                _cron_prompt = (
                    "[SYSTEM] You are a cron job executor. Rules:\n"
                    "1. ALWAYS use tools for real-time data (time, files, web). NEVER guess or estimate.\n"
                    "2. For current time: python_eval with: import datetime; kst=datetime.timezone(datetime.timedelta(hours=9)); _result=datetime.datetime.now(kst).strftime('%Y-%m-%d %H:%M:%S KST')\n"
                    "3. Return ONLY the tool result as your final answer. No apologies, no explanations.\n"
                    "[TASK] " + job["prompt"]
                )
                response = await process_message(_cron_sid, _cron_prompt, model_override=job.get("model") or "google/gemini-2.5-flash")
                try:
                    from salmalm.features.edge_cases import _usage as _u_tick2
                    cron_cost = _u_tick2.get("total_cost", 0) - cost_before
                    MAX_CRON_JOB_COST = 2.0
                    if cron_cost > MAX_CRON_JOB_COST:
                        log.warning(f"[CRON] Job {job['name']} cost ${cron_cost:.2f} — exceeds ${MAX_CRON_JOB_COST} cap")
                except Exception:
                    pass
                job["last_run"] = datetime.now(KST).isoformat()  # noqa: F405
                job["run_count"] = job.get("run_count", 0) + 1
                job["error_count"] = 0  # Reset on success
                job.pop("last_error", None)
                self.save_jobs()
                log.info(f"[CRON] Cron completed: {job['name']} ({len(response)} chars)")
                self._notify_completion(job, response)

                # Push result to web chat (async context — no loop capture needed)
                try:
                    from salmalm.core.session_store import get_session as _gs
                    _ws_sess = _gs("web")
                    _cron_msg = f"⏰ **[크론]** `{job['name']}`\n\n{response}"
                    _ws_sess.add_assistant(_cron_msg)
                    from salmalm.web.ws import ws_server as _ws
                    import asyncio as _aio_push
                    await _ws.broadcast({
                        "type": "chat",
                        "role": "assistant",
                        "content": _cron_msg,
                        "session": "web",
                        "source": "cron",
                    })
                    log.info(f"[CRON] WS push sent: {job['name']}")
                except Exception as _pe:
                    log.debug(f"[CRON] WS push failed: {_pe}")
                try:
                    from salmalm.core.memory import write_daily_log as _wdl; _wdl(f"[CRON] {job['name']}: {response[:150]}")
                except Exception: pass
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
