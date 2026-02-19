from __future__ import annotations
"""SalmAlm API Documentation — auto-generated from tool definitions and endpoints.

Serves an interactive API documentation page at /docs.
"""


from .constants import VERSION
from .crypto import log

def generate_api_docs_html() -> str:
    """Generate API documentation HTML page."""
    from .tools import TOOL_DEFINITIONS

    # Build tool docs
    tool_rows = []
    for t in sorted(TOOL_DEFINITIONS, key=lambda x: x['name']):
        params = t.get('input_schema', {}).get('properties', {})
        required = t.get('input_schema', {}).get('required', [])
        param_list = []
        for pname, pinfo in params.items():
            req = ' <span class="req">*</span>' if pname in required else ''
            ptype = pinfo.get('type', 'any')
            desc = pinfo.get('description', '')
            enum = pinfo.get('enum', [])
            enum_str = f' <code>({"|".join(enum)})</code>' if enum else ''
            param_list.append(
                f'<div class="param"><code>{pname}</code>{req} '
                f'<span class="type">{ptype}</span>{enum_str} — {desc}</div>'
            )
        params_html = '\n'.join(param_list) if param_list else '<div class="param">No parameters</div>'
        tool_rows.append(f'''
        <div class="tool">
            <div class="tool-name">{t['name']}</div>
            <div class="tool-desc">{t.get('description', '')}</div>
            <div class="params">{params_html}</div>
        </div>''')

    endpoints = [
        ('GET', '/api/status', 'Version, usage, current model'),
        ('GET', '/api/health', 'Full health check (8 components)'),
        ('POST', '/api/chat', 'Send message {"message": "...", "session": "web"}'),
        ('POST', '/api/unlock', 'Unlock vault {"password": "..."}'),
        ('GET', '/api/rag', 'RAG index statistics'),
        ('GET', '/api/rag/search?q=...', 'BM25 search'),
        ('GET', '/api/mcp', 'MCP servers and tools'),
        ('GET', '/api/nodes', 'Remote nodes'),
        ('GET', '/api/ws/status', 'WebSocket server status'),
        ('GET', '/api/dashboard', 'Sessions, usage, cron, plugins'),
        ('GET', '/api/cron', 'Cron jobs'),
        ('GET', '/api/plugins', 'Loaded plugins'),
        ('GET', '/api/notifications', 'Pending notifications'),
        ('POST', '/api/upload', 'Upload file (multipart)'),
        ('POST', '/api/config/telegram', 'Configure Telegram bot'),
        ('POST', '/api/auth/login', 'Authenticate {"username": "...", "password": "..."}'),
        ('POST', '/api/auth/register', 'Create user (admin only)'),
        ('GET', '/api/auth/users', 'List users (admin only)'),
        ('GET', '/api/metrics', 'Request metrics'),
        ('GET', '/api/cert', 'TLS certificate info'),
        ('WS', 'ws://host:18801', 'WebSocket real-time streaming'),
    ]

    endpoint_rows = '\n'.join(
        f'<tr><td><span class="method method-{m.lower()}">{m}</span></td>'
        f'<td><code>{p}</code></td><td>{d}</td></tr>'
        for m, p, d in endpoints
    )

    return f'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SalmAlm API Documentation v{VERSION}</title>
<style>
:root{{--bg:#0f1117;--bg2:#1a1d27;--text:#e0e0e0;--text2:#888;--accent:#7c5cfc;--green:#34d399;--border:#252838}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.45}}
.container{{max-width:900px;margin:0 auto;padding:16px}}
h1{{color:var(--accent);margin-bottom:8px;font-size:28px}}
h2{{color:var(--accent);margin:20px 0 10px;font-size:19px;border-bottom:1px solid var(--border);padding-bottom:6px}}
.subtitle{{color:var(--text2);margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;margin:8px 0}}
th,td{{padding:6px 10px;text-align:left;border-bottom:1px solid var(--border)}}
th{{color:var(--accent);font-size:12px;text-transform:uppercase;letter-spacing:1px}}
code{{background:#252838;padding:2px 6px;border-radius:4px;font-size:13px}}
.method{{padding:3px 8px;border-radius:4px;font-size:11px;font-weight:700;letter-spacing:0.5px}}
.method-get{{background:#0d3b2e;color:#34d399}}
.method-post{{background:#3b2e0d;color:#fbbf24}}
.method-ws{{background:#2e0d3b;color:#a78bfa}}
.tool{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:10px 14px;margin:8px 0}}
.tool-name{{font-weight:700;color:var(--green);font-size:16px}}
.tool-desc{{color:var(--text2);margin:4px 0 8px;font-size:14px}}
.params{{font-size:13px}}
.param{{margin:4px 0;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05)}}
.param code{{color:var(--accent)}}
.type{{color:var(--text2);font-size:12px}}
.req{{color:#f87171;font-weight:bold}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}}
.stat{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:10px 16px;text-align:center}}
.stat-value{{font-size:24px;font-weight:700;color:var(--accent)}}
.stat-label{{font-size:12px;color:var(--text2);margin-top:4px}}
a{{color:var(--accent);text-decoration:none}}
a:hover{{text-decoration:underline}}
</style></head><body>
<div class="container">
<h1>😈 SalmAlm API Documentation</h1>
<p class="subtitle">v{VERSION} — Personal AI Gateway — Pure Python, Zero Dependencies</p>

<div class="stats">
<div class="stat"><div class="stat-value">{len(TOOL_DEFINITIONS)}</div><div class="stat-label">Tools</div></div>
<div class="stat"><div class="stat-value">15</div><div class="stat-label">Modules</div></div>
<div class="stat"><div class="stat-value">7,334</div><div class="stat-label">Lines of Code</div></div>
<div class="stat"><div class="stat-value">0</div><div class="stat-label">Dependencies</div></div>
</div>

<h2>📡 REST API Endpoints</h2>
<table>
<thead><tr><th>Method</th><th>Endpoint</th><th>Description</th></tr></thead>
<tbody>{endpoint_rows}</tbody>
</table>

<h2>🔑 Authentication</h2>
<p>Three methods supported:</p>
<ul style="margin:8px 0 8px 24px;color:var(--text2)">
<li><code>Authorization: Bearer &lt;token&gt;</code> — JWT token from /api/auth/login</li>
<li><code>Authorization: ApiKey &lt;key&gt;</code> — API key from user profile</li>
<li><code>X-API-Key: &lt;key&gt;</code> — API key header</li>
</ul>

<h2>⚡ WebSocket Protocol</h2>
<p>Connect to <code>ws://host:18801</code></p>
<p>Send: <code>{{"type": "message", "text": "...", "session": "web"}}</code></p>
<p>Receive:</p>
<ul style="margin:8px 0 8px 24px;color:var(--text2)">
<li><code>{{"type": "chunk", "text": "...", "rid": "..."}}</code> — streaming response</li>
<li><code>{{"type": "tool", "name": "...", "input": {{}}, "result": "..."}}</code> — tool call</li>
<li><code>{{"type": "thinking", "text": "..."}}</code> — reasoning</li>
<li><code>{{"type": "done", "text": "..."}}</code> — complete response</li>
<li><code>{{"type": "error", "error": "..."}}</code> — error</li>
</ul>

<h2>🔧 Tools ({len(TOOL_DEFINITIONS)})</h2>
{''.join(tool_rows)}

<div style="margin-top:24px;padding:12px 0;border-top:1px solid var(--border);color:var(--text2);font-size:13px;text-align:center">
SalmAlm v{VERSION} — <a href="https://github.com/hyunjun6928-netizen/salmalm">GitHub</a>
</div>
</div></body></html>'''
