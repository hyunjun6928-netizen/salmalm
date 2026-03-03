"""Sub-agent system: spawn isolated AI workers for parallel tasks.

OpenClaw-style sub-agents with isolated sessions, async execution,
push-based completion notifications, full message history, and
steer-message injection for live guidance.
"""

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from salmalm.security.crypto import log


@dataclass
class SubAgentTask:
    """A sub-agent task definition."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    model: Optional[str] = None
    thinking_level: Optional[str] = None  # low/medium/high/xhigh
    label: Optional[str] = None
    max_turns: int = 10
    timeout_s: int = 300
    parent_session: str = "web"
    notify: bool = True
    status: str = "pending"  # pending, running, completed, failed, killed
    result: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float = 0
    completed_at: float = 0
    turns_used: int = 0
    tokens_used: int = 0
    # Full conversation history (system prompt excluded for brevity)
    messages: List[dict] = field(default_factory=list)
    # Queue for steer messages injected from parent
    _steer_queue: List[str] = field(default_factory=list, repr=False)
    _steer_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _thread: Optional[threading.Thread] = field(default=None, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def elapsed_s(self) -> float:
        if self.started_at == 0:
            return 0
        end = self.completed_at if self.completed_at else time.time()
        return round(end - self.started_at, 1)

    def push_steer(self, message: str) -> None:
        """Inject a steering message for the next LLM turn."""
        with self._steer_lock:
            self._steer_queue.append(message)

    def pop_steer(self) -> Optional[str]:
        """Pop a pending steer message (consumed once per turn)."""
        with self._steer_lock:
            return self._steer_queue.pop(0) if self._steer_queue else None

    def to_dict(self, include_messages: bool = False) -> dict:
        d = {
            "task_id": self.task_id,
            "label": self.label or self.description[:40],
            "description": self.description[:200],
            "model": self.model,
            "thinking_level": self.thinking_level,
            "status": self.status,
            "result": self.result[:1000] if self.result else "",
            "error": self.error,
            "elapsed_s": self.elapsed_s,
            "turns_used": self.turns_used,
            "tokens_used": self.tokens_used,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "notify": self.notify,
        }
        if include_messages:
            # Exclude system prompt, include user/assistant/tool
            d["messages"] = [
                m for m in self.messages
                if m.get("role") != "system"
            ]
        return d


class SubAgentManager:
    """Manages sub-agent lifecycle: spawn, monitor, kill, steer, collect."""

    _MAX_CONCURRENT = 5
    _MAX_HISTORY = 50

    def __init__(self) -> None:
        self._tasks: Dict[str, SubAgentTask] = {}
        self._lock = threading.Lock()

    def spawn(
        self,
        description: str,
        model: Optional[str] = None,
        thinking_level: Optional[str] = None,
        label: Optional[str] = None,
        max_turns: int = 10,
        timeout_s: int = 300,
        parent_session: str = "web",
        on_complete: Optional[Callable] = None,
        notify: bool = True,
    ) -> SubAgentTask:
        """Spawn a new sub-agent task."""
        with self._lock:
            running = sum(1 for t in self._tasks.values() if t.status == "running")
            if running >= self._MAX_CONCURRENT:
                task = SubAgentTask(
                    description=description,
                    status="failed",
                    error=f"Max concurrent sub-agents ({self._MAX_CONCURRENT}) reached",
                )
                return task
            self._cleanup_old()
            task = SubAgentTask(
                description=description,
                model=model,
                thinking_level=thinking_level,
                label=label,
                max_turns=max_turns,
                timeout_s=timeout_s,
                parent_session=parent_session,
                notify=notify,
            )
            self._tasks[task.task_id] = task

        thread = threading.Thread(
            target=self._run_agent,
            args=(task, on_complete),
            daemon=True,
            name=f"subagent-{task.task_id}",
        )
        task._thread = thread
        task.status = "running"
        task.started_at = time.time()
        thread.start()
        log.info(f"[SUBAGENT] Spawned {task.task_id}: {description[:80]}")
        return task

    def _run_agent(self, task: SubAgentTask, on_complete: Optional[Callable] = None):
        """Execute sub-agent in isolated session with message history + steer support."""
        try:
            from salmalm.core.core import get_session, Session  # noqa: F401
            from salmalm.core.llm import call_llm
            from salmalm.core.prompt import build_system_prompt
            from salmalm.tools.tool_handlers import execute_tool

            session_id = f"subagent_{task.task_id}"
            session = get_session(session_id)
            system_prompt = build_system_prompt(mode='minimal')

            # Bootstrap messages (system excluded from task.messages)
            all_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task.description},
            ]
            # Record initial user message
            task.messages.append({"role": "user", "content": task.description})

            model = task.model
            if not model:
                from salmalm.core.core import router
                model = router.force_model or router._pick_available(3)

            total_tokens = 0
            content = ""

            for turn in range(task.max_turns):
                if task._cancel.is_set():
                    task.status = "killed"
                    task.result = "(killed by user)"
                    break

                if time.time() - task.started_at > task.timeout_s:
                    task.status = "failed"
                    task.error = f"Timeout after {task.timeout_s}s"
                    break

                # Inject any pending steer message before LLM call
                steer_msg = task.pop_steer()
                if steer_msg:
                    inject = {"role": "user", "content": f"[Parent guidance] {steer_msg}"}
                    all_messages.append(inject)
                    task.messages.append(inject)

                _think = task.thinking_level if task.thinking_level and turn == 0 else False
                result = call_llm(all_messages, model=model, tools=_get_tool_defs(), thinking=_think)
                task.turns_used = turn + 1

                usage = result.get("usage", {})
                total_tokens += usage.get("input", 0) + usage.get("output", 0)
                task.tokens_used = total_tokens

                content = result.get("content", "")
                tool_calls = result.get("tool_calls", [])

                if tool_calls:
                    asst_msg = {"role": "assistant", "content": content, "tool_calls": tool_calls}
                    all_messages.append(asst_msg)
                    task.messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [{"name": tc.get("name"), "arguments": tc.get("arguments")} for tc in tool_calls],
                    })
                    for tc in tool_calls:
                        tool_name = tc.get("name", "")
                        tool_args = tc.get("arguments", {})
                        if isinstance(tool_args, str):
                            try:
                                tool_args = json.loads(tool_args)
                            except json.JSONDecodeError:
                                tool_args = {}
                        tool_result = execute_tool(tool_name, tool_args)
                        tool_str = str(tool_result)[:5000]
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": tool_str,
                        }
                        all_messages.append(tool_msg)
                        task.messages.append({"role": "tool", "name": tool_name, "content": tool_str[:500]})
                else:
                    # Final answer
                    task.messages.append({"role": "assistant", "content": content})
                    task.status = "completed"
                    task.result = content
                    break
            else:
                if task.status == "running":
                    if content:
                        task.messages.append({"role": "assistant", "content": content})
                    task.status = "completed"
                    task.result = content or "(max turns reached)"

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            log.error(f"[SUBAGENT] {task.task_id} error: {e}")

        finally:
            task.completed_at = time.time()
            log.info(f"[SUBAGENT] {task.task_id} {task.status} ({task.elapsed_s}s, {task.turns_used} turns)")

            if on_complete:
                try:
                    on_complete(task)
                except Exception as e:
                    log.error(f"[SUBAGENT] Callback error: {e}")

            if task.notify and task.status in ("completed", "failed"):
                self._auto_notify(task)

    # ── Push-based completion notification ───────────────────────────────────

    def _auto_notify(self, task: SubAgentTask) -> None:
        """Push completion event via WS and Telegram."""
        label = task.label or task.description[:40]
        if task.status == "completed":
            msg = (f"✅ **Sub-agent `{task.task_id}`** '{label}' completed "
                   f"({task.elapsed_s}s, {task.turns_used} turns)\n\n{task.result[:500]}")
        else:
            msg = f"❌ **Sub-agent `{task.task_id}`** '{label}' failed: {task.error}"

        # WS broadcast → triggers UI auto-refresh + toast
        try:
            from salmalm.web.ws import ws_server
            import asyncio
            _ws_loop = _get_ws_loop()
            if _ws_loop:
                asyncio.run_coroutine_threadsafe(
                    ws_server.broadcast({
                        "type": "subagent_done",
                        "task": task.to_dict(),
                        "message": msg,
                    }),
                    _ws_loop,
                )
        except Exception as e:
            log.debug(f"[SUBAGENT] WS broadcast skipped: {e}")

        # Push message into parent session chat (OpenClaw-style)
        try:
            from salmalm.core.core import get_session
            parent_sid = task.parent_session or "web"
            parent_sess = get_session(parent_sid)
            parent_sess.add_assistant(msg)
            # Also broadcast via SSE so the UI updates live
            try:
                from salmalm.web.ws import ws_server
                import asyncio as _aio
                _loop2 = _get_ws_loop()
                if _loop2:
                    _aio.run_coroutine_threadsafe(
                        ws_server.broadcast({
                            "type": "chat",
                            "role": "assistant",
                            "content": msg,
                            "session": parent_sid,
                            "source": "subagent_notify",
                        }),
                        _loop2,
                    )
                    log.info(f"[SUBAGENT] WS push sent to session {parent_sid}")
            except Exception as _e:
                log.debug(f"[SUBAGENT] SSE push skipped: {_e}")
        except Exception as e:
            log.debug(f"[SUBAGENT] Parent push skipped: {e}")

        # Telegram
        try:
            from salmalm.channels.telegram import TelegramBot
            TelegramBot.notify_owner(msg)
        except Exception as e:
            log.debug(f"[SUBAGENT] Telegram notification skipped: {e}")

        log.info(f"[SUBAGENT] Notified: {task.task_id} → {task.status}")

    # ── Steer ────────────────────────────────────────────────────────────────

    def steer(self, task_id: str, message: str) -> str:
        """Inject a steering message into a running sub-agent's next turn."""
        task = self._tasks.get(task_id)
        if not task:
            return f"Task {task_id} not found"
        if task.status not in ("running", "completed"):
            return f"Task {task_id} is {task.status} — cannot steer"

        if task.status == "running":
            task.push_steer(message)
            return f"📡 Steering message queued for `{task_id}` (picked up on next turn)"

        # Completed — re-run one more LLM turn
        try:
            from salmalm.core.llm import call_llm
            inject = {"role": "user", "content": f"[Parent guidance] {message}"}
            all_msgs = [{"role": "system", "content": ""}] + task.messages + [inject]
            model = task.model
            if not model:
                from salmalm.core.core import router
                model = router.force_model or router._pick_available(2)
            result = call_llm(all_msgs, model=model, tools=_get_tool_defs(), max_tokens=4096)
            content = result.get("content", "")
            task.messages.append(inject)
            task.messages.append({"role": "assistant", "content": content})
            task.result = content
            task.completed_at = time.time()
            return f"🤖 `{task_id}` steered:\n\n{content[:2000]}"
        except Exception as e:
            return f"❌ Steer failed: {e}"

    # ── CRUD helpers ─────────────────────────────────────────────────────────

    def list_tasks(self, include_completed: bool = True) -> List[dict]:
        with self._lock:
            tasks = list(self._tasks.values())
        if not include_completed:
            tasks = [t for t in tasks if t.status == "running"]
        return [t.to_dict() for t in sorted(tasks, key=lambda t: t.created_at, reverse=True)]

    def get_task(self, task_id: str) -> Optional[SubAgentTask]:
        return self._tasks.get(task_id)

    def kill(self, task_id: str) -> str:
        task = self._tasks.get(task_id)
        if not task:
            return f"Task {task_id} not found"
        if task.status != "running":
            return f"Task {task_id} is not running (status: {task.status})"
        task._cancel.set()
        return f"Kill signal sent to {task_id}"

    def kill_all(self) -> str:
        killed = 0
        for task in self._tasks.values():
            if task.status == "running":
                task._cancel.set()
                killed += 1
        return f"Kill signal sent to {killed} sub-agents"

    def clear_completed(self) -> int:
        """Remove all completed/failed/killed tasks. Returns count removed."""
        with self._lock:
            to_del = [tid for tid, t in self._tasks.items()
                      if t.status in ("completed", "failed", "killed")]
            for tid in to_del:
                del self._tasks[tid]
        return len(to_del)

    def collect_results(self, parent_session: str = "web") -> list:
        """Collect uncollected completed results for a parent session."""
        results = []
        with self._lock:
            for task in self._tasks.values():
                if (task.parent_session == parent_session
                        and task.status == "completed"
                        and not getattr(task, "_collected", False)):
                    results.append(task.to_dict())
                    task._collected = True  # type: ignore[attr-defined]
        return results

    def _cleanup_old(self):
        if len(self._tasks) <= self._MAX_HISTORY:
            return
        completed = [(tid, t) for tid, t in self._tasks.items()
                     if t.status in ("completed", "failed", "killed")]
        completed.sort(key=lambda x: x[1].completed_at)
        to_remove = len(self._tasks) - self._MAX_HISTORY
        for tid, _ in completed[:to_remove]:
            del self._tasks[tid]


def _get_tool_defs() -> list:
    """Get tool definitions for sub-agents (all except dangerous ones)."""
    from salmalm.tools.tool_registry import get_all_tools
    _BLOCKED = {"exec", "exec_session", "browser_action"}
    return [t for t in get_all_tools() if t.get("name") not in _BLOCKED]


# Singleton
subagent_manager = SubAgentManager()
