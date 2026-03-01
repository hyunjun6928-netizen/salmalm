"""Cron job API — list, add, delete, toggle, run."""


class WebCronMixin:
    GET_ROUTES = {
        "/api/cron": "_get_cron",
    }
    POST_ROUTES = {
        "/api/cron/add": "_post_api_cron_add",
        "/api/cron/delete": "_post_api_cron_delete",
        "/api/cron/toggle": "_post_api_cron_toggle",
        "/api/cron/run": "_post_api_cron_run",
    }

    """Mixin providing cron route handlers."""

    def _get_cron(self):
        """Get cron."""
        if not self._require_auth("user"):
            return
        from salmalm.core import _llm_cron

        self._json({"jobs": _llm_cron.list_jobs() if _llm_cron else []})

    def _post_api_cron_add(self):
        """Post api cron add."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core import _llm_cron

        if not _llm_cron:
            self._json({"ok": False, "error": "Cron not available"}, 500)
            return
        name = body.get("name", "untitled")
        try:
            interval = int(body.get("interval", 3600))
        except (TypeError, ValueError):
            interval = 3600
        prompt = body.get("prompt", "")
        run_at = body.get("run_at", "")  # HH:MM or ISO datetime
        if not prompt:
            self._json({"ok": False, "error": "Prompt required"}, 400)
            return
        if run_at:
            # "Run at" mode: daily alarm at specific time
            if len(run_at) <= 5:  # HH:MM format → daily
                schedule = {
                    "kind": "cron",
                    "expr": f"{run_at.split(':')[1]} {run_at.split(':')[0]} * * *",
                }
            else:  # ISO datetime → one-shot
                schedule = {"kind": "at", "time": run_at}
        else:
            schedule = {"kind": "every", "seconds": interval}
        job = _llm_cron.add_job(name, schedule, prompt)
        self._json({"ok": True, "job": job})

    def _post_api_cron_delete(self):
        """Post api cron delete."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core import _llm_cron

        job_id = body.get("id", "")
        if _llm_cron and _llm_cron.remove_job(job_id):
            self._json({"ok": True})
        else:
            self._json({"ok": False, "error": "Job not found"}, 404)

    def _post_api_cron_toggle(self):
        """Post api cron toggle."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core import _llm_cron

        job_id = body.get("id", "")
        if _llm_cron:
            for j in _llm_cron.jobs:
                if j["id"] == job_id:
                    j["enabled"] = not j["enabled"]
                    _llm_cron.save_jobs()
                    self._json({"ok": True, "enabled": j["enabled"]})
                    return
        self._json({"ok": False, "error": "Job not found"}, 404)

    def _post_api_cron_run(self):
        """POST /api/cron/run — Execute a cron job immediately."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core import _llm_cron

        job_id = body.get("id", "")
        if _llm_cron:
            for j in _llm_cron.jobs:
                if j["id"] == job_id:
                    import threading

                    threading.Thread(target=_llm_cron._execute_job, args=(j,), daemon=True).start()
                    self._json({"ok": True, "message": "Job triggered"})
                    return
        self._json({"ok": False, "error": "Job not found"}, 404)


# ── FastAPI router ────────────────────────────────────────────────────────────
import asyncio as _asyncio
from fastapi import APIRouter as _APIRouter, Request as _Request, Depends as _Depends, Query as _Query
from fastapi.responses import JSONResponse as _JSON, Response as _Response, HTMLResponse as _HTML, StreamingResponse as _SR, RedirectResponse as _RR
from salmalm.web.fastapi_deps import require_auth as _auth, optional_auth as _optauth

router = _APIRouter()

@router.get("/api/cron")
async def get_cron(_u=_Depends(_auth)):
    from salmalm.core import _llm_cron
    return _JSON(content={"jobs": _llm_cron.list_jobs() if _llm_cron else []})

@router.post("/api/cron/add")
async def post_cron_add(request: _Request, _u=_Depends(_auth)):
    from salmalm.core import _llm_cron
    body = await request.json()
    if not _llm_cron:
        return _JSON(content={"ok": False, "error": "Cron not available"}, status_code=500)
    name = body.get("name", "untitled")
    try:
        interval = int(body.get("interval", 3600))
    except (TypeError, ValueError):
        interval = 3600
    prompt = body.get("prompt", "")
    run_at = body.get("run_at", "")
    if not prompt:
        return _JSON(content={"ok": False, "error": "Prompt required"}, status_code=400)
    if run_at:
        if len(run_at) <= 5:
            schedule = {"kind": "cron", "expr": f"{run_at.split(':')[1]} {run_at.split(':')[0]} * * *"}
        else:
            schedule = {"kind": "at", "time": run_at}
    else:
        schedule = {"kind": "every", "seconds": interval}
    job = _llm_cron.add_job(name, schedule, prompt)
    return _JSON(content={"ok": True, "job": job})

@router.post("/api/cron/delete")
async def post_cron_delete(request: _Request, _u=_Depends(_auth)):
    from salmalm.core import _llm_cron
    body = await request.json()
    job_id = body.get("id", "")
    if _llm_cron and _llm_cron.remove_job(job_id):
        return _JSON(content={"ok": True})
    return _JSON(content={"ok": False, "error": "Job not found"}, status_code=404)

@router.post("/api/cron/toggle")
async def post_cron_toggle(request: _Request, _u=_Depends(_auth)):
    from salmalm.core import _llm_cron
    body = await request.json()
    job_id = body.get("id", "")
    if _llm_cron:
        for j in _llm_cron.jobs:
            if j["id"] == job_id:
                j["enabled"] = not j["enabled"]
                _llm_cron.save_jobs()
                return _JSON(content={"ok": True, "enabled": j["enabled"]})
    return _JSON(content={"ok": False, "error": "Job not found"}, status_code=404)

@router.post("/api/cron/run")
async def post_cron_run(request: _Request, _u=_Depends(_auth)):
    import threading
    from salmalm.core import _llm_cron
    body = await request.json()
    job_id = body.get("id", "")
    if _llm_cron:
        for j in _llm_cron.jobs:
            if j["id"] == job_id:
                threading.Thread(target=_llm_cron._execute_job, args=(j,), daemon=True).start()
                return _JSON(content={"ok": True, "message": "Job triggered"})
    return _JSON(content={"ok": False, "error": "Job not found"}, status_code=404)
