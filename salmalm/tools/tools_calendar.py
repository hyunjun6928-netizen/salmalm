"""Google Calendar tools — granular calendar_list, calendar_add, calendar_delete."""
import json, urllib.request
from datetime import datetime, timedelta
from salmalm.tool_registry import register
from salmalm.crypto import vault, log
from salmalm.tools_google import _google_oauth_headers


@register('calendar_list')
def handle_calendar_list(args: dict) -> str:
    """List upcoming calendar events."""
    headers = _google_oauth_headers()
    cal_id = args.get('calendar_id', 'primary')
    period = args.get('period', 'week')  # today, week, month
    base_url = f'https://www.googleapis.com/calendar/v3/calendars/{cal_id}'

    now = datetime.utcnow()
    if period == 'today':
        time_max = now.replace(hour=23, minute=59, second=59)
        label = 'today'
    elif period == 'month':
        time_max = now + timedelta(days=30)
        label = 'this month'
    else:
        time_max = now + timedelta(days=7)
        label = 'this week'

    time_min = now.isoformat() + 'Z'
    time_max_str = time_max.isoformat() + 'Z'

    url = (f'{base_url}/events?timeMin={time_min}&timeMax={time_max_str}'
           f'&maxResults=30&singleEvents=true&orderBy=startTime')
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    events = data.get('items', [])
    if not events:
        return f'📅 No events {label}.'

    lines = [f'📅 **Events {label} ({len(events)}):**']
    for e in events:
        start = e.get('start', {}).get('dateTime', e.get('start', {}).get('date', '?'))
        summary = e.get('summary', '(no title)')
        loc = e.get('location', '')
        eid = e.get('id', '')
        line = f"  • **{summary}** — {start[:16]}"
        if loc:
            line += f" 📍{loc}"
        line += f"\n    ID: `{eid}`"
        lines.append(line)
    return '\n'.join(lines)


@register('calendar_add')
def handle_calendar_add(args: dict) -> str:
    """Add a calendar event."""
    headers = _google_oauth_headers()
    cal_id = args.get('calendar_id', 'primary')
    base_url = f'https://www.googleapis.com/calendar/v3/calendars/{cal_id}'

    title = args.get('title', '')
    date = args.get('date', '')
    time_str = args.get('time', '')
    duration = int(args.get('duration_minutes', 60))
    description = args.get('description', '')

    if not title or not date:
        return '❌ title and date are required (e.g. calendar_add title="회의" date="2026-02-20" time="14:00")'

    if time_str:
        start_dt = f'{date}T{time_str}:00'
        # Calculate end
        from datetime import datetime as _dt
        s = _dt.fromisoformat(start_dt)
        e = s + timedelta(minutes=duration)
        end_dt = e.isoformat()
        event = {
            'summary': title,
            'start': {'dateTime': start_dt, 'timeZone': 'Asia/Seoul'},
            'end': {'dateTime': end_dt, 'timeZone': 'Asia/Seoul'},
        }
    else:
        # All-day event
        event = {
            'summary': title,
            'start': {'date': date},
            'end': {'date': date},
        }

    if description:
        event['description'] = description

    body = json.dumps(event).encode()
    req = urllib.request.Request(
        f'{base_url}/events', data=body,
        headers={**headers, 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())

    return f"📅 Event created: **{result.get('summary')}** ({result.get('htmlLink', '')})"


@register('calendar_delete')
def handle_calendar_delete(args: dict) -> str:
    """Delete a calendar event."""
    headers = _google_oauth_headers()
    cal_id = args.get('calendar_id', 'primary')
    event_id = args.get('event_id', '')

    if not event_id:
        return '❌ event_id is required'

    url = f'https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events/{event_id}'
    req = urllib.request.Request(url, headers=headers, method='DELETE')
    urllib.request.urlopen(req, timeout=15)
    return f'📅 Event deleted: {event_id}'
