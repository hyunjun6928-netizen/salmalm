"""SalmAlm Slack Bot — Pure stdlib Slack integration."""

from __future__ import annotations

import json
import urllib.request
import urllib.parse
from typing import Any, Callable, Dict, Optional

from salmalm import log

API_BASE = "https://slack.com/api"


class SlackBot:
    """Minimal Slack bot using Event API (webhook) + Web API (urllib)."""

    def __init__(self) -> None:
        """Init  ."""
        self.bot_token: Optional[str] = None
        self.signing_secret: Optional[str] = None
        self.bot_user_id: Optional[str] = None
        self._on_message: Optional[Callable] = None

    def configure(self, bot_token: str, signing_secret: Optional[str] = None) -> None:
        """Configure the Slack bot."""
        self.bot_token = bot_token
        self.signing_secret = signing_secret

    def on_message(self, func: Callable) -> Callable:
        """Register message handler."""
        self._on_message = func
        return func

    # ── REST API ──

    def _api(self, method: str, data: Optional[dict] = None) -> dict:
        """Call Slack Web API."""
        url = f"{API_BASE}/{method}"
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        payload = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=payload, method="POST")
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                if not result.get("ok"):
                    log.error(f"Slack API {method}: {result.get('error', 'unknown')}")
                return result
        except Exception as e:
            log.error(f"Slack API {method} error: {e}")
            return {"ok": False, "error": str(e)}

    def send_message(
        self, channel: str, text: str, *, thread_ts: Optional[str] = None, blocks: Optional[list] = None
    ) -> dict:
        """Send a message to a Slack channel."""
        data: Dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            data["thread_ts"] = thread_ts
        if blocks:
            data["blocks"] = blocks
        return self._api("chat.postMessage", data)

    def add_reaction(self, channel: str, timestamp: str, emoji: str) -> dict:
        """Add an emoji reaction to a message."""
        return self._api(
            "reactions.add",
            {
                "channel": channel,
                "timestamp": timestamp,
                "name": emoji.strip(":"),
            },
        )

    def get_bot_info(self) -> Optional[Dict]:
        """Fetch bot user info."""
        result = self._api("auth.test")
        if result.get("ok"):
            self.bot_user_id = result.get("user_id")
            return result
        return None

    # ── Event API webhook handler ──

    def verify_request(self, timestamp: str, signature: str, body: bytes) -> bool:
        """Verify Slack request signature."""
        if not self.signing_secret:
            return False  # No secret configured → fail-closed (reject all)
        import hashlib
        import hmac

        # Replay attack prevention: reject requests older than 5 minutes
        import time as _t
        try:
            ts_age = abs(_t.time() - float(timestamp))
            if ts_age > 300:  # 5 minutes
                return False
        except (ValueError, TypeError):
            return False
        base = f"v0:{timestamp}:{body.decode('utf-8')}"
        computed = "v0=" + hmac.new(self.signing_secret.encode(), base.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, signature)

    def handle_event(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle an incoming Slack event.

        Returns response dict (e.g. challenge response) or None.
        """
        # URL verification challenge
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge", "")}

        # Event callback
        if payload.get("type") == "event_callback":
            event = payload.get("event", {})
            event_type = event.get("type")

            # Skip bot's own messages
            if event.get("bot_id") or event.get("user") == self.bot_user_id:
                return None

            if event_type == "message" and not event.get("subtype"):
                if self._on_message:
                    # Build normalized message
                    msg = {
                        "channel": "slack",
                        "channel_id": event.get("channel", ""),
                        "user_id": event.get("user", ""),
                        "text": event.get("text", ""),
                        "thread_ts": event.get("thread_ts") or event.get("ts", ""),
                        "ts": event.get("ts", ""),
                        "team_id": payload.get("team_id", ""),
                        "raw": event,
                    }
                    try:
                        self._on_message(msg)
                    except Exception as e:
                        log.error(f"Slack message handler error: {e}")

            elif event_type == "app_mention":
                if self._on_message:
                    msg = {
                        "channel": "slack",
                        "channel_id": event.get("channel", ""),
                        "user_id": event.get("user", ""),
                        "text": event.get("text", ""),
                        "thread_ts": event.get("thread_ts") or event.get("ts", ""),
                        "ts": event.get("ts", ""),
                        "mentioned": True,
                        "raw": event,
                    }
                    try:
                        self._on_message(msg)
                    except Exception as e:
                        log.error(f"Slack mention handler error: {e}")

        return None

    def update_message(self, channel: str, ts: str, text: str) -> dict:
        """Update an existing message."""
        return self._api(
            "chat.update",
            {
                "channel": channel,
                "ts": ts,
                "text": text,
            },
        )

    def delete_message(self, channel: str, ts: str) -> dict:
        """Delete a message."""
        return self._api(
            "chat.delete",
            {
                "channel": channel,
                "ts": ts,
            },
        )


# Singleton
slack_bot = SlackBot()
