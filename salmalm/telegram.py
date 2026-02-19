"""SalmAlm Telegram bot."""
from __future__ import annotations

import asyncio, json, re, secrets, textwrap, time, urllib.request
from typing import Any, Dict, List, Optional

from .constants import *
from .crypto import vault, log
from .core import router, get_session, _sessions, audit_log, compact_messages, set_telegram_bot
from .llm import _http_post, _http_get
from .prompt import build_system_prompt
from .tools import execute_tool

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
        self.typing_mode = 'instant'

    def configure(self, token: str, owner_id: str):
        """Configure the Telegram bot with token and owner chat ID."""
        self.token = token
        self.owner_id = owner_id

    def _api(self, method: str, data: Optional[dict] = None) -> dict:
        url = f'https://api.telegram.org/bot{self.token}/{method}'
        if data:
            return _http_post(url, {'Content-Type': 'application/json'}, data)
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
            return ''
        clean = _re2.sub(r'<!--buttons:(\[.*?\])-->', _repl, text)
        return clean.strip(), buttons

    def send_message(self, chat_id, text: str, parse_mode: Optional[str] = None,
                     reply_markup: Optional[dict] = None):
        """Send a text message to a Telegram chat, with optional inline keyboard."""
        text, btn_labels = self._extract_buttons(text)
        if btn_labels and not reply_markup:
            reply_markup = {'inline_keyboard': [
                [{'text': label, 'callback_data': f'btn:{label}'[:64]} for label in btn_labels]
            ]}
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for idx, chunk in enumerate(chunks):
            data = {'chat_id': chat_id, 'text': chunk}
            if parse_mode:
                data['parse_mode'] = parse_mode
            if reply_markup and idx == len(chunks) - 1:
                data['reply_markup'] = reply_markup
            try:
                self._api('sendMessage', data)
            except Exception as e:
                if parse_mode:
                    data2 = {'chat_id': chat_id, 'text': chunk}
                    if reply_markup and idx == len(chunks) - 1:
                        data2['reply_markup'] = reply_markup
                    self._api('sendMessage', data2)

    def _send_photo(self, chat_id, path: Path, caption: str = ''):
        """Send a photo file to Telegram."""
        try:
            import mimetypes
            boundary = f'----SalmAlm{secrets.token_hex(8)}'
            body = b''
            # chat_id field
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode()
            if caption:
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption[:1000]}\r\n'.encode()
            # photo field
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{path.name}"\r\nContent-Type: image/png\r\n\r\n'.encode()
            body += path.read_bytes()
            body += f'\r\n--{boundary}--\r\n'.encode()
            req = urllib.request.Request(
                f'https://api.telegram.org/bot{self.token}/sendPhoto',
                data=body,
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
                method='POST'
            )
            urllib.request.urlopen(req, timeout=30)
        except Exception as e:
            log.error(f"Send photo error: {e}")
            self.send_message(chat_id, f'📷 Image send failed: {e}')

    def _send_audio(self, chat_id, path: Path, caption: str = ''):
        """Send an audio file to Telegram."""
        try:
            boundary = f'----SalmAlm{secrets.token_hex(8)}'
            body = b''
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode()
            if caption:
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption[:1000]}\r\n'.encode()
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="voice"; filename="{path.name}"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode()
            body += path.read_bytes()
            body += f'\r\n--{boundary}--\r\n'.encode()
            req = urllib.request.Request(
                f'https://api.telegram.org/bot{self.token}/sendVoice',
                data=body,
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
                method='POST'
            )
            urllib.request.urlopen(req, timeout=30)
        except Exception as e:
            log.error(f"Send audio error: {e}")
            self.send_message(chat_id, f'🔊 Voice send failed: {e}')

    def _send_tts_voice(self, chat_id, text: str, session):
        """Generate TTS audio via OpenAI API and send as voice message."""
        api_key = vault.get('openai_api_key')
        if not api_key:
            log.warning("[TTS] No openai_api_key in vault")
            return
        # Clean text for TTS (remove markdown, code blocks, URLs)
        import re as _re2
        clean = _re2.sub(r'```[\s\S]*?```', '', text)
        clean = _re2.sub(r'`[^`]+`', '', clean)
        clean = _re2.sub(r'https?://\S+', '', clean)
        clean = _re2.sub(r'[*_#\[\]()>]', '', clean)
        clean = clean.strip()
        if not clean or len(clean) < 3:
            return
        # Truncate to 4096 chars (API limit)
        clean = clean[:4096]
        voice = getattr(session, 'tts_voice', 'alloy')
        try:
            tts_body = json.dumps({
                'model': 'tts-1',
                'input': clean,
                'voice': voice,
                'response_format': 'opus',
            }).encode()
            req = urllib.request.Request(
                'https://api.openai.com/v1/audio/speech',
                data=tts_body,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio_data = resp.read()
            # Save to temp file and send
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
                f.write(audio_data)
                tmp_path = Path(f.name)
            self._send_audio(chat_id, tmp_path, '')
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
            self._api('sendChatAction', {'chat_id': chat_id, 'action': 'typing'})
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
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text[:4000],
        }
        if parse_mode:
            data['parse_mode'] = parse_mode
        try:
            self._api('editMessageText', data)
        except Exception:
            # Fallback without parse_mode
            if parse_mode:
                data2 = {k: v for k, v in data.items() if k != 'parse_mode'}
                try:
                    self._api('editMessageText', data2)
                except Exception:
                    pass

    def _send_draft(self, chat_id, text: str) -> Optional[int]:
        """Send initial draft message for block streaming. Returns message_id."""
        data = {'chat_id': chat_id, 'text': text[:4000]}
        try:
            resp = self._api('sendMessage', data)
            msg_id = resp.get('result', {}).get('message_id')
            if msg_id:
                self._draft_messages[str(chat_id)] = {
                    'msg_id': msg_id,
                    'text': text,
                    'last_edit': time.time(),
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
        if not force and (now - draft['last_edit']) < 2.0:
            return

        # Don't edit in the middle of a code block (odd number of ```)
        fence_count = text.count('```')
        if not force and fence_count % 2 != 0:
            return

        draft['text'] = text
        draft['last_edit'] = now
        self.edit_message(chat_id, draft['msg_id'], text)

    def _finalize_draft(self, chat_id, text: str, suffix: str = ''):
        """Finalize draft message with complete text + suffix."""
        key = str(chat_id)
        draft = self._draft_messages.get(key)
        final = f'{text}{suffix}' if suffix else text
        if draft:
            self.edit_message(chat_id, draft['msg_id'], final)
            del self._draft_messages[key]
            return draft['msg_id']
        else:
            # No draft — send as new message
            self.send_message(chat_id, final)
            return None

    # ── Webhook support ──────────────────────────────────────────

    def set_webhook(self, url: str) -> dict:
        """Set Telegram webhook. Generates a secret_token for request verification."""
        self._webhook_secret = secrets.token_hex(32)
        result = self._api('setWebhook', {
            'url': url,
            'secret_token': self._webhook_secret,
            'allowed_updates': ['message', 'callback_query'],
        })
        if result.get('ok'):
            self._webhook_mode = True
            log.info(f"[NET] Telegram webhook set: {url}")
        return result

    def delete_webhook(self) -> dict:
        """Delete Telegram webhook and return to polling mode."""
        result = self._api('deleteWebhook', {'drop_pending_updates': False})
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
                resp = await asyncio.to_thread(self._api, 'getUpdates', {
                    'offset': self.offset, 'timeout': 30,
                    'allowed_updates': ['message', 'callback_query']
                })
                for update in resp.get('result', []):
                    self.offset = update['update_id'] + 1
                    await self._handle_update(update)
            except Exception as e:
                log.error(f"Telegram poll error: {e}")
                await asyncio.sleep(5)

    def _download_file(self, file_id: str) -> tuple:
        """Download a file from Telegram. Returns (data, filename)."""
        info = self._api('getFile', {'file_id': file_id})
        file_path = info['result']['file_path']
        filename = file_path.split('/')[-1]
        # Sanitize filename — remove path traversal chars
        filename = re.sub(r'[/\\\.]{2,}', '_', filename)
        filename = re.sub(r'[^\w.\-]', '_', filename)
        if not filename or filename.startswith('.'):
            filename = f'file_{int(time.time())}'
        url = f'https://api.telegram.org/file/bot{self.token}/{file_path}'
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        return data, filename

    async def _handle_update(self, update: dict):
        # Handle inline button callback queries
        cb = update.get('callback_query')
        if cb:
            cb_data = cb.get('data', '')
            cb_chat_id = cb.get('message', {}).get('chat', {}).get('id')
            cb_user_id = str(cb.get('from', {}).get('id', ''))
            try:
                self._api('answerCallbackQuery', {'callback_query_id': cb['id']})
            except Exception:
                pass
            if cb_user_id == self.owner_id and cb_chat_id and cb_data.startswith('btn:'):
                btn_text = cb_data[4:]
                self.send_typing(cb_chat_id)
                session_id = f'telegram_{cb_chat_id}'
                _start = time.time()
                from .engine import process_message
                response = await process_message(session_id, btn_text)
                _elapsed = time.time() - _start
                self.send_message(cb_chat_id, f"{response}\n\n⏱️ {_elapsed:.1f}s")
            return

        msg = update.get('message')
        if not msg:
            return

        chat_id = msg['chat']['id']
        user_id = str(msg['from']['id'])

        # Owner check
        if user_id != self.owner_id:
            log.warning(f"[BLOCK] Unauthorized: {user_id} tried to message")
            audit_log('unauthorized', f'user_id={user_id}')
            return

        text = msg.get('text', '') or msg.get('caption', '') or ''
        file_info = None

        # Handle photos (with vision support)
        _image_data = None
        if msg.get('photo'):
            photo = msg['photo'][-1]  # Largest size
            try:
                data, fname = self._download_file(photo['file_id'])
                save_path = WORKSPACE_DIR / 'uploads' / fname
                save_path.parent.mkdir(exist_ok=True)
                save_path.write_bytes(data)
                file_info = f'[📷 Image saved: uploads/{fname} ({len(data)//1024}KB)]'
                log.info(f"[PHOTO] Photo saved: {save_path}")
                # Prepare vision data
                import base64 as _b64
                _image_data = (_b64.b64encode(data).decode(), 'image/jpeg')
            except Exception as e:
                file_info = f'[📷 Image download failed: {e}]'

        # Handle documents
        if msg.get('document'):
            doc = msg['document']
            try:
                data, fname = self._download_file(doc['file_id'])
                save_path = WORKSPACE_DIR / 'uploads' / (doc.get('file_name', fname))
                save_path.parent.mkdir(exist_ok=True)
                save_path.write_bytes(data)
                file_info = f'[📎 File saved: uploads/{save_path.name} ({len(data)//1024}KB)]'
                log.info(f"[CLIP] File saved: {save_path}")
                # If text file, include content preview
                if save_path.suffix in ('.txt', '.md', '.py', '.js', '.json', '.csv', '.log', '.html', '.css', '.sh', '.bat'):
                    try:
                        content = data.decode('utf-8', errors='replace')[:3000]
                        file_info += f'\n[File content preview]\n{content}'
                    except Exception:
                        pass
            except Exception as e:
                file_info = f'[📎 File download failed: {e}]'

        # Handle voice/audio
        if msg.get('voice') or msg.get('audio'):
            audio = msg.get('voice') or msg.get('audio')
            try:
                data, fname = self._download_file(audio['file_id'])
                save_path = WORKSPACE_DIR / 'uploads' / fname
                save_path.parent.mkdir(exist_ok=True)
                save_path.write_bytes(data)
                file_info = f'[🎤 Voice saved: uploads/{fname} ({len(data)//1024}KB)]'
                log.info(f"[MIC] Voice saved: {save_path}")
                # Whisper transcription
                api_key = vault.get('openai_api_key')
                if api_key:
                    try:
                        boundary = f'----Whisper{secrets.token_hex(8)}'
                        body = b''
                        body += f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n'.encode()
                        body += f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\nContent-Type: audio/ogg\r\n\r\n'.encode()
                        body += data
                        body += f'\r\n--{boundary}--\r\n'.encode()
                        req = urllib.request.Request(
                            'https://api.openai.com/v1/audio/transcriptions',
                            data=body,
                            headers={'Authorization': f'Bearer {api_key}',
                                     'Content-Type': f'multipart/form-data; boundary={boundary}'},
                            method='POST'
                        )
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            result = json.loads(resp.read())
                        transcript = result.get('text', '')
                        if transcript:
                            file_info = f'[🎤 Voice transcription]\n{transcript}'
                            log.info(f"[MIC] Transcribed: {transcript[:100]}")
                    except Exception as we:
                        log.error(f"Whisper error: {we}")
                        file_info += f'\n[Transcription failed: {we}]'
            except Exception as e:
                file_info = f'[🎤 Voice download failed: {e}]'

        # Build final message
        if file_info:
            text = f'{file_info}\n{text}' if text else file_info
        
        if not text:
            return

        audit_log('telegram_msg', text[:100])

        # Commands
        if text.startswith('/'):
            await self._handle_command(chat_id, text)
            return

        # Process message
        self.send_typing(chat_id)
        session_id = f'telegram_{chat_id}'
        _start = time.time()
        from .engine import process_message
        response = await process_message(session_id, text, image_data=_image_data)
        _elapsed = time.time() - _start

        # Model badge for response
        _model_name = getattr(session_obj, 'last_model', 'auto') if 'session_obj' in dir() else 'auto'
        session_obj = get_session(session_id)
        _model_short = (getattr(session_obj, 'last_model', '') or 'auto').split('/')[-1][:20]
        _complexity = getattr(session_obj, 'last_complexity', '')

        # Send response (check for generated files to send)
        import re as _re
        img_match = _re.search(r'uploads/[\w.-]+\.(png|jpg|jpeg|gif|webp)', response)
        audio_match = _re.search(r'uploads/[\w.-]+\.(mp3|wav|ogg)', response)
        suffix = f'\n\n🤖 {_model_short} · ⏱️ {_elapsed:.1f}s'
        if img_match:
            img_path = WORKSPACE_DIR / img_match.group(0)
            if img_path.exists():
                self._send_photo(chat_id, img_path, response[:1000])
            else:
                self.send_message(chat_id, f'{response}{suffix}')
        elif audio_match:
            audio_path = WORKSPACE_DIR / audio_match.group(0)
            if audio_path.exists():
                self._send_audio(chat_id, audio_path, response[:1000])
            else:
                self.send_message(chat_id, f'{response}{suffix}')
        else:
            self.send_message(chat_id, f'{response}{suffix}')

        # TTS: send voice message if enabled
        if getattr(session_obj, 'tts_enabled', False):
            try:
                self._send_tts_voice(chat_id, response, session_obj)
            except Exception as e:
                log.error(f"TTS error: {e}")

    async def _handle_command(self, chat_id, text: str):
        cmd = text.split()[0].lower()
        if cmd == '/start':
            self.send_message(chat_id, f'😈 {APP_NAME} v{VERSION} running\nready')
        elif cmd == '/usage':
            report = execute_tool('usage_report', {})
            self.send_message(chat_id, report)
        elif cmd == '/model':
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                router.force_model = parts[1] if parts[1] != 'auto' else None
                self.send_message(chat_id, f'Model changed: {parts[1]}')
            else:
                current = router.force_model or 'auto (routing)'
                models = '\n'.join(f'  {m}' for tier in router.TIERS.values() for m in tier)
                self.send_message(chat_id, f'Current: {current}\n\nAvailable:\n{models}\n\n/model auto — auto')
        elif cmd == '/compact':
            session = get_session(f'telegram_{chat_id}')
            before = len(session.messages)
            session.messages = compact_messages(session.messages)
            self.send_message(chat_id, f'Compacted: {before} → {len(session.messages)} messages')
        elif cmd == '/clear':
            session = get_session(f'telegram_{chat_id}')
            session.messages = []
            session.add_system(build_system_prompt())
            self.send_message(chat_id, '🗑️ Chat cleared')
        elif cmd == '/tts':
            parts = text.split(maxsplit=1)
            session = get_session(f'telegram_{chat_id}')
            if len(parts) > 1 and parts[1].strip() in ('on', 'off'):
                session.tts_enabled = (parts[1].strip() == 'on')
                status = 'ON 🔊' if session.tts_enabled else 'OFF 🔇'
                self.send_message(chat_id, f'TTS: {status}')
            else:
                status = 'ON' if getattr(session, 'tts_enabled', False) else 'OFF'
                voice = getattr(session, 'tts_voice', 'alloy')
                self.send_message(chat_id, f'🔊 TTS: {status} (voice: {voice})\n/tts on · /tts off\n/voice alloy|nova|echo|fable|onyx|shimmer')
        elif cmd == '/voice':
            parts = text.split(maxsplit=1)
            session = get_session(f'telegram_{chat_id}')
            valid_voices = ('alloy', 'nova', 'echo', 'fable', 'onyx', 'shimmer')
            if len(parts) > 1 and parts[1].strip() in valid_voices:
                session.tts_voice = parts[1].strip()
                self.send_message(chat_id, f'🎙️ Voice: {session.tts_voice}')
            else:
                self.send_message(chat_id, f'Voices: {", ".join(valid_voices)}')
        elif cmd == '/help':
            self.send_message(chat_id, textwrap.dedent(f"""
                😈 {APP_NAME} v{VERSION}
                /usage — Token usage/cost
                /model [auto|opus|sonnet|haiku] — Model
                /compact — Compact conversation
                /clear — Clear conversation
                /tts [on|off] — Voice replies
                /voice [name] — TTS voice
                /cal [today|week|month] — Calendar
                /cal add YYYY-MM-DD HH:MM title — Add event
                /cal delete <event_id> — Delete event
                /mail [inbox] — Recent emails
                /mail read <id> — Read email
                /mail send to subject body — Send email
                /mail search <query> — Search emails
                /telegram [webhook <url>|polling] — Bot mode
                /help — This help
            """).strip())
        elif cmd == '/telegram':
            parts = text.split(maxsplit=2)
            if len(parts) >= 2 and parts[1] == 'webhook':
                if len(parts) < 3:
                    self.send_message(chat_id, '❌ Usage: /telegram webhook <url>')
                    return
                url = parts[2].strip()
                result = self.set_webhook(url)
                if result.get('ok'):
                    self.send_message(chat_id, f'✅ Webhook set: {url}')
                else:
                    self.send_message(chat_id, f'❌ Webhook failed: {result}')
            elif len(parts) >= 2 and parts[1] == 'polling':
                result = self.delete_webhook()
                self.send_message(chat_id, '✅ Switched to polling mode')
            else:
                mode = 'webhook' if self._webhook_mode else 'polling'
                self.send_message(chat_id, f'📡 Mode: {mode}\n/telegram webhook <url>\n/telegram polling')

        elif cmd in ('/cal', '/calendar'):
            parts = text.split(maxsplit=3)
            sub = parts[1] if len(parts) > 1 else 'today'
            from .tool_registry import execute_tool as _exec_tool
            if sub == 'today':
                result = _exec_tool('calendar_list', {'period': 'today'})
            elif sub == 'week':
                result = _exec_tool('calendar_list', {'period': 'week'})
            elif sub == 'month':
                result = _exec_tool('calendar_list', {'period': 'month'})
            elif sub == 'add':
                # /cal add 2026-02-20 14:00 회의
                rest = parts[2] if len(parts) > 2 else ''
                cal_parts = rest.split(maxsplit=2)
                if len(cal_parts) < 2:
                    self.send_message(chat_id, '❌ Usage: /cal add YYYY-MM-DD HH:MM 제목')
                    return
                date_str = cal_parts[0]
                # Check if second part is time or title
                if ':' in cal_parts[1]:
                    time_str = cal_parts[1]
                    title = cal_parts[2] if len(cal_parts) > 2 else 'Event'
                else:
                    time_str = ''
                    title = ' '.join(cal_parts[1:])
                args = {'title': title, 'date': date_str}
                if time_str:
                    args['time'] = time_str
                result = _exec_tool('calendar_add', args)
            elif sub == 'delete':
                event_id = parts[2] if len(parts) > 2 else ''
                if not event_id:
                    self.send_message(chat_id, '❌ Usage: /cal delete <event_id>')
                    return
                result = _exec_tool('calendar_delete', {'event_id': event_id})
            else:
                result = _exec_tool('calendar_list', {'period': 'week'})
            self.send_message(chat_id, result)

        elif cmd in ('/mail', '/email'):
            parts = text.split(maxsplit=4)
            sub = parts[1] if len(parts) > 1 else 'inbox'
            from .tool_registry import execute_tool as _exec_tool
            if sub == 'inbox':
                result = _exec_tool('email_inbox', {})
            elif sub == 'read':
                msg_id = parts[2] if len(parts) > 2 else ''
                if not msg_id:
                    self.send_message(chat_id, '❌ Usage: /mail read <message_id>')
                    return
                result = _exec_tool('email_read', {'message_id': msg_id})
            elif sub == 'send':
                # /mail send to@email.com "제목" "본문"
                if len(parts) < 4:
                    self.send_message(chat_id, '❌ Usage: /mail send to@email.com "제목" "본문"')
                    return
                to_addr = parts[2]
                rest = text.split(to_addr, 1)[1].strip() if to_addr in text else ''
                # Parse quoted subject and body
                import shlex
                try:
                    parsed = shlex.split(rest)
                except ValueError:
                    parsed = rest.split(maxsplit=1)
                subject = parsed[0] if parsed else 'No subject'
                body = parsed[1] if len(parsed) > 1 else ''
                result = _exec_tool('email_send', {'to': to_addr, 'subject': subject, 'body': body})
            elif sub == 'search':
                query = ' '.join(parts[2:]) if len(parts) > 2 else ''
                if not query:
                    self.send_message(chat_id, '❌ Usage: /mail search <query>')
                    return
                result = _exec_tool('email_search', {'query': query})
            else:
                result = _exec_tool('email_inbox', {})
            self.send_message(chat_id, result)

        else:
            # Route unknown /commands through engine (handles /model auto/opus/sonnet/haiku etc.)
            self.send_typing(chat_id)
            session_id = f'telegram_{chat_id}'
            from .engine import process_message
            response = await process_message(session_id, text)
            self.send_message(chat_id, response)

    def stop(self):
        """Stop the Telegram polling loop."""
        self._running = False


telegram_bot = TelegramBot()
_tg_bot = telegram_bot  # Reference for sub-agent notifications
set_telegram_bot(telegram_bot)  # Register with core accessor
