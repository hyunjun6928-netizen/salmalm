"""SalmAlm Telegram bot."""

from __future__ import annotations

import asyncio
import json
import re
import secrets
import textwrap
import time
import urllib.request
from typing import Any, Dict, Optional

from pathlib import Path
from salmalm.constants import VERSION, WORKSPACE_DIR
from salmalm.security.crypto import vault, log
from salmalm.core import get_session, audit_log, set_telegram_bot
from salmalm.core.llm import _http_post, _http_get
from salmalm.core.prompt import build_system_prompt
from salmalm.tools import execute_tool
from salmalm.utils.chunker import EmbeddedBlockChunker, ChunkerConfig, CHANNEL_TELEGRAM, load_config_from_file
from salmalm.channels.telegram_commands import TelegramCommandsMixin


class TelegramBot(TelegramCommandsMixin):
    def __init__(self) -> None:
        """Init  ."""
        self.token: Optional[str] = None
        self.owner_id: Optional[str] = None
        self.offset = 0
        self._running = False
        self._webhook_secret: Optional[str] = None
        self._webhook_mode = False
        # Block streaming state per chat
        self._draft_messages: Dict[str, Dict[str, Any]] = {}  # chat_id -> {msg_id, text, last_edit}
        # Typing indicator config: instant|message|never
        self.typing_mode = "instant"

    def configure(self, token: str, owner_id: str) -> None:
        """Configure the Telegram bot with token and owner chat ID."""
        self.token = token
        self.owner_id = owner_id
        self._bot_username: Optional[str] = None
        # Try to fetch bot username
        try:
            me = self._api("getMe")
            if me.get("ok") and me.get("result"):
                self._bot_username = me["result"].get("username")
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")
        # Register command menu (OpenClaw-style)
        self._register_commands()

    def _api(self, method: str, data: Optional[dict] = None) -> dict:
        """Api."""
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        if data:
            return _http_post(url, {"Content-Type": "application/json"}, data)
        return _http_get(url)

    def _extract_buttons(self, text: str):
        """Extract inline button markers. Returns (clean_text, buttons_list)."""
        buttons = []
        import re as _re2

        def _repl(m):
            """Repl."""
            try:
                import json as _j2

                buttons.extend(_j2.loads(m.group(1)))
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
            return ""

        clean = _re2.sub(r"<!--buttons:(\[.*?\])-->", _repl, text)
        return clean.strip(), buttons

    def _register_commands(self):
        """Register bot command menu via setMyCommands (OpenClaw-style)."""
        commands = [
            {"command": "start", "description": "Start / show status"},
            {"command": "help", "description": "Show available commands"},
            {"command": "usage", "description": "Token usage & cost report"},
            {"command": "model", "description": "Switch AI model"},
            {"command": "briefing", "description": "Daily briefing"},
            {"command": "clear", "description": "Clear conversation"},
            {"command": "compact", "description": "Compress conversation"},
            {"command": "tts", "description": "Toggle voice responses"},
            {"command": "note", "description": "Quick note"},
            {"command": "remind", "description": "Reminders"},
            {"command": "cal", "description": "Calendar"},
            {"command": "mail", "description": "Email"},
        ]
        try:
            self._api("setMyCommands", {"commands": commands})
            log.info(f"[TG] Registered {len(commands)} bot commands")
        except Exception as e:
            log.warning(f"[TG] setMyCommands failed: {e}")

    def ack_reaction(self, chat_id, message_id: int):
        """Send ack reaction (👀) while processing — OpenClaw-style."""
        return self.set_message_reaction(chat_id, message_id, "👀")

    def clear_reaction(self, chat_id, message_id: int):
        """Clear reaction after processing completes."""
        try:
            return self._api(
                "setMessageReaction",
                {"chat_id": chat_id, "message_id": message_id, "reaction": []},
            )
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")

    def set_message_reaction(self, chat_id, message_id: int, emoji: str = "👍") -> dict:
        """React to a message with an emoji via setMessageReaction API."""
        try:
            return self._api(
                "setMessageReaction",
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reaction": [{"type": "emoji", "emoji": emoji}],
                    "is_big": False,
                },
            )
        except Exception as e:
            log.error(f"[TG] Reaction error: {e}")
            return {}

    def send_message(
        self,
        chat_id,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[dict] = None,
        message_thread_id: Optional[int] = None,
        reply_to_message_id: Optional[int] = None,
    ):
        """Send a text message to a Telegram chat, with optional inline keyboard.

        Edge cases handled:
        - Empty messages: skip
        - Length > 4096: smart split on paragraph/code block boundaries
        - MarkdownV2 parse error: fallback to plain text
        - Flood wait (429): respect retry_after
        - Chat not found (400): log warning, skip
        - Bot kicked (403): cleanup session
        - MessageNotModified: ignore
        """
        # Empty message guard
        if not text or not text.strip():
            return

        text, btn_labels = self._extract_buttons(text)
        if not text.strip():
            return

        if btn_labels and not reply_markup:
            reply_markup = {
                "inline_keyboard": [[{"text": label, "callback_data": f"btn:{label}"[:64]} for label in btn_labels]]
            }

        # Smart split: respect paragraph boundaries and code blocks
        chunks = self._smart_split(text, max_len=4096)

        for idx, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            data = {"chat_id": chat_id, "text": chunk}
            if message_thread_id:
                data["message_thread_id"] = message_thread_id
            if reply_to_message_id and idx == 0:
                data["reply_to_message_id"] = reply_to_message_id
            if parse_mode:
                data["parse_mode"] = parse_mode
            if reply_markup and idx == len(chunks) - 1:
                data["reply_markup"] = reply_markup
            try:
                self._api("sendMessage", data)
            except Exception as e:
                err_str = str(e).lower()
                # Flood wait — respect retry_after
                if "429" in str(e) or "flood" in err_str or "retry_after" in err_str:
                    wait = self._extract_retry_after(e)
                    log.warning(f"[TG] Flood wait: {wait}s for chat {chat_id}")
                    time.sleep(wait)
                    try:
                        self._api("sendMessage", data)
                    except Exception as e:  # noqa: broad-except
                        log.debug(f"Suppressed: {e}")
                    continue
                # Chat not found
                if "chat not found" in err_str or "400" in str(e):
                    log.warning(f"[TG] Chat not found: {chat_id}")
                    return
                # Bot kicked from group
                if "403" in str(e) or "forbidden" in err_str or "kicked" in err_str:
                    log.warning(f"[TG] Bot kicked/blocked: {chat_id}")
                    self._cleanup_session(chat_id)
                    return
                # MessageNotModified — ignore
                if "not modified" in err_str:
                    return
                # MarkdownV2 parse error → retry without parse_mode
                if parse_mode:
                    data2 = {"chat_id": chat_id, "text": chunk}
                    if reply_markup and idx == len(chunks) - 1:
                        data2["reply_markup"] = reply_markup
                    try:
                        self._api("sendMessage", data2)
                    except Exception as e2:
                        log.error(f"[TG] Send failed even without parse_mode: {e2}")
                else:
                    log.error(f"[TG] Send failed: {e}")

    def _smart_split(self, text: str, max_len: int = 4096) -> list:
        """Split text respecting paragraph boundaries and code blocks.

        Uses EmbeddedBlockChunker for code-fence-aware, smart-breakpoint splitting.
        """
        if len(text) <= max_len:
            return [text]

        config = ChunkerConfig(channel=CHANNEL_TELEGRAM, hardCap=max_len)
        chunker = EmbeddedBlockChunker(config)
        return chunker.split_for_channel(text)

    @staticmethod
    def _extract_retry_after(error) -> float:
        """Extract retry_after seconds from Telegram error."""
        try:
            err_str = str(error)
            import re as _re

            m = _re.search(r"retry.after[:\s]+(\d+)", err_str, _re.IGNORECASE)
            if m:
                return float(m.group(1))
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")
        return 5.0  # Default wait

    def _cleanup_session(self, chat_id):
        """Clean up session when bot is kicked from chat."""
        session_id = f"telegram_{chat_id}"
        try:
            from salmalm.core import _sessions, _session_lock

            with _session_lock:
                if session_id in _sessions:
                    del _sessions[session_id]
            log.info(f"[TG] Session cleaned up: {session_id}")
        except Exception as e:
            log.error(f"[TG] Session cleanup error: {e}")

    def _send_photo(self, chat_id, path: Path, caption: str = ""):  # noqa: F405
        """Send a photo file to Telegram."""
        try:
            import mimetypes  # noqa: F401

            boundary = f"----SalmAlm{secrets.token_hex(8)}"
            body = b""
            # chat_id field
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode()
            if caption:
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption[:1000]}\r\n'.encode()
            # photo field
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{path.name}"\r\nContent-Type: image/png\r\n\r\n'.encode()
            body += path.read_bytes()
            body += f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{self.token}/sendPhoto",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=30)
        except Exception as e:
            log.error(f"Send photo error: {e}")
            # Fallback: send as text link if file was from URL
            self.send_message(chat_id, f"📷 Image send failed: {e}\n{caption}")

    def _send_audio(self, chat_id, path: Path, caption: str = ""):  # noqa: F405
        """Send an audio file to Telegram."""
        try:
            boundary = f"----SalmAlm{secrets.token_hex(8)}"
            body = b""
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode()
            if caption:
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption[:1000]}\r\n'.encode()
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="voice"; filename="{path.name}"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode()
            body += path.read_bytes()
            body += f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{self.token}/sendVoice",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=30)
        except Exception as e:
            log.error(f"Send audio error: {e}")
            self.send_message(chat_id, f"🔊 Voice send failed: {e}")

    def _send_document(self, chat_id, data: bytes, filename: str, caption: str = ""):
        """Send a document (file) to Telegram."""
        try:
            boundary = f"----SalmAlm{secrets.token_hex(8)}"
            body = b""
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode()
            if caption:
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption[:1000]}\r\n'.encode()
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\nContent-Type: application/zip\r\n\r\n'.encode()
            body += data
            body += f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{self.token}/sendDocument",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=60)
        except Exception as e:
            log.error(f"Send document error: {e}")
            self.send_message(chat_id, f"📎 Document send failed: {e}")

    def _send_tts_voice(self, chat_id, text: str, session):
        """Generate TTS audio via OpenAI API and send as voice message."""
        api_key = vault.get("openai_api_key")
        if not api_key:
            log.warning("[TTS] No openai_api_key in vault")
            return
        # Clean text for TTS (remove markdown, code blocks, URLs)
        import re as _re2

        clean = _re2.sub(r"```[\s\S]*?```", "", text)
        clean = _re2.sub(r"`[^`]+`", "", clean)
        clean = _re2.sub(r"https?://\S+", "", clean)
        clean = _re2.sub(r"[*_#\[\]()>]", "", clean)
        clean = clean.strip()
        if not clean or len(clean) < 3:
            return
        # Truncate to 4096 chars (API limit)
        clean = clean[:4096]
        voice = getattr(session, "tts_voice", "alloy")
        try:
            tts_body = json.dumps(
                {
                    "model": "tts-1",
                    "input": clean,
                    "voice": voice,
                    "response_format": "opus",
                }
            ).encode()
            req = urllib.request.Request(
                "https://api.openai.com/v1/audio/speech",
                data=tts_body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio_data = resp.read()
            # Save to temp file and send
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                f.write(audio_data)
                tmp_path = Path(f.name)  # noqa: F405
            self._send_audio(chat_id, tmp_path, "")
            try:
                tmp_path.unlink()
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
            log.info(f"[TTS] Voice sent: {len(audio_data)} bytes, voice={voice}")
        except Exception as e:
            log.error(f"[TTS] OpenAI TTS API error: {e}")

    def send_typing(self, chat_id) -> None:
        """Send a typing indicator to a Telegram chat."""
        try:
            self._api("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")

    def _start_typing_loop(self, chat_id) -> asyncio.Task:
        """Start an async typing indicator loop that refreshes every 5 seconds.

        Returns a task that can be cancelled when the response is ready.
        """

        async def _loop():
            """Loop."""
            try:
                while True:
                    await asyncio.to_thread(self.send_typing, chat_id)
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                pass

        return asyncio.create_task(_loop())

    def edit_message(self, chat_id, message_id, text: str, parse_mode: Optional[str] = None) -> None:
        """Edit an existing Telegram message."""
        data: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:4000],
        }
        if parse_mode:
            data["parse_mode"] = parse_mode
        try:
            self._api("editMessageText", data)
        except Exception as e:  # noqa: broad-except
            # Fallback without parse_mode
            # Fallback without parse_mode
            if parse_mode:
                data2 = {k: v for k, v in data.items() if k != "parse_mode"}
                try:
                    self._api("editMessageText", data2)
                except Exception as e:  # noqa: broad-except
                    log.debug(f"Suppressed: {e}")

    def _send_draft(self, chat_id, text: str) -> Optional[int]:
        """Send initial draft message for block streaming. Returns message_id."""
        data = {"chat_id": chat_id, "text": text[:4000]}
        try:
            resp = self._api("sendMessage", data)
            msg_id = resp.get("result", {}).get("message_id")
            if msg_id:
                self._draft_messages[str(chat_id)] = {
                    "msg_id": msg_id,
                    "text": text,
                    "last_edit": time.time(),
                }
            return msg_id
        except Exception as e:  # noqa: broad-except
            return None

    def _update_draft(self, chat_id, text: str, force: bool = False):
        """Update draft message with new text (block streaming).

        Respects minimum 2-second edit interval.
        Skips updates if inside an unclosed code block.
        """
        key = str(chat_id)
        draft = self._draft_messages.get(key)
        if not draft:
            return

        now = time.time()
        # Min 2s between edits unless forced
        if not force and (now - draft["last_edit"]) < 2.0:
            return

        # Don't edit in the middle of a code block (odd number of ```)
        fence_count = text.count("```")
        if not force and fence_count % 2 != 0:
            return

        draft["text"] = text
        draft["last_edit"] = now
        self.edit_message(chat_id, draft["msg_id"], text)

    def _finalize_draft(self, chat_id, text: str, suffix: str = ""):
        """Finalize draft message with complete text + suffix."""
        key = str(chat_id)
        draft = self._draft_messages.get(key)
        final = f"{text}{suffix}" if suffix else text
        if draft:
            self.edit_message(chat_id, draft["msg_id"], final)
            del self._draft_messages[key]
            return draft["msg_id"]
        else:
            # No draft — send as new message
            self.send_message(chat_id, final)
            return None

    # ── Webhook support ──────────────────────────────────────────

    def set_webhook(self, url: str) -> dict:
        """Set Telegram webhook. Generates a secret_token for request verification."""
        self._webhook_secret = secrets.token_hex(32)
        result = self._api(
            "setWebhook",
            {
                "url": url,
                "secret_token": self._webhook_secret,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        if result.get("ok"):
            self._webhook_mode = True
            log.info(f"[NET] Telegram webhook set: {url}")
        return result

    def delete_webhook(self) -> dict:
        """Delete Telegram webhook and return to polling mode."""
        result = self._api("deleteWebhook", {"drop_pending_updates": False})
        self._webhook_mode = False
        self._webhook_secret = None
        log.info("[NET] Telegram webhook deleted, polling mode restored")
        return result

    def verify_webhook_request(self, secret_token: str) -> bool:
        """Verify the X-Telegram-Bot-Api-Secret-Token header."""
        if not self._webhook_secret:
            return False
        return secrets.compare_digest(secret_token, self._webhook_secret)

    async def handle_webhook_update(self, update: dict) -> None:
        """Process a single update received via webhook."""
        await self._handle_update(update)

    async def poll(self) -> None:
        """Long-polling loop for Telegram updates."""
        self._running = True
        log.info(f"[NET] Telegram bot started (owner: {self.owner_id})")

        while self._running:
            try:
                # Run blocking urllib in thread to not block event loop
                resp = await asyncio.to_thread(
                    self._api,
                    "getUpdates",
                    {"offset": self.offset, "timeout": 30, "allowed_updates": ["message", "callback_query"]},
                )
                for update in resp.get("result", []):
                    self.offset = update["update_id"] + 1
                    await self._handle_update(update)
            except Exception as e:
                log.error(f"Telegram poll error: {e}")
                await asyncio.sleep(5)

    def _download_file(self, file_id: str) -> tuple:
        """Download a file from Telegram. Returns (data, filename)."""
        info = self._api("getFile", {"file_id": file_id})
        file_path = info["result"]["file_path"]
        filename = file_path.split("/")[-1]
        # Sanitize filename — remove path traversal chars
        filename = re.sub(r"[/\\\.]{2,}", "_", filename)
        filename = re.sub(r"[^\w.\-]", "_", filename)
        if not filename or filename.startswith("."):
            filename = f"file_{int(time.time())}"
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        return data, filename

    async def _handle_update(self, update: dict):
        # Handle inline button callback queries
        """Handle update."""
        cb = update.get("callback_query")
        if cb:
            cb_data = cb.get("data", "")
            cb_chat_id = cb.get("message", {}).get("chat", {}).get("id")
            cb_user_id = str(cb.get("from", {}).get("id", ""))
            try:
                self._api("answerCallbackQuery", {"callback_query_id": cb["id"]})
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
            # Multi-tenant: allow registered users; legacy: owner only
            from salmalm.features.users import user_manager as _um_cb

            _cb_allowed = False
            if _um_cb.multi_tenant_enabled:
                _cb_tenant = _um_cb.get_user_by_telegram(str(cb_chat_id))
                _cb_allowed = bool(_cb_tenant and _cb_tenant.get("enabled"))
            else:
                _cb_allowed = cb_user_id == self.owner_id
            if _cb_allowed and cb_chat_id and cb_data.startswith("btn:"):
                btn_text = cb_data[4:]
                self.send_typing(cb_chat_id)
                session_id = f"telegram_{cb_chat_id}"
                _start = time.time()
                from salmalm.core.engine import process_message

                response = await process_message(session_id, btn_text)
                _elapsed = time.time() - _start
                self.send_message(cb_chat_id, f"{response}\n\n⏱️ {_elapsed:.1f}s")
            return

        msg = update.get("message")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        user_id = str(msg["from"]["id"])
        _tg_username = msg.get("from", {}).get("username", "")  # noqa: F841
        chat_type = msg.get("chat", {}).get("type", "private")
        _message_thread_id = msg.get("message_thread_id")  # noqa: F841

        # Group chat: only respond to mentions or replies to bot
        if chat_type in ("group", "supergroup"):
            _msg_text = msg.get("text", "") or ""
            _bot_info = getattr(self, "_bot_username", None)
            _is_mention = _bot_info and f"@{_bot_info}" in _msg_text
            _is_reply_to_bot = False
            if msg.get("reply_to_message", {}).get("from", {}).get("is_bot"):
                _is_reply_to_bot = True
            # Also check entities for bot_command or mention
            for ent in msg.get("entities", []):
                if ent.get("type") == "mention":
                    mention_text = _msg_text[ent["offset"] : ent["offset"] + ent["length"]]
                    if _bot_info and mention_text.lower() == f"@{_bot_info}".lower():
                        _is_mention = True
            if not _is_mention and not _is_reply_to_bot and not _msg_text.startswith("/"):
                return  # Silent: no mention, no reply to bot

        # Multi-tenant auth check
        from salmalm.features.users import user_manager

        _tenant_user = None  # Resolved multi-tenant user dict
        if user_manager.multi_tenant_enabled:
            _tenant_user = user_manager.get_user_by_telegram(str(chat_id))
            text_check = msg.get("text", "") or ""
            # Allow /register and /start for unregistered users
            if not _tenant_user and not text_check.startswith(("/register", "/start")):
                self.send_message(
                    chat_id,
                    "🔐 등록이 필요합니다. /register <비밀번호>로 등록하세요.\n"
                    "Registration required. Use /register <password> to sign up.",
                )
                return
            if _tenant_user and not _tenant_user.get("enabled", True):
                self.send_message(chat_id, "⛔ 계정이 비활성화되었습니다. 관리자에게 문의하세요. / Account disabled.")
                return
            # Check quota
            if _tenant_user:
                try:
                    from salmalm.features.users import QuotaExceeded

                    user_manager.check_quota(_tenant_user["id"])
                except QuotaExceeded as e:
                    self.send_message(chat_id, f"⚠️ {e.message}")
                    return
        else:
            # Legacy single-user mode: owner check
            if user_id != self.owner_id:
                log.warning(f"[BLOCK] Unauthorized: {user_id} tried to message")
                audit_log("unauthorized", f"user_id={user_id}")
                return

        text = msg.get("text", "") or msg.get("caption", "") or ""
        file_info = None

        # Handle photos (with vision support)
        _image_data = None
        if msg.get("photo"):
            photo = msg["photo"][-1]  # Largest size
            try:
                data, fname = self._download_file(photo["file_id"])
                save_path = WORKSPACE_DIR / "uploads" / fname  # noqa: F405
                save_path.parent.mkdir(exist_ok=True)
                save_path.write_bytes(data)
                file_info = f"[📷 Image saved: uploads/{fname} ({len(data) // 1024}KB)]"
                log.info(f"[PHOTO] Photo saved: {save_path}")
                # Prepare vision data
                import base64 as _b64

                _image_data = (_b64.b64encode(data).decode(), "image/jpeg")
            except Exception as e:
                file_info = f"[📷 Image download failed: {e}]"

        # Handle documents
        if msg.get("document"):
            doc = msg["document"]
            try:
                data, fname = self._download_file(doc["file_id"])
                doc_fname = doc.get("file_name", fname)
                # Auto-detect agent import ZIP
                if doc_fname.endswith(".zip") and "agent-export" in doc_fname.lower():
                    self.send_typing(chat_id)
                    from salmalm.utils.migration import import_agent

                    result = import_agent(data)
                    self.send_message(chat_id, f"📦 **Agent Import / 에이전트 가져오기**\n\n{result.summary()}")
                    return
                save_path = WORKSPACE_DIR / "uploads" / doc_fname  # noqa: F405
                save_path.parent.mkdir(exist_ok=True)
                save_path.write_bytes(data)
                file_info = f"[📎 File saved: uploads/{save_path.name} ({len(data) // 1024}KB)]"
                log.info(f"[CLIP] File saved: {save_path}")
                # If text file, include content preview
                if save_path.suffix in (
                    ".txt",
                    ".md",
                    ".py",
                    ".js",
                    ".json",
                    ".csv",
                    ".log",
                    ".html",
                    ".css",
                    ".sh",
                    ".bat",
                ):
                    try:
                        content = data.decode("utf-8", errors="replace")[:3000]
                        file_info += f"\n[File content preview]\n{content}"
                    except Exception as e:  # noqa: broad-except
                        log.debug(f"Suppressed: {e}")
            except Exception as e:
                file_info = f"[📎 File download failed: {e}]"

        # Handle voice/audio
        if msg.get("voice") or msg.get("audio"):
            audio = msg.get("voice") or msg.get("audio")
            try:
                data, fname = self._download_file(audio["file_id"])
                save_path = WORKSPACE_DIR / "uploads" / fname  # noqa: F405
                save_path.parent.mkdir(exist_ok=True)
                save_path.write_bytes(data)
                file_info = f"[🎤 Voice saved: uploads/{fname} ({len(data) // 1024}KB)]"
                log.info(f"[MIC] Voice saved: {save_path}")
                # Whisper transcription
                api_key = vault.get("openai_api_key")
                if api_key:
                    try:
                        boundary = f"----Whisper{secrets.token_hex(8)}"
                        body = b""
                        body += f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n'.encode()
                        body += f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\nContent-Type: audio/ogg\r\n\r\n'.encode()
                        body += data
                        body += f"\r\n--{boundary}--\r\n".encode()
                        req = urllib.request.Request(
                            "https://api.openai.com/v1/audio/transcriptions",
                            data=body,
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": f"multipart/form-data; boundary={boundary}",
                            },
                            method="POST",
                        )
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            result = json.loads(resp.read())
                        transcript = result.get("text", "")
                        if transcript:
                            file_info = f"[🎤 Voice transcription]\n{transcript}"
                            log.info(f"[MIC] Transcribed: {transcript[:100]}")
                    except Exception as we:
                        log.error(f"Whisper error: {we}")
                        file_info += f"\n[Transcription failed: {we}]"
            except Exception as e:
                file_info = f"[🎤 Voice download failed: {e}]"

        # Build final message
        if file_info:
            text = f"{file_info}\n{text}" if text else file_info

        if not text:
            return

        audit_log("telegram_msg", text[:100])

        # Commands
        if text.startswith("/"):
            await self._handle_command(chat_id, text, tenant_user=_tenant_user)
            return

        # Process message with typing loop + block streaming
        session_id = f"telegram_{chat_id}"
        # Bind user_id to session for multi-tenant
        _session_user_id = _tenant_user["id"] if _tenant_user else None
        _sess_obj = get_session(session_id, user_id=_session_user_id)
        if _session_user_id and not _sess_obj.user_id:
            _sess_obj.user_id = _session_user_id

        # Ack reaction (OpenClaw-style 👀 while processing)
        _msg_id = msg.get("message_id")
        self.ack_reaction(chat_id, _msg_id)

        # Start continuous typing indicator
        typing_task = None
        if self.typing_mode != "never":
            self.send_typing(chat_id)
            typing_task = self._start_typing_loop(chat_id)

        # Block streaming: accumulate streamed text and periodically edit
        _stream_buf = []
        _draft_sent = [False]
        _streaming_config = load_config_from_file()
        _streaming_config.channel = CHANNEL_TELEGRAM
        _BLOCK_STREAM_THRESHOLD = _streaming_config.minChars or 500

        # Streaming mode: 'partial' (every token) or 'block' (chunk-based)
        __stream_mode = getattr(_streaming_config, "streamingMode", "block")  # noqa: F841

        def _on_stream_token(event):
            """Handle streaming tokens for block streaming in Telegram."""
            etype = event.get("type", "")
            if etype == "content_delta":
                text_delta = event.get("text", "")
                if text_delta:
                    _stream_buf.append(text_delta)
                    full = "".join(_stream_buf)
                    if not _draft_sent[0] and len(full) >= _BLOCK_STREAM_THRESHOLD:
                        self._send_draft(chat_id, full + " ▍")
                        _draft_sent[0] = True
                    elif _draft_sent[0]:
                        self._update_draft(chat_id, full + " ▍")

        def _on_status(status_type, detail):
            """Handle status callbacks for typing indicator updates."""
            # We could update the draft with status, but typing action is already running
            pass

        _start = time.time()
        from salmalm.core.engine import process_message

        response = await process_message(
            session_id, text, image_data=_image_data, on_token=_on_stream_token, on_status=_on_status
        )
        _elapsed = time.time() - _start

        # Cancel typing loop
        if typing_task:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

        # Model badge for response
        session_obj = get_session(session_id)
        _model_short = (getattr(session_obj, "last_model", "") or "auto").split("/")[-1][:20]
        __complexity = getattr(session_obj, "last_complexity", "")  # noqa: F841

        # Send response (check for generated files to send)
        import re as _re

        img_match = _re.search(r"uploads/[\w.-]+\.(png|jpg|jpeg|gif|webp)", response)
        audio_match = _re.search(r"uploads/[\w.-]+\.(mp3|wav|ogg)", response)
        suffix = f"\n\n🤖 {_model_short} · ⏱️ {_elapsed:.1f}s"
        if img_match:
            img_path = WORKSPACE_DIR / img_match.group(0)  # noqa: F405
            if img_path.exists():
                # Finalize any draft first
                if _draft_sent[0]:
                    key = str(chat_id)
                    self._draft_messages.pop(key, None)
                self._send_photo(chat_id, img_path, response[:1000])
            else:
                if _draft_sent[0]:
                    self._finalize_draft(chat_id, response, suffix)
                else:
                    self.send_message(chat_id, f"{response}{suffix}")
        elif audio_match:
            audio_path = WORKSPACE_DIR / audio_match.group(0)  # noqa: F405
            if audio_path.exists():
                if _draft_sent[0]:
                    key = str(chat_id)
                    self._draft_messages.pop(key, None)
                self._send_audio(chat_id, audio_path, response[:1000])
            else:
                if _draft_sent[0]:
                    self._finalize_draft(chat_id, response, suffix)
                else:
                    self.send_message(chat_id, f"{response}{suffix}")
        else:
            if _draft_sent[0]:
                self._finalize_draft(chat_id, response, suffix)
            else:
                self.send_message(chat_id, f"{response}{suffix}", reply_to_message_id=_msg_id)

        # Clear ack reaction after response
        self.clear_reaction(chat_id, _msg_id)

        # TTS: send voice message if enabled
        if getattr(session_obj, "tts_enabled", False):
            try:
                self._send_tts_voice(chat_id, response, session_obj)
            except Exception as e:
                log.error(f"TTS error: {e}")


    def stop(self) -> None:
        """Stop the Telegram polling loop."""
        self._running = False


telegram_bot = TelegramBot()
_tg_bot = telegram_bot  # Reference for sub-agent notifications
set_telegram_bot(telegram_bot)  # Register with core accessor
