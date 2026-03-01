"""Gateway & webhook API — Telegram, Slack, gateway nodes."""

from salmalm.security.crypto import vault, log
import json


class WebGatewayMixin:
    GET_ROUTES = {
        "/api/gateway/nodes": "_get_gateway_nodes",
    }
    POST_ROUTES = {
        "/api/config/telegram": "_post_api_config_telegram",
        "/api/gateway/register": "_post_api_gateway_register",
        "/api/gateway/heartbeat": "_post_api_gateway_heartbeat",
        "/api/gateway/unregister": "_post_api_gateway_unregister",
        "/api/gateway/dispatch": "_post_api_gateway_dispatch",
        "/webhook/slack": "_post_webhook_slack",
        "/webhook/telegram": "_post_webhook_telegram",
    }

    """Mixin providing gateway route handlers."""

    def _get_gateway_nodes(self):
        """Get gateway nodes."""
        from salmalm.features.nodes import gateway

        self._json({"nodes": gateway.list_nodes()})

    def _post_api_config_telegram(self):
        """Post api config telegram."""
        if not self._require_auth("admin"):
            return
        body = self._body
        if not vault.is_unlocked:
            self._json({"error": "Vault locked"}, 403)
            return
        vault.set("telegram_token", body.get("token", ""))
        vault.set("telegram_owner_id", body.get("owner_id", ""))
        self._json({"ok": True, "message": "Telegram config saved. Restart required."})

    def _post_api_gateway_register(self):
        """Post api gateway register."""
        body = self._body
        from salmalm.features.nodes import gateway

        node_id = body.get("node_id", "")
        url = body.get("url", "")
        if not node_id or not url:
            self._json({"error": "node_id and url required"}, 400)
            return
        result = gateway.register(  # type: ignore[assignment]
            node_id,
            url,
            token=body.get("token", ""),
            capabilities=body.get("capabilities"),
            name=body.get("name", ""),
        )
        self._json(result)  # type: ignore[arg-type]

    def _post_api_gateway_heartbeat(self):
        """Post api gateway heartbeat."""
        body = self._body
        from salmalm.features.nodes import gateway

        node_id = body.get("node_id", "")
        self._json(gateway.heartbeat(node_id))

    def _post_api_gateway_dispatch(self):
        """Post api gateway dispatch."""
        if not self._require_auth("user"):
            return
        body = self._body
        from salmalm.features.nodes import gateway

        node_id = body.get("node_id", "")
        tool = body.get("tool", "")
        args = body.get("args", {})
        if node_id:
            result = gateway.dispatch(node_id, tool, args)  # type: ignore[assignment]
        else:
            result = gateway.dispatch_auto(tool, args)  # type: ignore[assignment]
            if result is None:
                result = {"error": "No available node for this tool"}
        self._json(result)  # type: ignore[arg-type]

    def _post_api_gateway_unregister(self):
        """Post api gateway unregister."""
        body = self._body
        from salmalm.features.nodes import gateway

        node_id = body.get("node_id", "")
        self._json(gateway.unregister(node_id))

    def _post_webhook_slack(self):
        """Post webhook slack."""
        body = self._body
        # Slack Event API webhook
        from salmalm.channels.slack_bot import slack_bot

        if not slack_bot.bot_token:
            self._json({"error": "Slack not configured"}, 503)
            return
        # Verify request
        ts = self.headers.get("X-Slack-Request-Timestamp", "")
        sig = self.headers.get("X-Slack-Signature", "")
        raw_body = json.dumps(body).encode() if isinstance(body, dict) else b""
        if not slack_bot.verify_request(ts, sig, raw_body):
            self._json({"error": "Invalid signature"}, 403)
            return
        result = slack_bot.handle_event(body)
        if result:
            self._json(result)
        else:
            self._json({"ok": True})

    def _post_webhook_telegram(self):
        """Post webhook telegram."""
        body = self._body
        # Telegram webhook endpoint
        from salmalm.channels.telegram import telegram_bot

        if not telegram_bot.token:
            self._json({"error": "Telegram not configured"}, 503)
            return
        # Verify secret token
        secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if telegram_bot._webhook_secret:
            if not telegram_bot.verify_webhook_request(secret):
                log.warning("[BLOCK] Telegram webhook: invalid secret token")
                self._json({"error": "Forbidden"}, 403)
                return
        else:
            _wh_ip = self._get_client_ip()
            if _wh_ip not in ("127.0.0.1", "::1", "localhost"):
                log.warning("[BLOCK] Telegram webhook without secret rejected from %s", _wh_ip)
                self._json({"error": "Webhook secret not configured"}, 403)
                return
        try:
            update = body
            # Run async handler in event loop
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                # Wait for result so webhook is fully processed before returning 200
                fut = asyncio.run_coroutine_threadsafe(telegram_bot.handle_webhook_update(update), loop)
                fut.result(timeout=10)
            except RuntimeError:
                # No running loop — safe to use asyncio.run()
                asyncio.run(telegram_bot.handle_webhook_update(update))
            self._json({"ok": True})
        except Exception as e:
            log.error(f"Webhook handler error: {e}")
            self._json({"ok": True})  # Always return 200 to Telegram


# ── FastAPI router ────────────────────────────────────────────────────────────
from fastapi import APIRouter as _APIRouter, Request as _Request, Depends as _Depends
from fastapi.responses import JSONResponse as _JSON
from salmalm.web.fastapi_deps import require_auth as _auth

router = _APIRouter()

@router.get("/api/gateway/nodes")
async def get_gateway_nodes(_u=_Depends(_auth)):
    from salmalm.features.nodes import gateway
    return _JSON(content={"nodes": gateway.list_nodes()})

@router.post("/api/config/telegram")
async def post_config_telegram(request: _Request, _u=_Depends(_auth)):
    from salmalm.security.crypto import vault
    if _u.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    body = await request.json()
    if not vault.is_unlocked:
        return _JSON(content={"error": "Vault locked"}, status_code=403)
    vault.set("telegram_token", body.get("token", ""))
    vault.set("telegram_owner_id", body.get("owner_id", ""))
    return _JSON(content={"ok": True, "message": "Telegram config saved. Restart required."})

@router.post("/api/gateway/register")
async def post_gateway_register(request: _Request):
    from salmalm.features.nodes import gateway
    body = await request.json()
    node_id = body.get("node_id", "")
    url = body.get("url", "")
    if not node_id or not url:
        return _JSON(content={"error": "node_id and url required"}, status_code=400)
    result = gateway.register(node_id, url, token=body.get("token", ""),
                              capabilities=body.get("capabilities"), name=body.get("name", ""))
    return _JSON(content=result)

@router.post("/api/gateway/heartbeat")
async def post_gateway_heartbeat(request: _Request):
    from salmalm.features.nodes import gateway
    body = await request.json()
    return _JSON(content=gateway.heartbeat(body.get("node_id", "")))

@router.post("/api/gateway/unregister")
async def post_gateway_unregister(request: _Request):
    from salmalm.features.nodes import gateway
    body = await request.json()
    return _JSON(content=gateway.unregister(body.get("node_id", "")))

@router.post("/api/gateway/dispatch")
async def post_gateway_dispatch(request: _Request, _u=_Depends(_auth)):
    from salmalm.features.nodes import gateway
    body = await request.json()
    node_id = body.get("node_id", "")
    tool = body.get("tool", "")
    args = body.get("args", {})
    if node_id:
        result = gateway.dispatch(node_id, tool, args)
    else:
        result = gateway.dispatch_auto(tool, args)
        if result is None:
            result = {"error": "No available node for this tool"}
    return _JSON(content=result)

@router.post("/webhook/slack")
async def post_webhook_slack(request: _Request):
    import json as _json
    from salmalm.channels.slack_bot import slack_bot
    body = await request.json()
    if not slack_bot.bot_token:
        return _JSON(content={"error": "Slack not configured"}, status_code=503)
    ts = request.headers.get("x-slack-request-timestamp", "")
    sig = request.headers.get("x-slack-signature", "")
    raw_body = _json.dumps(body).encode() if isinstance(body, dict) else b""
    if not slack_bot.verify_request(ts, sig, raw_body):
        return _JSON(content={"error": "Invalid signature"}, status_code=403)
    result = slack_bot.handle_event(body)
    return _JSON(content=result if result else {"ok": True})

@router.post("/webhook/telegram")
async def post_webhook_telegram(request: _Request):
    from salmalm.security.crypto import log
    from salmalm.channels.telegram import telegram_bot
    body = await request.json()
    if not telegram_bot.token:
        return _JSON(content={"error": "Telegram not configured"}, status_code=503)
    secret = request.headers.get("x-telegram-bot-api-secret-token", "")
    if telegram_bot._webhook_secret:
        if not telegram_bot.verify_webhook_request(secret):
            log.warning("[BLOCK] Telegram webhook: invalid secret token")
            return _JSON(content={"error": "Forbidden"}, status_code=403)
    else:
        # No webhook secret configured — only allow loopback (localhost-only guard)
        _wh_ip = request.client.host if request.client else ""
        if _wh_ip not in ("127.0.0.1", "::1", "localhost"):
            log.warning("[BLOCK] Telegram webhook without secret rejected from %s", _wh_ip)
            return _JSON(content={"error": "Webhook secret not configured"}, status_code=403)
    try:
        await telegram_bot.handle_webhook_update(body)
        return _JSON(content={"ok": True})
    except Exception as e:
        log.error(f"Webhook handler error: {e}")
        return _JSON(content={"ok": True})
