"""Tests for STT Manager."""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from salmalm.features.stt import STTManager


class TestSTTManager(unittest.TestCase):

    def test_default_config(self):
        mgr = STTManager()
        self.assertTrue(mgr.enabled)
        self.assertTrue(mgr.web_enabled)
        self.assertTrue(mgr.telegram_voice)

    def test_disabled(self):
        mgr = STTManager(config={'enabled': False})
        result = mgr.transcribe(b'fake audio')
        self.assertIn('비활성화', result)

    def test_no_api_key(self):
        mgr = STTManager(config={'enabled': True, 'provider': 'openai'})
        with patch.dict(os.environ, {}, clear=True):
            # Remove OPENAI_API_KEY if present
            os.environ.pop('OPENAI_API_KEY', None)
            result = mgr.transcribe(b'fake audio')
            self.assertIn('미설정', result)

    def test_unsupported_provider(self):
        mgr = STTManager(config={'enabled': True, 'provider': 'azure'})
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test'}):
            result = mgr.transcribe(b'fake audio')
            self.assertIn('지원하지 않는', result)

    def test_web_js_enabled(self):
        mgr = STTManager(config={'enabled': True, 'web_enabled': True})
        js = mgr.get_web_js()
        self.assertIn('SpeechRecognition', js)
        self.assertIn('🎤', js)

    def test_web_js_disabled(self):
        mgr = STTManager(config={'enabled': True, 'web_enabled': False})
        js = mgr.get_web_js()
        self.assertEqual(js, '')

    def test_telegram_voice_disabled(self):
        mgr = STTManager(config={'enabled': True, 'telegram_voice': False})
        result = mgr.handle_telegram_voice(b'audio')
        self.assertIsNone(result)

    @patch('salmalm.features.stt.urllib.request.urlopen')
    def test_whisper_success(self, mock_urlopen):
        import json
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({'text': '안녕하세요'}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        mgr = STTManager(config={'enabled': True, 'provider': 'openai', 'language': 'ko'})
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            result = mgr.transcribe(b'fake ogg data', 'voice.ogg')
            self.assertEqual(result, '안녕하세요')


if __name__ == '__main__':
    unittest.main()
