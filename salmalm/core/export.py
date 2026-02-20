"""Conversation Export — export current session as Markdown, JSON, or HTML.

Provides the /export command implementation.
stdlib-only.
"""
from __future__ import annotations

import html as _html
import json
from datetime import datetime

from salmalm.constants import VERSION, KST, BASE_DIR
from salmalm.security.crypto import log

EXPORT_DIR = BASE_DIR / 'exports'


def export_session(session, fmt: str = 'md') -> dict:
    """Export a session to the specified format.

    Args:
        session: Session object with .id and .messages
        fmt: 'md' | 'json' | 'html'

    Returns:
        {'ok': True, 'path': str, 'filename': str, 'size': int}
        or {'ok': False, 'error': str}
    """
    if fmt not in ('md', 'json', 'html'):
        return {'ok': False, 'error': f'Unsupported format: {fmt}. Use md, json, or html.'}

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST)
    timestamp = now.strftime('%Y%m%d_%H%M%S')
    sid_short = session.id[:20]

    if fmt == 'md':
        content = _export_markdown(session, now)
        filename = f'export_{sid_short}_{timestamp}.md'
    elif fmt == 'json':
        content = _export_json(session, now)
        filename = f'export_{sid_short}_{timestamp}.json'
    elif fmt == 'html':
        content = _export_html(session, now)
        filename = f'export_{sid_short}_{timestamp}.html'
    else:
        return {'ok': False, 'error': 'Unknown format'}

    filepath = EXPORT_DIR / filename
    try:
        filepath.write_text(content, encoding='utf-8')
        size = filepath.stat().st_size
        log.info(f"[EXPORT] Session {session.id} exported as {fmt}: {filepath} ({size} bytes)")
        return {'ok': True, 'path': str(filepath), 'filename': filename, 'size': size}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:200]}


def _msg_text(msg: dict) -> str:
    """Extract text from a message."""
    content = msg.get('content', '')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get('type') == 'text':
                    parts.append(block.get('text', ''))
                elif block.get('type') == 'tool_result':
                    parts.append(f"[Tool result: {block.get('content', '')[:100]}]")
                elif block.get('type') == 'tool_use':
                    parts.append(f"[Tool call: {block.get('name', '?')}]")
        return '\n'.join(parts)
    return str(content)


def _export_markdown(session, now: datetime) -> str:
    """Export session as Markdown."""
    lines = [
        '# SalmAlm Conversation Export',
        '',
        f'- **Session ID**: {session.id}',
        f'- **Date**: {now.isoformat()}',
        f'- **Version**: SalmAlm v{VERSION}',
        f'- **Messages**: {len(session.messages)}',
        '',
        '---',
        '',
    ]
    for msg in session.messages:
        role = msg.get('role', '')
        if role == 'system':
            continue
        text = _msg_text(msg)
        if role == 'user':
            lines.append('## 👤 User')
        elif role == 'assistant':
            lines.append('## 🤖 Assistant')
        elif role == 'tool':
            lines.append(f'## 🔧 Tool ({msg.get("name", "?")})')
        else:
            lines.append(f'## {role}')
        lines.append('')
        lines.append(text)
        lines.append('')
        lines.append('---')
        lines.append('')
    return '\n'.join(lines)


def _export_json(session, now: datetime) -> str:
    """Export session as JSON."""
    messages = []
    for msg in session.messages:
        role = msg.get('role', '')
        if role == 'system':
            continue
        messages.append({
            'role': role,
            'content': _msg_text(msg),
        })
    data = {
        'session_id': session.id,
        'exported_at': now.isoformat(),
        'version': VERSION,
        'message_count': len(messages),
        'messages': messages,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _export_html(session, now: datetime) -> str:
    """Export session as standalone HTML."""
    msgs_html = []
    for msg in session.messages:
        role = msg.get('role', '')
        if role == 'system':
            continue
        text = _html.escape(_msg_text(msg)).replace('\n', '<br>')
        if role == 'user':
            cls = 'user'
            icon = '👤'
        elif role == 'assistant':
            cls = 'assistant'
            icon = '🤖'
        else:
            cls = 'tool'
            icon = '🔧'
        msgs_html.append(
            f'<div class="msg {cls}"><span class="icon">{icon}</span>'
            f'<div class="content">{text}</div></div>'
        )

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SalmAlm Export — {_html.escape(session.id)}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       max-width: 800px; margin: 40px auto; padding: 0 20px; background: #0b0d14; color: #e2e8f0; }}
h1 {{ color: #818cf8; }}
.meta {{ color: #94a3b8; font-size: 0.9em; margin-bottom: 2em; }}
.msg {{ display: flex; gap: 12px; margin: 16px 0; padding: 16px; border-radius: 12px; }}
.msg.user {{ background: #1e293b; }}
.msg.assistant {{ background: #1a1a2e; border-left: 3px solid #818cf8; }}
.msg.tool {{ background: #1a2332; border-left: 3px solid #22d3ee; font-size: 0.9em; }}
.icon {{ font-size: 1.5em; flex-shrink: 0; }}
.content {{ white-space: pre-wrap; word-break: break-word; line-height: 1.6; }}
</style>
</head>
<body>
<h1>😈 SalmAlm Conversation Export</h1>
<div class="meta">
  Session: {_html.escape(session.id)}<br>
  Date: {now.isoformat()}<br>
  Version: SalmAlm v{VERSION}<br>
  Messages: {len(session.messages)}
</div>
{''.join(msgs_html)}
</body>
</html>'''
