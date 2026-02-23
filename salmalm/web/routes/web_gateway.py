"""Gateway & webhook API — Telegram, Slack, gateway nodes."""



from salmalm.security.crypto import vault, log
import json


class WebGatewayMixin:
    """Mixin providing gateway route handlers."""
    def _get_gateway_nodes(self):
        from salmalm.features.nodes import gateway

        self._json({"nodes": gateway.list_nodes()})

    def _post_api_config_telegram(self):
        body = self._body
        if not vault.is_unlocked:
            self._json({"error": "Vault locked"}, 403)
            return
        vault.set("telegram_token", body.get("token", ""))
        vault.set("telegram_owner_id", body.get("owner_id", ""))
        self._json({"ok": True, "message": "Telegram config saved. Restart required."})

    def _post_api_gateway_register(self):
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
        body = self._body
        from salmalm.features.nodes import gateway

        node_id = body.get("node_id", "")
        self._json(gateway.heartbeat(node_id))

    def _post_api_gateway_dispatch(self):
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
        body = self._body
        from salmalm.features.nodes import gateway

        node_id = body.get("node_id", "")
        self._json(gateway.unregister(node_id))

    def _post_webhook_slack(self):
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
        body = self._body
        # Telegram webhook endpoint
        from salmalm.channels.telegram import telegram_bot

        if not telegram_bot.token:
            self._json({"error": "Telegram not configured"}, 503)
            return
        # Verify secret token
        secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if telegram_bot._webhook_secret and not telegram_bot.verify_webhook_request(secret):
            log.warning("[BLOCK] Telegram webhook: invalid secret token")
            self._json({"error": "Forbidden"}, 403)
            return
        try:
            update = body
            # Run async handler in event loop
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(telegram_bot.handle_webhook_update(update))
                else:
                    loop.run_until_complete(telegram_bot.handle_webhook_update(update))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(telegram_bot.handle_webhook_update(update))
                loop.close()
            self._json({"ok": True})
        except Exception as e:
            log.error(f"Webhook handler error: {e}")
            self._json({"ok": True})  # Always return 200 to Telegram

