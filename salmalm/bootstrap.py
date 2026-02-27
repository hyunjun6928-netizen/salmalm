"""Server bootstrap — start all SalmAlm services."""

from __future__ import annotations

import asyncio
import http.server
import os
import signal
import sys
import threading
import time

from salmalm.constants import (  # noqa: F401
    VERSION,
    APP_NAME,
    VAULT_FILE,
    MEMORY_DIR,
    BASE_DIR,
    DATA_DIR,
)
from salmalm.security.crypto import vault, log, HAS_CRYPTO
from salmalm.core import (  # noqa: F401
    _init_audit_db,
    _restore_usage,
    audit_log,
    cron,
    LLMCronManager,
    PluginLoader,
)
from salmalm.telegram import telegram_bot
from salmalm.web import WebHandler
from salmalm.web.ws import ws_server, StreamingResponse
from salmalm.rag import rag_engine
from salmalm.mcp import mcp_manager
from salmalm.nodes import node_manager
from salmalm.stability import health_monitor
import salmalm.core as _core


_UPDATE_CHECK_INTERVAL = 86400  # 24h — avoid blocking startup on every run
_update_cache: dict = {}  # {"ts": float, "msg": str}


def _check_for_updates() -> str:
    """Check PyPI for newer version. Returns update message or empty string.

    Result is cached for 24h so offline environments don't pay the 5s timeout
    on every restart.
    """
    import time as _t
    now = _t.time()
    if _update_cache and now - _update_cache.get("ts", 0) < _UPDATE_CHECK_INTERVAL:
        return _update_cache.get("msg", "")

    msg = ""
    try:
        from salmalm.utils.http import request_json as _rj

        data = _rj(
            "https://pypi.org/pypi/salmalm/json",
            headers={"User-Agent": f"SalmAlm/{VERSION}", "Accept": "application/json"},
            timeout=5,
        )
        latest = data.get("info", {}).get("version", "")

        def _ver_tuple(v) -> tuple:
            """Ver tuple — handles 1.2.3, 1.2.3.post1, 1.2.3a1 etc."""
            import re as _re_ver
            return tuple(int(x) for x in _re_ver.findall(r"\d+", v.split("+")[0]))

        if latest and _ver_tuple(latest) > _ver_tuple(VERSION):
            if getattr(sys, "frozen", False):
                msg = (
                    f"⬆️  New version {latest} available!\n"
                    f"   Download: https://github.com/hyunjun6928-netizen/salmalm/releases/latest"
                )
            else:
                msg = f"⬆️  New version {latest} found! Upgrade: pip install --upgrade salmalm"
    except (OSError, ValueError, KeyError, ImportError):
        pass  # network/parse errors — silently skip

    _update_cache["ts"] = now
    _update_cache["msg"] = msg
    return msg


async def _start_telegram_bot() -> None:
    """Phase 11: Start Telegram bot polling."""
    if not vault.is_unlocked:
        log.warning("[TELEGRAM] Skipped — vault is locked. Unlock vault to enable Telegram.")
        return
    tg_token = vault.get("telegram_token")
    tg_owner = vault.get("telegram_owner_id")
    log.info(
        f"[TELEGRAM] token={'YES' if tg_token else 'NO'}, owner={'YES' if tg_owner else 'NO'}, vault_unlocked={vault.is_unlocked}"
    )
    if tg_token and tg_owner:
        telegram_bot.configure(tg_token, tg_owner)
        _core.set_telegram_bot(telegram_bot)
        log.info("[TELEGRAM] Bot configured, starting polling...")
        _wh_url = os.environ.get("SALMALM_TELEGRAM_WEBHOOK_URL") or vault.get("telegram_webhook_url") or ""
        if _wh_url:
            telegram_bot.set_webhook(
                _wh_url.rstrip("/") + "/webhook/telegram" if not _wh_url.endswith("/webhook/telegram") else _wh_url
            )
        else:
            asyncio.create_task(telegram_bot.poll())


async def _start_discord_bot() -> None:
    """Phase 12: Start Discord bot polling."""
    if not vault.is_unlocked:
        log.warning("[DISCORD] Skipped — vault is locked. Unlock vault to enable Discord.")
        return
    dc_token = vault.get("discord_token")
    dc_guild = vault.get("discord_guild_id")
    log.info(f"[DISCORD] token={'YES' if dc_token else 'NO'}, guild={'YES' if dc_guild else 'NO'}")
    if dc_token:
        try:
            from salmalm.channels.discord_bot import discord_bot

            discord_bot.configure(dc_token, dc_guild)

            # Register message handler → core engine
            async def _discord_message_handler(content: str, raw_data, on_token=None):
                """Discord message handler."""
                _channel_id = raw_data.get("channel_id", "")
                _session_id = f"discord_{_channel_id}"
                _start = time.time()
                from salmalm.core.engine import process_message

                response = await process_message(_session_id, content, on_token=on_token)
                _elapsed = time.time() - _start
                return f"{response}\n\n⏱️ {_elapsed:.1f}s" if response else None

            discord_bot.on_message(_discord_message_handler)
            asyncio.create_task(discord_bot.poll())
            log.info("[DISCORD] Bot configured, message handler registered, starting polling...")
        except Exception as e:
            log.warning(f"[DISCORD] Failed to start: {e}")


def _print_banner(selftest=None, bind_addr="127.0.0.1", port=18800, ws_port=18801):
    """Print startup banner (deferred to run_server call)."""
    # RAG stats available but not displayed in banner (intentional)
    st = f"{selftest['passed']}/{selftest['total']}" if selftest else "skipped"
    update_msg = _check_for_updates()
    _w = 42  # inner width between ║ markers
    _lines = [
        f"😈 {APP_NAME} v{VERSION}",
        f"Web UI:    http://{bind_addr}:{port}",
        f"WebSocket: ws://{bind_addr}:{ws_port}",
        f"Vault:     {'🔓 Unlocked' if vault.is_unlocked else '🔒 Locked — open Web UI'}",
        f"Crypto:    {'AES-256-GCM' if HAS_CRYPTO else ('HMAC-CTR (fallback)' if os.environ.get('SALMALM_VAULT_FALLBACK') else 'Vault disabled')}",
        f"Self-test: {st}",
    ]
    _box = "\n╔" + "═" * (_w + 2) + "╗\n"
    for _l in _lines:
        _box += f"║ {_l.ljust(_w)} ║\n"
    _box += "╚" + "═" * (_w + 2) + "╝"
    log.info(_box)
    if update_msg:
        log.info(f"  {update_msg}")


def _auto_unlock_vault() -> None:
    """Attempt vault auto-unlock via keychain, .vault_auto, env var, or empty password."""
    _bind_addr = os.environ.get("SALMALM_BIND", "127.0.0.1")
    _is_external_bind = _bind_addr not in ("127.0.0.1", "::1", "localhost")
    if _is_external_bind and not os.environ.get("SALMALM_AUTO_UNLOCK"):
        log.warning(
            "[VAULT] Auto-unlock disabled on external bind (%s). "
            "Set SALMALM_AUTO_UNLOCK=1 to override, or unlock manually via web UI.",
            _bind_addr,
        )
        return
    if not vault.is_unlocked and not VAULT_FILE.exists():
        log.info("[VAULT] No vault found — web setup wizard will guide creation")
        return
    _allow_auto_unlock = not _is_external_bind or os.environ.get("SALMALM_AUTO_UNLOCK")
    if not (_allow_auto_unlock and not vault.is_unlocked and VAULT_FILE.exists()):
        return
    # 1. Try OS keychain
    if vault.try_keychain_unlock():
        log.info("[UNLOCK] Vault auto-unlocked from keychain")
        _refresh_vault_backup()
        return
    # 2. Try .vault_auto file (WSL/no-keychain fallback)
    _try_vault_auto_file()
    if vault.is_unlocked:
        _refresh_vault_backup()
        return
    # 3. Try env var (deprecated)
    vault_pw = os.environ.get("SALMALM_VAULT_PW")
    if vault_pw and vault.unlock(vault_pw, save_to_keychain=True):
        log.info("[UNLOCK] Vault auto-unlocked from env")
        _refresh_vault_backup()
        return
    # 4. Try empty password
    if vault.unlock(""):
        log.info("[UNLOCK] Vault auto-unlocked (no password)")
        _refresh_vault_backup()
        return
    # 5. Vault file is corrupt/wrong password — try to restore from backup
    _backup = VAULT_FILE.parent / (VAULT_FILE.name + ".bak")
    if _backup.exists() and _backup.stat().st_size > 100:
        log.warning("[VAULT] All unlock methods failed. Attempting restore from backup...")
        import shutil as _shutil
        _corrupt = VAULT_FILE.parent / (VAULT_FILE.name + ".corrupt")
        try:
            _shutil.copy2(str(VAULT_FILE), str(_corrupt))
            _shutil.copy2(str(_backup), str(VAULT_FILE))
            log.info("[VAULT] Restored from backup. Retrying unlock...")
            _try_vault_auto_file()
            if vault.is_unlocked:
                log.info("[VAULT] Vault restored and unlocked from backup.")
                return
            if vault.unlock(""):
                log.info("[VAULT] Vault restored and unlocked (no password).")
                return
            log.warning("[VAULT] Backup restore did not unlock vault either.")
        except OSError as _e:
            log.warning(f"[VAULT] Backup restore failed: {_e}")
    # 6. All methods failed — warn but DO NOT delete vault data
    log.warning(
        "[VAULT] All auto-unlock methods failed. "
        "Visit the web UI to unlock manually, or reset with: salmalm doctor --reset-vault"
    )


def _refresh_vault_backup() -> None:
    """After a successful unlock, ensure .vault.enc.bak is up-to-date.

    The backup is the last line of defence when vault corruption occurs.
    Only updates the backup if the current vault file is substantively larger
    than a skeleton vault (> 100 bytes), so we never backup an empty vault.
    """
    try:
        if not VAULT_FILE.exists():
            return
        size = VAULT_FILE.stat().st_size
        if size <= 100:
            return
        _backup = VAULT_FILE.parent / (VAULT_FILE.name + ".bak")
        # Only overwrite backup if current file is larger (more data = better)
        if _backup.exists() and _backup.stat().st_size >= size:
            return
        import shutil as _shutil
        _shutil.copy2(str(VAULT_FILE), str(_backup))
        try:
            import os as _os
            _os.chmod(_backup, 0o600)
        except OSError:
            pass
        log.debug(f"[VAULT] Backup updated ({size} bytes)")
    except OSError as _e:
        log.debug(f"[VAULT] Backup refresh skipped: {_e}")


def _try_vault_auto_file() -> None:
    """Try unlocking vault from .vault_auto file."""
    try:
        _pw_hint_file = VAULT_FILE.parent / ".vault_auto"
        if not _pw_hint_file.exists():
            return
        _hint = _pw_hint_file.read_text(encoding="utf-8").strip()
        if _hint:
            import base64 as _b64

            try:
                _auto_pw = _b64.b64decode(_hint).decode()
            except Exception:
                _auto_pw = _hint  # Plain text fallback
        else:
            _auto_pw = ""
        if vault.unlock(_auto_pw, save_to_keychain=True):
            log.info("[UNLOCK] Vault auto-unlocked from .vault_auto")
    except (OSError, ValueError, ImportError) as _e:
        log.warning(f"[UNLOCK] .vault_auto read failed: {_e}")


def _start_https_if_configured(bind_addr: str) -> None:
    """Start HTTPS server with self-signed cert if configured."""
    https_port = int(os.environ.get("SALMALM_HTTPS_PORT", 0))
    if not https_port and os.environ.get("SALMALM_HTTPS", "").lower() not in ("1", "true", "yes"):
        return
    https_port = https_port or 18443
    try:
        import ssl

        cert_dir = DATA_DIR / ".certs"
        cert_dir.mkdir(exist_ok=True)
        cert_file = cert_dir / "salmalm.pem"
        key_file = cert_dir / "salmalm-key.pem"
        if not cert_file.exists():
            import subprocess

            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-keyout",
                    str(key_file),
                    "-out",
                    str(cert_file),
                    "-days",
                    "3650",
                    "-nodes",
                    "-batch",
                    "-subj",
                    "/CN=localhost",
                ],
                capture_output=True,
                timeout=30,
            )
            log.info("[HTTPS] Self-signed certificate generated")
        if cert_file.exists() and key_file.exists():
            ssl_server = http.server.ThreadingHTTPServer((bind_addr, https_port), WebHandler)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(cert_file), str(key_file))
            ssl_server.socket = ctx.wrap_socket(ssl_server.socket, server_side=True)
            threading.Thread(target=ssl_server.serve_forever, daemon=True).start()
            log.info(f"[HTTPS] Secure UI: https://localhost:{https_port}")
    except (OSError, ssl.SSLError, ValueError) as e:
        log.warning(f"[HTTPS] Failed to start: {e}")


def _start_https_uvicorn(bind_addr: str, asgi_app) -> None:
    """Start a second uvicorn instance on the HTTPS port with SSL (uvicorn path only).

    If SALMALM_HTTPS=1 or SALMALM_HTTPS_PORT is set, generates a self-signed cert
    (same as _start_https_if_configured) and launches uvicorn with ssl_keyfile /
    ssl_certfile so the ASGI app is served over TLS.
    """
    https_port = int(os.environ.get("SALMALM_HTTPS_PORT", 0))
    if not https_port and os.environ.get("SALMALM_HTTPS", "").lower() not in ("1", "true", "yes"):
        return
    https_port = https_port or 18443
    try:
        import ssl as _ssl
        import uvicorn as _uvicorn

        cert_dir = DATA_DIR / ".certs"
        cert_dir.mkdir(exist_ok=True)
        cert_file = cert_dir / "salmalm.pem"
        key_file = cert_dir / "salmalm-key.pem"

        # Generate self-signed cert if missing
        if not cert_file.exists() or not key_file.exists():
            import subprocess
            subprocess.run(
                [
                    "openssl", "req", "-x509", "-newkey", "rsa:2048",
                    "-keyout", str(key_file), "-out", str(cert_file),
                    "-days", "3650", "-nodes", "-batch", "-subj", "/CN=localhost",
                ],
                capture_output=True, timeout=30,
            )
            log.info("[HTTPS] Self-signed certificate generated")

        if not cert_file.exists() or not key_file.exists():
            log.warning("[HTTPS] Certificate generation failed — HTTPS not started")
            return

        https_config = _uvicorn.Config(
            asgi_app,
            host=bind_addr,
            port=https_port,
            log_level="warning",
            access_log=False,
            loop="asyncio",
            ws="websockets",
            ssl_keyfile=str(key_file),
            ssl_certfile=str(cert_file),
            timeout_keep_alive=75,
            timeout_graceful_shutdown=10,
        )
        https_server = _uvicorn.Server(https_config)
        threading.Thread(target=https_server.run, daemon=True).start()
        log.info(f"[HTTPS] Secure UI: https://localhost:{https_port} (uvicorn TLS)")
    except (ImportError, OSError, Exception) as e:
        log.warning(f"[HTTPS] uvicorn TLS startup failed: {e}")


async def _handle_ws_msg(client, data: dict) -> None:
    """Handle incoming WebSocket message."""
    msg_type = data.get("type", "message")
    if msg_type == "ping":
        await client.send_json({"type": "pong"})
        return
    if msg_type != "message":
        return
    text = data.get("text", "").strip()
    session_id = data.get("session") or client.session_id or "web"
    image_b64 = data.get("image")
    image_mime = data.get("image_mime", "image/png")
    if not text and not image_b64:
        await client.send_json({"type": "error", "error": "Empty message"})
        return
    stream = StreamingResponse(client)
    await client.send_json({"type": "typing", "status": "typing"})

    async def on_tool(name: str, args) -> None:
        """Forward tool call to WS client."""
        await stream.send_tool_call(name, args)

    async def on_status(status_type, detail) -> None:
        """Forward engine status to WS client."""
        await client.send_json({"type": "typing", "status": status_type, "detail": detail})

    try:
        from salmalm.core.engine import process_message
        from salmalm.core import get_session as _gs_ws

        image_data = (image_b64, image_mime) if image_b64 else None
        _sess_ws = _gs_ws(session_id)
        _model_ov_ws = getattr(_sess_ws, "model_override", None)
        if _model_ov_ws == "auto":
            _model_ov_ws = None
        response = await process_message(
            session_id,
            text or "",
            image_data=image_data,
            model_override=_model_ov_ws,
            on_tool=on_tool,
            on_status=on_status,
        )
        await stream.send_done(response)
    except Exception as e:
        await stream.send_error(str(e)[:200])


async def _setup_services(host: str, port: int, httpd, server_thread, url: str) -> None:
    """Setup vault, channels, background services (phases 5-12)."""
    _auto_unlock_vault()
    # ── Phase 6: WebSocket Server ──
    ws_port = int(os.environ.get("SALMALM_WS_PORT", 18801))
    try:
        ws_server.port = ws_port
        await ws_server.start()
    except Exception as e:
        log.error(f"WebSocket server failed: {e}")

    @ws_server.on_message
    async def handle_ws_message(client, data: dict) -> None:
        """Handle ws message."""
        await _handle_ws_msg(client, data)

    @ws_server.on_connect
    async def handle_ws_connect(client) -> None:
        """Handle ws connect."""
        await client.send_json({"type": "welcome", "version": VERSION, "session": client.session_id})

    # ── Phase 7: RAG Engine ──
    try:
        rag_engine.reindex(force=True)
    except Exception as e:
        log.warning(f"RAG init error: {e}")

    # ── Phase 8: MCP (Model Context Protocol) ──
    try:
        mcp_manager.load_config()
        from salmalm.tools import TOOL_DEFINITIONS, execute_tool

        async def mcp_tool_executor(name: str, args):
            """Mcp tool executor."""
            return execute_tool(name, args)

        mcp_manager.server.set_tools(TOOL_DEFINITIONS, mcp_tool_executor)
    except Exception as e:
        log.warning(f"MCP init error: {e}")

    # ── Phase 9: Cron Scheduler + Background Tasks ──
    llm_cron = LLMCronManager()
    llm_cron.load_jobs()
    _core._llm_cron = llm_cron  # type: ignore[attr-defined]

    # Schedule audit log cleanup (once daily)
    from salmalm.core import audit_log_cleanup

    cron.add_job("audit_cleanup", 86400, audit_log_cleanup, days=30)

    # ── Phase 10: Self-test, Nodes, Plugins, Cron start ──
    selftest = health_monitor.startup_selftest()
    log.info(f"[SELFTEST] {selftest.get('passed', 0)}/{selftest.get('total', 0)} passed")
    node_manager.load_config()
    PluginLoader.scan()
    asyncio.create_task(cron.run())

    # ── Phase 10.5: Auto-detect Ollama ──
    try:
        from salmalm.core.llm_router import detect_ollama
        ollama_info = detect_ollama()
        if ollama_info["available"]:
            models = ollama_info["models"]
            log.info(f"[OLLAMA] Auto-detected: {len(models)} models at {ollama_info['url']}")
            if models:
                log.info(f"[OLLAMA] Models: {', '.join(models[:10])}")
        else:
            log.debug("[OLLAMA] Not detected at localhost:11434")
    except Exception as e:
        log.debug(f"[OLLAMA] Detection skipped: {e}")

    # ── Phase 11: Telegram Bot ──
    await _start_telegram_bot()

    # ── Phase 12: Discord Bot ──
    await _start_discord_bot()

    # Browser auto-open is handled by run_server() via SALMALM_OPEN_BROWSER=1.
    # Do NOT open browser here — _setup_services is called on every start
    # including auto-restarts, and silently opening a new tab each time is
    # disruptive. (was: unconditional webbrowser.open — removed)

    # ── Graceful Shutdown ──
    _shutdown_count = [0]

    def _handle_shutdown(signum, frame):
        """Handle shutdown."""
        _shutdown_count[0] += 1
        if _shutdown_count[0] >= 2:
            log.warning("[SHUTDOWN] Forced exit (second signal)")
            os._exit(1)
        log.info(f"[SHUTDOWN] Signal received ({signum}), initiating graceful shutdown...")
        asyncio.get_event_loop().call_soon_threadsafe(_trigger_shutdown.set)

    _trigger_shutdown = asyncio.Event()


def _init_extensions() -> None:
    """Phase 3: Initialize hooks, plugins, agents."""
    try:
        from .hooks import hook_manager

        hook_manager.fire("on_startup", {"message": f"{APP_NAME} v{VERSION} starting"})
    except Exception as e:  # noqa: broad-except
        log.debug(f"Suppressed: {e}")
    # Plugins: OFF by default (arbitrary code execution risk)
    # Enable with SALMALM_PLUGINS=1
    if os.environ.get("SALMALM_PLUGINS", "0") == "1":
        try:
            from .plugin_manager import plugin_manager

            plugin_manager.scan_and_load()
            log.warning("[PLUGINS] ⚠️ Plugins enabled — arbitrary code execution is possible")
        except Exception as e:
            log.warning(f"Plugin scan error: {e}")
    else:
        log.info("[PLUGINS] Disabled (set SALMALM_PLUGINS=1 to enable)")
    try:
        from .features.agents import agent_manager

        agent_manager.scan()
    except Exception as e:
        log.warning(f"Agent scan error: {e}")


def _start_tunnel(port: int) -> None:
    """Start Cloudflare Tunnel in background. Prints public URL + QR code."""
    import shutil
    import subprocess
    import threading

    cf = shutil.which("cloudflared")
    if not cf:
        print("\n  ⚠️  cloudflared not found. Install it:")
        print("     https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        print("     Or: brew install cloudflared / apt install cloudflared / winget install Cloudflare.cloudflared\n")
        return

    def _run_tunnel():
        """Run tunnel and parse URL from stderr."""
        proc = subprocess.Popen(
            [cf, "tunnel", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        import re

        for line in proc.stderr:
            m = re.search(r"(https://[a-z0-9\-]+\.trycloudflare\.com)", line)
            if m:
                tunnel_url = m.group(1)
                print(f"\n  🌐 Tunnel URL: {tunnel_url}")
                print(f"  📱 폰에서 이 URL을 열거나, QR 코드를 스캔하세요:\n")
                try:
                    _print_qr(tunnel_url)
                except Exception as e:
                    log.debug(f"[TUNNEL] QR print skipped: {e}")
                break

    def _print_qr(url: str) -> None:
        """Print QR code to terminal using Unicode blocks."""
        try:
            api = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={url}&format=svg"
            print(f"  QR: {api}\n  (또는 브라우저에서 직접 접속: {url})\n")
        except Exception:
            print(f"  → {url}\n")

    t = threading.Thread(target=_run_tunnel, daemon=True, name="cloudflare-tunnel")
    t.start()


async def run_server():
    """Main async entry point — boot all services."""
    # ── PID file — enables `salmalm stop` without systemd ──
    _pid_path = DATA_DIR / "salmalm.pid"
    try:
        _pid_path.write_text(str(os.getpid()))
    except Exception as _e:
        log.warning(f"[PID] Could not write PID file: {_e}")

    # ── Phase 1: Database & Core State ──
    _init_audit_db()
    _restore_usage()
    # Restore sessions from disk so dashboard/status reflect history
    from salmalm.core.session_store import restore_all_sessions_from_disk
    restore_all_sessions_from_disk()
    audit_log("startup", f"{APP_NAME} v{VERSION}")
    MEMORY_DIR.mkdir(exist_ok=True)

    # ── Audit checkpoint cron (every 6 hours) ──
    from salmalm.features.audit_cron import start_audit_cron

    start_audit_cron(interval_hours=6)

    # ── Phase 2: SLA Monitoring ──
    try:
        from .features.sla import uptime_monitor, watchdog

        uptime_monitor.on_startup()
        watchdog.start()
        log.info("[SLA] Uptime monitor + watchdog initialized")
    except (ImportError, OSError, RuntimeError) as e:
        log.warning(f"[SLA] Init error: {e}")

    _init_extensions()

    # ── Phase 4: HTTP Server ──
    port = int(os.environ.get("SALMALM_PORT", 18800))
    # Always default to 127.0.0.1 (loopback only).
    # WSL users: set SALMALM_BIND=0.0.0.0 to allow Windows browser access.
    bind_addr = os.environ.get("SALMALM_BIND", "127.0.0.1")
    if bind_addr == "0.0.0.0":
        log.warning(
            "[WARN] Binding to 0.0.0.0 — server is accessible from LAN. "
            "Set SALMALM_BIND=127.0.0.1 to restrict to localhost."
        )
        # External exposure safety checks
        from salmalm.web.middleware import check_external_exposure_safety

        exposure_warnings = check_external_exposure_safety(bind_addr, WebHandler)
        for w in exposure_warnings:
            log.warning(w)
    url = f"http://{bind_addr}:{port}"

    # ── Pre-flight: check port availability ──────────────────────────────────
    import socket as _socket
    def _port_in_use(host: str, p: int) -> bool:
        with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as _s:
            _s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
            try:
                _s.bind((host, p))
                return False
            except OSError:
                return True

    if _port_in_use(bind_addr, port):
        print(
            f"\n❌  Port {port} is already in use.\n"
            f"   SalmAlm may already be running.\n\n"
            f"   To check:  salmalm service status\n"
            f"   To stop:   salmalm service stop\n"
            f"   To use a different port: SALMALM_PORT=18802 salmalm\n"
        )
        raise SystemExit(1)

    # ── Try uvicorn (ASGI) first; fall back to ThreadingHTTPServer ──────────
    _uvicorn_ok = False
    server = None
    web_thread = None

    try:
        import uvicorn
        from salmalm.web.asgi import create_asgi_app
        asgi_app = create_asgi_app()
        uvicorn_config = uvicorn.Config(
            asgi_app,
            host=bind_addr,
            port=port,
            log_level="warning",
            access_log=False,
            loop="asyncio",
            ws="websockets",
            timeout_keep_alive=75,   # > nginx default 60s
            timeout_graceful_shutdown=10,
        )
        uvicorn_server = uvicorn.Server(uvicorn_config)
        web_thread = threading.Thread(
            target=uvicorn_server.run, daemon=True,
            name="uvicorn-main",
        )
        web_thread.start()
        # Give uvicorn time to bind; verify thread is still alive
        import time as _time
        _time.sleep(0.5)
        if not web_thread.is_alive():
            raise OSError(f"uvicorn thread died immediately — port {port} likely stolen between check and bind")
        _uvicorn_ok = True
        log.info("[WEB] Running on uvicorn (ASGI)")
        server = uvicorn_server  # keep reference for shutdown
        # Start HTTPS uvicorn on separate port if configured
        _start_https_uvicorn(bind_addr, asgi_app)
    except ImportError:
        log.warning("[WEB] uvicorn not installed — falling back to ThreadingHTTPServer")
        log.warning("[WEB] Install for better stability: pip install 'uvicorn[standard]'")
    except Exception as e:
        log.warning(f"[WEB] uvicorn startup failed ({e}) — falling back to ThreadingHTTPServer")

    if not _uvicorn_ok:
        http.server.ThreadingHTTPServer.allow_reuse_address = True
        server = http.server.ThreadingHTTPServer((bind_addr, port), WebHandler)
        _start_https_if_configured(bind_addr)
        web_thread = threading.Thread(target=server.serve_forever, daemon=True)
        web_thread.start()

    log.info(f"[WEB] Web UI: {url}")
    print(f"\n  😈 SalmAlm v{VERSION} running at {url}\n  Press Ctrl+C to stop.\n", flush=True)

    # Auto-open browser if requested (--open flag or SALMALM_OPEN_BROWSER=1)
    if os.environ.get("SALMALM_OPEN_BROWSER", "") == "1":
        import webbrowser

        webbrowser.open(url)

    # Cloudflare Tunnel (--tunnel flag or SALMALM_TUNNEL=1)
    if os.environ.get("SALMALM_TUNNEL", "") == "1":
        _start_tunnel(port)

    await _setup_services(bind_addr, port, server, web_thread, url)

    _ws_port = int(os.environ.get("SALMALM_WS_PORT", 18801))
    _print_banner(bind_addr=bind_addr, port=port, ws_port=_ws_port)

    # ── Graceful Shutdown Setup ──
    _trigger_shutdown = asyncio.Event()
    _shutdown_count = [0]

    def _handle_shutdown(signum, frame):
        """Handle shutdown signal."""
        _shutdown_count[0] += 1
        if _shutdown_count[0] >= 2:
            log.warning("[SHUTDOWN] Forced exit (second signal)")
            os._exit(1)
        log.info(f"[SHUTDOWN] Signal received ({signum}), initiating graceful shutdown...")
        asyncio.get_event_loop().call_soon_threadsafe(_trigger_shutdown.set)

    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_shutdown)
        except (OSError, ValueError):
            pass

    # Wait for shutdown signal
    await _trigger_shutdown.wait()

    # === Shutdown Sequence ===
    log.info("[SHUTDOWN] Phase 1: Stop accepting new requests")
    from salmalm.core.engine import begin_shutdown, wait_for_active_requests

    begin_shutdown()

    log.info("[SHUTDOWN] Phase 2: Wait for active LLM requests (max 10s)")
    wait_for_active_requests(timeout=10.0)

    log.info("[SHUTDOWN] Phase 3: Notify WebSocket clients")
    await ws_server.shutdown()

    log.info("[SHUTDOWN] Phase 4: Stop cron scheduler")
    cron.stop()

    log.info("[SHUTDOWN] Phase 5: Close DB connections")
    from salmalm.core import close_all_db_connections

    close_all_db_connections()

    log.info("[SHUTDOWN] Phase 6: Stop HTTP server")
    try:
        import inspect as _inspect
        if _inspect.iscoroutinefunction(getattr(type(server), "shutdown", None)):
            # uvicorn.Server.shutdown() is a coroutine — must await
            server.should_exit = True          # signal the run loop first
            await asyncio.wait_for(server.shutdown(), timeout=5.0)
        else:
            server.shutdown()                  # ThreadingHTTPServer — sync
    except (asyncio.TimeoutError, Exception) as _e:
        log.debug(f"[SHUTDOWN] HTTP server stop: {_e}")
        try:
            server.should_exit = True          # fallback: just set the flag
        except AttributeError:
            pass

    # Fire on_shutdown hook
    try:
        from .hooks import hook_manager

        hook_manager.fire("on_shutdown", {"message": "Server shutting down"})
    except Exception as e:  # noqa: broad-except
        log.debug(f"Suppressed: {e}")

    # SLA: Graceful shutdown
    try:
        from .features.sla import uptime_monitor, watchdog

        watchdog.stop()
        uptime_monitor.on_shutdown()
        log.info("[SHUTDOWN] SLA cleanup complete")
    except Exception as e:
        log.warning(f"[SHUTDOWN] SLA cleanup error: {e}")

    try:
        from salmalm.features.audit_cron import stop_audit_cron

        stop_audit_cron()
    except Exception as e:  # noqa: broad-except
        log.debug(f"Suppressed: {e}")
    try:
        audit_log("shutdown", f"{APP_NAME} v{VERSION} graceful shutdown")
    except Exception as e:  # noqa: broad-except
        pass  # DB may already be closed
    # ── PID file cleanup ──
    try:
        _pid_path = DATA_DIR / "salmalm.pid"
        if _pid_path.exists():
            _pid_path.unlink()
    except Exception:
        pass
    log.info("[SHUTDOWN] Complete. Goodbye! 😈")
