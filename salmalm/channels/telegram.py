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
from salmalm.constants import APP_NAME, VERSION, WORKSPACE_DIR
from salmalm.security.crypto import vault, log
from salmalm.core import router, get_session, audit_log, compact_messages, set_telegram_bot
from salmalm.core.llm import _http_post, _http_get
from salmalm.core.prompt import build_system_prompt
from salmalm.tools import execute_tool
from salmalm.utils.chunker import EmbeddedBlockChunker, ChunkerConfig, CHANNEL_TELEGRAM, load_config_from_file


class TelegramBot:
    def __init__(self):
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

    def configure(self, token: str, owner_id: str):
        """Configure the Telegram bot with token and owner chat ID."""
        self.token = token
        self.owner_id = owner_id
        self._bot_username: Optional[str] = None
        # Try to fetch bot username
        try:
            me = self._api("getMe")
            if me.get("ok") and me.get("result"):
                self._bot_username = me["result"].get("username")
        except Exception:
            pass
        # Register command menu (OpenClaw-style)
        self._register_commands()

    def _api(self, method: str, data: Optional[dict] = None) -> dict:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        if data:
            return _http_post(url, {"Content-Type": "application/json"}, data)
        return _http_get(url)

    def _extract_buttons(self, text: str):
        """Extract inline button markers. Returns (clean_text, buttons_list)."""
        buttons = []
        import re as _re2

        def _repl(m):
            try:
                import json as _j2

                buttons.extend(_j2.loads(m.group(1)))
            except Exception:
                pass
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
        except Exception:
            pass

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
                    except Exception:
                        pass
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
        except Exception:
            pass
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
            except Exception:
                pass
            log.info(f"[TTS] Voice sent: {len(audio_data)} bytes, voice={voice}")
        except Exception as e:
            log.error(f"[TTS] OpenAI TTS API error: {e}")

    def send_typing(self, chat_id):
        """Send a typing indicator to a Telegram chat."""
        try:
            self._api("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        except Exception:
            pass

    def _start_typing_loop(self, chat_id) -> asyncio.Task:
        """Start an async typing indicator loop that refreshes every 5 seconds.

        Returns a task that can be cancelled when the response is ready.
        """

        async def _loop():
            try:
                while True:
                    await asyncio.to_thread(self.send_typing, chat_id)
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                pass

        return asyncio.create_task(_loop())

    def edit_message(self, chat_id, message_id, text: str, parse_mode: Optional[str] = None):
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
        except Exception:
            # Fallback without parse_mode
            if parse_mode:
                data2 = {k: v for k, v in data.items() if k != "parse_mode"}
                try:
                    self._api("editMessageText", data2)
                except Exception:
                    pass

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
        except Exception:
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

    async def handle_webhook_update(self, update: dict):
        """Process a single update received via webhook."""
        await self._handle_update(update)

    async def poll(self):
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
        cb = update.get("callback_query")
        if cb:
            cb_data = cb.get("data", "")
            cb_chat_id = cb.get("message", {}).get("chat", {}).get("id")
            cb_user_id = str(cb.get("from", {}).get("id", ""))
            try:
                self._api("answerCallbackQuery", {"callback_query_id": cb["id"]})
            except Exception:
                pass
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
                    except Exception:
                        pass
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

    async def _handle_command(self, chat_id, text: str, tenant_user=None):
        cmd = text.split()[0].lower()

        # Multi-tenant commands (available even when not registered)
        if cmd == "/register":
            from salmalm.features.users import user_manager

            if not user_manager.multi_tenant_enabled:
                self.send_message(chat_id, "멀티테넌트 모드가 비활성화되어 있습니다. / Multi-tenant mode is disabled.")
                return
            parts = text.split(maxsplit=1)
            if len(parts) < 2 or len(parts[1].strip()) < 8:
                self.send_message(
                    chat_id, "❌ 사용법: /register <비밀번호> (8자 이상)\nUsage: /register <password> (8+ chars)"
                )
                return
            password = parts[1].strip()
            tg_username = ""  # Will be set from update context
            result = user_manager.register_telegram_user(str(chat_id), password, tg_username)
            if result["ok"]:
                self.send_message(
                    chat_id,
                    f"✅ 등록 완료! 사용자: {result['user']['username']}\n"
                    f"Registration complete! User: {result['user']['username']}",
                )
            else:
                self.send_message(chat_id, f"❌ {result['error']}")
            return

        if cmd == "/quota":
            from salmalm.features.users import user_manager

            if not user_manager.multi_tenant_enabled or not tenant_user:
                self.send_message(chat_id, "멀티테넌트 모드가 비활성화되어 있습니다.")
                return
            parts = text.split()
            # Admin: /quota set <user> <daily> <monthly>
            if len(parts) >= 5 and parts[1] == "set" and tenant_user.get("role") == "admin":
                target = user_manager.get_user_by_username(parts[2])
                if not target:
                    self.send_message(chat_id, f"❌ 사용자를 찾을 수 없습니다: {parts[2]}")
                    return
                try:
                    user_manager.set_quota(target["id"], daily_limit=float(parts[3]), monthly_limit=float(parts[4]))
                    self.send_message(chat_id, f"✅ {parts[2]} 쿼터 설정: 일 ${parts[3]}, 월 ${parts[4]}")
                except Exception as e:
                    self.send_message(chat_id, f"❌ {e}")
                return
            # Show own quota
            quota = user_manager.get_quota(tenant_user["id"])
            self.send_message(
                chat_id,
                f"📊 사용량 / Quota\n"
                f"  일일: ${quota.get('current_daily', 0):.2f} / ${quota.get('daily_limit', 5):.2f} "
                f"(남은: ${quota.get('daily_remaining', 0):.2f})\n"
                f"  월별: ${quota.get('current_monthly', 0):.2f} / ${quota.get('monthly_limit', 50):.2f} "
                f"(남은: ${quota.get('monthly_remaining', 0):.2f})",
            )
            return

        if cmd == "/user" and tenant_user and tenant_user.get("role") == "admin":
            from salmalm.features.users import user_manager
            from salmalm.web.auth import auth_manager

            parts = text.split()
            if len(parts) >= 3 and parts[1] == "create":
                username = parts[2]
                password = parts[3] if len(parts) > 3 else None
                if not password:
                    self.send_message(chat_id, "❌ /user create <username> <password>")
                    return
                try:
                    user = auth_manager.create_user(username, password, "user")
                    user_manager.ensure_quota(user["id"])
                    self.send_message(chat_id, f"✅ 사용자 생성: {username}")
                except ValueError as e:
                    self.send_message(chat_id, f"❌ {e}")
                return
            elif len(parts) >= 2 and parts[1] == "list":
                users = user_manager.get_all_users_with_stats()
                lines = ["👥 사용자 목록:"]
                for u in users:
                    status = "✅" if u["enabled"] else "⛔"
                    lines.append(f"  {status} {u['username']} ({u['role']}) - ${u.get('total_cost', 0):.2f}")
                self.send_message(chat_id, "\n".join(lines))
                return
            elif len(parts) >= 3 and parts[1] == "delete":
                ok = auth_manager.delete_user(parts[2])
                self.send_message(chat_id, f"{'✅ 삭제됨' if ok else '❌ 실패'}: {parts[2]}")
                return
            self.send_message(chat_id, "Usage: /user create|list|delete")
            return

        if cmd == "/start":
            self.send_message(chat_id, f"😈 {APP_NAME} v{VERSION} running\nready")  # noqa: F405
        elif cmd == "/usage":
            report = execute_tool("usage_report", {})
            self.send_message(chat_id, report)
        elif cmd == "/model":
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                router.force_model = parts[1] if parts[1] != "auto" else None
                self.send_message(chat_id, f"Model changed: {parts[1]}")
            else:
                current = router.force_model or "auto (routing)"
                models = "\n".join(f"  {m}" for tier in router.TIERS.values() for m in tier)
                self.send_message(chat_id, f"Current: {current}\n\nAvailable:\n{models}\n\n/model auto — auto")
        elif cmd == "/compact":
            session = get_session(f"telegram_{chat_id}")
            before = len(session.messages)
            session.messages = compact_messages(session.messages)
            self.send_message(chat_id, f"Compacted: {before} → {len(session.messages)} messages")
        elif cmd == "/clear":
            session = get_session(f"telegram_{chat_id}")
            session.messages = []
            session.add_system(build_system_prompt())
            self.send_message(chat_id, "🗑️ Chat cleared")
        elif cmd == "/tts":
            parts = text.split(maxsplit=1)
            session = get_session(f"telegram_{chat_id}")
            if len(parts) > 1 and parts[1].strip() in ("on", "off"):
                session.tts_enabled = parts[1].strip() == "on"
                status = "ON 🔊" if session.tts_enabled else "OFF 🔇"
                self.send_message(chat_id, f"TTS: {status}")
            else:
                status = "ON" if getattr(session, "tts_enabled", False) else "OFF"
                voice = getattr(session, "tts_voice", "alloy")
                self.send_message(
                    chat_id,
                    f"🔊 TTS: {status} (voice: {voice})\n/tts on · /tts off\n/voice alloy|nova|echo|fable|onyx|shimmer",
                )
        elif cmd == "/voice":
            parts = text.split(maxsplit=1)
            session = get_session(f"telegram_{chat_id}")
            valid_voices = ("alloy", "nova", "echo", "fable", "onyx", "shimmer")
            if len(parts) > 1 and parts[1].strip() in valid_voices:
                session.tts_voice = parts[1].strip()
                self.send_message(chat_id, f"🎙️ Voice: {session.tts_voice}")
            else:
                self.send_message(chat_id, f"Voices: {', '.join(valid_voices)}")
        elif cmd == "/help":
            self.send_message(
                chat_id,
                textwrap.dedent(f"""
                😈 {APP_NAME} v{VERSION}  # noqa: F405

                📋 **Assistant**
                /briefing — Daily briefing (날씨+일정+메일)
                /routine [morning|evening] — 루틴 실행
                /remind list — 리마인더 목록
                /remind delete <id> — 리마인더 삭제
                /tr <lang> <text> — 빠른 번역

                📝 **Notes & Knowledge**
                /note <content> — 메모 저장
                /note search <query> — 메모 검색
                /note list — 최근 메모
                /note tag <tag> <content> — 태그 메모

                💰 **Expenses**
                /expense add <desc> <amount> [cat] — 지출 기록
                /expense today — 오늘 지출
                /expense month [YYYY-MM] — 월별 요약

                🔖 **Links**
                /save <url> — 링크 저장
                /saved list — 저장 목록
                /saved search <query> — 검색

                🍅 **Pomodoro**
                /pomodoro start [min] — 집중 시작
                /pomodoro break [min] — 휴식
                /pomodoro stop — 중지

                📅 **Calendar & Email**
                /cal [today|week|month] — Calendar
                /mail [inbox|read|send|search] — Email

                ⚙️ **System**
                /usage — Token usage/cost
                /model [auto|...] — Model
                /compact — Compact conversation
                /clear — Clear conversation
                /tts [on|off] — Voice
                /help — This help
            """).strip(),
            )
        elif cmd == "/telegram":
            parts = text.split(maxsplit=2)
            if len(parts) >= 2 and parts[1] == "webhook":
                if len(parts) < 3:
                    self.send_message(chat_id, "❌ Usage: /telegram webhook <url>")
                    return
                url = parts[2].strip()
                result = self.set_webhook(url)
                if result.get("ok"):
                    self.send_message(chat_id, f"✅ Webhook set: {url}")
                else:
                    self.send_message(chat_id, f"❌ Webhook failed: {result}")
            elif len(parts) >= 2 and parts[1] == "polling":
                result = self.delete_webhook()
                self.send_message(chat_id, "✅ Switched to polling mode")
            else:
                mode = "webhook" if self._webhook_mode else "polling"
                self.send_message(chat_id, f"📡 Mode: {mode}\n/telegram webhook <url>\n/telegram polling")

        elif cmd in ("/cal", "/calendar"):
            parts = text.split(maxsplit=3)
            sub = parts[1] if len(parts) > 1 else "today"
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            if sub == "today":
                result = _exec_tool("calendar_list", {"period": "today"})
            elif sub == "week":
                result = _exec_tool("calendar_list", {"period": "week"})
            elif sub == "month":
                result = _exec_tool("calendar_list", {"period": "month"})
            elif sub == "add":
                # /cal add 2026-02-20 14:00 회의
                rest = parts[2] if len(parts) > 2 else ""
                cal_parts = rest.split(maxsplit=2)
                if len(cal_parts) < 2:
                    self.send_message(chat_id, "❌ Usage: /cal add YYYY-MM-DD HH:MM 제목")
                    return
                date_str = cal_parts[0]
                # Check if second part is time or title
                if ":" in cal_parts[1]:
                    time_str = cal_parts[1]
                    title = cal_parts[2] if len(cal_parts) > 2 else "Event"
                else:
                    time_str = ""
                    title = " ".join(cal_parts[1:])
                args = {"title": title, "date": date_str}
                if time_str:
                    args["time"] = time_str
                result = _exec_tool("calendar_add", args)
            elif sub == "delete":
                event_id = parts[2] if len(parts) > 2 else ""
                if not event_id:
                    self.send_message(chat_id, "❌ Usage: /cal delete <event_id>")
                    return
                result = _exec_tool("calendar_delete", {"event_id": event_id})
            else:
                result = _exec_tool("calendar_list", {"period": "week"})
            self.send_message(chat_id, result)

        elif cmd in ("/mail", "/email"):
            parts = text.split(maxsplit=4)
            sub = parts[1] if len(parts) > 1 else "inbox"
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            if sub == "inbox":
                result = _exec_tool("email_inbox", {})
            elif sub == "read":
                msg_id = parts[2] if len(parts) > 2 else ""
                if not msg_id:
                    self.send_message(chat_id, "❌ Usage: /mail read <message_id>")
                    return
                result = _exec_tool("email_read", {"message_id": msg_id})
            elif sub == "send":
                # /mail send to@email.com "제목" "본문"
                if len(parts) < 4:
                    self.send_message(chat_id, '❌ Usage: /mail send to@email.com "제목" "본문"')
                    return
                to_addr = parts[2]
                rest = text.split(to_addr, 1)[1].strip() if to_addr in text else ""
                # Parse quoted subject and body
                import shlex

                try:
                    parsed = shlex.split(rest)
                except ValueError:
                    parsed = rest.split(maxsplit=1)
                subject = parsed[0] if parsed else "No subject"
                body = parsed[1] if len(parsed) > 1 else ""
                result = _exec_tool("email_send", {"to": to_addr, "subject": subject, "body": body})
            elif sub == "search":
                query = " ".join(parts[2:]) if len(parts) > 2 else ""
                if not query:
                    self.send_message(chat_id, "❌ Usage: /mail search <query>")
                    return
                result = _exec_tool("email_search", {"query": query})
            else:
                result = _exec_tool("email_inbox", {})
            self.send_message(chat_id, result)

        elif cmd == "/briefing":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            sections = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else None
            args = {"sections": sections} if sections else {}
            result = _exec_tool("briefing", args)
            self.send_message(chat_id, result)

        elif cmd == "/note":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=2)
            sub = parts[1] if len(parts) > 1 else ""
            if sub == "search":
                query = parts[2] if len(parts) > 2 else ""
                result = (
                    _exec_tool("note", {"action": "search", "query": query})
                    if query
                    else "❌ Usage: /note search <keyword>"
                )
            elif sub == "list":
                result = _exec_tool("note", {"action": "list"})
            elif sub == "tag":
                # /note tag work "content..."
                rest = text.split(maxsplit=3)
                tag = rest[2] if len(rest) > 2 else ""
                content = rest[3] if len(rest) > 3 else ""
                result = (
                    _exec_tool("note", {"action": "save", "content": content, "tags": tag})
                    if content
                    else "❌ Usage: /note tag <tag> <content>"
                )
            elif sub == "delete":
                nid = parts[2] if len(parts) > 2 else ""
                result = (
                    _exec_tool("note", {"action": "delete", "note_id": nid}) if nid else "❌ Usage: /note delete <id>"
                )
            else:
                # /note <content> → save directly
                content = text[len("/note") :].strip()
                result = (
                    _exec_tool("note", {"action": "save", "content": content})
                    if content
                    else "❌ Usage: /note <content> or /note search/list/tag/delete"
                )
            self.send_message(chat_id, result)

        elif cmd == "/expense":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=3)
            sub = parts[1] if len(parts) > 1 else "today"
            if sub == "add":
                # /expense add 점심 12000 식비
                rest = text.split(maxsplit=1)[1][4:].strip() if len(text) > 12 else ""
                eparts = rest.split()
                if len(eparts) >= 2:
                    desc = eparts[0]
                    amount = eparts[1]
                    cat = eparts[2] if len(eparts) > 2 else ""
                    result = _exec_tool(
                        "expense", {"action": "add", "description": desc, "amount": amount, "category": cat}
                    )
                else:
                    result = "❌ Usage: /expense add <description> <amount> [category]"
            elif sub == "today":
                result = _exec_tool("expense", {"action": "today"})
            elif sub == "month":
                month = parts[2] if len(parts) > 2 else ""
                args = {"action": "month"}
                if month:
                    args["month"] = month
                result = _exec_tool("expense", args)
            elif sub == "delete":
                eid = parts[2] if len(parts) > 2 else ""
                result = (
                    _exec_tool("expense", {"action": "delete", "expense_id": eid})
                    if eid
                    else "❌ Usage: /expense delete <id>"
                )
            else:
                result = _exec_tool("expense", {"action": "today"})
            self.send_message(chat_id, result)

        elif cmd == "/save":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            url = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if url:
                result = _exec_tool("save_link", {"action": "save", "url": url})
            else:
                result = "❌ Usage: /save <url>"
            self.send_message(chat_id, result)

        elif cmd == "/saved":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=2)
            sub = parts[1] if len(parts) > 1 else "list"
            if sub == "list":
                result = _exec_tool("save_link", {"action": "list"})
            elif sub == "search":
                query = parts[2] if len(parts) > 2 else ""
                result = (
                    _exec_tool("save_link", {"action": "search", "query": query})
                    if query
                    else "❌ Usage: /saved search <keyword>"
                )
            elif sub == "delete":
                lid = parts[2] if len(parts) > 2 else ""
                result = (
                    _exec_tool("save_link", {"action": "delete", "link_id": lid})
                    if lid
                    else "❌ Usage: /saved delete <id>"
                )
            else:
                result = _exec_tool("save_link", {"action": "list"})
            self.send_message(chat_id, result)

        elif cmd == "/pomodoro":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=2)
            sub = parts[1] if len(parts) > 1 else "status"
            if sub == "start":
                duration = parts[2] if len(parts) > 2 else "25"
                result = _exec_tool("pomodoro", {"action": "start", "duration": duration})
            elif sub == "break":
                duration = parts[2] if len(parts) > 2 else "5"
                result = _exec_tool("pomodoro", {"action": "break", "duration": duration})
            elif sub == "stop":
                result = _exec_tool("pomodoro", {"action": "stop"})
            else:
                result = _exec_tool("pomodoro", {"action": "status"})
            self.send_message(chat_id, result)

        elif cmd == "/routine":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=1)
            sub = parts[1].strip() if len(parts) > 1 else "list"
            result = _exec_tool("routine", {"action": sub})
            self.send_message(chat_id, result)

        elif cmd == "/remind":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=2)
            sub = parts[1] if len(parts) > 1 else "list"
            if sub == "list":
                result = _exec_tool("reminder", {"action": "list"})
            elif sub == "delete":
                rid = parts[2] if len(parts) > 2 else ""
                result = (
                    _exec_tool("reminder", {"action": "delete", "reminder_id": rid})
                    if rid
                    else "❌ Usage: /remind delete <id>"
                )
            else:
                result = _exec_tool("reminder", {"action": "list"})
            self.send_message(chat_id, result)

        elif cmd == "/tr":
            from salmalm.tools.tool_registry import execute_tool as _exec_tool

            parts = text.split(maxsplit=2)
            if len(parts) >= 3:
                target_lang = parts[1]
                tr_text = parts[2]
                result = _exec_tool("translate", {"text": tr_text, "target": target_lang})
            else:
                result = "❌ Usage: /tr <lang> <text>\nExample: /tr en 안녕하세요"
            self.send_message(chat_id, result)

        elif cmd == "/export":
            self.send_typing(chat_id)
            try:
                from salmalm.utils.migration import export_agent, export_filename

                parts = text.split()
                include_vault = "--vault" in parts
                zip_bytes = export_agent(include_vault=include_vault)
                fname = export_filename()
                # Send as document
                self._send_document(chat_id, zip_bytes, fname, caption=f"📦 Agent Export ({len(zip_bytes) // 1024}KB)")
            except Exception as e:
                self.send_message(chat_id, f"❌ Export failed: {e}")

        elif cmd == "/import":
            self.send_message(
                chat_id,
                "📦 에이전트 가져오기: ZIP 파일을 이 채팅에 보내주세요.\n"
                "Agent import: Send a ZIP file to this chat.\n"
                "(salmalm-agent-export-*.zip)",
            )

        elif cmd == "/sync":
            parts = text.split(maxsplit=1)
            sub = parts[1].strip() if len(parts) > 1 else "export"
            if sub == "export":
                from salmalm.utils.migration import quick_sync_export

                data = quick_sync_export()
                sync_json = json.dumps(data, ensure_ascii=False, indent=2)
                self.send_message(chat_id, f"📋 Quick Sync Export\n```json\n{sync_json[:3500]}\n```")
            elif sub.startswith("import"):
                json_str = sub[len("import") :].strip()
                if not json_str:
                    self.send_message(chat_id, "❌ Usage: /sync import <json>")
                    return
                try:
                    data = json.loads(json_str)
                    from salmalm.utils.migration import quick_sync_import

                    quick_sync_import(data)
                    self.send_message(chat_id, "✅ Quick sync imported / 빠른 동기화 완료")
                except json.JSONDecodeError:
                    self.send_message(chat_id, "❌ Invalid JSON")
                except Exception as e:
                    self.send_message(chat_id, f"❌ {e}")
            else:
                self.send_message(chat_id, "Usage: /sync export | /sync import <json>")

        else:
            # Route unknown /commands through engine (handles /model auto/opus/sonnet/haiku etc.)
            self.send_typing(chat_id)
            session_id = f"telegram_{chat_id}"
            from salmalm.core.engine import process_message

            response = await process_message(session_id, text)
            self.send_message(chat_id, response)

    def stop(self):
        """Stop the Telegram polling loop."""
        self._running = False


telegram_bot = TelegramBot()
_tg_bot = telegram_bot  # Reference for sub-agent notifications
set_telegram_bot(telegram_bot)  # Register with core accessor
