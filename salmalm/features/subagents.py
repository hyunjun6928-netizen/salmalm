"""Sub-agent system: spawn isolated AI workers for parallel tasks.

OpenClaw-style sub-agents with isolated sessions, async execution,
and result callbacks. Each sub-agent runs in its own session context
with independent conversation history.
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
    max_turns: int = 10
    timeout_s: int = 300
    parent_session: str = "web"
    status: str = "pending"  # pending, running, completed, failed, killed
    result: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float = 0
    completed_at: float = 0
    turns_used: int = 0
    tokens_used: int = 0
    _thread: Optional[threading.Thread] = field(default=None, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def elapsed_s(self) -> float:
        if self.started_at == 0:
            return 0
        end = self.completed_at if self.completed_at else time.time()
        return round(end - self.started_at, 1)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description[:100],
            "model": self.model,
            "status": self.status,
            "result": self.result[:500] if self.result else "",
            "error": self.error,
            "elapsed_s": self.elapsed_s,
            "turns_used": self.turns_used,
            "tokens_used": self.tokens_used,
            "created_at": self.created_at,
        }


class SubAgentManager:
    """Manages sub-agent lifecycle: spawn, monitor, kill, collect results."""

    _MAX_CONCURRENT = 5
    _MAX_HISTORY = 50

    def __init__(self):
        self._tasks: Dict[str, SubAgentTask] = {}
        self._lock = threading.Lock()

    def spawn(
        self,
        description: str,
        model: Optional[str] = None,
        max_turns: int = 10,
        timeout_s: int = 300,
        parent_session: str = "web",
        on_complete: Optional[Callable] = None,
    ) -> SubAgentTask:
        """Spawn a new sub-agent task."""
        with self._lock:
            # Check concurrent limit
            running = sum(1 for t in self._tasks.values() if t.status == "running")
            if running >= self._MAX_CONCURRENT:
                task = SubAgentTask(
                    description=description,
                    status="failed",
                    error=f"Max concurrent sub-agents ({self._MAX_CONCURRENT}) reached",
                )
                return task

            # Cleanup old tasks
            self._cleanup_old()

            task = SubAgentTask(
                description=description,
                model=model,
                max_turns=max_turns,
                timeout_s=timeout_s,
                parent_session=parent_session,
            )
            self._tasks[task.task_id] = task

        # Start in background thread
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
        """Execute sub-agent in isolated session."""
        try:
            from salmalm.core.core import get_session, Session  # noqa: F401
            from salmalm.core.llm import call_llm
            from salmalm.core.prompt import build_system_prompt
            from salmalm.tools.tool_handlers import execute_tool

            # Create isolated session
            session_id = f"subagent_{task.task_id}"
            session = get_session(session_id)

            # Build system prompt
            system_prompt = build_system_prompt(session)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task.description},
            ]

            model = task.model
            if not model:
                from salmalm.core.core import router

                model = router._pick_available(3)  # Pick a capable model

            total_tokens = 0

            for turn in range(task.max_turns):
                if task._cancel.is_set():
                    task.status = "killed"
                    task.result = "(killed by user)"
                    break

                # Check timeout
                if time.time() - task.started_at > task.timeout_s:
                    task.status = "failed"
                    task.error = f"Timeout after {task.timeout_s}s"
                    break

                # Call LLM
                result = call_llm(messages, model=model, tools=_get_tool_defs())
                task.turns_used = turn + 1

                usage = result.get("usage", {})
                total_tokens += usage.get("input", 0) + usage.get("output", 0)
                task.tokens_used = total_tokens

                content = result.get("content", "")
                tool_calls = result.get("tool_calls", [])

                if tool_calls:
                    # Execute tools
                    messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
                    for tc in tool_calls:
                        tool_name = tc.get("name", "")
                        tool_args = tc.get("arguments", {})
                        if isinstance(tool_args, str):
                            try:
                                tool_args = json.loads(tool_args)
                            except json.JSONDecodeError:
                                tool_args = {}
                        tool_result = execute_tool(tool_name, tool_args)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id", ""),
                                "content": str(tool_result)[:5000],
                            }
                        )
                else:
                    # No tool calls = final answer
                    task.status = "completed"
                    task.result = content
                    break
            else:
                # Max turns reached
                if task.status == "running":
                    task.status = "completed"
                    task.result = content if content else "(max turns reached)"

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

    def list_tasks(self, include_completed: bool = True) -> List[dict]:
        """List all tasks."""
        with self._lock:
            tasks = list(self._tasks.values())
        if not include_completed:
            tasks = [t for t in tasks if t.status == "running"]
        return [t.to_dict() for t in sorted(tasks, key=lambda t: t.created_at, reverse=True)]

    def get_task(self, task_id: str) -> Optional[SubAgentTask]:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def kill(self, task_id: str) -> str:
        """Kill a running sub-agent."""
        task = self._tasks.get(task_id)
        if not task:
            return f"Task {task_id} not found"
        if task.status != "running":
            return f"Task {task_id} is not running (status: {task.status})"
        task._cancel.set()
        return f"Kill signal sent to {task_id}"

    def kill_all(self) -> str:
        """Kill all running sub-agents."""
        killed = 0
        for task in self._tasks.values():
            if task.status == "running":
                task._cancel.set()
                killed += 1
        return f"Kill signal sent to {killed} sub-agents"

    def _cleanup_old(self):
        """Remove old completed tasks beyond history limit."""
        if len(self._tasks) <= self._MAX_HISTORY:
            return
        completed = [(tid, t) for tid, t in self._tasks.items() if t.status in ("completed", "failed", "killed")]
        completed.sort(key=lambda x: x[1].completed_at)
        to_remove = len(self._tasks) - self._MAX_HISTORY
        for tid, _ in completed[:to_remove]:
            del self._tasks[tid]

    def steer(self, task_id: str, message: str) -> str:
        """Send a steering message to a running or completed sub-agent.

        OpenClaw-style: inject guidance into the agent's session without
        killing it. For running agents, the message is queued and picked up
        on the next LLM turn. For completed agents, re-runs with the message.
        """
        task = self._tasks.get(task_id)
        if not task:
            return f"Task {task_id} not found"

        session_id = f"subagent_{task_id}"
        try:
            from salmalm.core.core import get_session

            session = get_session(session_id)
            session.messages.append({"role": "user", "content": f"[Steering from parent] {message}"})

            if task.status == "running":
                return f"📡 Steering message queued for {task_id} (will be picked up on next turn)"

            # Completed/failed — re-run with the steering message
            from salmalm.core.llm import call_llm

            model = task.model
            if not model:
                from salmalm.core.core import router

                model = router._pick_available(2)

            result = call_llm(session.messages, model=model, tools=_get_tool_defs(), max_tokens=4096)
            content = result.get("content", "")
            task.result = content
            task.status = "completed"
            task.completed_at = time.time()
            return f"🤖 [{task_id}] steered response:\n\n{content[:2000]}"
        except Exception as e:
            return f"❌ Steer failed: {e}"

    def collect_results(self, parent_session: str = "web") -> list:
        """Collect all completed results for a parent session (OpenClaw push-style).

        Returns list of completed tasks and marks them as collected.
        """
        results = []
        with self._lock:
            for task in self._tasks.values():
                if (
                    task.parent_session == parent_session
                    and task.status == "completed"
                    and not getattr(task, "_collected", False)
                ):
                    results.append(task.to_dict())
                    task._collected = True  # type: ignore[attr-defined]
        return results


def _get_tool_defs() -> list:
    """Get tool definitions for sub-agents (subset of safe tools)."""
    from salmalm.tools.tool_registry import get_all_tools

    # Sub-agents get all tools except dangerous ones
    _BLOCKED_FOR_SUBAGENTS = {"exec", "exec_session", "browser_action"}
    all_tools = get_all_tools()
    return [t for t in all_tools if t.get("name") not in _BLOCKED_FOR_SUBAGENTS]


# Singleton
subagent_manager = SubAgentManager()
