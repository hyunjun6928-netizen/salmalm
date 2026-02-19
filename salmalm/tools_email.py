"""Gmail tools — granular email_inbox, email_read, email_send, email_search."""
import json, base64, urllib.request
import email.mime.text
from .tool_registry import register
from .crypto import vault, log
from .tools_google import _google_oauth_headers

_BASE_URL = 'https://www.googleapis.com/gmail/v1/users/me'


def _fetch_message_summary(msg_id: str, headers: dict) -> str:
    """Fetch a single message's summary (subject, from, date, snippet)."""
    url = (f'{_BASE_URL}/messages/{msg_id}'
           f'?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date')
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            msg = json.loads(resp.read())
        hdrs = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
        subj = hdrs.get('Subject', '(no subject)')
        frm = hdrs.get('From', '?')
        date = hdrs.get('Date', '')[:22]
        snippet = msg.get('snippet', '')[:80]
        labels = msg.get('labelIds', [])
        unread = '🔵 ' if 'UNREAD' in labels else ''
        return (f"  {unread}📩 **{subj}** — {frm[:40]}\n"
                f"     {date} | {snippet}\n"
                f"     ID: `{msg_id}`")
    except Exception:
        return f"  📩 ID: {msg_id} (failed to fetch)"


@register('email_inbox')
def handle_email_inbox(args: dict) -> str:
    """List recent inbox messages."""
    headers = _google_oauth_headers()
    count = min(int(args.get('count', 10)), 30)
    url = f'{_BASE_URL}/messages?maxResults={count}&labelIds=INBOX'
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    messages = data.get('messages', [])
    if not messages:
        return '📧 Inbox is empty.'

    lines = [f'📧 **Inbox ({len(messages)} messages):**']
    for m in messages[:count]:
        lines.append(_fetch_message_summary(m['id'], headers))
    return '\n'.join(lines)


@register('email_read')
def handle_email_read(args: dict) -> str:
    """Read a specific email by message_id."""
    headers = _google_oauth_headers()
    msg_id = args.get('message_id', '')
    if not msg_id:
        return '❌ message_id is required'

    url = f'{_BASE_URL}/messages/{msg_id}?format=full'
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        msg = json.loads(resp.read())

    hdrs = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
    subj = hdrs.get('Subject', '(no subject)')
    frm = hdrs.get('From', '?')
    to = hdrs.get('To', '?')
    date = hdrs.get('Date', '')
    payload = msg.get('payload', {})

    def _extract_body(part: dict) -> str:
        if part.get('mimeType', '').startswith('text/plain'):
            data = part.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
        for sub in part.get('parts', []):
            result = _extract_body(sub)
            if result:
                return result
        return ''

    body_text = _extract_body(payload)
    if not body_text and payload.get('body', {}).get('data'):
        body_text = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='replace')

    return (f"📧 **{subj}**\n"
            f"From: {frm}\nTo: {to}\nDate: {date}\n\n"
            f"{body_text[:4000]}")


@register('email_send')
def handle_email_send(args: dict) -> str:
    """Send an email."""
    headers = _google_oauth_headers()
    to = args.get('to', '')
    subject = args.get('subject', '')
    body = args.get('body', '')

    if not to or not subject:
        return '❌ to and subject are required'

    msg = email.mime.text.MIMEText(body, 'plain', 'utf-8')
    msg['To'] = to
    msg['Subject'] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    send_body = json.dumps({'raw': raw}).encode()
    req = urllib.request.Request(
        f'{_BASE_URL}/messages/send', data=send_body,
        headers={**headers, 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())

    return f"📧 Email sent to {to} (ID: {result.get('id', '?')})"


@register('email_search')
def handle_email_search(args: dict) -> str:
    """Search emails with Gmail query syntax."""
    headers = _google_oauth_headers()
    query = args.get('query', '')
    if not query:
        return '❌ query is required'

    count = min(int(args.get('count', 10)), 30)
    import urllib.parse
    url = f'{_BASE_URL}/messages?maxResults={count}&q={urllib.parse.quote(query)}'
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    messages = data.get('messages', [])
    if not messages:
        return f'📧 No messages matching "{query}".'

    lines = [f'📧 **Search results for "{query}" ({len(messages)}):**']
    for m in messages[:count]:
        lines.append(_fetch_message_summary(m['id'], headers))
    return '\n'.join(lines)
