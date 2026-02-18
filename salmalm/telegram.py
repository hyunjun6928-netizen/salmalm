"""삶앎 Telegram bot."""
import asyncio, json, re, textwrap, time, urllib.request

from .constants import *
from .crypto import vault, log
from .core import router, get_session, _sessions
from .llm import _http_post, _http_get
from .prompt import build_system_prompt
from .tools import execute_tool

class TelegramBot:
    def __init__(self):
        self.token: Optional[str] = None
        self.owner_id: Optional[str] = None
        self.offset = 0
        self._running = False

    def configure(self, token: str, owner_id: str):
        self.token = token
        self.owner_id = owner_id

    def _api(self, method: str, data: dict = None) -> dict:
        url = f'https://api.telegram.org/bot{self.token}/{method}'
        if data:
            return _http_post(url, {'Content-Type': 'application/json'}, data)
        return _http_get(url)

    def send_message(self, chat_id, text: str, parse_mode: str = None):
        # Split long messages
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            data = {'chat_id': chat_id, 'text': chunk}
            if parse_mode:
                data['parse_mode'] = parse_mode
            try:
                self._api('sendMessage', data)
            except Exception as e:
                # Retry without parse_mode
                if parse_mode:
                    self._api('sendMessage', {'chat_id': chat_id, 'text': chunk})

    def _send_photo(self, chat_id, path: Path, caption: str = ''):
        """Send a photo file to Telegram."""
        try:
            import mimetypes
            boundary = f'----SalmAlm{int(time.time())}'
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
            self.send_message(chat_id, f'📷 이미지 전송 실패: {e}')

    def _send_audio(self, chat_id, path: Path, caption: str = ''):
        """Send an audio file to Telegram."""
        try:
            boundary = f'----SalmAlm{int(time.time())}'
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
            self.send_message(chat_id, f'🔊 음성 전송 실패: {e}')

    def send_typing(self, chat_id):
        try:
            self._api('sendChatAction', {'chat_id': chat_id, 'action': 'typing'})
        except Exception:
            pass

    async def poll(self):
        """Long-polling loop for Telegram updates."""
        self._running = True
        log.info(f"📡 Telegram bot started (owner: {self.owner_id})")

        while self._running:
            try:
                # Run blocking urllib in thread to not block event loop
                resp = await asyncio.to_thread(self._api, 'getUpdates', {
                    'offset': self.offset, 'timeout': 30,
                    'allowed_updates': ['message']
                })
                for update in resp.get('result', []):
                    self.offset = update['update_id'] + 1
                    await self._handle_update(update)
            except Exception as e:
                log.error(f"Telegram poll error: {e}")
                await asyncio.sleep(5)

    def _download_file(self, file_id: str) -> tuple[bytes, str]:
        """Download a file from Telegram. Returns (data, filename)."""
        info = self._api('getFile', {'file_id': file_id})
        file_path = info['result']['file_path']
        filename = file_path.split('/')[-1]
        url = f'https://api.telegram.org/file/bot{self.token}/{file_path}'
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        return data, filename

    async def _handle_update(self, update: dict):
        msg = update.get('message')
        if not msg:
            return

        chat_id = msg['chat']['id']
        user_id = str(msg['from']['id'])

        # Owner check
        if user_id != self.owner_id:
            log.warning(f"🚫 Unauthorized: {user_id} tried to message")
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
                file_info = f'[📷 이미지 저장: uploads/{fname} ({len(data)//1024}KB)]'
                log.info(f"📷 Photo saved: {save_path}")
                # Prepare vision data
                import base64 as _b64
                _image_data = (_b64.b64encode(data).decode(), 'image/jpeg')
            except Exception as e:
                file_info = f'[📷 이미지 다운로드 실패: {e}]'

        # Handle documents
        if msg.get('document'):
            doc = msg['document']
            try:
                data, fname = self._download_file(doc['file_id'])
                save_path = WORKSPACE_DIR / 'uploads' / (doc.get('file_name', fname))
                save_path.parent.mkdir(exist_ok=True)
                save_path.write_bytes(data)
                file_info = f'[📎 파일 저장: uploads/{save_path.name} ({len(data)//1024}KB)]'
                log.info(f"📎 File saved: {save_path}")
                # If text file, include content preview
                if save_path.suffix in ('.txt', '.md', '.py', '.js', '.json', '.csv', '.log', '.html', '.css', '.sh', '.bat'):
                    try:
                        content = data.decode('utf-8', errors='replace')[:3000]
                        file_info += f'\n[파일 내용 미리보기]\n{content}'
                    except Exception:
                        pass
            except Exception as e:
                file_info = f'[📎 파일 다운로드 실패: {e}]'

        # Handle voice/audio
        if msg.get('voice') or msg.get('audio'):
            audio = msg.get('voice') or msg.get('audio')
            try:
                data, fname = self._download_file(audio['file_id'])
                save_path = WORKSPACE_DIR / 'uploads' / fname
                save_path.parent.mkdir(exist_ok=True)
                save_path.write_bytes(data)
                file_info = f'[🎤 음성 저장: uploads/{fname} ({len(data)//1024}KB)]'
                log.info(f"🎤 Voice saved: {save_path}")
                # Whisper transcription
                api_key = vault.get('openai_api_key')
                if api_key:
                    try:
                        boundary = f'----Whisper{int(time.time())}'
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
                            file_info = f'[🎤 음성 전사]\n{transcript}'
                            log.info(f"🎤 Transcribed: {transcript[:100]}")
                    except Exception as we:
                        log.error(f"Whisper error: {we}")
                        file_info += f'\n[전사 실패: {we}]'
            except Exception as e:
                file_info = f'[🎤 음성 다운로드 실패: {e}]'

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

        # Send response (check for generated files to send)
        import re as _re
        img_match = _re.search(r'uploads/[\w.-]+\.(png|jpg|jpeg|gif|webp)', response)
        audio_match = _re.search(r'uploads/[\w.-]+\.(mp3|wav|ogg)', response)
        if img_match:
            img_path = WORKSPACE_DIR / img_match.group(0)
            if img_path.exists():
                self._send_photo(chat_id, img_path, response[:1000])
            else:
                self.send_message(chat_id, f'{response}\n\n⏱️ {_elapsed:.1f}초')
        elif audio_match:
            audio_path = WORKSPACE_DIR / audio_match.group(0)
            if audio_path.exists():
                self._send_audio(chat_id, audio_path, response[:1000])
            else:
                self.send_message(chat_id, f'{response}\n\n⏱️ {_elapsed:.1f}초')
        else:
            self.send_message(chat_id, f'{response}\n\n⏱️ {_elapsed:.1f}초')

    async def _handle_command(self, chat_id, text: str):
        cmd = text.split()[0].lower()
        if cmd == '/start':
            self.send_message(chat_id, f'😈 {APP_NAME} v{VERSION} 가동 중\n낄낄')
        elif cmd == '/usage':
            report = execute_tool('usage_report', {})
            self.send_message(chat_id, report)
        elif cmd == '/model':
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                router.force_model = parts[1] if parts[1] != 'auto' else None
                self.send_message(chat_id, f'모델 변경: {parts[1]}')
            else:
                current = router.force_model or 'auto (라우팅)'
                models = '\n'.join(f'  {m}' for tier in router.TIERS.values() for m in tier)
                self.send_message(chat_id, f'현재: {current}\n\n사용 가능:\n{models}\n\n/model auto — 자동')
        elif cmd == '/compact':
            session = get_session(f'telegram_{chat_id}')
            before = len(session.messages)
            session.messages = compact_messages(session.messages)
            self.send_message(chat_id, f'압축: {before} → {len(session.messages)} 메시지')
        elif cmd == '/clear':
            session = get_session(f'telegram_{chat_id}')
            session.messages = []
            session.add_system(build_system_prompt())
            self.send_message(chat_id, '🗑️ 대화 초기화')
        elif cmd == '/help':
            self.send_message(chat_id, textwrap.dedent(f"""
                😈 {APP_NAME} v{VERSION}
                /usage — 토큰 사용량/비용
                /model [name|auto] — 모델 변경
                /compact — 대화 압축
                /clear — 대화 초기화
                /help — 이 메시지
            """).strip())
        else:
            self.send_message(chat_id, f'❓ 알 수 없는 명령: {cmd}\n/help 참조')

    def stop(self):
        self._running = False


telegram_bot = TelegramBot()
_tg_bot = telegram_bot  # Reference for sub-agent notifications

