"""Server bootstrap — start all SalmAlm services."""

from __future__ import annotations

import asyncio
import http.server
import os
import signal
import sys
import threading

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
    _sessions,
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


def _check_for_updates() -> str:
    """Check PyPI for newer version. Returns update message or empty string."""
    try:
        from salmalm.utils.http import request_json as _rj

        data = _rj(
            "https://pypi.org/pypi/salmalm/json",
            headers={"User-Agent": f"SalmAlm/{VERSION}", "Accept": "application/json"},
            timeout=5,
        )
        latest = data.get("info", {}).get("version", "")

        def _ver_tuple(v) -> tuple:
            """Ver tuple."""
            return tuple(int(x) for x in v.split("."))

        if latest and _ver_tuple(latest) > _ver_tuple(VERSION):
            if getattr(sys, "frozen", False):
                return (
                    f"⬆️  New version {latest} available!\n"
                    f"   Download: https://github.com/hyunjun6928-netizen/salmalm/releases/latest"
                )
            return f"⬆️  New version {latest} found! Upgrade: pip install --upgrade salmalm"
    except Exception as e:  # noqa: broad-except
        pass  # silently skip if no network
    return ""


async def _start_telegram_bot() -> None:
    """Phase 11: Start Telegram bot polling."""


if not vault.is_unlocked:
    log.warning("[TELEGRAM] Skipped — vault is locked. Unlock vault to enable Telegram.")
if vault.is_unlocked:
    tg_token = vault.get("telegram_token")
    tg_owner = vault.get("telegram_owner_id")
    log.info(
        f"[TELEGRAM] token={'YES' if tg_token else 'NO'}, owner={'YES' if tg_owner else 'NO'}, vault_unlocked={vault.is_unlocked}"
    )
    if tg_token and tg_owner:
        telegram_bot.configure(tg_token, tg_owner)
        log.info("[TELEGRAM] Bot configured, starting polling...")
        import os as _os2

        _wh_url = _os2.environ.get("SALMALM_TELEGRAM_WEBHOOK_URL") or vault.get("telegram_webhook_url") or ""
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
if vault.is_unlocked:
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
                import time as _t

                _channel_id = raw_data.get("channel_id", "")
                _session_id = f"discord_{_channel_id}"
                _start = _t.time()
                from salmalm.core.engine import process_message

                response = await process_message(_session_id, content, on_token=on_token)
                _elapsed = _t.time() - _start
                return f"{response}\n\n⏱️ {_elapsed:.1f}s" if response else None

            discord_bot.on_message(_discord_message_handler)
            asyncio.create_task(discord_bot.poll())
            log.info("[DISCORD] Bot configured, message handler registered, starting polling...")
        except Exception as e:
            log.warning(f"[DISCORD] Failed to start: {e}")

_rag_stats = rag_engine.get_stats()  # noqa: F841
try:
    st = f"{selftest['passed']}/{selftest['total']}"  # noqa: F821
except NameError:
    st = "skipped"
update_msg = _check_for_updates()
log.info(
    f"\n╔══════════════════════════════════════════════╗\n"
    f"║  😈 {APP_NAME} v{VERSION}                   ║\n"
    f"║  Web UI:    http://{bind_addr}:{port:<5}           ║\n"
    f"║  WebSocket: ws://{bind_addr}:{ws_port:<5}            ║\n"
    f"║  Vault:     {'🔓 Unlocked' if vault.is_unlocked else '🔒 Locked — open Web UI'}         ║\n"
    f"║  Crypto:    {'AES-256-GCM' if HAS_CRYPTO else ('HMAC-CTR (fallback)' if os.environ.get('SALMALM_VAULT_FALLBACK') else 'Vault disabled')}            ║\n"
    f"║  Self-test: {st}                               ║\n"
    f"╚══════════════════════════════════════════════╝"
)
if update_msg:
    log.info(f"  {update_msg}")


def _auto_unlock_vault() -> None:
    """Phase 5: Vault auto-unlock with cascade fallbacks."""


_auto_unlock_vault()
_core.set_telegram_bot(telegram_bot)


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
        return
    # 2. Try .vault_auto file (WSL/no-keychain fallback)
    _try_vault_auto_file()
    if vault.is_unlocked:
        return
    # 3. Try env var (deprecated)
    vault_pw = os.environ.get("SALMALM_VAULT_PW")
    if vault_pw and vault.unlock(vault_pw, save_to_keychain=True):
        log.info("[UNLOCK] Vault auto-unlocked from env")
        return
    # 4. Try empty password
    if vault.unlock(""):
        log.info("[UNLOCK] Vault auto-unlocked (no password)")
        return
    # 5. All methods failed on localhost → reset vault
    if not _is_external_bind:
        log.warning("[VAULT] All auto-unlock failed — resetting vault for setup wizard")
        try:
            VAULT_FILE.unlink(missing_ok=True)
            (VAULT_FILE.parent / ".vault_auto").unlink(missing_ok=True)
            log.info("[VAULT] Vault reset — setup wizard will run on next page load")
        except Exception as _e:
            log.error(f"[VAULT] Reset failed: {_e}")


def _try_vault_auto_file() -> None:
    """Try unlocking vault from .vault_auto file."""
    try:
        _pw_hint_file = VAULT_FILE.parent / ".vault_auto"
        if not _pw_hint_file.exists():
            return
        _hint = _pw_hint_file.read_text(encoding="utf-8").strip()
        if _hint:
            import base64 as _b64

            _auto_pw = _b64.b64decode(_hint).decode()
        else:
            _auto_pw = ""
        if vault.unlock(_auto_pw, save_to_keychain=True):
            log.info("[UNLOCK] Vault auto-unlocked from .vault_auto")
    except Exception as _e:
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
    except Exception as e:
        log.warning(f"[HTTPS] Failed to start: {e}")


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
    node_manager.load_config()
    PluginLoader.scan()
    asyncio.create_task(cron.run())

    # ── Phase 11: Telegram Bot ──
    await _start_telegram_bot()

    # ── Phase 12: Discord Bot ──
    await _start_discord_bot()

    # Auto-open browser on first start
    try:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{port}")
    except Exception as e:  # noqa: broad-except
        log.debug(f"Suppressed: {e}")

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
        from .agents import agent_manager

        agent_manager.scan()
    except Exception as e:
        log.warning(f"Agent scan error: {e}")


async def run_server():
    """Main async entry point — boot all services."""
    # ── Phase 1: Database & Core State ──
    _init_audit_db()
    _restore_usage()
    audit_log("startup", f"{APP_NAME} v{VERSION}")
    MEMORY_DIR.mkdir(exist_ok=True)

    # ── Audit checkpoint cron (every 6 hours) ──
    from salmalm.features.audit_cron import start_audit_cron

    start_audit_cron(interval_hours=6)

    # ── Phase 2: SLA Monitoring ──
    try:
        from .sla import uptime_monitor, watchdog

        uptime_monitor.on_startup()
        watchdog.start()
        log.info("[SLA] Uptime monitor + watchdog initialized")
    except Exception as e:
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
    server = http.server.ThreadingHTTPServer((bind_addr, port), WebHandler)

    # Auto-generate self-signed cert for HTTPS (enables microphone, camera, etc.)
    _start_https_if_configured(bind_addr)

    web_thread = threading.Thread(target=server.serve_forever, daemon=True)
    web_thread.start()
    url = f"http://{bind_addr}:{port}"
    log.info(f"[WEB] Web UI: {url}")
    # Always print to stdout so users see the URL even without logging config
    print(f"\n  😈 SalmAlm v{VERSION} running at {url}\n  Press Ctrl+C to stop.\n", flush=True)

    # Auto-open browser if requested (--open flag or SALMALM_OPEN_BROWSER=1)
    if os.environ.get("SALMALM_OPEN_BROWSER", "") == "1":
        import webbrowser

        webbrowser.open(url)

    await _setup_services(host, port, httpd, server_thread, url)

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

    log.info("[SHUTDOWN] Phase 2: Wait for active LLM requests (max 30s)")
    wait_for_active_requests(timeout=30.0)

    log.info("[SHUTDOWN] Phase 3: Notify WebSocket clients")
    await ws_server.shutdown()

    log.info("[SHUTDOWN] Phase 4: Stop cron scheduler")
    cron.stop()

    log.info("[SHUTDOWN] Phase 5: Close DB connections")
    from salmalm.core import close_all_db_connections

    close_all_db_connections()

    log.info("[SHUTDOWN] Phase 6: Stop HTTP server")
    server.shutdown()

    # Fire on_shutdown hook
    try:
        from .hooks import hook_manager

        hook_manager.fire("on_shutdown", {"message": "Server shutting down"})
    except Exception as e:  # noqa: broad-except
        log.debug(f"Suppressed: {e}")

    # SLA: Graceful shutdown
    try:
        from .sla import uptime_monitor, watchdog

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
    log.info("[SHUTDOWN] Complete. Goodbye! 😈")
