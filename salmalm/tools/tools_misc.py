"""Misc tools: reminder, workflow, file_index, notification, weather, rss_reader."""
import json
import re
import time
import secrets
import threading
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from salmalm.tools.tool_registry import register
from salmalm.constants import WORKSPACE_DIR
from salmalm.security.crypto import vault, log
from salmalm.core import _tg_bot


# ── Reminder System ──────────────────────────────────────────

_reminders: list = []
_reminder_lock = threading.Lock()
_reminder_thread_started = False


def _parse_relative_time(s: str) -> datetime:
    """Parse time string into datetime."""
    now = datetime.now()
    s_stripped = s.strip().lower()

    m = re.match(r'^(\d+)\s*(m|min|h|hr|hour|d|day|w|week)s?$', s_stripped)
    if m:
        val = int(m.group(1))
        unit = m.group(2)[0]
        delta = {'m': timedelta(minutes=val), 'h': timedelta(hours=val),
                 'd': timedelta(days=val), 'w': timedelta(weeks=val)}
        return now + delta.get(unit, timedelta(minutes=val))

    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass

    s_orig = s.strip()
    day_offset = 0
    hour = None
    minute = 0

    if '오늘' in s_orig:
        day_offset = 0
    elif '내일' in s_orig:
        day_offset = 1
    elif '모레' in s_orig:
        day_offset = 2
    elif '다음주' in s_orig or 'next week' in s_stripped:
        day_offset = 7
        weekdays_kr = {'월': 0, '화': 1, '수': 2, '목': 3, '금': 4, '토': 5, '일': 6}
        weekdays_en = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
        for wd, idx in {**weekdays_kr, **weekdays_en}.items():
            if wd in s_orig or wd in s_stripped:
                current_wd = now.weekday()
                days_ahead = (idx - current_wd + 7) % 7
                if days_ahead == 0:
                    days_ahead = 7
                day_offset = days_ahead
                break
    elif 'tomorrow' in s_stripped:
        day_offset = 1

    if '아침' in s_orig or 'morning' in s_stripped:
        hour = 8
    elif '점심' in s_orig or 'noon' in s_stripped or 'lunch' in s_stripped:
        hour = 12
    elif '저녁' in s_orig or 'evening' in s_stripped:
        hour = 18
    elif '밤' in s_orig or 'night' in s_stripped:
        hour = 21

    m_kr = re.search(r'(오전|오후|AM|PM)?\s*(\d{1,2})\s*시\s*(\d{1,2})?\s*분?', s_orig)
    if m_kr:
        period = m_kr.group(1)
        hour = int(m_kr.group(2))
        minute = int(m_kr.group(3) or 0)
        if period in ('오후', 'PM') and hour < 12:
            hour += 12
        elif period in ('오전', 'AM') and hour == 12:
            hour = 0
        elif not period:
            if ('저녁' in s_orig or '밤' in s_orig) and hour < 12:
                hour += 12
            elif ('오후' in s_orig) and hour < 12:
                hour += 12

    m_en = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', s_stripped)
    if m_en and hour is None:
        hour = int(m_en.group(1))
        minute = int(m_en.group(2) or 0)
        period = m_en.group(3)
        if period == 'pm' and hour < 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0

    if day_offset > 0 or hour is not None:
        target = now + timedelta(days=day_offset)
        if hour is not None:
            target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        elif day_offset > 0:
            target = target.replace(hour=9, minute=0, second=0, microsecond=0)
        return target

    raise ValueError(f'Cannot parse time: {s}')


def _reminders_file() -> Path:
    return WORKSPACE_DIR / 'reminders.json'


def _load_reminders():
    global _reminders
    fp = _reminders_file()
    if fp.exists():
        try:
            _reminders = json.loads(fp.read_text(encoding='utf-8'))
        except Exception:
            _reminders = []


def _save_reminders():
    fp = _reminders_file()
    fp.write_text(json.dumps(_reminders, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def _send_notification_impl(message: str, title: str = '', channel: str = 'all',
                            url: str = '', priority: str = 'normal'):
    """Send notification via available channels."""
    results = []

    if channel in ('telegram', 'all'):
        try:
            tg = _tg_bot
            if tg:
                owner = vault.get('telegram_owner_id') or ''
                if owner:
                    text = f"🔔 {title}\n{message}" if title else f"🔔 {message}"
                    tg_url = f"https://api.telegram.org/bot{vault.get('telegram_bot_token')}/sendMessage"
                    body = json.dumps({'chat_id': owner, 'text': text}).encode()
                    req = urllib.request.Request(
                        tg_url, data=body,
                        headers={'Content-Type': 'application/json'},
                        method='POST')
                    urllib.request.urlopen(req, timeout=10)
                    results.append('telegram: ✅')
                else:
                    results.append('telegram: ⚠️ no owner_id')
            else:
                results.append('telegram: ⚠️ not configured')
        except Exception as e:
            results.append(f'telegram: ❌ {e}')

    if channel in ('desktop', 'all'):
        try:
            if sys.platform == 'darwin':
                subprocess.run(['osascript', '-e',
                                f'display notification "{message}" with title "{title or "SalmAlm"}"'],
                               timeout=5, capture_output=True)
                results.append('desktop: ✅')
            elif sys.platform == 'linux':
                subprocess.run(['notify-send', title or 'SalmAlm', message],
                               timeout=5, capture_output=True)
                results.append('desktop: ✅')
            elif sys.platform == 'win32':
                ps_cmd = f'''
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
                $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
                $template.GetElementsByTagName("text")[0].AppendChild($template.CreateTextNode("{title or 'SalmAlm'}")) | Out-Null
                $template.GetElementsByTagName("text")[1].AppendChild($template.CreateTextNode("{message}")) | Out-Null
                $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
                [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("SalmAlm").Show($toast)
                '''
                subprocess.run(['powershell', '-Command', ps_cmd],
                               timeout=10, capture_output=True)
                results.append('desktop: ✅')
            else:
                results.append('desktop: ⚠️ unsupported platform')
        except FileNotFoundError:
            results.append('desktop: ⚠️ notification tool not found')
        except Exception as e:
            results.append(f'desktop: ❌ {e}')

    if channel == 'webhook' and url:
        try:
            body = json.dumps({
                'title': title or 'SalmAlm',
                'message': message,
                'priority': priority,
                'timestamp': datetime.now().isoformat(),
            }).encode()
            req = urllib.request.Request(
                url, data=body,
                headers={'Content-Type': 'application/json'},
                method='POST')
            urllib.request.urlopen(req, timeout=10)
            results.append('webhook: ✅')
        except Exception as e:
            results.append(f'webhook: ❌ {e}')

    return results


def _reminder_check_loop():
    while True:
        time.sleep(30)
        now = datetime.now()
        with _reminder_lock:
            due = []
            remaining = []
            for r in _reminders:
                try:
                    trigger_time = datetime.fromisoformat(r['time'])
                    if trigger_time <= now:
                        due.append(r)
                    else:
                        remaining.append(r)
                except Exception:
                    remaining.append(r)
            if due:
                _reminders.clear()
                _reminders.extend(remaining)
                _save_reminders()
        for r in due:
            try:
                _send_notification_impl(
                    f"⏰ Reminder: {r['message']}",
                    title='Reminder',
                    channel='all')
            except Exception as e:
                log.error(f"Reminder notification failed: {e}")
            if r.get('repeat'):
                try:
                    repeat = r['repeat']
                    deltas = {'daily': timedelta(days=1), 'weekly': timedelta(weeks=1),
                              'monthly': timedelta(days=30)}
                    if repeat in deltas:
                        r['time'] = (datetime.fromisoformat(r['time']) + deltas[repeat]).isoformat()
                        with _reminder_lock:
                            _reminders.append(r)
                            _save_reminders()
                except Exception:
                    pass


def _ensure_reminder_thread():
    global _reminder_thread_started
    if not _reminder_thread_started:
        _reminder_thread_started = True
        _load_reminders()
        t = threading.Thread(target=_reminder_check_loop, daemon=True)
        t.start()


@register('reminder')
def handle_reminder(args: dict) -> str:
    _ensure_reminder_thread()
    action = args.get('action', 'set')

    if action == 'set':
        message = args.get('message', '')
        time_str = args.get('time', '')
        if not message or not time_str:
            return '❌ message and time are required'
        trigger_time = _parse_relative_time(time_str)
        reminder = {
            'id': secrets.token_hex(4),
            'message': message,
            'time': trigger_time.isoformat(),
            'repeat': args.get('repeat'),
            'created': datetime.now().isoformat(),
        }
        with _reminder_lock:
            _reminders.append(reminder)
            _save_reminders()
        return f"⏰ Reminder set: **{message}** at {trigger_time.strftime('%Y-%m-%d %H:%M')}" + \
            (f" (repeat: {args['repeat']})" if args.get('repeat') else '')

    elif action == 'list':
        _load_reminders()
        if not _reminders:
            return '⏰ No active reminders.'
        lines = [f'⏰ **Active Reminders ({len(_reminders)}):**']
        for r in sorted(_reminders, key=lambda x: x.get('time', '')):
            repeat_str = f" 🔁{r['repeat']}" if r.get('repeat') else ''
            lines.append(f"  • [{r['id']}] **{r['message']}** — {r['time'][:16]}{repeat_str}")
        return '\n'.join(lines)

    elif action == 'delete':
        rid = args.get('reminder_id', '')
        if not rid:
            return '❌ reminder_id is required'
        with _reminder_lock:
            before = len(_reminders)
            _reminders[:] = [r for r in _reminders if r.get('id') != rid]
            _save_reminders()
            if len(_reminders) < before:
                return f'⏰ Reminder deleted: {rid}'
        return f'❌ Reminder not found: {rid}'

    return f'❌ Unknown reminder action: {action}'


# ── Workflow Engine ──────────────────────────────────────────

_workflows_file = WORKSPACE_DIR / 'workflows.json'


def _load_workflows() -> dict:
    if _workflows_file.exists():
        try:
            return json.loads(_workflows_file.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def _save_workflows(wf: dict):
    _workflows_file.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding='utf-8')


@register('workflow')
def handle_workflow(args: dict) -> str:
    from salmalm.tools.tool_registry import execute_tool
    action = args.get('action', 'list')

    if action == 'list':
        wf = _load_workflows()
        if not wf:
            return '🔄 No saved workflows.'
        lines = ['🔄 **Saved Workflows:**']
        for name, data in wf.items():
            steps = data.get('steps', [])
            lines.append(f"  • **{name}** — {len(steps)} steps")
        return '\n'.join(lines)

    elif action == 'save':
        name = args.get('name', '')
        steps = args.get('steps', [])
        if not name or not steps:
            return '❌ name and steps are required for save'
        wf = _load_workflows()
        wf[name] = {'steps': steps, 'created': datetime.now().isoformat()}
        _save_workflows(wf)
        return f'🔄 Workflow saved: **{name}** ({len(steps)} steps)'

    elif action == 'delete':
        name = args.get('name', '')
        wf = _load_workflows()
        if name in wf:
            del wf[name]
            _save_workflows(wf)
            return f'🔄 Workflow deleted: {name}'
        return f'❌ Workflow not found: {name}'

    elif action == 'run':
        name = args.get('name', '')
        steps = args.get('steps', [])
        variables = args.get('variables', {})
        if name and not steps:
            wf = _load_workflows()
            if name not in wf:
                return f'❌ Workflow not found: {name}'
            steps = wf[name].get('steps', [])
        if not steps:
            return '❌ No steps defined'
        context = dict(variables)
        results = []
        for i, step in enumerate(steps):
            tool_name = step.get('tool', '')
            step_args = dict(step.get('args', {}))
            for k, v in step_args.items():
                if isinstance(v, str) and v.startswith('$'):
                    var_name = v[1:]
                    if var_name in context:
                        step_args[k] = context[var_name]
            result = execute_tool(tool_name, step_args)
            results.append(f"Step {i + 1} ({tool_name}): {result[:200]}")
            output_var = step.get('output_var', f'step_{i + 1}')
            context[output_var] = result
        return '🔄 **Workflow Complete:**\n' + '\n'.join(results)

    return f'❌ Unknown workflow action: {action}'


# ── File Index ───────────────────────────────────────────────

_file_index: dict = {}
_file_index_lock = threading.Lock()


@register('file_index')
def handle_file_index(args: dict) -> str:
    action = args.get('action', 'search')

    if action == 'index' or action == 'status':
        target_dir = Path(args.get('path', str(WORKSPACE_DIR)))
        if not target_dir.exists():
            return f'❌ Directory not found: {target_dir}'
        exts = args.get('extensions', 'py,md,txt,json,yaml,yml,toml,cfg,ini,sh,bat,js,ts,html,css')
        ext_set = set(f'.{e.strip()}' for e in exts.split(','))
        count = 0
        with _file_index_lock:
            for fp in target_dir.rglob('*'):
                if fp.is_file() and fp.suffix in ext_set and fp.stat().st_size < 500_000:
                    try:
                        if any(p.startswith('.') for p in fp.relative_to(target_dir).parts[:-1]):
                            continue
                        content = fp.read_text(encoding='utf-8', errors='replace')[:50000]
                        words = set(re.findall(r'\w+', content.lower()))
                        _file_index[str(fp)] = {
                            'mtime': fp.stat().st_mtime,
                            'words': words,
                            'size': fp.stat().st_size,
                            'preview': content[:200],
                        }
                        count += 1
                    except Exception:
                        pass
        if action == 'status':
            return f'📂 File index: {len(_file_index)} files indexed'
        return f'📂 Indexed {count} files from {target_dir}'

    elif action == 'search':
        query = args.get('query', '')
        if not query:
            return '❌ query is required'
        limit = args.get('limit', 10)
        if not _file_index:
            handle_file_index({'action': 'index'})
        query_words = set(re.findall(r'\w+', query.lower()))
        if not query_words:
            return '❌ No searchable terms in query'
        scored = []
        with _file_index_lock:
            for path, info in _file_index.items():
                overlap = len(query_words & info['words'])
                if overlap > 0:
                    score = overlap / len(query_words)
                    scored.append((score, path, info))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:limit]
        if not results:
            return f'🔍 No files matching: {query}'
        lines = [f'🔍 **File Search: "{query}" ({len(results)} results):**']
        for score, path, info in results:
            rel = Path(path).relative_to(WORKSPACE_DIR) if path.startswith(str(WORKSPACE_DIR)) else Path(path)
            lines.append(f"  📄 **{rel}** (score: {score:.1%}, {info['size']}B)")
            lines.append(f"     {info['preview'][:100]}...")
        return '\n'.join(lines)

    return f'❌ Unknown file_index action: {action}'


@register('notification')
def handle_notification(args: dict) -> str:
    message = args.get('message', '')
    if not message:
        return '❌ message is required'
    title = args.get('title', '')
    channel = args.get('channel', 'all')
    url = args.get('url', '')
    priority = args.get('priority', 'normal')
    results = _send_notification_impl(message, title, channel, url, priority)
    return '🔔 Notification sent:\n  ' + '\n  '.join(results)


@register('weather')
def handle_weather(args: dict) -> str:
    location = args.get('location', '')
    if not location:
        return '❌ location is required'
    fmt = args.get('format', 'full')
    lang = args.get('lang', 'ko')

    import urllib.parse
    loc_encoded = urllib.parse.quote(location)

    if fmt == 'short':
        url = f'https://wttr.in/{loc_encoded}?format=%l:+%c+%t+%h+%w&lang={lang}'
    elif fmt == 'forecast':
        url = f'https://wttr.in/{loc_encoded}?format=3&lang={lang}'
    else:
        url = f'https://wttr.in/{loc_encoded}?format=j1&lang={lang}'

    req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.0', 'Accept-Language': lang})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        return f'❌ Weather fetch failed: {e}'

    if fmt in ('short', 'forecast'):
        return f'🌤️ {data.strip()}'

    try:
        wdata = json.loads(data)
        current = wdata.get('current_condition', [{}])[0]
        area = wdata.get('nearest_area', [{}])[0]
        city = area.get('areaName', [{}])[0].get('value', location)
        country = area.get('country', [{}])[0].get('value', '')

        temp_c = current.get('temp_C', '?')
        feels = current.get('FeelsLikeC', '?')
        humidity = current.get('humidity', '?')
        desc_kr = current.get('lang_ko', [{}])[0].get('value', '') if lang == 'ko' else ''
        desc = desc_kr or current.get('weatherDesc', [{}])[0].get('value', '?')
        wind = current.get('windspeedKmph', '?')
        wind_dir = current.get('winddir16Point', '')
        uv = current.get('uvIndex', '?')
        precip = current.get('precipMM', '0')
        visibility = current.get('visibility', '?')

        lines = [f'🌤️ **{city}** ({country})']
        lines.append(f'  🌡️ {temp_c}°C (체감 {feels}°C) | {desc}')
        lines.append(f'  💧 습도 {humidity}% | 💨 풍속 {wind}km/h {wind_dir}')
        lines.append(f'  ☀️ UV {uv} | 🌧️ 강수 {precip}mm | 👁️ 가시거리 {visibility}km')

        forecasts = wdata.get('weather', [])[:3]
        if forecasts:
            lines.append('\n📅 **3일 예보:**')
            for day in forecasts:
                date = day.get('date', '?')
                max_t = day.get('maxtempC', '?')
                min_t = day.get('mintempC', '?')
                hourly = day.get('hourly', [])
                desc_day = ''
                if hourly:
                    mid = hourly[len(hourly) // 2]
                    desc_day = mid.get('lang_ko', [{}])[0].get('value', '') if lang == 'ko' else ''
                    desc_day = desc_day or mid.get('weatherDesc', [{}])[0].get('value', '')
                lines.append(f'  • {date}: {min_t}~{max_t}°C {desc_day}')

        return '\n'.join(lines)
    except (json.JSONDecodeError, KeyError, IndexError):
        return f'🌤️ {data[:500]}'


# ── RSS Reader ───────────────────────────────────────────────

_feeds_file = WORKSPACE_DIR / 'rss_feeds.json'


def _load_feeds() -> dict:
    if _feeds_file.exists():
        try:
            return json.loads(_feeds_file.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def _save_feeds(feeds: dict):
    _feeds_file.write_text(json.dumps(feeds, ensure_ascii=False, indent=2), encoding='utf-8')


def _parse_rss(xml_text: str) -> list:
    from xml.etree import ElementTree as ET
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for item in root.iter('item'):
        title = item.findtext('title', '').strip()
        link = item.findtext('link', '').strip()
        pub = item.findtext('pubDate', '').strip()
        desc = item.findtext('description', '').strip()
        desc = re.sub(r'<[^>]+>', '', desc)[:200]
        articles.append({'title': title, 'link': link, 'date': pub[:25], 'summary': desc})

    if not articles:
        for entry in root.iter('{http://www.w3.org/2005/Atom}entry'):
            title = ''
            t = entry.find('{http://www.w3.org/2005/Atom}title')
            if t is not None and t.text:
                title = t.text.strip()
            link = ''
            l = entry.find('{http://www.w3.org/2005/Atom}link')  # noqa: E741
            if l is not None:
                link = l.get('href', '')
            pub = ''
            p = entry.find('{http://www.w3.org/2005/Atom}published')
            if p is None:
                p = entry.find('{http://www.w3.org/2005/Atom}updated')
            if p is not None and p.text:
                pub = p.text[:25]
            summary = ''
            s = entry.find('{http://www.w3.org/2005/Atom}summary')
            if s is not None and s.text:
                summary = re.sub(r'<[^>]+>', '', s.text)[:200]
            articles.append({'title': title, 'link': link, 'date': pub, 'summary': summary})

    return articles


@register('rss_reader')
def handle_rss_reader(args: dict) -> str:
    action = args.get('action', 'fetch')

    if action == 'list':
        feeds = _load_feeds()
        if not feeds:
            return '📰 No subscribed feeds.'
        lines = ['📰 **Subscribed Feeds:**']
        for name, info in feeds.items():
            lines.append(f"  • **{name}** — {info['url']}")
        return '\n'.join(lines)

    elif action == 'subscribe':
        url = args.get('url', '')
        name = args.get('name', '')
        if not url:
            return '❌ url is required for subscribe'
        if not name:
            name = url.split('/')[2] if '/' in url else url[:30]
        feeds = _load_feeds()
        feeds[name] = {'url': url, 'added': datetime.now().isoformat()}
        _save_feeds(feeds)
        return f'📰 Subscribed: **{name}** ({url})'

    elif action == 'unsubscribe':
        name = args.get('name', '')
        feeds = _load_feeds()
        if name in feeds:
            del feeds[name]
            _save_feeds(feeds)
            return f'📰 Unsubscribed: {name}'
        return f'❌ Feed not found: {name}'

    elif action == 'fetch':
        url = args.get('url', '')
        count = args.get('count', 5)

        if not url:
            feeds = _load_feeds()
            if not feeds:
                return '❌ No URL provided and no subscribed feeds.'
            all_articles = []
            for name, info in feeds.items():
                try:
                    req = urllib.request.Request(info['url'], headers={
                        'User-Agent': 'SalmAlm/1.0 RSS Reader'})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        xml = resp.read().decode('utf-8', errors='replace')
                    articles = _parse_rss(xml)
                    for a in articles[:3]:
                        a['feed'] = name
                    all_articles.extend(articles[:3])
                except Exception:
                    pass
            if not all_articles:
                return '📰 No articles fetched from subscribed feeds.'
            lines = [f'📰 **Latest Articles ({len(all_articles)}):**']
            for a in all_articles[:count]:
                feed_tag = f" [{a.get('feed', '')}]" if a.get('feed') else ''
                lines.append(f"  📄 **{a['title']}**{feed_tag}")
                if a['date']:
                    lines.append(f"     {a['date']}")
                if a['summary']:
                    lines.append(f"     {a['summary'][:100]}")
                if a['link']:
                    lines.append(f"     🔗 {a['link']}")
            return '\n'.join(lines)

        req = urllib.request.Request(url, headers={'User-Agent': 'SalmAlm/1.0 RSS Reader'})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml = resp.read().decode('utf-8', errors='replace')
        except Exception as e:
            return f'❌ RSS fetch failed: {e}'

        articles = _parse_rss(xml)
        if not articles:
            return f'📰 No articles found in feed: {url}'

        lines = [f'📰 **Articles ({min(count, len(articles))}):**']
        for a in articles[:count]:
            lines.append(f"  📄 **{a['title']}**")
            if a['date']:
                lines.append(f"     {a['date']}")
            if a['summary']:
                lines.append(f"     {a['summary'][:100]}")
            if a['link']:
                lines.append(f"     🔗 {a['link']}")
        return '\n'.join(lines)

    return f'❌ Unknown rss_reader action: {action}'
