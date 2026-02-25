"""Agent task delegation — spawn autonomous sub-sessions to handle tasks."""
from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any, Dict, List

from salmalm import log
from salmalm.security.crypto import vault

# ── In-memory task store (persisted to DB on create/update) ──────────────────
_tasks: Dict[str, Dict[str, Any]] = {}
_tasks_lock = threading.Lock()


def _task_record(
    task_id: str,
    description: str,
    model: str,
    status: str = "pending",
    output: str = "",
    result_preview: str = "",
    elapsed_ms: int = 0,
    created_at: float | None = None,
) -> Dict[str, Any]:
    return {
        "id": task_id,
        "description": description,
        "model": model,
        "status": status,
        "created_at": created_at or time.time(),
        "elapsed_ms": elapsed_ms,
        "result_preview": result_preview,
        "output": output,
    }


def _run_task(task_id: str, description: str, model: str) -> None:
    """Run an agent task in a background thread."""
    start = time.time()

    def _update(status: str, output: str = "", result_preview: str = "") -> None:
        elapsed = int((time.time() - start) * 1000)
        with _tasks_lock:
            if task_id in _tasks:
                _tasks[task_id].update(
                    status=status,
                    output=output,
                    result_preview=result_preview[:120],
                    elapsed_ms=elapsed,
                )

    _update("running")
    try:
        from salmalm.core import get_session
        from salmalm.core.engine import process_message

        session_id = f"agent_{task_id[:8]}"
        session = get_session(session_id)

        # Set model override
        if model and model != "auto":
            session.model_override = model
        else:
            session.model_override = None

        # System prompt for autonomous agent
        system_prompt = (
            "You are an autonomous AI agent. Complete the assigned task thoroughly "
            "and concisely. Provide a clear result. Do not ask clarifying questions — "
            "make reasonable assumptions and proceed."
        )

        # Run the task
        result_chunks: List[str] = []

        def _on_chunk(chunk: str) -> None:
            result_chunks.append(chunk)

        # Check if cancelled before running
        with _tasks_lock:
            if _tasks.get(task_id, {}).get("status") == "cancelled":
                return

        # Process via engine
        full_output = ""
        try:
            for chunk in process_message(
                text=description,
                session=session,
                system_override=system_prompt,
                stream=True,
            ):
                # Check for cancellation
                with _tasks_lock:
                    if _tasks.get(task_id, {}).get("status") == "cancelled":
                        return
                full_output += chunk
        except TypeError:
            # process_message may not support stream=True — try non-streaming
            full_output = process_message(
                text=description,
                session=session,
                system_override=system_prompt,
            ) or ""

        _update("done", output=full_output, result_preview=full_output[:120])

    except Exception as e:
        log.error(f"[AGENT] Task {task_id} failed: {e}")
        _update("failed", output=f"Error: {e}", result_preview=f"Error: {str(e)[:80]}")


class AgentsMixin:
    """Route mixin for /api/agent/* endpoints."""

    def _post_api_agent_task(self) -> None:
        """POST /api/agent/task — create and spawn a new agent task."""
        if not self._require_auth("user"):
            return
        if not vault.is_unlocked:
            self._json({"error": "Vault locked"}, 403)
            return

        body = self._body
        description = (body.get("description") or "").strip()
        model = body.get("model", "auto") or "auto"

        if not description:
            self._json({"error": "description required"}, 400)
            return
        if len(description) > 4000:
            self._json({"error": "description too long (max 4000 chars)"}, 400)
            return

        task_id = uuid.uuid4().hex[:12]
        rec = _task_record(task_id, description, model)
        with _tasks_lock:
            _tasks[task_id] = rec

        # Spawn background thread
        t = threading.Thread(target=_run_task, args=(task_id, description, model), daemon=True)
        t.start()

        log.info(f"[AGENT] Task {task_id} spawned: {description[:60]}")
        self._json({"ok": True, "task_id": task_id})

    def _get_api_agent_tasks(self) -> None:
        """GET /api/agent/tasks — list all tasks."""
        if not self._require_auth("user"):
            return
        with _tasks_lock:
            tasks = list(_tasks.values())
        # Sort: running first, then by created_at desc
        tasks.sort(key=lambda t: (t["status"] != "running", -t["created_at"]))
        self._json({"tasks": tasks})

    def _delete_api_agent_task(self) -> None:
        """DELETE /api/agent/task — cancel/delete a task."""
        if not self._require_auth("user"):
            return
        body = self._body
        task_id = body.get("task_id") or self.path.rstrip("/").split("/")[-1]
        if not task_id:
            self._json({"error": "task_id required"}, 400)
            return
        with _tasks_lock:
            if task_id not in _tasks:
                self._json({"error": "Task not found"}, 404)
                return
            _tasks[task_id]["status"] = "cancelled"
        self._json({"ok": True})

    def _post_api_directive(self) -> None:
        """POST /api/directive — handle $-prefixed CEO directives from chat."""
        if not self._require_auth("user"):
            return
        body = self._body
        raw = (body.get("text") or "").strip()

        if not raw.startswith("$"):
            self._json({"error": "Not a directive"}, 400)
            return

        # Parse: $command [args...]
        text = raw[1:].strip()
        parts = text.split(None, 1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        # ── $task <description> ───────────────────────────────────────────
        if cmd == "task":
            if not args:
                self._json({"ok": False, "result": "Usage: $task <description>"})
                return
            task_id = uuid.uuid4().hex[:12]
            model = body.get("model", "auto") or "auto"
            rec = _task_record(task_id, args, model)
            with _tasks_lock:
                _tasks[task_id] = rec
            t = threading.Thread(target=_run_task, args=(task_id, args, model), daemon=True)
            t.start()
            self._json({
                "ok": True,
                "type": "task",
                "result": f"✅ Agent task `{task_id}` spawned\n\n**Task:** {args[:80]}",
                "task_id": task_id,
            })

        # ── $status ───────────────────────────────────────────────────────
        elif cmd == "status":
            with _tasks_lock:
                all_tasks = list(_tasks.values())
            running = [t for t in all_tasks if t["status"] == "running"]
            done = [t for t in all_tasks if t["status"] == "done"]
            failed = [t for t in all_tasks if t["status"] == "failed"]
            lines = [
                f"**Agent Status**",
                f"- 🔄 Running: {len(running)}",
                f"- ✅ Done: {len(done)}",
                f"- ❌ Failed: {len(failed)}",
            ]
            if running:
                lines.append("\n**Active tasks:**")
                for t in running[:3]:
                    lines.append(f"- `{t['id']}` — {t['description'][:60]}")
            self._json({"ok": True, "type": "status", "result": "\n".join(lines)})

        # ── $vault list / set / get / delete ─────────────────────────────
        elif cmd == "vault":
            if not vault.is_unlocked:
                self._json({"ok": False, "result": "❌ Vault is locked"})
                return
            sub_parts = args.split(None, 2)
            sub = sub_parts[0].lower() if sub_parts else "list"
            if sub == "list":
                keys = vault.keys()
                self._json({"ok": True, "type": "vault", "result": f"**Vault keys:** {', '.join(keys) or '(empty)'}"})
            elif sub == "get" and len(sub_parts) >= 2:
                val = vault.get(sub_parts[1])
                masked = ("••••" + str(val)[-4:]) if val and len(str(val)) > 8 else ("(empty)" if not val else str(val))
                self._json({"ok": True, "type": "vault", "result": f"**{sub_parts[1]}:** {masked}"})
            elif sub == "set" and len(sub_parts) >= 3:
                vault.set(sub_parts[1], sub_parts[2])
                self._json({"ok": True, "type": "vault", "result": f"✅ `{sub_parts[1]}` saved to vault"})
            elif sub == "delete" and len(sub_parts) >= 2:
                vault.delete(sub_parts[1])
                self._json({"ok": True, "type": "vault", "result": f"✅ `{sub_parts[1]}` deleted from vault"})
            else:
                self._json({"ok": True, "type": "vault", "result": "Usage: $vault [list|get key|set key val|delete key]"})

        # ── $model <name> ─────────────────────────────────────────────────
        elif cmd == "model":
            if not args:
                self._json({"ok": False, "result": "Usage: $model <auto|haiku|sonnet|opus|model-name>"})
                return
            try:
                from salmalm.core.llm_router import llm_router
                msg = llm_router.switch_model(args)
                self._json({"ok": True, "type": "model", "result": f"✅ {msg}"})
            except Exception as e:
                self._json({"ok": False, "result": f"❌ {e}"})

        # ── $help ─────────────────────────────────────────────────────────
        elif cmd in ("help", "?", ""):
            self._json({
                "ok": True, "type": "help",
                "result": (
                    "**Available directives:**\n"
                    "- `$task <description>` — spawn an autonomous agent\n"
                    "- `$status` — show running agent tasks\n"
                    "- `$vault list` — list vault keys\n"
                    "- `$vault get <key>` — get a vault value (masked)\n"
                    "- `$vault set <key> <value>` — store a vault key\n"
                    "- `$vault delete <key>` — delete a vault key\n"
                    "- `$model <name>` — switch active model\n"
                    "- `$help` — show this help"
                ),
            })

        else:
            self._json({
                "ok": False,
                "result": f"❌ Unknown directive: `${cmd}`\nType `$help` for available commands.",
            })
