"""Web Manage routes mixin."""

import logging
import os
import sys
import time

from salmalm.core import audit_log

from salmalm.constants import DATA_DIR, VERSION, WORKSPACE_DIR, BASE_DIR  # noqa: F401
from salmalm.security.crypto import vault, log  # noqa: F401
from salmalm.web.auth import extract_auth, auth_manager  # noqa: F401

log = logging.getLogger(__name__)


def _systemd_restart_after_upgrade() -> None:
    """Schedule a `systemctl --user restart salmalm` 2s after upgrade completes.

    Non-blocking: spawns a background thread so the HTTP response returns first.
    Silently no-ops if systemd is unavailable or service isn't installed.
    """
    import threading
    import subprocess
    import time

    def _restart():
        time.sleep(2)  # Let the HTTP response flush to client
        try:
            r = subprocess.run(
                ["systemctl", "--user", "is-active", "salmalm.service"],
                capture_output=True, text=True, timeout=5,
            )
            if r.stdout.strip() == "active":
                subprocess.run(
                    ["systemctl", "--user", "restart", "salmalm.service"],
                    capture_output=True, timeout=10,
                )
                log.info("[UPDATE] systemd service restarted with new binary")
        except Exception as e:
            log.debug(f"[UPDATE] systemd restart skipped: {e}")

    threading.Thread(target=_restart, daemon=True, name="systemd-restart").start()


class ManageMixin:
    GET_ROUTES = {
        "/api/backup": "_get_backup",
    }
    POST_ROUTES = {
        "/api/do-update": "_post_api_do_update",
        "/api/restart": "_post_api_restart",
        "/api/update": "_post_api_update",
        "/api/persona/switch": "_post_api_persona_switch",
        "/api/persona/create": "_post_api_persona_create",
        "/api/persona/delete": "_post_api_persona_delete",
        "/api/stt": "_post_api_stt",
        "/api/agent/sync": "_post_api_agent_sync",
        "/api/queue/mode": "_post_api_queue_mode",
        "/api/soul": "_post_api_soul",
        "/api/agents": "_post_api_agents",
        "/api/hooks": "_post_api_hooks",
        "/api/plugins/manage": "_post_api_plugins_manage",
        "/api/groups": "_post_api_groups",
        "/api/paste/detect": "_post_api_paste_detect",
        "/api/vault": "_post_api_vault",
        "/api/cooldowns/reset": "_post_api_cooldowns_reset",
        "/api/backup/restore": "_post_api_backup_restore",
        "/api/presence": "_post_api_presence",
        "/api/node/execute": "_post_api_node_execute",
    }

    def _post_api_cooldowns_reset(self):
        """POST /api/cooldowns/reset — Clear all model cooldowns."""
        if not self._require_auth("user"):
            return
        from salmalm.core.llm_loop import reset_cooldowns

        reset_cooldowns()
        self._json({"ok": True, "message": "All cooldowns cleared"})

    def _get_backup(self):
        """GET /api/backup — download ~/SalmAlm as zip."""
        if not self._require_auth("admin"):
            return
        import zipfile
        import io
        import time as _time

        buf = io.BytesIO()
        skip_ext = {".pyc"}
        skip_dirs = {"__pycache__", ".git", "node_modules"}
        max_file_size = 50 * 1024 * 1024  # 50MB

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(str(DATA_DIR)):
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                for fname in files:
                    fpath = os.path.join(root, fname)
                    if any(fname.endswith(e) for e in skip_ext):
                        continue
                    try:
                        if os.path.getsize(fpath) > max_file_size:
                            continue
                    except OSError:
                        continue
                    arcname = os.path.relpath(fpath, str(DATA_DIR))
                    zf.write(fpath, arcname)

        body = buf.getvalue()
        ts = _time.strftime("%Y%m%d_%H%M%S")
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="salmalm_backup_{ts}.zip"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _post_api_backup_restore(self):
        """POST /api/backup/restore — restore from uploaded zip."""
        if not self._require_auth("admin"):
            return
        import zipfile
        import io

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 100 * 1024 * 1024:  # 100MB limit
            self._json({"ok": False, "error": "File too large (max 100MB)"}, 400)
            return
        body = self.rfile.read(content_length)
        try:
            zf = zipfile.ZipFile(io.BytesIO(body))
        except zipfile.BadZipFile:
            self._json({"ok": False, "error": "Invalid zip file"}, 400)
            return

        # Safety: check for path traversal
        for name in zf.namelist():
            if name.startswith("/") or ".." in name:
                self._json({"ok": False, "error": f"Unsafe path in zip: {name}"}, 400)
                return

        zf.extractall(str(DATA_DIR))
        zf.close()
        self._json({"ok": True, "message": f"Restored {len(zf.namelist())} files to {DATA_DIR}"})

    def _post_api_vault(self):
        """Post api vault."""
        body = self._body
        if not vault.is_unlocked:
            self._json({"error": "Vault locked"}, 403)
            return
        # Vault ops require admin
        user = extract_auth(dict(self.headers))
        ip = self._get_client_ip()
        _is_localhost = ip in ("127.0.0.1", "::1", "localhost")
        _is_admin = user and user.get("role") == "admin"
        if not _is_admin and not _is_localhost:
            self._json({"error": "Admin access required"}, 403)
            return
        action = body.get("action")
        if action == "set":
            key = body.get("key")
            value = body.get("value")
            if not key:
                self._json({"error": "key required"}, 400)
                return
            try:
                vault.set(key, value)
                self._json({"ok": True})
            except Exception as e:
                self._json({"error": f"Vault error: {type(e).__name__}: {e}"}, 500)
        elif action == "get":
            key = body.get("key")
            if not key:
                self._json({"error": "key required"}, 400)
                return
            val = vault.get(key)
            self._json({"value": val})
        elif action == "keys":
            self._json({"keys": vault.keys()})
        elif action == "delete":
            key = body.get("key")
            if not key:
                self._json({"error": "key required"}, 400)
                return
            vault.delete(key)
            self._json({"ok": True})
        elif action == "change_password":
            old_pw = body.get("old_password", "")
            new_pw = body.get("new_password", "")
            if new_pw and len(new_pw) < 4:
                self._json({"error": "Password must be at least 4 characters"}, 400)
            elif vault.change_password(old_pw, new_pw):
                audit_log("vault", "master password changed")
                self._json({"ok": True})
            else:
                self._json({"error": "Current password is incorrect"}, 403)
        else:
            self._json({"error": "Unknown action"}, 400)

    def _post_api_do_update(self):
        """Post api do update."""
        if not self._require_auth("admin"):
            return
        if self._get_client_ip() not in ("127.0.0.1", "::1", "localhost"):
            self._json({"error": "Update only allowed from localhost"}, 403)
            return
        try:
            import subprocess
            import sys

            # Try pipx first (common install method), fallback to pip
            import shutil

            _use_pipx = shutil.which("pipx") is not None
            if _use_pipx:
                _update_cmd = ["pipx", "install", "salmalm", "--force"]
            else:
                _update_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", "salmalm"]
            result = subprocess.run(
                _update_cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                # Get installed version
                ver_result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "from salmalm.constants import VERSION; print(VERSION)",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                new_ver = ver_result.stdout.strip() or "?"
                audit_log("update", f"upgraded to v{new_ver}")
                # If running under systemd, schedule a service restart so the
                # new binary is loaded (non-blocking — response returns first)
                _systemd_restart_after_upgrade()
                self._json({"ok": True, "version": new_ver, "output": result.stdout[-200:]})
            else:
                self._json({"ok": False, "error": result.stderr[-200:]})
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:200]})
        return

    def _post_api_restart(self):
        """Post api restart."""
        if not self._require_auth("admin"):
            return
        if self._get_client_ip() not in ("127.0.0.1", "::1", "localhost"):
            self._json({"error": "Restart only allowed from localhost"}, 403)
            return

        audit_log("restart", "user-initiated restart")
        self._json({"ok": True, "message": "Restarting..."})
        # Graceful restart: flush response, then replace process after a short delay
        import threading
        import sys as _sys

        def _do_restart():
            """Do restart."""
            import time

            time.sleep(0.5)  # Let HTTP response flush
            os.execv(_sys.executable, [_sys.executable] + _sys.argv)

        threading.Thread(target=_do_restart, daemon=True).start()
        return

    def _post_api_update(self):
        # Alias for /api/do-update with WebSocket progress
        """Post api update."""
        if not self._require_auth("admin"):
            return
        if self._get_client_ip() not in ("127.0.0.1", "::1", "localhost"):
            self._json({"error": "Update only allowed from localhost"}, 403)
            return
        try:
            import subprocess
            import shutil

            # Broadcast update start via WebSocket
            try:
                from salmalm.web.ws import ws_server
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(ws_server.broadcast({"type": "update_status", "status": "installing"}))
            except Exception as e:
                log.debug(f"Suppressed: {e}")

            # pipx first (preferred), fallback to pip
            _use_pipx = shutil.which("pipx") is not None
            if _use_pipx:
                _update_cmd = ["pipx", "install", "salmalm", "--force"]
            else:
                _update_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", "salmalm"]

            result = subprocess.run(_update_cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                ver_result = subprocess.run(
                    [sys.executable, "-c", "from salmalm.constants import VERSION; print(VERSION)"],
                    capture_output=True, text=True, timeout=10,
                )
                new_ver = ver_result.stdout.strip() or "?"
                audit_log("update", f"upgraded to v{new_ver}")
                # Broadcast completion + schedule systemd reload
                try:
                    from salmalm.web.ws import ws_server
                    import asyncio

                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(ws_server.broadcast({
                            "type": "update_status", "status": "complete", "version": new_ver
                        }))
                except Exception as e:
                    log.debug(f"Suppressed: {e}")
                _systemd_restart_after_upgrade()
                self._json({"ok": True, "version": new_ver, "output": result.stdout[-200:]})
            else:
                self._json({"ok": False, "error": result.stderr[-200:]})
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:200]})
        return

    def _post_api_persona_switch(self):
        """Post api persona switch."""
        body = self._body
        if not self._require_auth("user"):
            return
        session_id = body.get("session_id", self.headers.get("X-Session-Id", "web"))
        name = body.get("name", "")
        if not name:
            self._json({"error": "name required"}, 400)
            return
        from salmalm.core.prompt import switch_persona

        content = switch_persona(session_id, name)
        if content is None:
            self._json({"error": f'Persona "{name}" not found'}, 404)
            return
        self._json({"ok": True, "name": name, "content": content})
        return

    def _post_api_persona_create(self):
        """Post api persona create."""
        body = self._body
        if not self._require_auth("user"):
            return
        name = body.get("name", "")
        content = body.get("content", "")
        if not name or not content:
            self._json({"error": "name and content required"}, 400)
            return
        from salmalm.core.prompt import create_persona

        ok = create_persona(name, content)
        if ok:
            self._json({"ok": True})
        else:
            self._json({"error": "Invalid persona name"}, 400)
        return

    def _post_api_persona_delete(self):
        """Post api persona delete."""
        body = self._body
        if not self._require_auth("user"):
            return
        name = body.get("name", "")
        if not name:
            self._json({"error": "name required"}, 400)
            return
        from salmalm.core.prompt import delete_persona

        ok = delete_persona(name)
        if ok:
            self._json({"ok": True})
        else:
            self._json({"error": "Cannot delete built-in persona or not found"}, 400)
        return

    def _post_api_stt(self):
        """Post api stt."""
        body = self._body
        if not self._require_auth("user"):
            return
        audio_b64 = body.get("audio_base64", "")
        lang = body.get("language", "ko")
        if not audio_b64:
            self._json({"error": "No audio data"}, 400)
            return
        try:
            from salmalm.tools.tool_handlers import execute_tool

            result = execute_tool("stt", {"audio_base64": audio_b64, "language": lang})  # type: ignore[assignment]
            text = result.replace("🎤 Transcription:\n", "") if isinstance(result, str) else ""
            self._json({"ok": True, "text": text})
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)

    def _post_api_agent_sync(self):
        """Post api agent sync."""
        body = self._body
        if not self._require_auth("user"):
            return
        action = body.get("action", "export")
        if action == "export":
            import json as _json

            export_data = {}
            # Quick sync: lightweight JSON export (no ZIP)
            soul_path = DATA_DIR / "soul.md"
            if soul_path.exists():
                export_data["soul"] = soul_path.read_text(encoding="utf-8")
            config_path = DATA_DIR / "config.json"
            if config_path.exists():
                export_data["config"] = _json.loads(config_path.read_text(encoding="utf-8"))
            routing_path = DATA_DIR / "routing.json"
            if routing_path.exists():
                export_data["routing"] = _json.loads(routing_path.read_text(encoding="utf-8"))
            memory_dir = BASE_DIR / "memory"
            if memory_dir.exists():
                export_data["memory"] = {}
                for f in memory_dir.glob("*"):
                    if f.is_file():
                        export_data["memory"][f.name] = f.read_text(encoding="utf-8")
            self._json({"ok": True, "data": export_data})
        else:
            self._json({"ok": False, "error": "Unknown action"}, 400)

    def _post_api_queue_mode(self):
        """Post api queue mode."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.features.queue import set_queue_mode

        mode = body.get("mode", "collect")
        session_id = body.get("session_id", "web")
        try:
            result = set_queue_mode(session_id, mode)
            self._json({"ok": True, "message": result})
        except ValueError as e:
            self._json({"ok": False, "error": str(e)}, 400)

    def _post_api_soul(self):
        """Post api soul."""
        body = self._body
        if not self._require_auth("user"):
            return
        content = body.get("content", "")
        from salmalm.core.prompt import set_user_soul, reset_user_soul

        if content.strip():
            set_user_soul(content)
            self._json({"ok": True, "message": "SOUL.md saved"})
        else:
            reset_user_soul()
            self._json({"ok": True, "message": "SOUL.md reset to default"})
        return

    def _post_api_agents(self):
        """Post api agents."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.features.agents import agent_manager

        action = body.get("action", "")
        if action == "create":
            result = agent_manager.create(body.get("id", ""), body.get("display_name", ""))
            self._json({"ok": "✅" in result, "message": result})
        elif action == "delete":
            result = agent_manager.delete(body.get("id", ""))
            self._json({"ok": True, "message": result})
        elif action == "bind":
            result = agent_manager.bind(body.get("chat_key", ""), body.get("agent_id", ""))
            self._json({"ok": True, "message": result})
        elif action == "switch":
            result = agent_manager.switch(body.get("chat_key", ""), body.get("agent_id", ""))
            self._json({"ok": True, "message": result})
        else:
            self._json({"error": "Unknown action. Use: create, delete, bind, switch"}, 400)

    def _post_api_hooks(self):
        """Post api hooks."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.features.hooks import hook_manager

        action = body.get("action", "")
        if action == "add":
            result = hook_manager.add_hook(body.get("event", ""), body.get("command", ""))
            self._json({"ok": True, "message": result})
        elif action == "remove":
            result = hook_manager.remove_hook(body.get("event", ""), body.get("index", 0))
            self._json({"ok": True, "message": result})
        elif action == "test":
            result = hook_manager.test_hook(body.get("event", ""))
            self._json({"ok": True, "message": result})
        elif action == "reload":
            hook_manager.reload()
            self._json({"ok": True, "message": "🔄 Hooks reloaded"})
        else:
            self._json({"error": "Unknown action"}, 400)

    def _post_api_plugins_manage(self):
        """Post api plugins manage."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.features.plugin_manager import plugin_manager

        action = body.get("action", "")
        if action == "reload":
            result = plugin_manager.reload_all()
            self._json({"ok": True, "message": result})
        elif action == "enable":
            result = plugin_manager.enable(body.get("name", ""))
            self._json({"ok": True, "message": result})
        elif action == "disable":
            result = plugin_manager.disable(body.get("name", ""))
            self._json({"ok": True, "message": result})
        else:
            self._json({"error": "Unknown action"}, 400)

    def _post_api_groups(self):
        """Post api groups."""
        body = self._body
        # Session group CRUD — LobeChat style (그룹 관리)
        if not self._require_auth("user"):
            return
        action = body.get("action", "create")
        from salmalm.features.edge_cases import session_groups

        if action == "create":
            name = body.get("name", "").strip()
            if not name:
                self._json({"error": "Missing name"}, 400)
                return
            result = session_groups.create_group(name, body.get("color", "#6366f1"))
            self._json(result)
        elif action == "update":
            gid = body.get("id")
            if not gid:
                self._json({"error": "Missing id"}, 400)
                return
            kwargs = {k: v for k, v in body.items() if k in ("name", "color", "sort_order", "collapsed")}
            ok = session_groups.update_group(int(gid), **kwargs)
            self._json({"ok": ok})
        elif action == "delete":
            gid = body.get("id")
            if not gid:
                self._json({"error": "Missing id"}, 400)
                return
            ok = session_groups.delete_group(int(gid))
            self._json({"ok": ok})
        elif action == "move":
            sid = body.get("session_id", "")
            gid = body.get("group_id")
            ok = session_groups.move_session(sid, int(gid) if gid else None)
            self._json({"ok": ok})
        else:
            self._json({"error": "Unknown action"}, 400)
        return

    def _post_api_paste_detect(self):
        """Post api paste detect."""
        body = self._body
        # Smart paste detection — BIG-AGI style (스마트 붙여넣기 감지)
        if not self._require_auth("user"):
            return
        text = body.get("text", "")
        if not text:
            self._json({"error": "Missing text"}, 400)
            return
        from salmalm.features.edge_cases import detect_paste_type

        self._json(detect_paste_type(text))
        return

    def _post_api_presence(self):
        """Post api presence."""
        body = self._body
        # Register/heartbeat presence
        instance_id = body.get("instanceId", "")
        if not instance_id:
            self._json({"error": "instanceId required"}, 400)
            return
        from salmalm.features.presence import presence_manager

        entry = presence_manager.register(
            instance_id,
            host=body.get("host", ""),
            ip=self._get_client_ip(),
            mode=body.get("mode", "web"),
            user_agent=body.get("userAgent", ""),
        )
        self._json({"ok": True, "state": entry.state})

    def _post_api_node_execute(self):
        """Post api node execute."""
        body = self._body
        # Node endpoint: execute a tool locally (called by gateway)
        from salmalm.tools.tool_handlers import execute_tool

        tool = body.get("tool", "")
        args = body.get("args", {})
        if not tool:
            self._json({"error": "tool name required"}, 400)
            return
        try:
            result = execute_tool(tool, args)  # type: ignore[assignment]
            self._json({"ok": True, "result": result[:50000]})  # type: ignore[index]
        except Exception as e:
            self._json({"error": str(e)[:500]}, 500)


# ── FastAPI router ────────────────────────────────────────────────────────────
import asyncio as _asyncio
from fastapi import APIRouter as _APIRouter, Request as _Request, Depends as _Depends, Query as _Query
from fastapi.responses import JSONResponse as _JSON, Response as _Response, HTMLResponse as _HTML, StreamingResponse as _SR, RedirectResponse as _RR
from salmalm.web.fastapi_deps import require_auth as _auth, optional_auth as _optauth

router = _APIRouter()

@router.get("/api/backup")
async def get_backup(request: _Request, _u=_Depends(_auth)):
    import zipfile, io, time as _time, os
    from salmalm.constants import DATA_DIR
    if _u.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    buf = io.BytesIO()
    skip_ext = {".pyc"}
    skip_dirs = {"__pycache__", ".git", "node_modules"}
    max_file_size = 50 * 1024 * 1024
    def _make_zip():
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(str(DATA_DIR)):
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                for fname in files:
                    fpath = os.path.join(root, fname)
                    if any(fname.endswith(e) for e in skip_ext):
                        continue
                    try:
                        if os.path.getsize(fpath) > max_file_size:
                            continue
                    except OSError:
                        continue
                    arcname = os.path.relpath(fpath, str(DATA_DIR))
                    zf.write(fpath, arcname)
        return buf.getvalue()
    body = await _asyncio.to_thread(_make_zip)
    ts = _time.strftime("%Y%m%d_%H%M%S")
    return _Response(content=body, media_type="application/zip",
                     headers={"Content-Disposition": f'attachment; filename="salmalm_backup_{ts}.zip"',
                              "Content-Length": str(len(body))})

@router.post("/api/do-update")
async def post_do_update(request: _Request, _u=_Depends(_auth)):
    import subprocess, sys, shutil
    from salmalm.core import audit_log
    if _u.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    if request.client and request.client.host not in ("127.0.0.1", "::1", "localhost"):
        return _JSON(content={"error": "Update only allowed from localhost"}, status_code=403)
    try:
        _use_pipx = shutil.which("pipx") is not None
        _update_cmd = ["pipx", "install", "salmalm", "--force"] if _use_pipx else [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", "salmalm"]
        result = await _asyncio.to_thread(lambda: subprocess.run(_update_cmd, capture_output=True, text=True, timeout=120))
        if result.returncode == 0:
            ver_result = await _asyncio.to_thread(lambda: subprocess.run([sys.executable, "-c", "from salmalm.constants import VERSION; print(VERSION)"], capture_output=True, text=True, timeout=10))
            new_ver = ver_result.stdout.strip() or "?"
            audit_log("update", f"upgraded to v{new_ver}")
            from salmalm.web.routes.web_manage import _systemd_restart_after_upgrade
            _systemd_restart_after_upgrade()
            return _JSON(content={"ok": True, "version": new_ver, "output": result.stdout[-200:]})
        return _JSON(content={"ok": False, "error": result.stderr[-200:]})
    except Exception as e:
        return _JSON(content={"ok": False, "error": str(e)[:200]})

@router.post("/api/restart")
async def post_restart(request: _Request, _u=_Depends(_auth)):
    import sys, threading, time, os
    from salmalm.core import audit_log
    if _u.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    if request.client and request.client.host not in ("127.0.0.1", "::1", "localhost"):
        return _JSON(content={"error": "Restart only allowed from localhost"}, status_code=403)
    audit_log("restart", "user-initiated restart")
    def _do_restart():
        time.sleep(0.5)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Thread(target=_do_restart, daemon=True).start()
    return _JSON(content={"ok": True, "message": "Restarting..."})

@router.post("/api/update")
async def post_update(request: _Request, _u=_Depends(_auth)):
    import subprocess, sys, shutil
    from salmalm.core import audit_log
    if _u.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    if request.client and request.client.host not in ("127.0.0.1", "::1", "localhost"):
        return _JSON(content={"error": "Update only allowed from localhost"}, status_code=403)
    try:
        _use_pipx = shutil.which("pipx") is not None
        _update_cmd = ["pipx", "install", "salmalm", "--force"] if _use_pipx else [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", "salmalm"]
        result = await _asyncio.to_thread(lambda: subprocess.run(_update_cmd, capture_output=True, text=True, timeout=120))
        if result.returncode == 0:
            ver_result = await _asyncio.to_thread(lambda: subprocess.run([sys.executable, "-c", "from salmalm.constants import VERSION; print(VERSION)"], capture_output=True, text=True, timeout=10))
            new_ver = ver_result.stdout.strip() or "?"
            audit_log("update", f"upgraded to v{new_ver}")
            from salmalm.web.routes.web_manage import _systemd_restart_after_upgrade
            _systemd_restart_after_upgrade()
            return _JSON(content={"ok": True, "version": new_ver, "output": result.stdout[-200:]})
        return _JSON(content={"ok": False, "error": result.stderr[-200:]})
    except Exception as e:
        return _JSON(content={"ok": False, "error": str(e)[:200]})

@router.post("/api/persona/switch")
async def post_persona_switch(request: _Request, _u=_Depends(_auth)):
    body = await request.json()
    session_id = body.get("session_id", request.headers.get("x-session-id", "web"))
    name = body.get("name", "")
    if not name:
        return _JSON(content={"error": "name required"}, status_code=400)
    from salmalm.core.prompt import switch_persona
    content = switch_persona(session_id, name)
    if content is None:
        return _JSON(content={"error": f'Persona "{name}" not found'}, status_code=404)
    return _JSON(content={"ok": True, "name": name, "content": content})

@router.post("/api/persona/create")
async def post_persona_create(request: _Request, _u=_Depends(_auth)):
    body = await request.json()
    name = body.get("name", "")
    content = body.get("content", "")
    if not name or not content:
        return _JSON(content={"error": "name and content required"}, status_code=400)
    from salmalm.core.prompt import create_persona
    ok = create_persona(name, content)
    return _JSON(content={"ok": True} if ok else {"error": "Invalid persona name"}, status_code=200 if ok else 400)

@router.post("/api/persona/delete")
async def post_persona_delete(request: _Request, _u=_Depends(_auth)):
    body = await request.json()
    name = body.get("name", "")
    if not name:
        return _JSON(content={"error": "name required"}, status_code=400)
    from salmalm.core.prompt import delete_persona
    ok = delete_persona(name)
    return _JSON(content={"ok": True} if ok else {"error": "Cannot delete built-in persona or not found"}, status_code=200 if ok else 400)

@router.post("/api/stt")
async def post_stt(request: _Request, _u=_Depends(_auth)):
    body = await request.json()
    audio_b64 = body.get("audio_base64", "")
    lang = body.get("language", "ko")
    if not audio_b64:
        return _JSON(content={"error": "No audio data"}, status_code=400)
    try:
        from salmalm.tools.tool_handlers import execute_tool
        result = await _asyncio.to_thread(execute_tool, "stt", {"audio_base64": audio_b64, "language": lang})
        text = result.replace("🎤 Transcription:\n", "") if isinstance(result, str) else ""
        return _JSON(content={"ok": True, "text": text})
    except Exception as e:
        return _JSON(content={"ok": False, "error": str(e)}, status_code=500)

@router.post("/api/agent/sync")
async def post_agent_sync(request: _Request, _u=_Depends(_auth)):
    import json as _json
    from salmalm.constants import DATA_DIR, BASE_DIR
    body = await request.json()
    action = body.get("action", "export")
    if action == "export":
        export_data = {}
        soul_path = DATA_DIR / "soul.md"
        if soul_path.exists():
            export_data["soul"] = soul_path.read_text(encoding="utf-8")
        config_path = DATA_DIR / "config.json"
        if config_path.exists():
            export_data["config"] = _json.loads(config_path.read_text(encoding="utf-8"))
        routing_path = DATA_DIR / "routing.json"
        if routing_path.exists():
            export_data["routing"] = _json.loads(routing_path.read_text(encoding="utf-8"))
        memory_dir = BASE_DIR / "memory"
        if memory_dir.exists():
            export_data["memory"] = {}
            for f in memory_dir.glob("*"):
                if f.is_file():
                    export_data["memory"][f.name] = f.read_text(encoding="utf-8")
        return _JSON(content={"ok": True, "data": export_data})
    return _JSON(content={"ok": False, "error": "Unknown action"}, status_code=400)

@router.post("/api/queue/mode")
async def post_queue_mode(request: _Request, _u=_Depends(_auth)):
    from salmalm.features.queue import set_queue_mode
    body = await request.json()
    mode = body.get("mode", "collect")
    session_id = body.get("session_id", "web")
    try:
        result = set_queue_mode(session_id, mode)
        return _JSON(content={"ok": True, "message": result})
    except ValueError as e:
        return _JSON(content={"ok": False, "error": str(e)}, status_code=400)

@router.post("/api/soul")
async def post_soul(request: _Request, _u=_Depends(_auth)):
    body = await request.json()
    content = body.get("content", "")
    from salmalm.core.prompt import set_user_soul, reset_user_soul
    if content.strip():
        set_user_soul(content)
        return _JSON(content={"ok": True, "message": "SOUL.md saved"})
    else:
        reset_user_soul()
        return _JSON(content={"ok": True, "message": "SOUL.md reset to default"})

@router.post("/api/agents")
async def post_agents_manage(request: _Request, _u=_Depends(_auth)):
    from salmalm.features.agents import agent_manager
    body = await request.json()
    action = body.get("action", "")
    if action == "create":
        result = agent_manager.create(body.get("id", ""), body.get("display_name", ""))
        return _JSON(content={"ok": "✅" in result, "message": result})
    elif action == "delete":
        result = agent_manager.delete(body.get("id", ""))
        return _JSON(content={"ok": True, "message": result})
    elif action == "bind":
        result = agent_manager.bind(body.get("chat_key", ""), body.get("agent_id", ""))
        return _JSON(content={"ok": True, "message": result})
    elif action == "switch":
        result = agent_manager.switch(body.get("chat_key", ""), body.get("agent_id", ""))
        return _JSON(content={"ok": True, "message": result})
    return _JSON(content={"error": "Unknown action. Use: create, delete, bind, switch"}, status_code=400)

@router.post("/api/hooks")
async def post_hooks(request: _Request, _u=_Depends(_auth)):
    from salmalm.features.hooks import hook_manager
    body = await request.json()
    action = body.get("action", "")
    if action == "add":
        result = hook_manager.add_hook(body.get("event", ""), body.get("command", ""))
        return _JSON(content={"ok": True, "message": result})
    elif action == "remove":
        result = hook_manager.remove_hook(body.get("event", ""), body.get("index", 0))
        return _JSON(content={"ok": True, "message": result})
    elif action == "test":
        result = hook_manager.test_hook(body.get("event", ""))
        return _JSON(content={"ok": True, "message": result})
    elif action == "reload":
        hook_manager.reload()
        return _JSON(content={"ok": True, "message": "🔄 Hooks reloaded"})
    return _JSON(content={"error": "Unknown action"}, status_code=400)

@router.post("/api/plugins/manage")
async def post_plugins_manage(request: _Request, _u=_Depends(_auth)):
    from salmalm.features.plugin_manager import plugin_manager
    body = await request.json()
    action = body.get("action", "")
    if action == "reload":
        result = plugin_manager.reload_all()
        return _JSON(content={"ok": True, "message": result})
    elif action == "enable":
        result = plugin_manager.enable(body.get("name", ""))
        return _JSON(content={"ok": True, "message": result})
    elif action == "disable":
        result = plugin_manager.disable(body.get("name", ""))
        return _JSON(content={"ok": True, "message": result})
    return _JSON(content={"error": "Unknown action"}, status_code=400)

@router.post("/api/groups")
async def post_groups(request: _Request, _u=_Depends(_auth)):
    from salmalm.features.edge_cases import session_groups
    body = await request.json()
    action = body.get("action", "create")
    if action == "create":
        name = body.get("name", "").strip()
        if not name:
            return _JSON(content={"error": "Missing name"}, status_code=400)
        result = session_groups.create_group(name, body.get("color", "#6366f1"))
        return _JSON(content=result)
    elif action == "update":
        gid = body.get("id")
        if not gid:
            return _JSON(content={"error": "Missing id"}, status_code=400)
        kwargs = {k: v for k, v in body.items() if k in ("name", "color", "sort_order", "collapsed")}
        ok = session_groups.update_group(int(gid), **kwargs)
        return _JSON(content={"ok": ok})
    elif action == "delete":
        gid = body.get("id")
        if not gid:
            return _JSON(content={"error": "Missing id"}, status_code=400)
        ok = session_groups.delete_group(int(gid))
        return _JSON(content={"ok": ok})
    elif action == "move":
        sid = body.get("session_id", "")
        gid = body.get("group_id")
        ok = session_groups.move_session(sid, int(gid) if gid else None)
        return _JSON(content={"ok": ok})
    return _JSON(content={"error": "Unknown action"}, status_code=400)

@router.post("/api/paste/detect")
async def post_paste_detect(request: _Request, _u=_Depends(_auth)):
    from salmalm.features.edge_cases import detect_paste_type
    body = await request.json()
    text = body.get("text", "")
    if not text:
        return _JSON(content={"error": "Missing text"}, status_code=400)
    return _JSON(content=detect_paste_type(text))

@router.post("/api/vault")
async def post_vault(request: _Request):
    from salmalm.security.crypto import vault
    from salmalm.web.auth import extract_auth, auth_manager
    from salmalm.core import audit_log
    if not vault.is_unlocked:
        return _JSON(content={"error": "Vault locked"}, status_code=403)
    user = extract_auth(dict(request.headers))
    ip = request.client.host if request.client else "unknown"
    _is_localhost = ip in ("127.0.0.1", "::1", "localhost")
    _is_admin = user and user.get("role") == "admin"
    if not _is_admin and not _is_localhost:
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    body = await request.json()
    action = body.get("action")
    if action == "set":
        key = body.get("key")
        if not key:
            return _JSON(content={"error": "key required"}, status_code=400)
        try:
            vault.set(key, body.get("value"))
            return _JSON(content={"ok": True})
        except Exception as e:
            return _JSON(content={"error": f"Vault error: {type(e).__name__}: {e}"}, status_code=500)
    elif action == "get":
        key = body.get("key")
        if not key:
            return _JSON(content={"error": "key required"}, status_code=400)
        return _JSON(content={"value": vault.get(key)})
    elif action == "keys":
        return _JSON(content={"keys": vault.keys()})
    elif action == "delete":
        key = body.get("key")
        if not key:
            return _JSON(content={"error": "key required"}, status_code=400)
        vault.delete(key)
        return _JSON(content={"ok": True})
    elif action == "change_password":
        old_pw = body.get("old_password", "")
        new_pw = body.get("new_password", "")
        if new_pw and len(new_pw) < 4:
            return _JSON(content={"error": "Password must be at least 4 characters"}, status_code=400)
        elif vault.change_password(old_pw, new_pw):
            audit_log("vault", "master password changed")
            return _JSON(content={"ok": True})
        else:
            return _JSON(content={"error": "Current password is incorrect"}, status_code=403)
    return _JSON(content={"error": "Unknown action"}, status_code=400)

@router.post("/api/cooldowns/reset")
async def post_cooldowns_reset(_u=_Depends(_auth)):
    from salmalm.core.llm_loop import reset_cooldowns
    reset_cooldowns()
    return _JSON(content={"ok": True, "message": "All cooldowns cleared"})

@router.post("/api/backup/restore")
async def post_backup_restore(request: _Request, _u=_Depends(_auth)):
    import zipfile, io
    from salmalm.constants import DATA_DIR
    if _u.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    body_bytes = await request.body()
    if len(body_bytes) > 100 * 1024 * 1024:
        return _JSON(content={"ok": False, "error": "File too large (max 100MB)"}, status_code=400)
    try:
        zf = zipfile.ZipFile(io.BytesIO(body_bytes))
    except zipfile.BadZipFile:
        return _JSON(content={"ok": False, "error": "Invalid zip file"}, status_code=400)
    for name in zf.namelist():
        if name.startswith("/") or ".." in name:
            return _JSON(content={"ok": False, "error": f"Unsafe path in zip: {name}"}, status_code=400)
    zf.extractall(str(DATA_DIR))
    n = len(zf.namelist())
    zf.close()
    return _JSON(content={"ok": True, "message": f"Restored {n} files to {DATA_DIR}"})

@router.post("/api/presence")
async def post_presence(request: _Request):
    from salmalm.features.presence import presence_manager
    body = await request.json()
    instance_id = body.get("instanceId", "")
    if not instance_id:
        return _JSON(content={"error": "instanceId required"}, status_code=400)
    ip = request.client.host if request.client else ""
    entry = presence_manager.register(instance_id, host=body.get("host", ""), ip=ip,
                                      mode=body.get("mode", "web"), user_agent=body.get("userAgent", ""))
    return _JSON(content={"ok": True, "state": entry.state})

@router.post("/api/node/execute")
async def post_node_execute(request: _Request, _u=_Depends(_auth)):
    from salmalm.tools.tool_handlers import execute_tool
    body = await request.json()
    tool = body.get("tool", "")
    args = body.get("args", {})
    if not tool:
        return _JSON(content={"error": "tool name required"}, status_code=400)
    try:
        result = await _asyncio.to_thread(execute_tool, tool, args)
        return _JSON(content={"ok": True, "result": result[:50000]})
    except Exception as e:
        return _JSON(content={"error": str(e)[:500]}, status_code=500)
