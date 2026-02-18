#!/usr/bin/env python3
"""
삶앎 (SalmAlm) v0.7.0 — Personal AI Gateway
Modularized entry point.

Modules (19):
  salmalm/constants.py   — paths, costs, thresholds
  salmalm/crypto.py      — Vault (AES-256-GCM), logging
  salmalm/core.py        — audit, cache, usage, router, compaction,
                           search, subagent, skills, session, cron
  salmalm/llm.py         — LLM API calls (Anthropic/OpenAI/xAI/Google)
  salmalm/tools.py       — 30 tool definitions + execute_tool
  salmalm/prompt.py      — system prompt builder
  salmalm/engine.py      — Intelligence Engine (Plan→Execute→Reflect)
  salmalm/telegram.py    — Telegram bot
  salmalm/web.py         — Web UI + HTTP handler
  salmalm/ws.py          — WebSocket server (RFC 6455)
  salmalm/rag.py         — RAG engine (BM25 + SQLite)
  salmalm/mcp.py         — MCP server + client (JSON-RPC 2.0)
  salmalm/browser.py     — Browser automation (Chrome CDP)
  salmalm/nodes.py       — Remote node control (SSH/HTTP)
  salmalm/stability.py   — Health monitor + circuit breaker + watchdog
  salmalm/auth.py        — Multi-user auth, RBAC, rate limiting
  salmalm/tls.py         — Self-signed TLS cert generation
  salmalm/logging_ext.py — Structured JSON logging + rotation
  salmalm/docs.py        — Auto-generated API documentation
"""

import asyncio
import http.server
import os
import threading
import time

from salmalm.constants import *
from salmalm.crypto import vault, log, HAS_CRYPTO
from salmalm.core import (
    _init_audit_db, _restore_usage, audit_log,
    _sessions, cron, CronScheduler
)
from salmalm.telegram import telegram_bot
from salmalm.web import WebHandler
from salmalm.ws import ws_server, StreamingResponse
from salmalm.rag import rag_engine
from salmalm.mcp import mcp_manager
from salmalm.nodes import node_manager
from salmalm.stability import health_monitor, watchdog_tick
import salmalm.core as _core


async def main():
    _init_audit_db()
    _restore_usage()
    audit_log('startup', f'{APP_NAME} v{VERSION}')

    MEMORY_DIR.mkdir(exist_ok=True)

    # Start web server
    port = int(os.environ.get('SALMALM_PORT', 18800))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), WebHandler)
    web_thread = threading.Thread(target=server.serve_forever, daemon=True)
    web_thread.start()
    log.info(f"🌐 Web UI: http://127.0.0.1:{port}")

    # Auto-unlock vault
    vault_pw = os.environ.get('SALMALM_VAULT_PW')
    if vault_pw and VAULT_FILE.exists():
        if vault.unlock(vault_pw):
            log.info("🔓 Vault auto-unlocked from env")
        else:
            log.warning("🔒 Vault auto-unlock failed")

    # Wire up cross-references
    _core._tg_bot = telegram_bot

    # ══ WebSocket server ══
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
            'type': 'welcome',
            'version': VERSION,
            'session': client.session_id,
        })

    # ══ RAG engine — initial index ══
    try:
        rag_engine.reindex(force=True)
        log.info(f"🧠 RAG index ready: {rag_engine.get_stats()}")
    except Exception as e:
        log.warning(f"RAG init error: {e}")

    # ══ MCP — load configured servers ══
    try:
        mcp_manager.load_config()
        # Set up MCP server with 삶앎 tools
        from salmalm.tools import TOOL_DEFINITIONS, execute_tool
        async def mcp_tool_executor(name, args):
            return execute_tool(name, args)
        mcp_manager.server.set_tools(TOOL_DEFINITIONS, mcp_tool_executor)
        log.info(f"🔌 MCP ready: {len(mcp_manager.list_servers())} external servers")
    except Exception as e:
        log.warning(f"MCP init error: {e}")

    # ══ Heartbeat: LLM-powered autonomous action (30min) ══
    async def heartbeat_job():
        if not vault.is_unlocked:
            return
        active = len([s for s in _sessions.values() if s.messages])
        log.info(f"💓 Heartbeat: {active} active sessions")

        # Daily file creation
        today = time.strftime('%Y-%m-%d')
        daily = MEMORY_DIR / f'{today}.md'
        if not daily.exists():
            daily.write_text(f'# {today} 일일 기록\n\n', encoding='utf-8')

        # Stale session cleanup
        now = time.time()
        stale = [k for k, s in _sessions.items()
                 if now - s.last_active > 7200 and k != 'web']
        for k in stale:
            del _sessions[k]
            log.info(f"🧹 Cleaned stale session: {k}")

        # Read HEARTBEAT.md and run through LLM
        heartbeat_file = BASE_DIR / 'HEARTBEAT.md'
        if heartbeat_file.exists():
            try:
                from salmalm.engine import process_message
                hb_content = heartbeat_file.read_text(encoding='utf-8')
                prompt = f"[HEARTBEAT] HEARTBEAT.md 내용을 읽고 지시를 따르세요. 할 일이 없으면 'HEARTBEAT_OK'만 응답:\n\n{hb_content}"
                response = await process_message('heartbeat', prompt)
                if response and 'HEARTBEAT_OK' not in response:
                    log.info(f"💓 Heartbeat action: {response[:100]}")
                    # Notify owner via Telegram
                    if telegram_bot.token and telegram_bot.owner_id:
                        telegram_bot.send_message(
                            telegram_bot.owner_id,
                            f"💓 삶앎 하트비트 알림\n{response[:1000]}")
                else:
                    log.info("💓 Heartbeat: OK (nothing to do)")
            except Exception as e:
                log.error(f"Heartbeat LLM error: {e}")

    # cron.add_job('heartbeat', 1800, heartbeat_job)  # 주인놈 요청으로 비활성화

    # ══ LLM Cron Jobs: scheduled tasks with LLM execution ══
    from salmalm.core import LLMCronManager
    llm_cron = LLMCronManager()
    llm_cron.load_jobs()  # Load persisted cron jobs
    _core._llm_cron = llm_cron

    async def llm_cron_tick():
        if not vault.is_unlocked:
            return
        await llm_cron.tick()

    # cron.add_job('llm_cron', 60, llm_cron_tick)  # 주인놈 요청으로 비활성화

    # ══ Startup self-test ══
    selftest = health_monitor.startup_selftest()
    if not selftest['all_ok']:
        log.warning(f"⚠️ Self-test: {selftest['passed']}/{selftest['total']} modules OK")

    # ══ Node manager ══
    node_manager.load_config()

    # ══ Plugin auto-loader ══
    from salmalm.core import PluginLoader
    PluginLoader.scan()

    # ══ Watchdog: auto-recovery every 5 min ══
    async def _watchdog():
        await watchdog_tick(health_monitor)
    # cron.add_job('watchdog', 300, _watchdog)  # 주인놈 요청으로 비활성화

    asyncio.create_task(cron.run())

    # ══ Start Telegram LAST (long-polling blocks event loop) ══
    if vault.is_unlocked:
        tg_token = vault.get('telegram_token')
        tg_owner = vault.get('telegram_owner_id')
        if tg_token and tg_owner:
            telegram_bot.configure(tg_token, tg_owner)
            asyncio.create_task(telegram_bot.poll())

    rag_stats = rag_engine.get_stats()
    mcp_count = len(mcp_manager.list_servers())
    node_count = len(node_manager.list_nodes())
    st_result = f"{selftest['passed']}/{selftest['total']}"
    print(f"""
╔══════════════════════════════════════════════╗
║  😈 {APP_NAME} v{VERSION}                   ║
║  Web UI:    http://127.0.0.1:{port:<5}           ║
║  WebSocket: ws://127.0.0.1:{ws_port:<5}            ║
║  Vault:     {'🔓 Unlocked' if vault.is_unlocked else '🔒 Locked — open Web UI'}         ║
║  Crypto:    {'AES-256-GCM' if HAS_CRYPTO else 'HMAC-CTR (fallback)'}            ║
║  Modules:   15 (self-test: {st_result})             ║
║  RAG:       {rag_stats['total_chunks']} chunks, {rag_stats['unique_terms']} terms         ║
║  MCP:       {mcp_count} server(s)                        ║
║  Nodes:     {node_count} remote node(s)                  ║
║  Browser:   CDP (Chrome DevTools Protocol)   ║
║  Watchdog:  ✅ Auto-recovery (5min cycle)    ║
╚══════════════════════════════════════════════╝
""")

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down...")
        telegram_bot.stop()
        cron.stop()
        await ws_server.stop()
        mcp_manager.shutdown()
        rag_engine.close()
        server.shutdown()
        audit_log('shutdown', 'clean')


if __name__ == '__main__':
    asyncio.run(main())
