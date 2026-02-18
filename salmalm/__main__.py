"""Allow running salmalm as: python -m salmalm or `salmalm` CLI."""
from __future__ import annotations

import os
import sys


def main() -> None:
    """CLI entry point — start the salmalm server."""
    # Ensure working directory has required folders
    for d in ('memory', 'workspace', 'uploads', 'plugins'):
        os.makedirs(d, exist_ok=True)

    # Try to find server.py (development mode)
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    dev_server = os.path.join(os.path.dirname(pkg_dir), 'server.py')

    if os.path.exists(dev_server):
        # Development: run server.py directly
        import runpy
        os.chdir(os.path.dirname(dev_server))
        if os.path.dirname(dev_server) not in sys.path:
            sys.path.insert(0, os.path.dirname(dev_server))
        runpy.run_path(dev_server, run_name='__main__')
    else:
        # pip install mode: import and run directly
        import asyncio
        import http.server
        import threading
        import time

        from salmalm.constants import (
            VERSION, APP_NAME, VAULT_FILE, MEMORY_DIR, BASE_DIR
        )
        from salmalm.crypto import vault, log, HAS_CRYPTO
        from salmalm.core import (
            _init_audit_db, _restore_usage, audit_log,
            _sessions, cron, LLMCronManager, PluginLoader
        )
        from salmalm.telegram import telegram_bot
        from salmalm.web import WebHandler
        from salmalm.ws import ws_server, StreamingResponse
        from salmalm.rag import rag_engine
        from salmalm.mcp import mcp_manager
        from salmalm.nodes import node_manager
        from salmalm.stability import health_monitor, watchdog_tick
        import salmalm.core as _core

        def _check_for_updates() -> str:
            """Check PyPI for newer version. Returns update message or empty string."""
            try:
                import urllib.request, json as _json
                req = urllib.request.Request(
                    'https://pypi.org/pypi/salmalm/json',
                    headers={'User-Agent': f'SalmAlm/{VERSION}', 'Accept': 'application/json'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = _json.loads(resp.read())
                latest = data.get('info', {}).get('version', '')
                if latest and latest != VERSION:
                    if getattr(sys, 'frozen', False):
                        return (f"⬆️  New version {latest} available!\n"
                                f"   Download: https://github.com/hyunjun6928-netizen/salmalm/releases/latest")
                    return f"⬆️  New version {latest} found! Upgrade: pip install --upgrade salmalm"
            except Exception:
                pass  # silently skip if no network
            return ""

        async def _main():
            _init_audit_db()
            _restore_usage()
            audit_log('startup', f'{APP_NAME} v{VERSION}')
            MEMORY_DIR.mkdir(exist_ok=True)

            port = int(os.environ.get('SALMALM_PORT', 18800))
            server = http.server.ThreadingHTTPServer(('127.0.0.1', port), WebHandler)
            web_thread = threading.Thread(target=server.serve_forever, daemon=True)
            web_thread.start()
            log.info(f"🌐 Web UI: http://127.0.0.1:{port}")

            vault_pw = os.environ.get('SALMALM_VAULT_PW')
            if vault_pw and VAULT_FILE.exists():
                if vault.unlock(vault_pw):
                    log.info("🔓 Vault auto-unlocked from env")

            _core._tg_bot = telegram_bot

            ws_port = int(os.environ.get('SALMALM_WS_PORT', 18801))
            try:
                ws_server.port = ws_port
                await ws_server.start()
            except Exception as e:
                log.error(f"WebSocket server failed: {e}")

            @ws_server.on_message
            async def handle_ws_message(client, data):
                msg_type = data.get('type', 'message')
                if msg_type == 'ping':
                    await client.send_json({'type': 'pong'})
                    return
                if msg_type == 'message':
                    text = data.get('text', '').strip()
                    session_id = client.session_id or 'web'
                    if not text:
                        await client.send_json({'type': 'error', 'error': 'Empty message'})
                        return
                    stream = StreamingResponse(client)
                    async def on_tool(name, args):
                        await stream.send_tool_call(name, args)
                    try:
                        from salmalm.engine import process_message
                        response = await process_message(session_id, text, on_tool=on_tool)
                        await stream.send_done(response)
                    except Exception as e:
                        await stream.send_error(str(e)[:200])

            @ws_server.on_connect
            async def handle_ws_connect(client):
                await client.send_json({
                    'type': 'welcome', 'version': VERSION,
                    'session': client.session_id,
                })

            try:
                rag_engine.reindex(force=True)
            except Exception as e:
                log.warning(f"RAG init error: {e}")

            try:
                mcp_manager.load_config()
                from salmalm.tools import TOOL_DEFINITIONS, execute_tool
                async def mcp_tool_executor(name, args):
                    return execute_tool(name, args)
                mcp_manager.server.set_tools(TOOL_DEFINITIONS, mcp_tool_executor)
            except Exception as e:
                log.warning(f"MCP init error: {e}")

            llm_cron = LLMCronManager()
            llm_cron.load_jobs()
            _core._llm_cron = llm_cron

            selftest = health_monitor.startup_selftest()
            node_manager.load_config()
            PluginLoader.scan()
            asyncio.create_task(cron.run())

            if vault.is_unlocked:
                tg_token = vault.get('telegram_token')
                tg_owner = vault.get('telegram_owner_id')
                if tg_token and tg_owner:
                    telegram_bot.configure(tg_token, tg_owner)
                    asyncio.create_task(telegram_bot.poll())

            rag_stats = rag_engine.get_stats()
            st = f"{selftest['passed']}/{selftest['total']}"
            update_msg = _check_for_updates()
            print(f"""
╔══════════════════════════════════════════════╗
║  😈 {APP_NAME} v{VERSION}                   ║
║  Web UI:    http://127.0.0.1:{port:<5}           ║
║  WebSocket: ws://127.0.0.1:{ws_port:<5}            ║
║  Vault:     {'🔓 Unlocked' if vault.is_unlocked else '🔒 Locked — open Web UI'}         ║
║  Crypto:    {'AES-256-GCM' if HAS_CRYPTO else 'HMAC-CTR (fallback)'}            ║
║  Self-test: {st}                               ║
╚══════════════════════════════════════════════╝
""")
            if update_msg:
                print(f"  {update_msg}\n")
            try:
                while True:
                    await asyncio.sleep(1)
            except (KeyboardInterrupt, SystemExit):
                log.info("Shutting down...")
                server.shutdown()

        asyncio.run(_main())


if __name__ == '__main__':
    main()
