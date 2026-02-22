"""Canvas — local HTML preview and rendering.

Adapts OpenClaw's Canvas concept for SalmAlm's pip-install philosophy:
Instead of browser-embedded rendering, Canvas serves generated content
on a local port and optionally opens the system browser.

Use cases:
- Preview generated HTML/CSS/JS
- Render charts (SVG/Matplotlib output)
- Markdown → HTML rendering
- Code output visualization
- A2UI: natural language → UI generation

All content served from a temporary directory, auto-cleaned.
"""

import hashlib
import html
import http.server
import re
import socketserver
import threading
import time
import webbrowser
from typing import Dict, Optional

from salmalm.security.crypto import log
from salmalm.constants import DATA_DIR


_CANVAS_DIR = DATA_DIR / "canvas"
_CANVAS_PORT = 18803
_CANVAS_HOST = "127.0.0.1"


class CanvasServer:
    """Lightweight HTTP server for previewing generated content."""

    def __init__(self):
        self._server: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._pages: Dict[str, dict] = {}  # page_id -> {html, title, created}
        self._running = False
        _CANVAS_DIR.mkdir(parents=True, exist_ok=True)

    def start(self, port: int = _CANVAS_PORT, host: str = _CANVAS_HOST):
        """Start the canvas preview server."""
        if self._running:
            return

        canvas = self

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(_CANVAS_DIR), **kwargs)

            def do_GET(self):
                path = self.path.strip("/")
                if not path or path == "index":
                    self._serve_index()
                elif path in canvas._pages:
                    self._serve_page(path)
                else:
                    super().do_GET()

            def _serve_index(self):
                """Serve canvas index page."""
                pages = sorted(canvas._pages.values(), key=lambda p: p["created"], reverse=True)
                items = "".join(
                    f'<li><a href="/{p["id"]}">{html.escape(p["title"])}</a> '
                    f"<small>({time.strftime('%H:%M', time.localtime(p['created']))})</small></li>"
                    for p in pages
                )
                body = f"""<!DOCTYPE html>
<html><head><title>SalmAlm Canvas</title>
<style>body{{font-family:system-ui;max-width:800px;margin:40px auto;padding:0 20px}}
li{{margin:8px 0}}a{{color:#2563eb}}</style></head>
<body><h1>🎨 SalmAlm Canvas</h1>
<p>{len(pages)} pages</p><ul>{items or "<li>No pages yet</li>"}</ul></body></html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode())

            def _serve_page(self, page_id):
                """Serve a canvas page."""
                page = canvas._pages.get(page_id)
                if not page:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(page["html"].encode())

            def log_message(self, format, *args):
                pass  # Suppress request logs

        try:
            self._server = socketserver.TCPServer((host, port), Handler)
            self._server.allow_reuse_address = True
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="canvas-server")
            self._thread.start()
            self._running = True
            log.info(f"[CANVAS] Preview server: http://{host}:{port}")
        except Exception as e:
            log.error(f"[CANVAS] Failed to start: {e}")

    def stop(self):
        """Stop the canvas server."""
        if self._server:
            self._server.shutdown()
            self._running = False

    def present(self, html_content: str, title: str = "Preview", open_browser: bool = False) -> dict:
        """Present HTML content on the canvas.

        Returns {'url': str, 'page_id': str}.
        """
        if not self._running:
            self.start()

        page_id = hashlib.md5(f"{time.time()}{title}".encode()).hexdigest()[:8]

        # Wrap raw HTML if it doesn't have doctype
        if not html_content.strip().lower().startswith("<!doctype"):
            html_content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:system-ui;max-width:900px;margin:40px auto;padding:0 20px}}</style>
</head><body>{html_content}</body></html>"""

        self._pages[page_id] = {
            "id": page_id,
            "html": html_content,
            "title": title,
            "created": time.time(),
        }

        # Also save to file for persistence
        page_file = _CANVAS_DIR / f"{page_id}.html"
        page_file.write_text(html_content, encoding="utf-8")

        url = f"http://{_CANVAS_HOST}:{_CANVAS_PORT}/{page_id}"

        if open_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass

        # Cleanup old pages (keep last 30)
        if len(self._pages) > 30:
            oldest = sorted(self._pages.items(), key=lambda x: x[1]["created"])[: len(self._pages) - 30]
            for pid, _ in oldest:
                del self._pages[pid]
                try:
                    (_CANVAS_DIR / f"{pid}.html").unlink(missing_ok=True)
                except Exception:
                    pass

        return {"url": url, "page_id": page_id}

    def render_markdown(self, markdown_text: str, title: str = "Markdown") -> dict:
        """Render markdown as HTML and present on canvas.

        Uses a simple regex-based markdown→HTML converter (no dependencies).
        """
        html_body = _markdown_to_html(markdown_text)
        return self.present(html_body, title=title)

    def render_code(self, code: str, language: str = "python", title: str = "Code") -> dict:
        """Render code with syntax highlighting (basic CSS-based)."""
        escaped = html.escape(code)
        html_content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body {{font-family: system-ui; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #1e1e1e; color: #d4d4d4;}}
pre {{background: #2d2d2d; padding: 20px; border-radius: 8px; overflow-x: auto; font-size: 14px; line-height: 1.6;}}
code {{font-family: 'Fira Code', 'Cascadia Code', monospace;}}
h1 {{color: #e0e0e0;}}
.lang {{color: #888; font-size: 12px;}}
</style></head>
<body><h1>📝 {html.escape(title)}</h1>
<span class="lang">{html.escape(language)}</span>
<pre><code>{escaped}</code></pre></body></html>"""
        return self.present(html_content, title=title)

    def render_chart_svg(self, svg_content: str, title: str = "Chart") -> dict:
        """Render an SVG chart on canvas."""
        html_content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body {{font-family: system-ui; max-width: 900px; margin: 40px auto; padding: 0 20px; text-align: center;}}
svg {{max-width: 100%; height: auto;}}</style>
</head><body><h1>📊 {html.escape(title)}</h1>{svg_content}</body></html>"""
        return self.present(html_content, title=title)

    def list_pages(self) -> list:
        """List all canvas pages."""
        return [
            {"id": p["id"], "title": p["title"], "created": p["created"]}
            for p in sorted(self._pages.values(), key=lambda x: x["created"], reverse=True)
        ]

    def get_status(self) -> dict:
        """Get canvas server status."""
        return {
            "running": self._running,
            "port": _CANVAS_PORT,
            "pages": len(self._pages),
            "url": f"http://{_CANVAS_HOST}:{_CANVAS_PORT}" if self._running else None,
        }


def _markdown_to_html(md: str) -> str:
    """Simple markdown→HTML converter (stdlib only, no deps)."""
    lines = md.split("\n")
    html_lines = []
    in_code = False
    in_list = False

    for line in lines:
        # Code blocks
        if line.strip().startswith("```"):
            if in_code:
                html_lines.append("</code></pre>")
                in_code = False
            else:
                lang = line.strip()[3:].strip()
                html_lines.append(f'<pre><code class="language-{html.escape(lang)}">')
                in_code = True
            continue
        if in_code:
            html_lines.append(html.escape(line))
            continue

        # Headers
        if line.startswith("### "):
            html_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            html_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        # Lists
        elif line.strip().startswith("- ") or line.strip().startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{html.escape(line.strip()[2:])}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if line.strip():
                # Inline formatting
                text = html.escape(line)
                text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
                text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
                text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
                html_lines.append(f"<p>{text}</p>")
            else:
                html_lines.append("<br>")

    if in_list:
        html_lines.append("</ul>")
    if in_code:
        html_lines.append("</code></pre>")

    return "\n".join(html_lines)


# Singleton
canvas = CanvasServer()
