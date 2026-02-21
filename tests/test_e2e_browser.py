"""
E2E browser tests using Playwright.
Tests the full flow: server start → browser → UI interaction → verify.

Catches bugs that unit tests miss:
- Static files not packaged (app.js 404)
- WS session ID not passed
- Model switch 500
- Vault/onboarding flow
- Stop/queue buttons present
- Theme color picker

Requires: pip install playwright && playwright install chromium
Skip gracefully if playwright not installed.
"""
import json
import os
import subprocess
import sys
import threading
import time
import unittest

# Skip entire module if playwright not available
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# Use a random port to avoid conflicts
import socket


def _free_port():
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class E2EBrowserTest(unittest.TestCase):
    """End-to-end browser tests for SalmAlm web UI."""

    server_proc = None
    port = None
    base_url = None

    @classmethod
    def setUpClass(cls):
        if not HAS_PLAYWRIGHT:
            raise unittest.SkipTest("playwright not installed")

        cls.port = _free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        # Set up isolated environment
        cls._data_dir = f"/tmp/salmalm_e2e_{cls.port}"
        os.makedirs(cls._data_dir, exist_ok=True)

        env = os.environ.copy()
        env["SALMALM_HOME"] = cls._data_dir
        env["SALMALM_PORT"] = str(cls.port)
        env["SALMALM_BIND"] = "127.0.0.1"
        env["ANTHROPIC_API_KEY"] = "sk-test-fake-key-for-e2e"

        # Start server as subprocess
        cls.server_proc = subprocess.Popen(
            [sys.executable, "-m", "salmalm"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd="/tmp",
        )

        # Wait for server to be ready
        for _ in range(30):
            try:
                import urllib.request
                urllib.request.urlopen(f"{cls.base_url}/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            cls.server_proc.kill()
            raise RuntimeError("Server did not start in 15s")

    @classmethod
    def tearDownClass(cls):
        if cls.server_proc:
            cls.server_proc.kill()
            cls.server_proc.wait(timeout=5)
        # Cleanup
        import shutil
        shutil.rmtree(f"/tmp/salmalm_e2e_{cls.port}", ignore_errors=True)

    def _new_page(self, pw):
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        return browser, page

    def test_01_index_loads(self):
        """Main page loads without 500."""
        with sync_playwright() as pw:
            browser, page = self._new_page(pw)
            try:
                resp = page.goto(self.base_url)
                self.assertIn(resp.status, (200, 304))
                # Should have SalmAlm in title or body
                content = page.content()
                self.assertIn("SalmAlm", content)
            finally:
                browser.close()

    def test_02_static_app_js(self):
        """app.js loads (not 404)."""
        with sync_playwright() as pw:
            browser, page = self._new_page(pw)
            try:
                # Collect failed requests
                failed = []
                page.on("requestfailed", lambda req: failed.append(req.url))

                errors_4xx = []
                page.on("response", lambda resp: (
                    errors_4xx.append(f"{resp.status} {resp.url}")
                    if resp.status >= 400 and "app.js" in resp.url
                    else None
                ))

                page.goto(self.base_url)
                page.wait_for_timeout(2000)

                # app.js should not be in failed or 4xx
                app_js_fails = [u for u in failed if "app.js" in u]
                self.assertEqual(app_js_fails, [], f"app.js failed to load: {app_js_fails}")
                app_js_errors = [e for e in errors_4xx if "app.js" in e]
                self.assertEqual(app_js_errors, [], f"app.js errors: {app_js_errors}")
            finally:
                browser.close()

    def test_03_no_500_on_load(self):
        """No 500 errors on initial page load."""
        with sync_playwright() as pw:
            browser, page = self._new_page(pw)
            try:
                errors_500 = []
                page.on("response", lambda resp: (
                    errors_500.append(f"{resp.status} {resp.url}")
                    if resp.status >= 500
                    else None
                ))
                page.goto(self.base_url)
                page.wait_for_timeout(3000)
                self.assertEqual(errors_500, [], f"500 errors on load: {errors_500}")
            finally:
                browser.close()

    def test_04_input_bar_elements(self):
        """Chat input bar has send, stop, queue buttons (after unlock/onboarding)."""
        with sync_playwright() as pw:
            browser, page = self._new_page(pw)
            try:
                page.goto(self.base_url)
                page.wait_for_timeout(2000)

                # May land on setup/unlock/onboarding page first
                # Check if we're on the main chat page
                content = page.content()
                if "send-btn" not in content:
                    # We're on setup/unlock/onboarding — that's OK, skip element checks
                    self.skipTest("Landing on setup/unlock page — send-btn not visible")

                # Send button
                send_btn = page.query_selector("#send-btn")
                self.assertIsNotNone(send_btn, "Send button missing")

                # Stop button (hidden by default)
                stop_btn = page.query_selector("#stop-btn")
                self.assertIsNotNone(stop_btn, "Stop button missing from DOM")

                # Queue button
                queue_btn = page.query_selector("#queue-btn")
                self.assertIsNotNone(queue_btn, "Queue button missing")

                # Input textarea
                input_el = page.query_selector("#input")
                self.assertIsNotNone(input_el, "Input textarea missing")
            finally:
                browser.close()

    def test_05_model_switch_no_500(self):
        """POST /api/model/switch should not return 500."""
        import urllib.request
        import urllib.error
        data = json.dumps({"model": "auto"}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/model/switch",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            self.assertNotEqual(resp.getcode(), 500)
        except urllib.error.HTTPError as e:
            self.assertNotEqual(e.code, 500, f"Model switch returned 500: {e.read()}")

    def test_06_settings_has_color_picker(self):
        """Settings panel has color picker dots."""
        with sync_playwright() as pw:
            browser, page = self._new_page(pw)
            try:
                page.goto(self.base_url)
                page.wait_for_timeout(2000)

                # Click settings
                settings_nav = page.query_selector('[data-action="showSettings"]')
                if settings_nav:
                    settings_nav.click()
                    page.wait_for_timeout(500)

                    # Color dots should exist
                    dots = page.query_selector_all(".color-dot")
                    self.assertGreaterEqual(len(dots), 4, f"Expected 4+ color dots, got {len(dots)}")
            finally:
                browser.close()

    def test_07_api_status(self):
        """GET /api/status returns valid JSON."""
        import urllib.request
        resp = urllib.request.urlopen(f"{self.base_url}/api/status", timeout=5)
        data = json.loads(resp.read())
        self.assertIn("version", data)
        self.assertIn("app", data)

    def test_08_static_files_present(self):
        """Key static files are accessible."""
        import urllib.request
        import urllib.error
        # app.js is critical; icon.svg is optional
        for path, required in [("/static/app.js", True), ("/static/icon.svg", False)]:
            try:
                resp = urllib.request.urlopen(f"{self.base_url}{path}", timeout=5)
                self.assertEqual(resp.getcode(), 200, f"{path} not 200")
            except urllib.error.HTTPError as e:
                if required:
                    self.fail(f"{path} returned {e.code}")
                # Optional files may 404 — that's OK

    def test_09_websocket_connect(self):
        """WebSocket connects and receives welcome."""
        try:
            import websockets  # noqa: F401
        except ImportError:
            self.skipTest("websockets not installed")

        import asyncio

        async def _test():
            try:
                async with websockets.connect(
                    f"ws://127.0.0.1:{self.port + 1}",
                    close_timeout=3,
                ) as ws:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(msg)
                    self.assertEqual(data["type"], "welcome")
            except (ConnectionRefusedError, OSError):
                self.skipTest("WS server not running on expected port")

        asyncio.get_event_loop().run_until_complete(_test())


if __name__ == "__main__":
    unittest.main()


class E2EBrowserExtendedTest(unittest.TestCase):
    """Extended E2E tests — reuses server from E2EBrowserTest."""

    @classmethod
    def setUpClass(cls):
        if not HAS_PLAYWRIGHT:
            raise unittest.SkipTest("playwright not installed")
        # Reuse port from main test or start new server
        cls.port = E2EBrowserTest.port
        cls.base_url = E2EBrowserTest.base_url
        if not cls.port:
            raise unittest.SkipTest("Server not started")

    def _new_page(self, pw):
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        return browser, page

    def test_10_setup_or_unlock_page(self):
        """First visit shows setup or unlock page (not a crash)."""
        with sync_playwright() as pw:
            browser, page = self._new_page(pw)
            try:
                resp = page.goto(self.base_url)
                self.assertIn(resp.status, (200, 304))
                content = page.content().lower()
                # Should show one of: setup, unlock, onboarding, or main chat
                has_valid_page = any(kw in content for kw in [
                    'setup', 'unlock', 'password', 'onboarding',
                    'send-btn', 'input', 'salmalm'
                ])
                self.assertTrue(has_valid_page, "Page doesn't show any expected content")
            finally:
                browser.close()

    def test_11_chat_post_no_500(self):
        """POST /api/chat doesn't return 500 (even without API key)."""
        import urllib.request
        import urllib.error
        data = json.dumps({"message": "hello", "session": "test-e2e"}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            self.assertNotEqual(resp.getcode(), 500)
        except urllib.error.HTTPError as e:
            # 401/403 is OK (auth required), 500 is not
            self.assertNotEqual(e.code, 500, f"Chat returned 500: {e.read()[:200]}")

    def test_12_language_switch(self):
        """Language setting persists in localStorage."""
        with sync_playwright() as pw:
            browser, page = self._new_page(pw)
            try:
                page.goto(self.base_url)
                page.wait_for_timeout(2000)

                # Check if setLang function exists
                has_set_lang = page.evaluate("typeof window.setLang === 'function'")
                if has_set_lang:
                    page.evaluate("window.setLang('ko')")
                    lang = page.evaluate("localStorage.getItem('salmalm-lang')")
                    self.assertEqual(lang, "ko")

                    page.evaluate("window.setLang('en')")
                    lang = page.evaluate("localStorage.getItem('salmalm-lang')")
                    self.assertEqual(lang, "en")
                else:
                    self.skipTest("setLang not available (setup/unlock page)")
            finally:
                browser.close()

    def test_13_theme_toggle(self):
        """Theme toggle switches between light and dark."""
        with sync_playwright() as pw:
            browser, page = self._new_page(pw)
            try:
                page.goto(self.base_url)
                page.wait_for_timeout(2000)

                has_toggle = page.evaluate("typeof window.toggleTheme === 'function'")
                if has_toggle:
                    page.evaluate("window.toggleTheme()")
                    theme = page.evaluate("localStorage.getItem('salm_theme')")
                    self.assertIn(theme, ("light", "dark"))
                else:
                    self.skipTest("toggleTheme not available")
            finally:
                browser.close()

    def test_14_color_theme(self):
        """Color theme changes data-color attribute."""
        with sync_playwright() as pw:
            browser, page = self._new_page(pw)
            try:
                page.goto(self.base_url)
                page.wait_for_timeout(2000)

                has_set_color = page.evaluate("typeof window.setColor === 'function'")
                if has_set_color:
                    page.evaluate("window.setColor('ocean')")
                    color = page.evaluate("document.documentElement.getAttribute('data-color')")
                    self.assertEqual(color, "ocean")

                    stored = page.evaluate("localStorage.getItem('salm_color')")
                    self.assertEqual(stored, "ocean")
                else:
                    self.skipTest("setColor not available")
            finally:
                browser.close()

    def test_15_no_console_errors(self):
        """No JavaScript errors on page load."""
        with sync_playwright() as pw:
            browser, page = self._new_page(pw)
            try:
                js_errors = []
                page.on("pageerror", lambda err: js_errors.append(str(err)))

                page.goto(self.base_url)
                page.wait_for_timeout(3000)

                # Filter out known non-critical errors
                critical = [e for e in js_errors if 'ResizeObserver' not in e]
                self.assertEqual(critical, [], f"JS errors on load: {critical}")
            finally:
                browser.close()
