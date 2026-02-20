"""Google tools: google_calendar, gmail."""
import json
import base64
import urllib.request
from datetime import datetime
from salmalm.tool_registry import register
from salmalm.crypto import vault


def _google_oauth_headers() -> dict:
    """Get OAuth2 headers for Google APIs."""
    token = vault.get('google_access_token') or ''
    refresh = vault.get('google_refresh_token') or ''
    client_id = vault.get('google_client_id') or ''
    client_secret = vault.get('google_client_secret') or ''

    if not token and not refresh:
        raise ValueError(
            'Google API credentials not configured. '
            'Set google_refresh_token, google_client_id, google_client_secret in vault.')

    if token:
        return {'Authorization': f'Bearer {token}'}

    if refresh and client_id and client_secret:
        data = json.dumps({
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh,
            'grant_type': 'refresh_token',
        }).encode()
        req = urllib.request.Request(
            'https://oauth2.googleapis.com/token',
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST')
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                new_token = result.get('access_token', '')
                if new_token:
                    vault.set('google_access_token', new_token)
                    return {'Authorization': f'Bearer {new_token}'}
        except Exception as e:
            raise ValueError(f'OAuth2 refresh failed: {e}')

    raise ValueError('Cannot authenticate with Google. Check vault credentials.')


@register('google_calendar')
def handle_google_calendar(args: dict) -> str:
    action = args.get('action', 'list')
    cal_id = args.get('calendar_id', 'primary')
    base_url = f'https://www.googleapis.com/calendar/v3/calendars/{cal_id}'
    headers = _google_oauth_headers()

    if action == 'list':
        days = args.get('days', 7)
        now = datetime.utcnow()
        from datetime import timedelta
        time_min = now.isoformat() + 'Z'
        time_max = (now + timedelta(days=days)).isoformat() + 'Z'
        url = f'{base_url}/events?timeMin={time_min}&timeMax={time_max}&maxResults=20&singleEvents=true&orderBy=startTime'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        events = data.get('items', [])
        if not events:
            return f'📅 No events in the next {days} days.'
        lines = [f'📅 **Upcoming Events ({len(events)}):**']
        for e in events:
            start = e.get('start', {}).get('dateTime', e.get('start', {}).get('date', '?'))
            summary = e.get('summary', '(no title)')
            loc = e.get('location', '')
            line = f"  • **{summary}** — {start[:16]}"
            if loc:
                line += f" 📍{loc}"
            lines.append(line)
        return '\n'.join(lines)

    elif action == 'create':
        title = args.get('title', '')
        start = args.get('start', '')
        end = args.get('end', '')
        desc = args.get('description', '')
        if not title or not start:
            return '❌ title and start are required for create'
        event = {
            'summary': title,
            'start': {'dateTime': start, 'timeZone': 'Asia/Seoul'},
            'end': {'dateTime': end or start, 'timeZone': 'Asia/Seoul'},
        }
        if desc:
            event['description'] = desc
        body = json.dumps(event).encode()
        req = urllib.request.Request(
            f'{base_url}/events', data=body,
            headers={**headers, 'Content-Type': 'application/json'},
            method='POST')
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        return f"📅 Event created: **{result.get('summary')}** ({result.get('htmlLink', '')})"

    elif action == 'delete':
        event_id = args.get('event_id', '')
        if not event_id:
            return '❌ event_id is required for delete'
        req = urllib.request.Request(
            f'{base_url}/events/{event_id}', headers=headers, method='DELETE')
        urllib.request.urlopen(req, timeout=15)
        return f'📅 Event deleted: {event_id}'

    return f'❌ Unknown calendar action: {action}'


@register('gmail')
def handle_gmail(args: dict) -> str:
    action = args.get('action', 'list')
    base_url = 'https://www.googleapis.com/gmail/v1/users/me'
    headers = _google_oauth_headers()

    if action == 'list' or action == 'search':
        count = min(args.get('count', 10), 50)
        query = args.get('query', '')
        label = args.get('label', 'INBOX')
        params = f'maxResults={count}'
        if query:
            import urllib.parse
            params += f'&q={urllib.parse.quote(query)}'
        elif label:
            params += f'&labelIds={label}'
        url = f'{base_url}/messages?{params}'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        messages = data.get('messages', [])
        if not messages:
            return '📧 No messages found.'

        lines = [f'📧 **Messages ({len(messages)}):**']
        for msg_ref in messages[:count]:
            msg_url = f'{base_url}/messages/{msg_ref["id"]}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date'
            req = urllib.request.Request(msg_url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    msg = json.loads(resp.read())
                hdrs = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
                subj = hdrs.get('Subject', '(no subject)')
                frm = hdrs.get('From', '?')
                date = hdrs.get('Date', '')[:22]
                snippet = msg.get('snippet', '')[:80]
                lines.append(f"  📩 **{subj}** — {frm[:30]}")
                lines.append(f"     {date} | {snippet}")
                lines.append(f"     ID: `{msg_ref['id']}`")
            except Exception:
                lines.append(f"  📩 ID: {msg_ref['id']} (failed to fetch)")
        return '\n'.join(lines)

    elif action == 'read':
        msg_id = args.get('message_id', '')
        if not msg_id:
            return '❌ message_id is required for read'
        url = f'{base_url}/messages/{msg_id}?format=full'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            msg = json.loads(resp.read())
        hdrs = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
        subj = hdrs.get('Subject', '(no subject)')
        frm = hdrs.get('From', '?')
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

        return f"📧 **{subj}**\nFrom: {frm}\nDate: {date}\n\n{body_text[:3000]}"

    elif action == 'send':
        to = args.get('to', '')
        subject = args.get('subject', '')
        body = args.get('body', '')
        if not to or not subject:
            return '❌ to and subject are required for send'
        import email.mime.text
        msg = email.mime.text.MIMEText(body, 'plain', 'utf-8')
        msg['To'] = to
        msg['Subject'] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        send_body = json.dumps({'raw': raw}).encode()
        req = urllib.request.Request(
            f'{base_url}/messages/send', data=send_body,
            headers={**headers, 'Content-Type': 'application/json'},
            method='POST')
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        return f"📧 Email sent to {to} (ID: {result.get('id', '?')})"

    return f'❌ Unknown gmail action: {action}'
