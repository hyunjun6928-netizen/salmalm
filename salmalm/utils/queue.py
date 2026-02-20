"""SalmAlm Message Queue — lane-based FIFO with 5 modes, overflow policies, concurrency control.

Architecture:
- QueueLane: per-session (serial) + global concurrency semaphores
- 5 modes: collect, steer, followup, steer-backlog, interrupt
- Overflow: cap + drop policy (old / new / summarize)
- /queue command for runtime config
- Config from ~/.salmalm/queue.json
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Coroutine, Dict, List, Optional, Tuple

from salmalm.crypto import log

# ── Enums ──


class QueueMode(str, Enum):
    COLLECT = "collect"
    STEER = "steer"
    FOLLOWUP = "followup"
    STEER_BACKLOG = "steer-backlog"
    INTERRUPT = "interrupt"


class DropPolicy(str, Enum):
    OLD = "old"
    NEW = "new"
    SUMMARIZE = "summarize"


# ── Config ──

DEFAULT_CONFIG = {
    "mode": "collect",
    "debounceMs": 1000,
    "cap": 20,
    "drop": "summarize",
    "maxConcurrent": {"main": 4, "subagent": 8},
    "byChannel": {},
}

CONFIG_PATH = Path.home() / ".salmalm" / "queue.json"


def load_config() -> dict:
    """Load queue config from ~/.salmalm/queue.json, falling back to defaults."""
    cfg = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                user = json.load(f)
            cfg.update(user)
    except Exception as e:
        log.warning(f"[QUEUE] Failed to load config: {e}")
    return cfg


def save_config(cfg: dict) -> None:
    """Persist config to ~/.salmalm/queue.json."""
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning(f"[QUEUE] Failed to save config: {e}")


# ── Data ──

@dataclass
class QueuedMessage:
    text: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SessionOptions:
    """Per-session overrides, set via /queue command."""
    mode: Optional[QueueMode] = None
    debounce_ms: Optional[int] = None
    cap: Optional[int] = None
    drop: Optional[DropPolicy] = None


# ── Overflow ──

def apply_overflow(pending: List[QueuedMessage], cap: int, policy: DropPolicy) -> Tuple[List[QueuedMessage], Optional[str]]:
    """Enforce cap on pending list. Returns (trimmed_list, summary_or_none)."""
    if len(pending) <= cap:
        return pending, None

    overflow_count = len(pending) - cap

    if policy == DropPolicy.NEW:
        # reject newest — keep only first `cap`
        return pending[:cap], None

    if policy == DropPolicy.OLD:
        # drop oldest
        return pending[overflow_count:], None

    # summarize: drop oldest, produce summary
    dropped = pending[:overflow_count]
    kept = pending[overflow_count:]
    bullets = "\n".join(f"- {m.text[:80]}" for m in dropped)
    summary = f"[이전 {len(dropped)}개 메시지 요약 / {len(dropped)} earlier messages summarized]\n{bullets}"
    summary_msg = QueuedMessage(text=summary, timestamp=dropped[0].timestamp)
    return [summary_msg] + kept, summary


# ── QueueLane ──

class QueueLane:
    """Per-session FIFO lane with serial execution guarantee.

    Only one processor runs per session at a time (session semaphore = 1).
    Global concurrency is controlled by the parent MessageQueue semaphores.
    """

    def __init__(self, session_id: str, global_semaphore: asyncio.Semaphore):
        self.session_id = session_id
        self._global_sem = global_semaphore
        self._session_sem = asyncio.Semaphore(1)  # serial per session
        self._pending: List[QueuedMessage] = []
        self._debounce_task: Optional[asyncio.Task] = None
        self._current_task: Optional[asyncio.Task] = None
        self._steer_event: Optional[asyncio.Event] = None
        self._steer_message: Optional[str] = None
        self._cancel_requested = False
        self._collect_futures: List[asyncio.Future] = []
        self.last_active = time.time()
        self.options = SessionOptions()

    def _resolve(self, cfg: dict, attr: str, cfg_key: str):
        """Resolve option: session override > config > default."""
        val = getattr(self.options, attr, None)
        if val is not None:
            return val if not isinstance(val, Enum) else val.value
        return cfg.get(cfg_key, DEFAULT_CONFIG[cfg_key])

    async def enqueue(
        self,
        message: str,
        processor: Callable[..., Coroutine],
        cfg: dict,
        channel: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Main entry: enqueue message, apply mode logic, return result."""
        self.last_active = time.time()

        mode_str = self._resolve(cfg, "mode", "mode")
        # channel override
        if channel and not self.options.mode:
            by_ch = cfg.get("byChannel", {})
            if channel in by_ch:
                mode_str = by_ch[channel]
        mode = QueueMode(mode_str)

        cap = int(self._resolve(cfg, "cap", "cap"))
        drop = DropPolicy(self._resolve(cfg, "drop", "drop"))
        debounce_s = int(self._resolve(cfg, "debounce_ms", "debounceMs")) / 1000.0

        if mode == QueueMode.INTERRUPT:
            return await self._handle_interrupt(message, processor, cap, drop, **kwargs)
        elif mode == QueueMode.STEER:
            return await self._handle_steer(message, processor, cap, drop, debounce_s, followup=False, **kwargs)
        elif mode == QueueMode.STEER_BACKLOG:
            return await self._handle_steer(message, processor, cap, drop, debounce_s, followup=True, **kwargs)
        elif mode == QueueMode.FOLLOWUP:
            return await self._handle_followup(message, processor, cap, drop, debounce_s, **kwargs)
        else:
            return await self._handle_collect(message, processor, cap, drop, debounce_s, **kwargs)

    # ── Mode handlers ──

    async def _handle_collect(self, message, processor, cap, drop, debounce_s, **kwargs) -> str:
        """Collect mode: debounce, merge, process as single turn."""
        self._pending.append(QueuedMessage(text=message))
        self._pending, _ = apply_overflow(self._pending, cap, drop)

        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._collect_futures.append(future)

        async def _debounce():
            await asyncio.sleep(debounce_s)
            async with self._session_sem:
                async with _SemaphoreContext(self._global_sem):
                    futures = self._collect_futures[:]
                    self._collect_futures.clear()
                    if not self._pending:
                        for f in futures:
                            if not f.done():
                                f.set_result("")
                        return
                    collected = self._pending[:]
                    self._pending.clear()
                    merged = _merge_messages(collected)
                    log.info(f"[QUEUE] collect {self.session_id}: {len(collected)} msgs merged")
                    try:
                        result = await processor(self.session_id, merged, **kwargs)
                        for f in futures:
                            if not f.done():
                                f.set_result(result)
                    except Exception as e:
                        for f in futures:
                            if not f.done():
                                f.set_exception(e)

        self._debounce_task = asyncio.ensure_future(_debounce())
        return await future

    async def _handle_followup(self, message, processor, cap, drop, debounce_s, **kwargs) -> str:
        """Followup mode: wait for current task to finish, then queue as next turn."""
        self._pending.append(QueuedMessage(text=message))
        self._pending, _ = apply_overflow(self._pending, cap, drop)

        # Wait for session lock (current execution finishes)
        async with self._session_sem:
            async with _SemaphoreContext(self._global_sem):
                if not self._pending:
                    return ""
                collected = self._pending[:]
                self._pending.clear()
                merged = _merge_messages(collected)
                log.info(f"[QUEUE] followup {self.session_id}: processing {len(collected)} msgs")
                return await processor(self.session_id, merged, **kwargs)

    async def _handle_steer(self, message, processor, cap, drop, debounce_s, followup=False, **kwargs) -> str:
        """Steer mode: inject into running agent. If followup=True (steer-backlog), also queue remainder."""
        # If something is currently running, steer into it
        if self._session_sem.locked():
            self._steer_message = message
            if self._steer_event:
                self._steer_event.set()
            log.info(f"[QUEUE] steer {self.session_id}: injected message")

            if followup:
                # Also queue for after current execution
                self._pending.append(QueuedMessage(text=message))
                self._pending, _ = apply_overflow(self._pending, cap, drop)
            return "[steered]"

        # Nothing running — treat as collect
        return await self._handle_collect(message, processor, cap, drop, debounce_s, **kwargs)

    async def _handle_interrupt(self, message, processor, cap, drop, **kwargs) -> str:
        """Interrupt mode: cancel current, start fresh with latest message."""
        # Cancel current task
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            self._cancel_requested = True
            log.info(f"[QUEUE] interrupt {self.session_id}: cancelled current task")

        # Clear pending, only latest message
        self._pending.clear()

        async with self._session_sem:
            async with _SemaphoreContext(self._global_sem):
                self._cancel_requested = False
                log.info(f"[QUEUE] interrupt {self.session_id}: starting fresh")
                task = asyncio.ensure_future(processor(self.session_id, message, **kwargs))
                self._current_task = task
                return await task

    # ── Steer support ──

    def get_steer_event(self) -> asyncio.Event:
        """Get/create the steer event for the current execution."""
        if self._steer_event is None:
            self._steer_event = asyncio.Event()
        return self._steer_event

    def consume_steer(self) -> Optional[str]:
        """Consume a steered message (called at tool boundaries)."""
        msg = self._steer_message
        self._steer_message = None
        if self._steer_event:
            self._steer_event.clear()
        return msg

    def reset_options(self):
        """Reset per-session overrides to defaults."""
        self.options = SessionOptions()


class _SemaphoreContext:
    """Async context manager for semaphore."""

    def __init__(self, sem: asyncio.Semaphore):
        self._sem = sem

    async def __aenter__(self):
        await self._sem.acquire()
        return self

    async def __aexit__(self, *args):
        self._sem.release()


def _merge_messages(messages: List[QueuedMessage]) -> str:
    if len(messages) == 1:
        return messages[0].text
    return "\n".join(m.text for m in messages)


# ── MessageQueue (global manager) ──

class MessageQueue:
    """Global message queue manager with lane-based concurrency control.

    - Per-session lanes (serial execution)
    - Global semaphores for main/subagent concurrency limits
    - Runtime config from ~/.salmalm/queue.json
    """

    def __init__(self, config: Optional[dict] = None):
        self._config = config or load_config()
        self._lanes: Dict[str, QueueLane] = {}
        self._lock = threading.Lock()
        self._cleanup_ts = 0.0

        mc = self._config.get("maxConcurrent", DEFAULT_CONFIG["maxConcurrent"])
        self._main_sem = asyncio.Semaphore(mc.get("main", 4))
        self._subagent_sem = asyncio.Semaphore(mc.get("subagent", 8))

    @property
    def config(self) -> dict:
        return self._config

    def reload_config(self):
        self._config = load_config()

    def _get_semaphore(self, session_id: str) -> asyncio.Semaphore:
        if "subagent" in session_id:
            return self._subagent_sem
        return self._main_sem

    def _get_lane(self, session_id: str) -> QueueLane:
        with self._lock:
            if session_id not in self._lanes:
                sem = self._get_semaphore(session_id)
                self._lanes[session_id] = QueueLane(session_id, sem)
            return self._lanes[session_id]

    async def process(
        self,
        session_id: str,
        message: str,
        processor: Callable[..., Coroutine],
        channel: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Process a message through the session's lane."""
        lane = self._get_lane(session_id)
        try:
            return await lane.enqueue(message, processor, self._config, channel=channel, **kwargs)
        except Exception as e:
            log.error(f"[QUEUE] Error processing {session_id}: {e}")
            raise

    def get_lane(self, session_id: str) -> Optional[QueueLane]:
        """Get lane without creating."""
        with self._lock:
            return self._lanes.get(session_id)

    def handle_queue_command(self, session_id: str, args: str) -> str:
        """Handle /queue command. Returns user-facing response.

        /queue collect|steer|followup|steer-backlog|interrupt
        /queue debounce:2s cap:25 drop:summarize
        /queue reset
        /queue              (show current)
        """
        lane = self._get_lane(session_id)
        args = args.strip()

        if not args:
            return self._show_status(lane)

        if args == "reset":
            lane.reset_options()
            return "✅ Queue settings reset to defaults."

        # Parse tokens
        tokens = args.split()
        changes = []

        for token in tokens:
            # Mode
            try:
                mode = QueueMode(token)
                lane.options.mode = mode
                changes.append(f"mode={mode.value}")
                continue
            except ValueError:
                pass

            # key:value pairs
            if ":" in token:
                key, val = token.split(":", 1)
                key = key.lower()

                if key == "debounce":
                    ms = _parse_duration_ms(val)
                    if ms is not None:
                        lane.options.debounce_ms = ms
                        changes.append(f"debounce={ms}ms")
                elif key == "cap":
                    try:
                        lane.options.cap = int(val)
                        changes.append(f"cap={val}")
                    except ValueError:
                        pass
                elif key == "drop":
                    try:
                        lane.options.drop = DropPolicy(val)
                        changes.append(f"drop={val}")
                    except ValueError:
                        pass

        if not changes:
            return f"❌ Unknown queue command: `{args}`\nUsage: /queue [collect|steer|followup|steer-backlog|interrupt] [debounce:Xs] [cap:N] [drop:old|new|summarize] [reset]"

        return f"✅ Queue updated: {', '.join(changes)}"

    def _show_status(self, lane: QueueLane) -> str:
        cfg = self._config
        mode = lane.options.mode.value if lane.options.mode else cfg.get("mode", "collect")
        debounce = lane.options.debounce_ms if lane.options.debounce_ms is not None else cfg.get("debounceMs", 1000)
        cap = lane.options.cap if lane.options.cap is not None else cfg.get("cap", 20)
        drop = lane.options.drop.value if lane.options.drop else cfg.get("drop", "summarize")
        pending = len(lane._pending)

        return (
            f"📋 Queue Status\n"
            f"  mode: {mode}\n"
            f"  debounce: {debounce}ms\n"
            f"  cap: {cap}\n"
            f"  drop: {drop}\n"
            f"  pending: {pending}\n"
            f"  sessions: {self.active_sessions}"
        )

    def cleanup(self, max_idle: float = 3600):
        """Remove idle session lanes."""
        now = time.time()
        if now - self._cleanup_ts < 600:
            return
        self._cleanup_ts = now
        with self._lock:
            stale = [sid for sid, lane in self._lanes.items()
                     if now - lane.last_active > max_idle]
            for sid in stale:
                del self._lanes[sid]
            if stale:
                log.info(f"[QUEUE] Cleaned up {len(stale)} idle lanes")

    @property
    def active_sessions(self) -> int:
        return len(self._lanes)

    @property
    def main_semaphore(self) -> asyncio.Semaphore:
        return self._main_sem

    @property
    def subagent_semaphore(self) -> asyncio.Semaphore:
        return self._subagent_sem


def _parse_duration_ms(s: str) -> Optional[int]:
    """Parse duration string like '2s', '500ms', '1.5s' → milliseconds."""
    s = s.strip().lower()
    try:
        if s.endswith("ms"):
            return int(float(s[:-2]))
        elif s.endswith("s"):
            return int(float(s[:-1]) * 1000)
        else:
            return int(float(s) * 1000)
    except (ValueError, TypeError):
        return None


# Singleton
message_queue = MessageQueue()
