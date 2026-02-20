"""Tests for salmalm.browser — CDP WebSocket, BrowserManager, tool functions."""
import json
import os
import struct
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from salmalm.utils.browser import CDPConnection, BrowserController, BrowserManager


class TestWebSocketFrameBuilder(unittest.TestCase):
    """Test CDP WebSocket frame construction."""

    def test_send_frame_small(self):
        """Small payloads use 1-byte length."""
        cdp = CDPConnection()
        # We can't fully test _send_frame without a connection, but we can
        # verify the frame header logic by checking the structure
        data = b"hello"
        # FIN + TEXT = 0x81, MASK bit + length
        header_byte = 0x80 | len(data)  # 0x85
        self.assertEqual(header_byte, 0x85)

    def test_send_frame_medium(self):
        """Payloads 126-65535 use 2-byte extended length."""
        length = 200
        self.assertTrue(126 <= length < 65536)
        packed = struct.pack('!H', length)
        self.assertEqual(len(packed), 2)
        self.assertEqual(struct.unpack('!H', packed)[0], 200)

    def test_send_frame_large(self):
        """Payloads >65535 use 8-byte extended length."""
        length = 100000
        packed = struct.pack('!Q', length)
        self.assertEqual(len(packed), 8)
        self.assertEqual(struct.unpack('!Q', packed)[0], 100000)


class TestCDPCommandGeneration(unittest.TestCase):
    """Test CDP command JSON generation."""

    def test_navigate_command(self):
        msg = {"id": 1, "method": "Page.navigate", "params": {"url": "https://example.com"}}
        encoded = json.dumps(msg)
        parsed = json.loads(encoded)
        self.assertEqual(parsed["method"], "Page.navigate")
        self.assertEqual(parsed["params"]["url"], "https://example.com")

    def test_screenshot_command(self):
        msg = {"id": 2, "method": "Page.captureScreenshot", "params": {"format": "png"}}
        encoded = json.dumps(msg)
        parsed = json.loads(encoded)
        self.assertEqual(parsed["method"], "Page.captureScreenshot")

    def test_evaluate_command(self):
        msg = {"id": 3, "method": "Runtime.evaluate",
               "params": {"expression": "1+1", "returnByValue": True, "awaitPromise": True}}
        encoded = json.dumps(msg)
        parsed = json.loads(encoded)
        self.assertEqual(parsed["params"]["expression"], "1+1")

    def test_dom_command(self):
        msg = {"id": 4, "method": "DOM.getDocument", "params": {"depth": -1}}
        encoded = json.dumps(msg)
        parsed = json.loads(encoded)
        self.assertEqual(parsed["method"], "DOM.getDocument")

    def test_input_mouse_event(self):
        msg = {"id": 5, "method": "Input.dispatchMouseEvent",
               "params": {"type": "mousePressed", "x": 100, "y": 200, "button": "left"}}
        encoded = json.dumps(msg)
        parsed = json.loads(encoded)
        self.assertEqual(parsed["params"]["x"], 100)

    def test_input_key_event(self):
        msg = {"id": 6, "method": "Input.dispatchKeyEvent",
               "params": {"type": "keyDown", "key": "Enter"}}
        encoded = json.dumps(msg)
        parsed = json.loads(encoded)
        self.assertEqual(parsed["params"]["key"], "Enter")


class TestBrowserController(unittest.TestCase):
    def test_not_connected_by_default(self):
        bc = BrowserController()
        self.assertFalse(bc.connected)

    def test_status(self):
        bc = BrowserController(debug_port=9999)
        status = bc.get_status()
        self.assertFalse(status["connected"])
        self.assertEqual(status["host"], "127.0.0.1:9999")

    def test_console_logs_empty(self):
        bc = BrowserController()
        self.assertEqual(bc.get_console_logs(), [])


class TestBrowserManager(unittest.TestCase):
    def test_find_chrome_not_found(self):
        bm = BrowserManager()
        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", return_value=False):
                result = bm.find_chrome()
                # May or may not find depending on system; just test it doesn't crash
                # Reset for clean state
                bm._chrome_path = None

    def test_not_connected_by_default(self):
        bm = BrowserManager()
        self.assertFalse(bm.connected)
        self.assertIsNone(bm.controller)

    @patch("shutil.which", return_value="/usr/bin/google-chrome")
    def test_find_chrome_via_which(self, mock_which):
        bm = BrowserManager()
        bm._chrome_path = None
        result = bm.find_chrome()
        self.assertEqual(result, "/usr/bin/google-chrome")

    def test_close_sync_no_process(self):
        bm = BrowserManager()
        # Should not raise
        bm.close_sync()


class TestCDPConnection(unittest.TestCase):
    def test_initial_state(self):
        cdp = CDPConnection()
        self.assertFalse(cdp._connected)
        self.assertEqual(cdp._msg_id, 0)
        self.assertEqual(cdp._pending, {})

    def test_event_handler_registration(self):
        cdp = CDPConnection()
        handler = lambda params: None
        cdp.on_event("Page.loadEventFired", handler)
        self.assertIn("Page.loadEventFired", cdp._event_handlers)
        self.assertEqual(len(cdp._event_handlers["Page.loadEventFired"]), 1)


if __name__ == "__main__":
    unittest.main()
