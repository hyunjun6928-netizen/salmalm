"""Cron scheduler + Heartbeat manager — extracted from core.py."""

import asyncio
import json
import time
from datetime import datetime
from typing import Optional

from salmalm.constants import BASE_DIR, KST, MEMORY_DIR
from salmalm.security.crypto import log


class CronScheduler:
    """OpenClaw-style cron scheduler with isolated session execution."""

    def __init__(self) -> None:
        """Init  ."""
        self.jobs = []
        self._running = False

    def add_job(self, name: str, interval_seconds: int, callback: object, **kwargs: object) -> None:
        """Add a new cron job with the given schedule and callback."""
        self.jobs.append(
            {
                "name": name,
                "interval": interval_seconds,
                "callback": callback,
                "kwargs": kwargs,
                "last_run": 0,
                "enabled": True,
            }
        )

    async def run(self) -> None:
        """Start the cron scheduler loop."""
        self._running = True
        log.info(f"[CRON] Cron scheduler started ({len(self.jobs)} jobs)")
        while self._running:
            now = time.time()
            for job in self.jobs:
                if not job["enabled"]:
                    continue
                if now - job["last_run"] >= job["interval"]:
                    try:
                        log.info(f"[CRON] Running cron: {job['name']}")
                        if asyncio.iscoroutinefunction(job["callback"]):
                            await job["callback"](**job["kwargs"])
                        else:
                            job["callback"](**job["kwargs"])
                        job["last_run"] = now
                    except Exception as e:
                        log.error(f"Cron error ({job['name']}): {e}")
            await asyncio.sleep(10)

    def stop(self) -> None:
        """Stop the cron scheduler loop."""
        self._running = False


cron = CronScheduler()


# ============================================================
# HEARTBEAT SYSTEM — OpenClaw-style periodic self-check
# ============================================================


class HeartbeatManager:
    """OpenClaw-style heartbeat: periodic self-check with HEARTBEAT.md.

    Reads HEARTBEAT.md for a checklist of things to do on each heartbeat.
    Runs in an isolated session to avoid polluting main conversation.
    Announces results to configured channels.
    Tracks check state in heartbeat-state.json.
    """

    _HEARTBEAT_FILE = BASE_DIR / "HEARTBEAT.md"  # noqa: F405
    _STATE_FILE = MEMORY_DIR / "heartbeat-state.json"  # noqa: F405
    _DEFAULT_INTERVAL = 1800  # 30 minutes
    _last_beat = 0.0
    _enabled = True
    _beat_count = 0

    @classmethod
    def _load_state(cls) -> dict:
        """Load heartbeat state from JSON file."""
        try:
            if cls._STATE_FILE.exists():
                return json.loads(cls._STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        return {"lastChecks": {}, "history": [], "totalBeats": 0}

    @classmethod
    def _save_state(cls, state: dict) -> None:
        """Persist heartbeat state to JSON file."""
        try:
            MEMORY_DIR.mkdir(exist_ok=True)  # noqa: F405
            cls._STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.error(f"[HEARTBEAT] Failed to save state: {e}")

    @classmethod
    def get_prompt(cls) -> str:
        """Read HEARTBEAT.md for the heartbeat checklist."""
        if cls._HEARTBEAT_FILE.exists():
            try:
                content = cls._HEARTBEAT_FILE.read_text(encoding="utf-8", errors="replace")
                if content.strip():
                    return content
            except Exception as e:
                log.debug(f"Suppressed: {e}")
        return ""

    @classmethod
    def should_beat(cls) -> bool:
        """Check if it's time for a heartbeat."""
        if not cls._enabled:
            return False
        now = time.time()
        if now - cls._last_beat < cls._DEFAULT_INTERVAL:
            return False
        # Respect quiet hours (23:00-08:00 KST)
        hour = datetime.now(KST).hour  # noqa: F405
        if hour >= 23 or hour < 8:
            return False
        return True

    @classmethod
    def get_state(cls) -> dict:
        """Get current heartbeat state (for tools/API)."""
        state = cls._load_state()
        state["enabled"] = cls._enabled
        state["interval"] = cls._DEFAULT_INTERVAL
        state["lastBeat"] = cls._last_beat
        state["beatCount"] = cls._beat_count
        return state

    @classmethod
    def update_check(cls, check_name: str) -> None:
        """Record that a specific check was performed (email, calendar, etc)."""
        state = cls._load_state()
        state["lastChecks"][check_name] = time.time()
        cls._save_state(state)

    @classmethod
    def time_since_check(cls, check_name: str) -> Optional[float]:
        """Seconds since a named check was last performed. None if never."""
        state = cls._load_state()
        ts = state.get("lastChecks", {}).get(check_name)
        if ts:
            return time.time() - ts
        return None

    @classmethod
    async def beat(cls) -> Optional[str]:
        """Execute a heartbeat check in an isolated session.

        Returns the heartbeat result or None if nothing to do.
        """
        prompt = cls.get_prompt()
        if not prompt:
            cls._last_beat = time.time()
            return None

        cls._last_beat = time.time()
        cls._beat_count += 1
        log.info("[HEARTBEAT] Running periodic heartbeat check")

        # Load state for context injection
        state = cls._load_state()
        state_ctx = ""
        if state.get("lastChecks"):
            checks = []
            for name, ts in state["lastChecks"].items():
                ago = int((time.time() - ts) / 60)
                checks.append(f"  {name}: {ago}min ago")
            state_ctx = "\n\nLast checks:\n" + "\n".join(checks)

        try:
            from salmalm.core.engine import process_message

            # Run in isolated session (OpenClaw pattern: no cross-contamination)
            result = await process_message(
                f"heartbeat-{int(time.time())}",
                f"[Heartbeat check]\n{prompt}{state_ctx}\n\nIf nothing needs attention, reply HEARTBEAT_OK.",
                model_override=None,  # Use auto-routing
            )

            # Update state
            state["totalBeats"] = state.get("totalBeats", 0) + 1
            state["lastBeatTime"] = time.time()
            state["lastBeatResult"] = "ok" if (result and "HEARTBEAT_OK" in result) else "action"
            # Keep last 20 history entries
            history = state.get("history", [])
            history.append(
                {
                    "time": time.time(),
                    "result": state["lastBeatResult"],
                    "summary": (result or "")[:200],
                }
            )
            state["history"] = history[-20:]
            cls._save_state(state)

            # Announce if result is meaningful
            if result and "HEARTBEAT_OK" not in result:
                cls._announce(result)
                write_daily_log(f"[HEARTBEAT] {result[:200]}")

            return result
        except Exception as e:
            log.error(f"[HEARTBEAT] Error: {e}")
            return None

    @classmethod
    def _announce(cls, result: str) -> None:
        """Announce heartbeat results to configured channels."""
        # Telegram notification
        if _tg_bot and _tg_bot.token and _tg_bot.owner_id:
            try:
                summary = result[:800] + ("..." if len(result) > 800 else "")
                _tg_bot.send_message(_tg_bot.owner_id, f"💓 Heartbeat alert:\n{summary}")
            except Exception as e:
                log.error(f"[HEARTBEAT] Announce error: {e}")

        # Store for web polling
        web_session = _sessions.get("web")
        if web_session:
            if not hasattr(web_session, "_notifications"):
                web_session._notifications = []
            web_session._notifications.append({"time": time.time(), "text": f"💓 Heartbeat: {result[:200]}"})


heartbeat = HeartbeatManager()


# ============================================================
# CONTEXT COMPACTION — Auto-compress old messages when token count exceeds threshold
# ============================================================
AUTO_COMPACT_TOKEN_THRESHOLD = 80_000  # ~80K tokens (chars/4 approximation = 320K chars)
COMPACT_PRESERVE_RECENT = 10  # Keep last N messages intact
