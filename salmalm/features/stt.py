"""STT (Speech-to-Text) Manager — voice input via Web Speech API and OpenAI Whisper.

Web UI: Browser-native Web Speech API (JavaScript injection).
Telegram: Voice message (.ogg) → OpenAI Whisper API transcription.
stdlib-only on Python side.
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional

from salmalm import log
from salmalm.constants import DATA_DIR

_STT_CONFIG_PATH = DATA_DIR / "stt.json"


from salmalm.config_manager import ConfigManager

_STT_DEFAULTS = {
    "enabled": True,
    "provider": "openai",
    "language": "auto",
    "web_enabled": True,
    "telegram_voice": True,
}


def _load_config() -> dict:
    return ConfigManager.load("stt", defaults=_STT_DEFAULTS)


class STTManager:
    """Speech-to-text manager supporting Web Speech API and OpenAI Whisper."""

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or _load_config()

    @property
    def enabled(self) -> bool:
        return self.config.get("enabled", True)

    @property
    def web_enabled(self) -> bool:
        return self.config.get("web_enabled", True)

    @property
    def telegram_voice(self) -> bool:
        return self.config.get("telegram_voice", True)

    # ── Web Speech API JavaScript ────────────────────────────

    def get_web_js(self) -> str:
        """Return JavaScript snippet for Web Speech API integration."""
        if not self.web_enabled:
            return ""
        return """
(function() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { console.log.info('SpeechRecognition not supported'); return; }

  const btn = document.createElement('button');
  btn.innerHTML = '🎤';
  btn.title = '음성 입력';
  btn.style.cssText = 'font-size:1.5em;background:none;border:none;cursor:pointer;padding:4px 8px;';

  const input = document.querySelector('#message-input, textarea, input[type="text"]');
  if (!input) return;
  input.parentElement.insertBefore(btn, input.nextSibling);

  let recognition = null;
  let isListening = false;

  btn.addEventListener('click', function() {
    if (isListening) {
      recognition.stop();
      return;
    }
    recognition = new SR();
    recognition.lang = 'auto';
    recognition.continuous = false;
    recognition.interimResults = true;

    // Auto-detect language
    const lang = navigator.language || 'ko-KR';
    recognition.lang = lang.startsWith('ko') ? 'ko-KR' : 'en-US';

    recognition.onstart = function() {
      isListening = true;
      btn.innerHTML = '🔴';
      btn.title = '녹음 중... 클릭하여 중지';
    };
    recognition.onresult = function(event) {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      input.value = transcript;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    };
    recognition.onend = function() {
      isListening = false;
      btn.innerHTML = '🎤';
      btn.title = '음성 입력';
    };
    recognition.onerror = function(event) {
      console.error('STT error:', event.error);
      isListening = false;
      btn.innerHTML = '🎤';
    };
    recognition.start();
  });
})();
"""

    # ── OpenAI Whisper Transcription ─────────────────────────

    def transcribe(self, audio_data: bytes, filename: str = "audio.ogg", content_type: str = "audio/ogg") -> str:
        """Transcribe audio using OpenAI Whisper API. Returns text or error."""
        if not self.enabled:
            return "❌ 음성 인식이 비활성화되어 있습니다."

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return "❌ 음성 인식 미설정 (OPENAI_API_KEY 필요)"

        provider = self.config.get("provider", "openai")
        if provider != "openai":
            return f"❌ 지원하지 않는 STT 프로바이더: {provider}"

        language = self.config.get("language", "auto")
        return self._whisper_transcribe(audio_data, filename, content_type, api_key, language)

    def _whisper_transcribe(
        self, audio_data: bytes, filename: str, content_type: str, api_key: str, language: str
    ) -> str:
        """Call OpenAI Whisper API using urllib multipart."""
        boundary = "----SalmAlmSTTBoundary"
        body = b""

        # File field
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
        body += f"Content-Type: {content_type}\r\n\r\n".encode()
        body += audio_data
        body += b"\r\n"

        # Model field
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
        body += b"whisper-1\r\n"

        # Language field (if not auto)
        if language and language != "auto":
            body += f"--{boundary}\r\n".encode()
            body += b'Content-Disposition: form-data; name="language"\r\n\r\n'
            body += language.encode() + b"\r\n"

        body += f"--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                return result.get("text", "")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            log.info(f"STT Whisper error: {e.code} {error_body}")
            return f"❌ 음성 인식 실패 (HTTP {e.code})"
        except Exception as e:
            log.info(f"STT error: {e}")
            return f"❌ 음성 인식 오류: {e}"

    # ── Telegram Voice Handler ───────────────────────────────

    def handle_telegram_voice(self, file_data: bytes, file_name: str = "voice.ogg") -> Optional[str]:
        """Process a Telegram voice message. Returns transcribed text or None."""
        if not self.telegram_voice:
            return None
        result = self.transcribe(file_data, file_name, "audio/ogg")
        if result.startswith("❌"):
            return result
        return result if result.strip() else None
