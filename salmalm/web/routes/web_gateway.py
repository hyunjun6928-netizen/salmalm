"""Gateway & webhook API — Telegram, Slack, gateway nodes."""

from salmalm.security.crypto import vault, log
import json


class WebGatewayMixin:
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
        """Post api gateway register — requires admin auth."""
        if not self._require_auth("admin"):
            return
        body = self._body
        from salmalm.features.nodes import gateway

        node_id = body.get("node_id", "")
        url = body.get("url", "")
        if not node_id or not url:
            self._json({"error": "node_id and url required"}, 400)
            return
        # SSRF protection: reject private/internal URLs
        from salmalm.tools.tools_common import _is_private_url
        if _is_private_url(url):
            self._json({"error": "Private/internal URLs not allowed"}, 400)
            return
        result = gateway.register(  # type: ignore[assignment]
            node_id,
            url,
            token=body.get("token", ""),
            auth_token=body.get("auth_token", ""),
            capabilities=body.get("capabilities"),
            name=body.get("name", ""),
        )
        self._json(result)  # type: ignore[arg-type]

    def _post_api_gateway_heartbeat(self):
        """Post api gateway heartbeat — requires admin auth."""
        if not self._require_auth("admin"):
            return
        body = self._body
        from salmalm.features.nodes import gateway

        node_id = body.get("node_id", "")
        self._json(gateway.heartbeat(node_id))

    def _post_api_gateway_dispatch(self):
        """Post api gateway dispatch — requires admin auth."""
        if not self._require_auth("admin"):
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
        """Post api gateway unregister — requires admin auth."""
        if not self._require_auth("admin"):
            return
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
        # Verify request — HMAC must be over the raw request body bytes,
        # NOT re-serialized JSON (key ordering can differ → signature mismatch).
        ts = self.headers.get("X-Slack-Request-Timestamp", "")
        sig = self.headers.get("X-Slack-Signature", "")
        # Prefer the preserved raw bytes; fall back to re-serialized (legacy path)
        raw_body: bytes = getattr(self, "_body_bytes", None) or (
            json.dumps(body, separators=(",", ":")).encode() if isinstance(body, dict) else b""
        )
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
        # Verify secret token — REQUIRED.
        # If _webhook_secret is unset the webhook was not registered securely;
        # reject ALL incoming requests to avoid unauthenticated command injection.
        secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not telegram_bot._webhook_secret:
            log.error("[BLOCK] Telegram webhook: _webhook_secret not set — rejecting all requests. "
                      "Re-register the webhook via /api/telegram/setup to generate a secret.")
            self._json({"error": "Webhook not properly configured"}, 503)
            return
        if not telegram_bot.verify_webhook_request(secret):
            log.warning("[BLOCK] Telegram webhook: invalid secret token from %s",
                        self._get_client_ip())
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
                    loop.run_until_complete(
                        asyncio.wait_for(telegram_bot.handle_webhook_update(update), timeout=60)
                    )
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(
                        asyncio.wait_for(telegram_bot.handle_webhook_update(update), timeout=60)
                    )
                except asyncio.TimeoutError:
                    log.warning("[GATEWAY] Telegram webhook handler timeout (60s)")
                finally:
                    loop.close()
            self._json({"ok": True})
        except Exception as e:
            log.error(f"Webhook handler error: {e}")
            self._json({"ok": True})  # Always return 200 to Telegram
