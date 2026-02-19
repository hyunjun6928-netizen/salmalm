"""Tests for screen_capture.py — screen capture and Computer Use."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from salmalm.screen_capture import (
    ScreenCapture, ScreenHistory, ScreenManager, DEFAULT_CONFIG,
)


class TestScreenCapture:
    def test_image_to_base64(self):
        sc = ScreenCapture()
        b64 = sc.image_to_base64(b'\x89PNG\r\n\x1a\n')
        assert isinstance(b64, str)
        assert len(b64) > 0

    @patch('salmalm.screen_capture.subprocess.run')
    @patch('salmalm.screen_capture.sys')
    def test_capture_macos(self, mock_sys, mock_run):
        mock_sys.platform = 'darwin'
        sc = ScreenCapture()
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp.write(b'fake-png-data')
            tmp_path = tmp.name
        mock_run.return_value = MagicMock(returncode=0)
        result = sc._capture_macos(tmp_path)
        assert result == b'fake-png-data'
        os.unlink(tmp_path)

    @patch('salmalm.screen_capture.shutil.which', return_value=None)
    def test_capture_linux_no_tools(self, mock_which):
        sc = ScreenCapture()
        result = sc._capture_linux('/tmp/test.png')
        assert result is None

    def test_capture_and_analyze_no_tool(self):
        sc = ScreenCapture()
        with patch.object(sc, 'capture_screen', return_value=None):
            result = sc.capture_and_analyze()
            assert '❌' in result

    def test_capture_and_analyze_with_ocr(self):
        sc = ScreenCapture()
        with patch.object(sc, 'capture_screen', return_value=b'png-data'), \
             patch.object(sc, 'ocr_image', return_value='Hello World'):
            result = sc.capture_and_analyze()
            assert 'Hello World' in result

    def test_capture_and_analyze_no_ocr_no_vision(self):
        sc = ScreenCapture()
        with patch.object(sc, 'capture_screen', return_value=b'png-data'), \
             patch.object(sc, 'ocr_image', return_value=None):
            result = sc.capture_and_analyze()
            assert 'captured' in result.lower()

    @patch('salmalm.screen_capture.shutil.which', return_value=None)
    def test_ocr_no_tesseract(self, mock_which):
        sc = ScreenCapture()
        assert sc.ocr_image('/fake.png') is None

    @patch('salmalm.screen_capture.shutil.which', return_value='/usr/bin/tesseract')
    @patch('salmalm.screen_capture.subprocess.run')
    def test_ocr_with_tesseract(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=0, stdout='OCR text here')
        sc = ScreenCapture()
        result = sc.ocr_image('/fake.png')
        assert result == 'OCR text here'


class TestScreenHistory:
    @pytest.fixture
    def history(self, tmp_path):
        with patch('salmalm.screen_capture._HISTORY_DIR', tmp_path / 'history'), \
             patch('salmalm.screen_capture._SCREEN_CONFIG_PATH', tmp_path / 'config.json'), \
             patch('salmalm.screen_capture._CONFIG_DIR', tmp_path):
            (tmp_path / 'history').mkdir()
            h = ScreenHistory()
            yield h

    def test_save_capture(self, history, tmp_path):
        with patch('salmalm.screen_capture._HISTORY_DIR', tmp_path / 'history'):
            path = history.save_capture(b'fake-png', 'some text')
            assert os.path.exists(path)

    def test_get_history_empty(self, history):
        result = history.get_history(5)
        assert result == []

    def test_search_no_results(self, history):
        result = history.search('nonexistent')
        assert result == []


class TestScreenManager:
    def test_watch_on(self):
        mgr = ScreenManager()
        with patch.object(mgr.history_mgr, 'start_watching'):
            result = mgr.watch('on')
            assert 'started' in result.lower()

    def test_watch_off(self):
        mgr = ScreenManager()
        with patch.object(mgr.history_mgr, 'stop_watching'):
            result = mgr.watch('off')
            assert 'stopped' in result.lower()

    def test_history_empty(self):
        mgr = ScreenManager()
        with patch.object(mgr.history_mgr, 'get_history', return_value=[]):
            result = mgr.history()
            assert 'No screen captures' in result

    def test_search_empty(self):
        mgr = ScreenManager()
        with patch.object(mgr.history_mgr, 'search', return_value=[]):
            result = mgr.search('test')
            assert 'No captures' in result

    def test_search_no_query(self):
        mgr = ScreenManager()
        result = mgr.search('')
        assert 'Usage' in result
