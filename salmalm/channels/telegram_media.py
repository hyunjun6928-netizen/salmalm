"""Telegram media handling mixin."""

import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


class TelegramMediaMixin:
    """Mixin for media extraction and TTS."""

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

    def _extract_media(self, msg: dict) -> tuple:
        """Extract media (photo/doc/voice/sticker) from Telegram message.

        Returns (text, file_info, image_data). file_info="__HANDLED__" if message was fully handled.
        """
        text = msg.get("text", "") or msg.get("caption", "") or ""
        file_info = None
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
                    return (text, "__HANDLED__", None)
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

        return (text, file_info, _image_data)

    async def _handle_update_continued(self, chat_id, msg, text, _image_data, _tenant_user) -> None:
        """Handle update after auth + media extraction (LLM call + response)."""
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

        # Pass session-level model override (same as web_chat.py)
        _model_ov = getattr(_sess_obj, "model_override", None)
        if _model_ov == "auto":
            _model_ov = None

        response = await process_message(
            session_id, text, model_override=_model_ov, image_data=_image_data,
            on_token=_on_stream_token, on_status=_on_status,
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

        self._send_llm_response(chat_id, response, _model_short, _elapsed, _draft_sent[0], _msg_id, session_obj)
