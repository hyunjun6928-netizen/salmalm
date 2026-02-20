"""Browser tool."""
import json
import time
import base64
from salmalm.tools.tool_registry import register
from salmalm.constants import WORKSPACE_DIR


@register('browser')
def handle_browser(args: dict) -> str:
    import asyncio
    from salmalm.utils.browser import browser

    def _run_async(coro):
        try:
            _loop = asyncio.get_running_loop()  # noqa: F841
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                return pool.submit(lambda: asyncio.run(coro)).result(timeout=30)
        except RuntimeError:
            return asyncio.run(coro)

    action = args.get('action', 'status')
    if action == 'status':
        return json.dumps(browser.get_status(), ensure_ascii=False)
    elif action == 'connect':
        ok = _run_async(browser.connect())
        return '🌐 Browser connected' if ok else '❌ Connection failed. Check Chrome --remote-debugging-port=9222'
    elif action == 'navigate':
        url = args.get('url', '')
        if not url:
            return '❌ url is required'
        result = _run_async(browser.navigate(url))
        return f'🌐 Navigated: {url}\n{json.dumps(result, ensure_ascii=False)}'
    elif action == 'text':
        text = _run_async(browser.get_text())
        return text[:5000] if text else '(empty page or not connected)'
    elif action == 'html':
        html = _run_async(browser.get_html())
        return html[:8000] if html else '(empty page or not connected)'
    elif action == 'screenshot':
        b64 = _run_async(browser.screenshot())
        if b64:
            save_dir = WORKSPACE_DIR / 'uploads'
            save_dir.mkdir(exist_ok=True)
            fname = f'screenshot_{int(time.time())}.png'
            (save_dir / fname).write_bytes(base64.b64decode(b64))
            return f'📸 Screenshot saved: uploads/{fname} ({len(b64) // 1024}KB base64)'
        return '❌ Screenshot failed (not connected?)'
    elif action == 'evaluate':
        expr = args.get('expression', '')
        if not expr:
            return '❌ expression is required'
        result = _run_async(browser.evaluate(expr))
        return json.dumps(result, ensure_ascii=False, default=str)[:5000]
    elif action == 'click':
        sel = args.get('selector', '')
        ok = _run_async(browser.click(sel))
        return f'✅ Clicked: {sel}' if ok else f'❌ Element not found: {sel}'
    elif action == 'type':
        sel = args.get('selector', '')
        text = args.get('text', '')
        ok = _run_async(browser.type_text(sel, text))
        return f'✅ Input: {sel}' if ok else f'❌ Element not found: {sel}'
    elif action == 'tabs':
        tabs = _run_async(browser.get_tabs())
        return json.dumps(tabs, ensure_ascii=False)
    elif action == 'console':
        logs = browser.get_console_logs(limit=30)
        return '\n'.join(logs) if logs else '(no console logs)'
    elif action == 'pdf':
        b64 = _run_async(browser.pdf())
        if b64:
            save_dir = WORKSPACE_DIR / 'uploads'
            save_dir.mkdir(exist_ok=True)
            fname = f'page_{int(time.time())}.pdf'
            (save_dir / fname).write_bytes(base64.b64decode(b64))
            return f'📄 PDF saved: uploads/{fname}'
        return '❌ PDF generation failed'
    return f'❌ Unknown action: {action}'
