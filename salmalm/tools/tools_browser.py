"""Browser automation tool — OpenClaw snapshot/act pattern via Playwright subprocess.

Requires: pip install salmalm[browser] (installs playwright)
Design: Playwright runs in a subprocess to isolate browser from main process.
Pattern: snapshot → reason → act → snapshot (OpenClaw's core browser loop)

This is a lightweight adaptation of OpenClaw's browser control system,
tailored for SalmAlm's pip-install-one-liner philosophy.
"""

import json
import os
import subprocess
import sys
import tempfile
import time

from salmalm.tools.tool_registry import register
from salmalm.constants import WORKSPACE_DIR, DATA_DIR

# Browser state directory
_BROWSER_DIR = DATA_DIR / "browser"
_SCREENSHOT_DIR = _BROWSER_DIR / "screenshots"


def _check_playwright() -> bool:
    """Check if playwright is installed."""
    try:
        import importlib

        importlib.import_module("playwright")
        return True
    except ImportError:
        return False


def _ensure_browser_dirs():
    """Create browser working directories."""
    _BROWSER_DIR.mkdir(parents=True, exist_ok=True)
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ── Playwright subprocess scripts ──

_SNAPSHOT_SCRIPT = """
import json, sys
from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else "about:blank"
timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 30000

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        # Get accessibility tree (OpenClaw snapshot pattern)
        snapshot = page.accessibility.snapshot()
        # Get page title and URL
        result = {
            "url": page.url,
            "title": page.title(),
            "snapshot": snapshot,
            "text": page.inner_text("body")[:5000] if snapshot else "",
        }
        print(json.dumps(result, ensure_ascii=False, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
    finally:
        browser.close()
"""

_ACT_SCRIPT = """
import json, sys
from playwright.sync_api import sync_playwright

action = json.loads(sys.argv[1])
url = action.get("url", "about:blank")
kind = action.get("kind", "click")
selector = action.get("selector", "")
text = action.get("text", "")
screenshot_path = action.get("screenshot_path", "")
timeout = action.get("timeout", 30000)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        result = {"url": page.url, "title": page.title()}

        if kind == "click" and selector:
            page.click(selector, timeout=5000)
            page.wait_for_timeout(500)
            result["action"] = f"clicked {selector}"
        elif kind == "type" and selector and text:
            page.fill(selector, text, timeout=5000)
            result["action"] = f"typed into {selector}"
        elif kind == "press" and text:
            page.keyboard.press(text)
            result["action"] = f"pressed {text}"
        elif kind == "screenshot":
            path = screenshot_path or "/tmp/screenshot.png"
            page.screenshot(path=path, full_page=True)
            result["screenshot"] = path
        elif kind == "evaluate" and text:
            eval_result = page.evaluate(text)
            result["eval_result"] = str(eval_result)[:5000]
        elif kind == "navigate" and text:
            page.goto(text, timeout=timeout, wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            result["url"] = page.url
            result["title"] = page.title()

        result["text"] = page.inner_text("body")[:3000]
        print(json.dumps(result, ensure_ascii=False, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
    finally:
        browser.close()
"""


def _run_playwright_script(script: str, args: list, timeout: int = 60) -> dict:
    """Run a Playwright script in a subprocess. Returns parsed JSON result."""
    if not _check_playwright():
        return {"error": "Playwright not installed. Run: pip install salmalm[browser] && playwright install chromium"}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        cmd = [sys.executable, script_path] + [str(a) for a in args]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE_DIR),
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                return {"error": f"Invalid JSON output: {result.stdout[:500]}"}
        return {"error": result.stderr[:500] if result.stderr else "No output"}
    except subprocess.TimeoutExpired:
        return {"error": f"Browser operation timed out ({timeout}s)"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


def _is_internal_url(url: str) -> bool:
    """Check if URL targets internal/private network (SSRF prevention)."""
    try:
        from urllib.parse import urlparse
        import socket
        import ipaddress

        parsed = urlparse(url)
        hostname = (parsed.hostname or "").strip("[]")
        if not hostname or hostname in ("about", ""):
            return False  # about:blank is safe
        # Resolve hostname
        addrs = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        # Also check metadata endpoints
        if hostname in ("169.254.169.254", "metadata.google.internal"):
            return True
    except Exception:
        pass
    return False


@register("browser")
def handle_browser(args: dict) -> str:
    """Browser automation — OpenClaw snapshot/act pattern.

    Actions:
    - snapshot: Get page accessibility tree + text content
    - act: Perform an action (click, type, press, navigate, evaluate)
    - screenshot: Take a full-page screenshot
    - status: Check if Playwright is available
    """
    _ensure_browser_dirs()
    action = args.get("action", "status")

    if action == "status":
        available = _check_playwright()
        if available:
            return "🌐 Browser automation: ✅ Ready (Playwright installed) / 브라우저 자동화 준비 완료"
        return (
            "🌐 Browser automation: ❌ Not available / 사용 불가\n"
            "Install / 설치: `pip install salmalm[browser]` → `playwright install chromium`"
        )

    # SSRF: block internal/private URLs when externally bound
    def _check_url_safe(url: str):
        if url.startswith("about:"):
            return None
        if _is_internal_url(url):
            bind = os.environ.get("SALMALM_BIND", "127.0.0.1")
            if bind != "127.0.0.1":
                return "❌ Browser blocked: internal/private URL not allowed on external bind"
        return None

    if action == "snapshot":
        url = args.get("url", "about:blank")
        if not url.startswith(("http://", "https://", "about:")):
            url = "https://" + url
        err = _check_url_safe(url)
        if err:
            return err
        timeout = args.get("timeout", 30000)
        result = _run_playwright_script(_SNAPSHOT_SCRIPT, [url, str(timeout)])
        if "error" in result:
            return f"❌ Browser error: {result['error']}"
        lines = [f"🌐 **{result.get('title', '?')}**", f"URL: {result.get('url', url)}"]
        text = result.get("text", "")
        if text:
            lines.append(f"\n{text[:3000]}")
        snapshot = result.get("snapshot")
        if snapshot:
            lines.append(f"\n📋 Accessibility tree: {json.dumps(snapshot, ensure_ascii=False)[:2000]}")
        return "\n".join(lines)

    if action == "act":
        act_args = {
            "url": args.get("url", "about:blank"),
            "kind": args.get("kind", "click"),
            "selector": args.get("selector", ""),
            "text": args.get("text", ""),
            "screenshot_path": str(_SCREENSHOT_DIR / f"act_{int(time.time())}.png"),
            "timeout": args.get("timeout", 30000),
        }
        if not act_args["url"].startswith(("http://", "https://", "about:")):
            act_args["url"] = "https://" + act_args["url"]
        err = _check_url_safe(act_args["url"])
        if err:
            return err
        result = _run_playwright_script(_ACT_SCRIPT, [json.dumps(act_args)])
        if "error" in result:
            return f"❌ Browser error: {result['error']}"
        lines = [f"🌐 {result.get('action', 'done')}", f"URL: {result.get('url', act_args['url'])}"]
        if result.get("screenshot"):
            lines.append(f"📸 Screenshot: {result['screenshot']}")
        if result.get("eval_result"):
            lines.append(f"📊 Result: {result['eval_result'][:2000]}")
        text = result.get("text", "")
        if text:
            lines.append(f"\n{text[:2000]}")
        return "\n".join(lines)

    if action == "screenshot":
        url = args.get("url", "about:blank")
        if not url.startswith(("http://", "https://", "about:")):
            url = "https://" + url
        err = _check_url_safe(url)
        if err:
            return err
        screenshot_path = str(_SCREENSHOT_DIR / f"screenshot_{int(time.time())}.png")
        act_args = {
            "url": url,
            "kind": "screenshot",
            "screenshot_path": screenshot_path,
            "timeout": args.get("timeout", 30000),
        }
        result = _run_playwright_script(_ACT_SCRIPT, [json.dumps(act_args)])
        if "error" in result:
            return f"❌ Browser error: {result['error']}"
        return f"📸 Screenshot saved: {result.get('screenshot', screenshot_path)}"

    return f"❌ Unknown browser action / 알 수 없는 액션: {action}. Use: status, snapshot, act, screenshot"
