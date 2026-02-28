"""Agent task delegation — spawn autonomous sub-sessions to handle tasks."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict

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
    import asyncio as _asyncio

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

    with _tasks_lock:
        if _tasks.get(task_id, {}).get("status") == "cancelled":
            return

    loop = _asyncio.new_event_loop()
    try:
        from salmalm.core.engine import process_message

        session_id = f"agent_{task_id[:8]}"
        model_override = model if model and model != "auto" else None

        full_output = loop.run_until_complete(
            process_message(
                session_id,
                description,
                model_override=model_override,
            )
        ) or ""

        _update("done", output=full_output, result_preview=full_output[:120])

    except Exception as e:
        log.error(f"[AGENT] Task {task_id} failed: {e}")
        _update("failed", output=f"Error: {e}", result_preview=f"Error: {str(e)[:80]}")
    finally:
        loop.close()


# ── Directive handlers (shared by class mixin + FastAPI route) ────────────────

def _spawn_task(args: str, model: str) -> Dict[str, Any]:
    """Spawn a new agent task and return the response dict."""
    if not args:
        return {"ok": False, "result": "Usage: $task <description>"}
    task_id = uuid.uuid4().hex[:12]
    rec = _task_record(task_id, args, model)
    with _tasks_lock:
        _tasks[task_id] = rec
    threading.Thread(target=_run_task, args=(task_id, args, model), daemon=True).start()
    return {
        "ok": True,
        "type": "task",
        "result": f"✅ Agent task `{task_id}` spawned\n\n**Task:** {args[:80]}",
        "task_id": task_id,
    }


def _handle_directive_task(args: str, model: str) -> Dict[str, Any]:
    """Handle $task directive."""
    return _spawn_task(args, model)


def _handle_directive_status() -> Dict[str, Any]:
    """Handle $status directive."""
    with _tasks_lock:
        all_tasks = list(_tasks.values())
    running = [t for t in all_tasks if t["status"] == "running"]
    done = [t for t in all_tasks if t["status"] == "done"]
    failed = [t for t in all_tasks if t["status"] == "failed"]
    lines = [
        "**Agent Status**",
        f"- 🔄 Running: {len(running)}",
        f"- ✅ Done: {len(done)}",
        f"- ❌ Failed: {len(failed)}",
    ]
    if running:
        lines.append("\n**Active tasks:**")
        for t in running[:3]:
            lines.append(f"- `{t['id']}` — {t['description'][:60]}")
    return {"ok": True, "type": "status", "result": "\n".join(lines)}


def _handle_directive_vault_list() -> Dict[str, Any]:
    keys = vault.keys()
    return {"ok": True, "type": "vault", "result": f"**Vault keys:** {', '.join(keys) or '(empty)'}"}


def _handle_directive_vault_get(key: str) -> Dict[str, Any]:
    val = vault.get(key)
    masked = ("••••" + str(val)[-4:]) if val and len(str(val)) > 8 else ("(empty)" if not val else str(val))
    return {"ok": True, "type": "vault", "result": f"**{key}:** {masked}"}


def _handle_directive_vault_set(key: str, value: str) -> Dict[str, Any]:
    vault.set(key, value)
    return {"ok": True, "type": "vault", "result": f"✅ `{key}` saved to vault"}


def _handle_directive_vault_delete(key: str) -> Dict[str, Any]:
    vault.delete(key)
    return {"ok": True, "type": "vault", "result": f"✅ `{key}` deleted from vault"}


def _handle_directive_vault(args: str) -> Dict[str, Any]:
    """Handle $vault [list|get|set|delete] directive."""
    if not vault.is_unlocked:
        return {"ok": False, "result": "❌ Vault is locked"}
    sub_parts = args.split(None, 2)
    sub = sub_parts[0].lower() if sub_parts else "list"
    if sub == "list":
        return _handle_directive_vault_list()
    if sub == "get" and len(sub_parts) >= 2:
        return _handle_directive_vault_get(sub_parts[1])
    if sub == "set" and len(sub_parts) >= 3:
        return _handle_directive_vault_set(sub_parts[1], sub_parts[2])
    if sub == "delete" and len(sub_parts) >= 2:
        return _handle_directive_vault_delete(sub_parts[1])
    return {"ok": True, "type": "vault", "result": "Usage: $vault [list|get key|set key val|delete key]"}


def _handle_directive_model(args: str) -> Dict[str, Any]:
    """Handle $model <name> directive."""
    if not args:
        return {"ok": False, "result": "Usage: $model <auto|haiku|sonnet|opus|model-name>"}
    try:
        from salmalm.core.llm_router import llm_router
        msg = llm_router.switch_model(args)
        try:
            from salmalm.core.core import router as _router
            _router.set_force_model(None if args == "auto" else args)
        except Exception as _e:
            log.warning("[AGENT] set_force_model failed: %s", _e)
        return {"ok": True, "type": "model", "result": f"✅ {msg}"}
    except Exception as e:
        return {"ok": False, "result": f"❌ {e}"}


def _handle_directive_help() -> Dict[str, Any]:
    """Handle $help directive."""
    return {
        "ok": True,
        "type": "help",
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
    }


def _dispatch_directive(raw: str, model: str = "auto") -> tuple[Dict[str, Any], int]:
    """Parse and dispatch a $-prefixed directive string.

    Returns (response_dict, http_status_code).
    """
    if not raw.startswith("$"):
        return {"error": "Not a directive"}, 400

    text = raw[1:].strip()
    parts = text.split(None, 1)
    cmd = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "task":
        return _handle_directive_task(args, model), 200
    if cmd == "status":
        return _handle_directive_status(), 200
    if cmd == "vault":
        return _handle_directive_vault(args), 200
    if cmd == "model":
        return _handle_directive_model(args), 200
    if cmd in ("help", "?", ""):
        return _handle_directive_help(), 200

    return {
        "ok": False,
        "result": f"❌ Unknown directive: `${cmd}`\nType `$help` for available commands.",
    }, 200


class AgentsMixin:
    GET_ROUTES = {
        "/api/agent/tasks": "_get_api_agent_tasks",
    }
    POST_ROUTES = {
        "/api/agent/task": "_post_api_agent_task",
        "/api/agent/task/cancel": "_delete_api_agent_task",
        "/api/agent/tasks/clear": "_post_api_agent_tasks_clear",
        "/api/directive": "_post_api_directive",
    }

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

    def _post_api_agent_tasks_clear(self) -> None:
        """POST /api/agent/tasks/clear — remove all completed/failed/cancelled tasks."""
        if not self._require_auth("user"):
            return
        _DONE_STATUSES = {"done", "failed", "cancelled"}
        with _tasks_lock:
            to_remove = [tid for tid, t in _tasks.items() if t.get("status") in _DONE_STATUSES]
            for tid in to_remove:
                del _tasks[tid]
        self._json({"ok": True, "removed": len(to_remove)})

    def _post_api_directive(self) -> None:
        """POST /api/directive — handle $-prefixed CEO directives from chat."""
        if not self._require_auth("user"):
            return
        body = self._body
        raw = (body.get("text") or "").strip()
        model = body.get("model", "auto") or "auto"
        result, status = _dispatch_directive(raw, model)
        self._json(result, status)


# ── FastAPI router ────────────────────────────────────────────────────────────
from fastapi import APIRouter as _APIRouter, Request as _Request, Depends as _Depends
from fastapi.responses import JSONResponse as _JSON
from salmalm.web.fastapi_deps import require_auth as _auth

router = _APIRouter()

@router.get("/api/agent/tasks")
async def get_agent_tasks(_u=_Depends(_auth)):
    with _tasks_lock:
        tasks = list(_tasks.values())
    tasks.sort(key=lambda t: (t["status"] != "running", -t["created_at"]))
    return _JSON(content={"tasks": tasks})

@router.post("/api/agent/task")
async def post_agent_task(request: _Request, _u=_Depends(_auth)):
    if not vault.is_unlocked:
        return _JSON(content={"error": "Vault locked"}, status_code=403)
    body = await request.json()
    description = (body.get("description") or "").strip()
    model = body.get("model", "auto") or "auto"
    if not description:
        return _JSON(content={"error": "description required"}, status_code=400)
    if len(description) > 4000:
        return _JSON(content={"error": "description too long (max 4000 chars)"}, status_code=400)
    task_id = uuid.uuid4().hex[:12]
    rec = _task_record(task_id, description, model)
    with _tasks_lock:
        _tasks[task_id] = rec
    threading.Thread(target=_run_task, args=(task_id, description, model), daemon=True).start()
    return _JSON(content={"ok": True, "task_id": task_id})

@router.post("/api/agent/task/cancel")
async def post_agent_task_cancel(request: _Request, _u=_Depends(_auth)):
    body = await request.json()
    task_id = body.get("task_id", "")
    if not task_id:
        return _JSON(content={"error": "task_id required"}, status_code=400)
    with _tasks_lock:
        if task_id not in _tasks:
            return _JSON(content={"error": "Task not found"}, status_code=404)
        _tasks[task_id]["status"] = "cancelled"
    return _JSON(content={"ok": True})

@router.post("/api/agent/tasks/clear")
async def post_agent_tasks_clear(_u=_Depends(_auth)):
    _DONE_STATUSES = {"done", "failed", "cancelled"}
    with _tasks_lock:
        to_remove = [tid for tid, t in _tasks.items() if t.get("status") in _DONE_STATUSES]
        for tid in to_remove:
            del _tasks[tid]
    return _JSON(content={"ok": True, "removed": len(to_remove)})

@router.post("/api/directive")
async def post_directive(request: _Request, _u=_Depends(_auth)):
    body = await request.json()
    raw = (body.get("text") or "").strip()
    model = body.get("model", "auto") or "auto"
    result, status = _dispatch_directive(raw, model)
    return _JSON(content=result, status_code=status)
