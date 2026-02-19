from __future__ import annotations
"""SalmAlm Browser Automation — Chrome DevTools Protocol (CDP) over WebSocket.

Pure stdlib. No Playwright/Selenium/Puppeteer needed.
Connects to Chrome's debug port via CDP WebSocket to:
  - Navigate pages
  - Take screenshots (base64 PNG)
  - Extract page content (DOM → text/markdown)
  - Execute JavaScript
  - Click elements, fill forms
  - Capture console logs
  - Generate PDFs

Requirements:
  Chrome/Chromium must be running with: --remote-debugging-port=9222
  Launch: google-chrome --remote-debugging-port=9222 --headless=new

Usage:
  from salmalm.browser import browser
  await browser.connect()
  await browser.navigate("https://example.com")
  text = await browser.get_text()
  screenshot = await browser.screenshot()  # base64 PNG
"""


import asyncio
import base64
import json
import os
import struct
import hashlib
import subprocess
import tempfile
import time
import urllib.request
from typing import Any, Dict, List, Optional

from salmalm.crypto import log

# CDP WebSocket frame helpers (reuse ws.py logic but as client)
_WS_MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class CDPConnection:
    """Low-level CDP WebSocket connection to Chrome."""

    def __init__(self):
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False
        self._msg_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._events: List[dict] = []
        self._event_handlers: Dict[str, list] = {}
        self._read_task: Optional[asyncio.Task] = None

    async def connect(self, ws_url: str) -> bool:
        """Connect to CDP WebSocket endpoint."""
        try:
            # Parse ws://host:port/path
            url = ws_url.replace("ws://", "")
            if "/" in url:
                hostport, path = url.split("/", 1)
                path = "/" + path
            else:
                hostport, path = url, "/"
            host, port_str = hostport.split(":")
            port = int(port_str)

            self._reader, self._writer = await asyncio.open_connection(host, port)

            # WebSocket handshake (as client)
            import os
            key = base64.b64encode(os.urandom(16)).decode()
            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {hostport}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"\r\n"
            )
            self._writer.write(request.encode())
            await self._writer.drain()

            # Read response
            while True:
                line = await asyncio.wait_for(self._reader.readline(), timeout=5)
                if line == b'\r\n' or not line:
                    break

            self._connected = True
            self._read_task = asyncio.create_task(self._read_loop())
            return True

        except Exception as e:
            log.error(f"CDP connect failed: {e}")
            return False

    async def disconnect(self):
        """Disconnect from the browser WebSocket."""
        self._connected = False
        if self._read_task:
            self._read_task.cancel()
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass
        for f in self._pending.values():
            if not f.done():
                f.set_exception(ConnectionError("Disconnected"))
        self._pending.clear()

    async def send(self, method: str, params: Optional[dict] = None, timeout: float = 30) -> dict:
        """Send CDP command and wait for response."""
        if not self._connected:
            raise ConnectionError("Not connected to Chrome")
        self._msg_id += 1
        msg_id = self._msg_id
        msg = {"id": msg_id, "method": method}
        if params:
            msg["params"] = params

        future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        await self._send_frame(json.dumps(msg).encode('utf-8'))

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result  # type: ignore[no-any-return]
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"CDP command timeout: {method}")

    def on_event(self, method: str, handler):
        """Register event handler."""
        if method not in self._event_handlers:
            self._event_handlers[method] = []
        self._event_handlers[method].append(handler)

    async def _send_frame(self, data: bytes):
        """Send masked WebSocket frame (client must mask)."""
        import os
        mask_key = os.urandom(4)
        masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))

        length = len(data)
        header = bytes([0x81])  # FIN + TEXT
        if length < 126:
            header += bytes([0x80 | length])  # MASK bit set
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack('!H', length)
        else:
            header += bytes([0x80 | 127]) + struct.pack('!Q', length)

        self._writer.write(header + mask_key + masked)  # type: ignore[union-attr]
        await self._writer.drain()  # type: ignore[union-attr]

    async def _read_loop(self):
        """Background task reading CDP responses/events."""
        try:
            while self._connected:
                frame = await self._recv_frame()
                if frame is None:
                    break
                try:
                    msg = json.loads(frame)
                except json.JSONDecodeError:
                    continue

                if "id" in msg:
                    # Response to a command
                    fut = self._pending.pop(msg["id"], None)
                    if fut and not fut.done():
                        if "error" in msg:
                            fut.set_exception(
                                RuntimeError(f"CDP error: {msg['error'].get('message', '')}"))
                        else:
                            fut.set_result(msg.get("result", {}))
                elif "method" in msg:
                    # Event
                    method = msg["method"]
                    self._events.append(msg)
                    if len(self._events) > 200:
                        self._events = self._events[-100:]
                    for handler in self._event_handlers.get(method, []):
                        try:
                            handler(msg.get("params", {}))
                        except Exception:
                            pass
        except (asyncio.CancelledError, ConnectionError, OSError):
            pass
        self._connected = False

    async def _recv_frame(self) -> Optional[str]:
        """Read one WebSocket frame (server frames are unmasked)."""
        try:
            b0, b1 = await self._reader.readexactly(2)  # type: ignore[union-attr]
            opcode = b0 & 0x0F
            length = b1 & 0x7F

            if length == 126:
                data = await self._reader.readexactly(2)  # type: ignore[union-attr]
                length = struct.unpack('!H', data)[0]
            elif length == 127:
                data = await self._reader.readexactly(8)  # type: ignore[union-attr]
                length = struct.unpack('!Q', data)[0]

            if length > 64 * 1024 * 1024:
                return None

            payload = await self._reader.readexactly(length) if length > 0 else b''  # type: ignore[union-attr]

            if opcode == 0x1:  # Text
                return payload.decode('utf-8', errors='replace')
            elif opcode == 0x8:  # Close
                return None
            elif opcode == 0x9:  # Ping → Pong
                await self._send_frame(payload)  # Should be pong opcode but simplified
                return await self._recv_frame()
            return None
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            return None


class BrowserController:
    """High-level browser automation API over CDP."""

    def __init__(self, debug_host: str = "127.0.0.1", debug_port: int = 9222):
        self.debug_host = debug_host
        self.debug_port = debug_port
        self._cdp: Optional[CDPConnection] = None
        self._console_logs: List[str] = []

    @property
    def connected(self) -> bool:
        """Check if the browser connection is active."""
        return self._cdp is not None and self._cdp._connected

    async def connect(self, tab_index: int = 0) -> bool:
        """Connect to Chrome's first tab via CDP."""
        try:
            # Get available targets
            url = f"http://{self.debug_host}:{self.debug_port}/json"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                targets = json.loads(resp.read())

            # Find a page target
            pages = [t for t in targets if t.get("type") == "page"]
            if not pages:
                log.error("No browser tabs found")
                return False

            target = pages[min(tab_index, len(pages) - 1)]
            ws_url = target.get("webSocketDebuggerUrl", "")
            if not ws_url:
                log.error("No WebSocket URL for target")
                return False

            self._cdp = CDPConnection()
            ok = await self._cdp.connect(ws_url)
            if not ok:
                return False

            # Enable domains
            await self._cdp.send("Page.enable")
            await self._cdp.send("Runtime.enable")
            await self._cdp.send("DOM.enable")
            await self._cdp.send("Network.enable")

            # Capture console
            self._cdp.on_event("Runtime.consoleAPICalled", self._on_console)

            log.info(f"[WEB] Browser connected: {target.get('title', '?')}")
            return True

        except Exception as e:
            log.error(f"Browser connect failed: {e}")
            return False

    async def disconnect(self):
        """Disconnect from the browser WebSocket."""
        if self._cdp:
            await self._cdp.disconnect()
            self._cdp = None

    def _on_console(self, params: dict):
        """Capture console.log messages."""
        args = params.get("args", [])
        texts = [a.get("value", str(a.get("description", ""))) for a in args]
        line = f"[{params.get('type', 'log')}] {' '.join(str(t) for t in texts)}"
        self._console_logs.append(line)
        if len(self._console_logs) > 500:
            self._console_logs = self._console_logs[-250:]

    async def navigate(self, url: str, wait_load: bool = True) -> dict:
        """Navigate to URL. Returns {frameId, loaderId}."""
        if not self.connected:
            return {"error": "Not connected"}
        result = await self._cdp.send("Page.navigate", {"url": url})  # type: ignore[union-attr]
        if wait_load:
            try:
                await asyncio.sleep(1)  # Simple wait; could listen for Page.loadEventFired
            except Exception:
                pass
        return result

    async def screenshot(self, full_page: bool = False,
                         format: str = "png", quality: int = 80) -> str:
        """Take screenshot, return base64 encoded image."""
        if not self.connected:
            return ""
        params = {"format": format}
        if format == "jpeg":
            params["quality"] = quality  # type: ignore[assignment]
        if full_page:
            # Get full page dimensions
            metrics = await self._cdp.send("Page.getLayoutMetrics")  # type: ignore[union-attr]
            content = metrics.get("contentSize", {})
            params["clip"] = {  # type: ignore[assignment]
                "x": 0, "y": 0,
                "width": content.get("width", 1280),
                "height": content.get("height", 720),
                "scale": 1,
            }
        result = await self._cdp.send("Page.captureScreenshot", params)  # type: ignore[union-attr]
        return result.get("data", "")  # type: ignore[no-any-return]

    async def get_text(self) -> str:
        """Extract page text content."""
        if not self.connected:
            return ""
        result = await self.evaluate(
            "document.body ? document.body.innerText : document.documentElement.textContent || ''")
        return result.get("value", "")  # type: ignore[no-any-return]

    async def get_html(self) -> str:
        """Get page HTML."""
        if not self.connected:
            return ""
        result = await self._cdp.send("DOM.getDocument", {"depth": -1})  # type: ignore[union-attr]
        root = result.get("root", {})
        node_id = root.get("nodeId", 0)
        if node_id:
            html = await self._cdp.send("DOM.getOuterHTML", {"nodeId": node_id})  # type: ignore[union-attr]
            return html.get("outerHTML", "")  # type: ignore[no-any-return]
        return ""

    async def evaluate(self, expression: str, return_by_value: bool = True) -> dict:
        """Execute JavaScript and return result."""
        if not self.connected:
            return {"error": "Not connected"}
        result = await self._cdp.send("Runtime.evaluate", {  # type: ignore[union-attr]
            "expression": expression,
            "returnByValue": return_by_value,
            "awaitPromise": True,
        })
        remote = result.get("result", {})
        if remote.get("type") == "undefined":
            return {"value": None}
        return {"value": remote.get("value", remote.get("description", str(remote)))}

    async def click(self, selector: str) -> bool:
        """Click an element by CSS selector."""
        if not self.connected:
            return False
        # Use JS to find and click
        result = await self.evaluate(f"""
            (function() {{
                var el = document.querySelector({json.dumps(selector)});
                if (!el) return 'NOT_FOUND';
                el.click();
                return 'OK';
            }})()
        """)
        return result.get("value") == "OK"

    async def type_text(self, selector: str, text: str) -> bool:
        """Type text into an input element."""
        if not self.connected:
            return False
        result = await self.evaluate(f"""
            (function() {{
                var el = document.querySelector({json.dumps(selector)});
                if (!el) return 'NOT_FOUND';
                el.focus();
                el.value = {json.dumps(text)};
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                return 'OK';
            }})()
        """)
        return result.get("value") == "OK"

    async def get_tabs(self) -> List[dict]:
        """List all browser tabs."""
        try:
            url = f"http://{self.debug_host}:{self.debug_port}/json"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                targets = json.loads(resp.read())
            return [{"id": t["id"], "title": t.get("title", ""),
                     "url": t.get("url", ""), "type": t.get("type", "")}
                    for t in targets if t.get("type") == "page"]
        except Exception as e:
            return [{"error": str(e)}]

    async def new_tab(self, url: str = "about:blank") -> dict:
        """Open a new tab."""
        try:
            api_url = f"http://{self.debug_host}:{self.debug_port}/json/new?{url}"
            req = urllib.request.Request(api_url, method="PUT")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())  # type: ignore[no-any-return]
        except Exception as e:
            return {"error": str(e)}

    async def pdf(self) -> str:
        """Generate PDF of current page, return base64."""
        if not self.connected:
            return ""
        result = await self._cdp.send("Page.printToPDF", {  # type: ignore[union-attr]
            "printBackground": True,
            "preferCSSPageSize": True,
        })
        return result.get("data", "")  # type: ignore[no-any-return]

    def get_console_logs(self, limit: int = 50) -> List[str]:
        """Get captured console logs."""
        return self._console_logs[-limit:]

    def get_status(self) -> dict:
        """Get current browser connection status and page info."""
        return {
            "connected": self.connected,
            "host": f"{self.debug_host}:{self.debug_port}",
            "console_logs": len(self._console_logs),
        }


class BrowserManager:
    """Manages Chrome lifecycle — auto-detect, launch, connect, close.

    Unlike BrowserController which connects to an already-running Chrome,
    BrowserManager can find and launch Chrome automatically.
    """

    # Common Chrome/Chromium binary paths
    _CHROME_NAMES = [
        "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
        "brave-browser", "microsoft-edge",
    ]
    _CHROME_PATHS = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
        "/usr/bin/brave-browser",
        "/usr/bin/microsoft-edge",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ]

    def __init__(self):
        self._browser: Optional[BrowserController] = None
        self._process: Optional[Any] = None  # subprocess.Popen
        self._chrome_path: Optional[str] = None
        self._debug_port: int = 0
        self._tmpdir: Optional[str] = None

    def find_chrome(self) -> Optional[str]:
        """Auto-detect Chrome/Chromium binary."""
        if self._chrome_path:
            return self._chrome_path
        import shutil as _shutil
        for name in self._CHROME_NAMES:
            path = _shutil.which(name)
            if path:
                self._chrome_path = path
                return path
        for path in self._CHROME_PATHS:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                self._chrome_path = path
                return path
        return None

    async def launch(self, url: str = "about:blank", headless: bool = True) -> bool:
        """Launch Chrome and connect via CDP."""
        import os as _os
        chrome = self.find_chrome()
        if not chrome:
            log.error("[BROWSER] No Chrome/Chromium found")
            return False

        self._tmpdir = tempfile.mkdtemp(prefix="salmalm_browser_")
        user_data = os.path.join(self._tmpdir, "profile")

        args = [
            chrome,
            "--remote-debugging-port=0",  # OS picks a free port
            f"--user-data-dir={user_data}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-translate",
            "--metrics-recording-only",
            "--safebrowsing-disable-auto-update",
        ]
        if headless:
            args.append("--headless=new")
        args.append(url)

        try:
            self._process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except Exception as e:
            log.error(f"[BROWSER] Failed to launch Chrome: {e}")
            return False

        # Wait for DevTools port — parse stderr for "DevTools listening on ws://..."
        port = None
        deadline = time.time() + 10
        while time.time() < deadline:
            line = self._process.stderr.readline()  # type: ignore[union-attr]
            if not line:
                await asyncio.sleep(0.1)
                continue
            text = line.decode("utf-8", errors="replace")
            if "DevTools listening on" in text:
                # Extract port from ws://127.0.0.1:PORT/...
                import re
                m = re.search(r"ws://[\w.]+:(\d+)/", text)
                if m:
                    port = int(m.group(1))
                break

        if not port:
            log.error("[BROWSER] Could not detect DevTools port")
            self.close_sync()
            return False

        self._debug_port = port
        self._browser = BrowserController(debug_port=port)

        # Give Chrome a moment then connect
        await asyncio.sleep(0.5)
        ok = await self._browser.connect()
        if ok:
            log.info(f"[BROWSER] Launched Chrome on port {port}")
        return ok

    @property
    def controller(self) -> Optional[BrowserController]:
        return self._browser

    @property
    def connected(self) -> bool:
        return self._browser is not None and self._browser.connected

    async def close(self) -> None:
        """Disconnect and kill Chrome."""
        if self._browser:
            await self._browser.disconnect()
            self._browser = None
        self.close_sync()

    def close_sync(self) -> None:
        """Kill Chrome process (sync)."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        if self._tmpdir:
            import shutil as _shutil
            _shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None


# ── Agent tool functions ────────────────────────────────────

# Module-level instances
browser = BrowserController()
browser_manager = BrowserManager()


async def browser_open(url: str) -> str:
    """Open a URL. Launches Chrome if not connected."""
    if not browser_manager.connected:
        ok = await browser_manager.launch(url)
        if not ok:
            return "Error: Could not launch Chrome. Is it installed?"
        return f"Opened {url}"
    ctrl = browser_manager.controller
    if ctrl:
        await ctrl.navigate(url)
        return f"Navigated to {url}"
    return "Error: no browser controller"


async def browser_screenshot() -> str:
    """Take screenshot, return base64 PNG."""
    ctrl = browser_manager.controller
    if not ctrl or not ctrl.connected:
        return "Error: Browser not connected"
    return await ctrl.screenshot()


async def browser_snapshot() -> str:
    """Extract page text (accessibility tree approximation)."""
    ctrl = browser_manager.controller
    if not ctrl or not ctrl.connected:
        return "Error: Browser not connected"
    # Get structured text: headings, links, form elements
    js = """
    (function() {
        var out = [];
        var walk = document.createTreeWalker(document.body || document.documentElement,
            NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, null, false);
        var node;
        while (node = walk.nextNode()) {
            if (node.nodeType === 3) {
                var t = node.textContent.trim();
                if (t) out.push(t);
            } else if (node.nodeType === 1) {
                var tag = node.tagName.toLowerCase();
                if (tag === 'a' && node.href) out.push('[link: ' + node.textContent.trim() + ' -> ' + node.href + ']');
                else if (tag === 'img' && node.alt) out.push('[img: ' + node.alt + ']');
                else if (tag === 'input') out.push('[input ' + (node.type||'text') + ': ' + (node.name||node.id||'') + '=' + (node.value||'') + ']');
                else if (tag === 'button') out.push('[button: ' + node.textContent.trim() + ']');
                else if (tag === 'select') out.push('[select: ' + (node.name||node.id||'') + ']');
                else if (/^h[1-6]$/.test(tag)) out.push('[' + tag + ': ' + node.textContent.trim() + ']');
            }
        }
        return out.slice(0, 500).join('\\n');
    })()
    """
    result = await ctrl.evaluate(js)
    return result.get("value", "")


async def browser_click(selector: str) -> str:
    """Click element by CSS selector."""
    ctrl = browser_manager.controller
    if not ctrl or not ctrl.connected:
        return "Error: Browser not connected"
    ok = await ctrl.click(selector)
    return "Clicked" if ok else "Element not found"


async def browser_type(selector: str, text: str) -> str:
    """Type text into element."""
    ctrl = browser_manager.controller
    if not ctrl or not ctrl.connected:
        return "Error: Browser not connected"
    ok = await ctrl.type_text(selector, text)
    return "Typed" if ok else "Element not found"


async def browser_evaluate(js: str) -> str:
    """Execute JavaScript and return result."""
    ctrl = browser_manager.controller
    if not ctrl or not ctrl.connected:
        return "Error: Browser not connected"
    result = await ctrl.evaluate(js)
    val = result.get("value")
    return str(val) if val is not None else "(undefined)"


async def browser_close() -> str:
    """Close browser."""
    await browser_manager.close()
    return "Browser closed"
