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
# _tg_bot imported lazily inside functions (mutable global — module-level import captures stale None)


# ── Reminder System ──────────────────────────────────────────

_reminders: list = []
_reminder_lock = threading.RLock()  # RLock: _load_reminders may be called while lock held
_reminder_thread_started = False


def _resolve_next_weekday(s_orig: str, s_stripped: str, now) -> int:
    """Resolve 'next week' + optional weekday name to day offset."""
    _WEEKDAYS = {
        "월": 0,
        "화": 1,
        "수": 2,
        "목": 3,
        "금": 4,
        "토": 5,
        "일": 6,
        "mon": 0,
        "tue": 1,
        "wed": 2,
        "thu": 3,
        "fri": 4,
        "sat": 5,
        "sun": 6,
    }
    for wd, idx in _WEEKDAYS.items():
        if wd in s_orig or wd in s_stripped:
            days_ahead = (idx - now.weekday() + 7) % 7
            return days_ahead if days_ahead > 0 else 7
    return 7


def _parse_kr_time(s_orig: str, m_kr) -> tuple:
    """Parse Korean time expression. Returns (hour, minute)."""
    hour = int(m_kr.group(2))
    minute = int(m_kr.group(3) or 0)
    period = m_kr.group(1)
    if period in ("오후", "PM") and hour < 12:
        hour += 12
    elif period in ("오전", "AM") and hour == 12:
        hour = 0
    elif not period:
        if any(k in s_orig for k in ("저녁", "밤", "오후")) and hour < 12:
            hour += 12
    return hour, minute


def _parse_en_time(m_en) -> tuple:
    """Parse English time expression. Returns (hour, minute)."""
    hour = int(m_en.group(1))
    minute = int(m_en.group(2) or 0)
    period = m_en.group(3)
    if period == "pm" and hour < 12:
        hour += 12
    elif period == "am" and hour == 12:
        hour = 0
    return hour, minute


def _parse_relative_time(s: str) -> datetime:
    """Parse time string into datetime."""
    now = datetime.now()
    s_stripped = s.strip().lower()

    m = re.match(r"^(\d+)\s*(m|min|h|hr|hour|d|day|w|week)s?$", s_stripped)
    if m:
        val = int(m.group(1))
        unit = m.group(2)[0]
        delta = {
            "m": timedelta(minutes=val),
            "h": timedelta(hours=val),
            "d": timedelta(days=val),
            "w": timedelta(weeks=val),
        }
        return now + delta.get(unit, timedelta(minutes=val))

    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass

    s_orig = s.strip()
    day_offset = 0
    hour = None
    minute = 0

    _DAY_KEYWORDS = {"오늘": 0, "내일": 1, "모레": 2, "tomorrow": 1}
    for kw, off in _DAY_KEYWORDS.items():
        if kw in s_orig or kw in s_stripped:
            day_offset = off
            break
    if "다음주" in s_orig or "next week" in s_stripped:
        day_offset = _resolve_next_weekday(s_orig, s_stripped, now)

    _TIME_KEYWORDS = [
        (("아침", "morning"), 8),
        (("점심", "noon", "lunch"), 12),
        (("저녁", "evening"), 18),
        (("밤", "night"), 21),
    ]
    for keywords, h in _TIME_KEYWORDS:
        if any(k in s_orig or k in s_stripped for k in keywords):
            hour = h
            break

    m_kr = re.search(r"(오전|오후|AM|PM)?\s*(\d{1,2})\s*시\s*(\d{1,2})?\s*분?", s_orig)
    if m_kr:
        hour, minute = _parse_kr_time(s_orig, m_kr)

    m_en = re.search(r"(\d{1,2}):?(\d{2})?\s*(am|pm)?", s_stripped)
    if m_en and hour is None:
        hour, minute = _parse_en_time(m_en)

    if day_offset > 0 or hour is not None:
        target = now + timedelta(days=day_offset)
        if hour is not None:
            target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        elif day_offset > 0:
            target = target.replace(hour=9, minute=0, second=0, microsecond=0)
        return target

    raise ValueError(f"Cannot parse time: {s}")


def _reminders_file() -> Path:
    """Reminders file."""
    return WORKSPACE_DIR / "reminders.json"


def _load_reminders():
    """Load reminders from disk — in-place mutation to preserve module-level references."""
    fp = _reminders_file()
    loaded: list = []
    if fp.exists():
        try:
            loaded = json.loads(fp.read_text(encoding="utf-8"))
            if not isinstance(loaded, list):
                loaded = []
        except Exception:
            loaded = []
    _reminders.clear()
    _reminders.extend(loaded)


def _save_reminders():
    """Atomic save — write to temp file then replace (prevents corrupt state on crash)."""
    import tempfile, os as _os
    fp = _reminders_file()
    data = json.dumps(_reminders, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=fp.parent, prefix=".reminders_", suffix=".tmp", delete=False
        ) as tmp:
            tmp.write(data)
            tmp.flush()
            _os.fsync(tmp.fileno())
            tmp_path = tmp.name
        _os.replace(tmp_path, fp)
    except Exception as e:
        log.warning(f"[REMINDERS] Save failed: {e}")


def _send_notification_impl(
    message: str, title: str = "", channel: str = "all", url: str = "", priority: str = "normal"
):
    """Send notification via available channels."""
    results = []

    if channel in ("telegram", "all"):
        try:
            from salmalm.core import _tg_bot

            tg = _tg_bot
            if tg:
                owner = vault.get("telegram_owner_id") or ""
                if owner:
                    text = f"🔔 {title}\n{message}" if title else f"🔔 {message}"
                    tg_url = f"https://api.telegram.org/bot{vault.get('telegram_bot_token')}/sendMessage"
                    body = json.dumps({"chat_id": owner, "text": text}).encode()
                    req = urllib.request.Request(
                        tg_url, data=body, headers={"Content-Type": "application/json"}, method="POST"
                    )
                    urllib.request.urlopen(req, timeout=10)
                    results.append("telegram: ✅")
                else:
                    results.append("telegram: ⚠️ no owner_id")
            else:
                results.append("telegram: ⚠️ not configured")
        except Exception as e:
            results.append(f"telegram: ❌ {e}")

    if channel in ("desktop", "all"):
        try:
            if sys.platform == "darwin":
                # Escape quotes to prevent AppleScript injection
                safe_msg = message.replace("\\", "\\\\").replace('"', '\\"')
                safe_title = (title or "SalmAlm").replace("\\", "\\\\").replace('"', '\\"')
                subprocess.run(
                    ["osascript", "-e", f'display notification "{safe_msg}" with title "{safe_title}"'],
                    timeout=5,
                    capture_output=True,
                )
                results.append("desktop: ✅")
            elif sys.platform == "linux":
                subprocess.run(["notify-send", title or "SalmAlm", message], timeout=5, capture_output=True)
                results.append("desktop: ✅")
            elif sys.platform == "win32":
                # Escape PowerShell string injection
                ps_title = (title or "SalmAlm").replace('"', '`"').replace("'", "`'")
                ps_msg = message.replace('"', '`"').replace("'", "`'")
                ps_cmd = f'''
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
                $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
                $template.GetElementsByTagName("text")[0].AppendChild($template.CreateTextNode("{ps_title}")) | Out-Null
                $template.GetElementsByTagName("text")[1].AppendChild($template.CreateTextNode("{ps_msg}")) | Out-Null
                $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
                [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("SalmAlm").Show($toast)
                '''
                subprocess.run(["powershell", "-Command", ps_cmd], timeout=10, capture_output=True)
                results.append("desktop: ✅")
            else:
                results.append("desktop: ⚠️ unsupported platform")
        except FileNotFoundError:
            results.append("desktop: ⚠️ notification tool not found")
        except Exception as e:
            results.append(f"desktop: ❌ {e}")

    if channel == "webhook" and url:
        try:
            from salmalm.tools.tools_common import _is_private_url_follow_redirects
            blocked, reason, _ = _is_private_url_follow_redirects(url)
            if blocked:
                results.append(f"webhook: ❌ Blocked (SSRF): {reason}")
                return "\n".join(results) if results else "⚠️ Blocked"
            body = json.dumps(
                {
                    "title": title or "SalmAlm",
                    "message": message,
                    "priority": priority,
                    "timestamp": datetime.now().isoformat(),
                }
            ).encode()
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=10)
            results.append("webhook: ✅")
        except Exception as e:
            results.append(f"webhook: ❌ {e}")

    return results


def _reminder_check_loop():
    """Reminder check loop."""
    while True:
        time.sleep(30)
        now = datetime.now()
        with _reminder_lock:
            due = []
            remaining = []
            for r in _reminders:
                try:
                    trigger_time = datetime.fromisoformat(r["time"])
                    if trigger_time <= now:
                        due.append(r)
                    else:
                        remaining.append(r)
                except Exception as e:  # noqa: broad-except
                    remaining.append(r)
            if due:
                _reminders.clear()
                _reminders.extend(remaining)
                _save_reminders()
        for r in due:
            try:
                _send_notification_impl(f"⏰ Reminder: {r['message']}", title="Reminder", channel="all")
            except Exception as e:
                log.error(f"Reminder notification failed: {e}")
            if r.get("repeat"):
                try:
                    repeat = r["repeat"]
                    deltas = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1), "monthly": timedelta(days=30)}
                    if repeat in deltas:
                        r["time"] = (datetime.fromisoformat(r["time"]) + deltas[repeat]).isoformat()
                        with _reminder_lock:
                            _reminders.append(r)
                            _save_reminders()
                except Exception as e:  # noqa: broad-except
                    log.debug(f"Suppressed: {e}")


def _ensure_reminder_thread():
    """Ensure reminder thread."""
    global _reminder_thread_started
    if not _reminder_thread_started:
        _reminder_thread_started = True
        _load_reminders()
        t = threading.Thread(target=_reminder_check_loop, daemon=True)
        t.start()


@register("reminder")
def handle_reminder(args: dict) -> str:
    """Handle reminder."""
    _ensure_reminder_thread()
    action = args.get("action", "set")

    if action == "set":
        message = args.get("message", "")
        time_str = args.get("time", "")
        if not message or not time_str:
            return "❌ message and time are required"
        trigger_time = _parse_relative_time(time_str)
        reminder = {
            "id": secrets.token_hex(4),
            "message": message,
            "time": trigger_time.isoformat(),
            "repeat": args.get("repeat"),
            "created": datetime.now().isoformat(),
        }
        with _reminder_lock:
            _reminders.append(reminder)
            _save_reminders()
        return f"⏰ Reminder set: **{message}** at {trigger_time.strftime('%Y-%m-%d %H:%M')}" + (
            f" (repeat: {args['repeat']})" if args.get("repeat") else ""
        )

    elif action == "list":
        _load_reminders()
        if not _reminders:
            return "⏰ No active reminders."
        lines = [f"⏰ **Active Reminders ({len(_reminders)}):**"]
        for r in sorted(_reminders, key=lambda x: x.get("time", "")):
            repeat_str = f" 🔁{r['repeat']}" if r.get("repeat") else ""
            lines.append(f"  • [{r['id']}] **{r['message']}** — {r['time'][:16]}{repeat_str}")
        return "\n".join(lines)

    elif action == "delete":
        rid = args.get("reminder_id", "")
        if not rid:
            return "❌ reminder_id is required"
        with _reminder_lock:
            before = len(_reminders)
            _reminders[:] = [r for r in _reminders if r.get("id") != rid]
            _save_reminders()
            if len(_reminders) < before:
                return f"⏰ Reminder deleted: {rid}"
        return f"❌ Reminder not found: {rid}"

    return f"❌ Unknown reminder action: {action}"


# ── Workflow Engine ──────────────────────────────────────────

_workflows_file = WORKSPACE_DIR / "workflows.json"


def _load_workflows() -> dict:
    """Load workflows."""
    if _workflows_file.exists():
        try:
            return json.loads(_workflows_file.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")
    return {}


def _save_workflows(wf: dict):
    """Save workflows."""
    _workflows_file.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")


@register("workflow")
def handle_workflow(args: dict) -> str:
    """Handle workflow."""
    from salmalm.tools.tool_registry import execute_tool

    action = args.get("action", "list")

    if action == "list":
        wf = _load_workflows()
        if not wf:
            return "🔄 No saved workflows."
        lines = ["🔄 **Saved Workflows:**"]
        for name, data in wf.items():
            steps = data.get("steps", [])
            lines.append(f"  • **{name}** — {len(steps)} steps")
        return "\n".join(lines)

    elif action == "save":
        name = args.get("name", "")
        steps = args.get("steps", [])
        if not name or not steps:
            return "❌ name and steps are required for save"
        wf = _load_workflows()
        wf[name] = {"steps": steps, "created": datetime.now().isoformat()}
        _save_workflows(wf)
        return f"🔄 Workflow saved: **{name}** ({len(steps)} steps)"

    elif action == "delete":
        name = args.get("name", "")
        wf = _load_workflows()
        if name in wf:
            del wf[name]
            _save_workflows(wf)
            return f"🔄 Workflow deleted: {name}"
        return f"❌ Workflow not found: {name}"

    elif action == "run":
        name = args.get("name", "")
        steps = args.get("steps", [])
        variables = args.get("variables", {})
        if name and not steps:
            wf = _load_workflows()
            if name not in wf:
                return f"❌ Workflow not found: {name}"
            steps = wf[name].get("steps", [])
        if not steps:
            return "❌ No steps defined"
        context = dict(variables)
        results = []
        for i, step in enumerate(steps):
            tool_name = step.get("tool", "")
            step_args = dict(step.get("args", {}))
            for k, v in step_args.items():
                if isinstance(v, str) and v.startswith("$"):
                    var_name = v[1:]
                    if var_name in context:
                        step_args[k] = context[var_name]
            result = execute_tool(tool_name, step_args)
            results.append(f"Step {i + 1} ({tool_name}): {result[:200]}")
            output_var = step.get("output_var", f"step_{i + 1}")
            context[output_var] = result
        return "🔄 **Workflow Complete:**\n" + "\n".join(results)

    return f"❌ Unknown workflow action: {action}"


# ── File Index ───────────────────────────────────────────────

_file_index: dict = {}
_file_index_lock = threading.Lock()


@register("file_index")
def handle_file_index(args: dict) -> str:
    """Handle file index."""
    action = args.get("action", "search")

    if action == "index" or action == "status":
        target_dir = Path(args.get("path", str(WORKSPACE_DIR))).resolve()
        workspace = Path(WORKSPACE_DIR).resolve()
        try:
            target_dir.relative_to(workspace)
        except ValueError:
            try:
                target_dir.relative_to(Path.home())
            except ValueError:
                return "❌ Access denied: path outside allowed directories"
        if not target_dir.exists():
            return f"❌ Directory not found: {target_dir}"
        exts = args.get("extensions", "py,md,txt,json,yaml,yml,toml,cfg,ini,sh,bat,js,ts,html,css")
        ext_set = set(f".{e.strip()}" for e in exts.split(","))
        count = 0
        with _file_index_lock:
            for fp in target_dir.rglob("*"):
                if fp.is_file() and fp.suffix in ext_set and fp.stat().st_size < 500_000:
                    try:
                        if any(p.startswith(".") for p in fp.relative_to(target_dir).parts[:-1]):
                            continue
                        content = fp.read_text(encoding="utf-8", errors="replace")[:50000]
                        words = set(re.findall(r"\w+", content.lower()))
                        _file_index[str(fp)] = {
                            "mtime": fp.stat().st_mtime,
                            "words": words,
                            "size": fp.stat().st_size,
                            "preview": content[:200],
                        }
                        count += 1
                    except Exception as e:  # noqa: broad-except
                        log.debug(f"Suppressed: {e}")
        if action == "status":
            return f"📂 File index: {len(_file_index)} files indexed"
        return f"📂 Indexed {count} files from {target_dir}"

    elif action == "search":
        query = args.get("query", "")
        if not query:
            return "❌ query is required"
        limit = args.get("limit", 10)
        if not _file_index:
            handle_file_index({"action": "index"})
        query_words = set(re.findall(r"\w+", query.lower()))
        if not query_words:
            return "❌ No searchable terms in query"
        scored = []
        with _file_index_lock:
            for path, info in _file_index.items():
                overlap = len(query_words & info["words"])
                if overlap > 0:
                    score = overlap / len(query_words)
                    scored.append((score, path, info))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:limit]
        if not results:
            return f"🔍 No files matching: {query}"
        lines = [f'🔍 **File Search: "{query}" ({len(results)} results):**']
        for score, path, info in results:
            rel = Path(path).relative_to(WORKSPACE_DIR) if path.startswith(str(WORKSPACE_DIR)) else Path(path)
            lines.append(f"  📄 **{rel}** (score: {score:.1%}, {info['size']}B)")
            lines.append(f"     {info['preview'][:100]}...")
        return "\n".join(lines)

    return f"❌ Unknown file_index action: {action}"


@register("notification")
def handle_notification(args: dict) -> str:
    """Handle notification."""
    message = args.get("message", "")
    if not message:
        return "❌ message is required"
    title = args.get("title", "")
    channel = args.get("channel", "all")
    url = args.get("url", "")
    priority = args.get("priority", "normal")
    results = _send_notification_impl(message, title, channel, url, priority)
    return "🔔 Notification sent:\n  " + "\n  ".join(results)


@register("weather")
def handle_weather(args: dict) -> str:
    """Handle weather."""
    location = args.get("location", "")
    if not location:
        return "❌ location is required"
    fmt = args.get("format", "full")
    lang = args.get("lang", "ko")

    import urllib.parse

    loc_encoded = urllib.parse.quote(location)

    if fmt == "short":
        url = f"https://wttr.in/{loc_encoded}?format=%l:+%c+%t+%h+%w&lang={lang}"
    elif fmt == "forecast":
        url = f"https://wttr.in/{loc_encoded}?format=3&lang={lang}"
    else:
        url = f"https://wttr.in/{loc_encoded}?format=j1&lang={lang}"

    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0", "Accept-Language": lang})
    data = None
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8", errors="replace")
    except Exception as _wttr_err:
        # wttr.in unavailable — fallback to Open-Meteo (no API key required)
        try:
            # Korean city → lat/lon table (common cities, avoids geocoding failures with Korean text)
            _KR_CITIES = {
                "서울": (37.5665, 126.9780, "서울"), "seoul": (37.5665, 126.9780, "Seoul"),
                "부산": (35.1796, 129.0756, "부산"), "busan": (35.1796, 129.0756, "Busan"),
                "인천": (37.4563, 126.7052, "인천"), "incheon": (37.4563, 126.7052, "Incheon"),
                "대구": (35.8714, 128.6014, "대구"), "대전": (36.3504, 127.3845, "대전"),
                "광주": (35.1595, 126.8526, "광주"), "울산": (35.5384, 129.3114, "울산"),
                "수원": (37.2636, 127.0286, "수원"), "용인": (37.2411, 127.1776, "용인"),
                "성남": (37.4201, 127.1267, "성남"), "안양": (37.3942, 126.9568, "안양"),
                "안산": (37.3219, 126.8309, "안산"), "고양": (37.6564, 126.8350, "고양"),
                "의정부": (37.7381, 127.0338, "의정부"), "남양주": (37.6360, 127.2165, "남양주"),
                "화성": (37.1995, 126.8312, "화성"), "평택": (36.9921, 127.1126, "평택"),
                "제주": (33.4996, 126.5312, "제주"), "수지": (37.3220, 127.0972, "수지(용인)"),
                "분당": (37.3825, 127.1194, "분당(성남)"), "판교": (37.3952, 127.1101, "판교(성남)"),
                "세종": (36.4800, 127.2890, "세종"),
            }
            _res = []
            _loc_lower = location.lower().replace("시", "").replace("구", "").replace("동", "").replace("군", "").replace("읍", "").strip()
            # Try known cities first
            for _ckey, (_clat, _clon, _cname) in _KR_CITIES.items():
                if _ckey in location or _ckey in _loc_lower:
                    _res = [{"latitude": _clat, "longitude": _clon, "name": _cname, "country_code": "KR"}]
                    break
            # Fallback: Open-Meteo geocoding with ASCII tokens
            if not _res:
                _ascii_tokens = [t for t in location.replace(",", " ").split() if t.isascii() and len(t) > 2]
                for _tok in _ascii_tokens:
                    _tok_enc = urllib.parse.quote(_tok)
                    _geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={_tok_enc}&count=5&language=ko&format=json"
                    try:
                        with urllib.request.urlopen(_geo_url, timeout=5) as _gr:
                            _gd = json.loads(_gr.read())
                        _kr = [r for r in _gd.get("results", []) if r.get("country_code") == "KR"]
                        if _kr:
                            _res = _kr
                            break
                        elif _gd.get("results") and not _res:
                            _res = _gd["results"]
                    except Exception:
                        continue
            if not _res:
                return f"❌ 위치를 찾을 수 없소: {location}"
            _lat, _lon, _city = _res[0]["latitude"], _res[0]["longitude"], _res[0].get("name", location)
            _murl = (f"https://api.open-meteo.com/v1/forecast?latitude={_lat}&longitude={_lon}"
                     "&current_weather=true&hourly=relativehumidity_2m,precipitation_probability"
                     "&forecast_days=1&timezone=Asia/Seoul")
            with urllib.request.urlopen(_murl, timeout=5) as _mr:
                _md = json.loads(_mr.read())
            _cw = _md.get("current_weather", {})
            _temp = _cw.get("temperature", "?")
            _wind = _cw.get("windspeed", "?")
            _wcode = {0:"맑음",1:"대체로 맑음",2:"부분적으로 흐림",3:"흐림",45:"안개",48:"안개",51:"이슬비",53:"이슬비",55:"이슬비",
                      61:"비",63:"비",65:"비",71:"눈",73:"눈",75:"눈",80:"소나기",81:"소나기",82:"폭우",
                      95:"뇌우",96:"뇌우",99:"뇌우"}
            _desc = _wcode.get(int(_cw.get("weathercode", 0)), "알 수 없음")
            _hourly = _md.get("hourly", {})
            _humid = _hourly.get("relativehumidity_2m", [None])[0]
            _precip = _hourly.get("precipitation_probability", [None])[0]
            lines = [f"🌤️ **{_city}** (Open-Meteo)"]
            lines.append(f"  🌡️ {_temp}°C | {_desc}")
            lines.append(f"  💨 풍속 {_wind}km/h" + (f" | 💧 습도 {_humid}%" if _humid else "") + (f" | 🌧️ 강수확률 {_precip}%" if _precip is not None else ""))
            return "\n".join(lines)
        except Exception as _om_err:
            return f"❌ 날씨 조회 실패: wttr.in={_wttr_err}, open-meteo={_om_err}"

    if fmt in ("short", "forecast"):
        return f"🌤️ {data.strip()}"

    try:
        wdata = json.loads(data)
        current = wdata.get("current_condition", [{}])[0]
        area = wdata.get("nearest_area", [{}])[0]
        city = area.get("areaName", [{}])[0].get("value", location)
        country = area.get("country", [{}])[0].get("value", "")

        temp_c = current.get("temp_C", "?")
        feels = current.get("FeelsLikeC", "?")
        humidity = current.get("humidity", "?")
        desc_kr = current.get("lang_ko", [{}])[0].get("value", "") if lang == "ko" else ""
        desc = desc_kr or current.get("weatherDesc", [{}])[0].get("value", "?")
        wind = current.get("windspeedKmph", "?")
        wind_dir = current.get("winddir16Point", "")
        uv = current.get("uvIndex", "?")
        precip = current.get("precipMM", "0")
        visibility = current.get("visibility", "?")

        lines = [f"🌤️ **{city}** ({country})"]
        lines.append(f"  🌡️ {temp_c}°C (체감 {feels}°C) | {desc}")
        lines.append(f"  💧 습도 {humidity}% | 💨 풍속 {wind}km/h {wind_dir}")
        lines.append(f"  ☀️ UV {uv} | 🌧️ 강수 {precip}mm | 👁️ 가시거리 {visibility}km")

        forecasts = wdata.get("weather", [])[:3]
        if forecasts:
            lines.append("\n📅 **3일 예보:**")
            for day in forecasts:
                date = day.get("date", "?")
                max_t = day.get("maxtempC", "?")
                min_t = day.get("mintempC", "?")
                hourly = day.get("hourly", [])
                desc_day = ""
                if hourly:
                    mid = hourly[len(hourly) // 2]
                    desc_day = mid.get("lang_ko", [{}])[0].get("value", "") if lang == "ko" else ""
                    desc_day = desc_day or mid.get("weatherDesc", [{}])[0].get("value", "")
                lines.append(f"  • {date}: {min_t}~{max_t}°C {desc_day}")

        return "\n".join(lines)
    except (json.JSONDecodeError, KeyError, IndexError):
        return f"🌤️ {data[:500]}"


# ── RSS Reader ───────────────────────────────────────────────

_feeds_file = WORKSPACE_DIR / "rss_feeds.json"


def _load_feeds() -> dict:
    """Load feeds."""
    if _feeds_file.exists():
        try:
            return json.loads(_feeds_file.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")
    return {}


def _save_feeds(feeds: dict):
    """Save feeds."""
    _feeds_file.write_text(json.dumps(feeds, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_rss(xml_text: str) -> list:
    """Parse rss."""
    from xml.etree import ElementTree as ET

    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub = item.findtext("pubDate", "").strip()
        desc = item.findtext("description", "").strip()
        desc = re.sub(r"<[^>]+>", "", desc)[:200]
        articles.append({"title": title, "link": link, "date": pub[:25], "summary": desc})

    if not articles:
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = ""
            t = entry.find("{http://www.w3.org/2005/Atom}title")
            if t is not None and t.text:
                title = t.text.strip()
            link = ""
            l = entry.find("{http://www.w3.org/2005/Atom}link")  # noqa: E741
            if l is not None:
                link = l.get("href", "")
            pub = ""
            p = entry.find("{http://www.w3.org/2005/Atom}published")
            if p is None:
                p = entry.find("{http://www.w3.org/2005/Atom}updated")
            if p is not None and p.text:
                pub = p.text[:25]
            summary = ""
            s = entry.find("{http://www.w3.org/2005/Atom}summary")
            if s is not None and s.text:
                summary = re.sub(r"<[^>]+>", "", s.text)[:200]
            articles.append({"title": title, "link": link, "date": pub, "summary": summary})

    return articles


def _rss_list(args: dict) -> str:
    """List subscribed RSS feeds."""
    feeds = _load_feeds()
    if not feeds:
        return "📰 No subscribed feeds."
    lines = ["📰 **Subscribed Feeds:**"]
    for name, info in feeds.items():
        lines.append(f"  • **{name}** — {info['url']}")
    return "\n".join(lines)


def _rss_subscribe(args: dict) -> str:
    """Subscribe to an RSS feed."""
    url = args.get("url", "")
    name = args.get("name", "")
    if not url:
        return "❌ url is required for subscribe"
    from salmalm.tools.tools_common import _is_private_url_follow_redirects

    blocked, reason, _ = _is_private_url_follow_redirects(url)
    if blocked:
        return f"❌ Blocked URL (SSRF protection): {reason}"
    if not name:
        name = url.split("/")[2] if "/" in url else url[:30]
    feeds = _load_feeds()
    feeds[name] = {"url": url, "added": datetime.now().isoformat()}
    _save_feeds(feeds)
    return f"📰 Subscribed: **{name}** ({url})"


def _rss_unsubscribe(args: dict) -> str:
    """Unsubscribe from an RSS feed."""
    name = args.get("name", "")
    feeds = _load_feeds()
    if name in feeds:
        del feeds[name]
        _save_feeds(feeds)
        return f"📰 Unsubscribed: {name}"
    return f"❌ Feed not found: {name}"


_RSS_DISPATCH = {
    "list": _rss_list,
    "subscribe": _rss_subscribe,
    "unsubscribe": _rss_unsubscribe,
}


def _rss_fetch(args: dict) -> str:
    """Fetch RSS articles from URL or subscribed feeds."""
    url = args.get("url", "")
    count = args.get("count", 5)
    if not url:
        return _rss_fetch_all_feeds(count)
    from salmalm.tools.tools_common import _is_private_url_follow_redirects
    blocked, reason, _ = _is_private_url_follow_redirects(url)
    if blocked:
        return f"❌ Blocked URL (SSRF protection): {reason}"
    req = urllib.request.Request(url, headers={"User-Agent": "SalmAlm/1.0 RSS Reader"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"❌ RSS fetch failed: {e}"
    articles = _parse_rss(xml)
    if not articles:
        return f"📰 No articles found in feed: {url}"
    return _format_articles(articles[:count])


def _rss_fetch_all_feeds(count: int) -> str:
    """Fetch articles from all subscribed feeds."""
    from salmalm.tools.tools_common import _is_private_url_follow_redirects

    feeds = _load_feeds()
    if not feeds:
        return "❌ No URL provided and no subscribed feeds."
    all_articles = []
    for name, info in feeds.items():
        try:
            feed_url = info.get("url", "")
            blocked, reason, _ = _is_private_url_follow_redirects(feed_url)
            if blocked:
                log.warning(f"[RSS] Blocked subscribed feed '{name}': {reason}")
                continue
            req = urllib.request.Request(feed_url, headers={"User-Agent": "SalmAlm/1.0 RSS Reader"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml = resp.read().decode("utf-8", errors="replace")
            articles = _parse_rss(xml)
            for a in articles[:3]:
                a["feed"] = name
            all_articles.extend(articles[:3])
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")
    if not all_articles:
        return "📰 No articles fetched from subscribed feeds."
    return _format_articles(all_articles[:count])


def _format_articles(articles: list) -> str:
    """Format articles list for display."""
    lines = [f"📰 **Articles ({len(articles)}):**"]
    for a in articles:
        feed_tag = f" [{a.get('feed', '')}]" if a.get("feed") else ""
        lines.append(f"  📄 **{a['title']}**{feed_tag}")
        if a.get("date"):
            lines.append(f"     {a['date']}")
        if a.get("summary"):
            lines.append(f"     {a['summary'][:100]}")
        if a.get("link"):
            lines.append(f"     🔗 {a['link']}")
    return "\n".join(lines)


@register("rss_reader")
def handle_rss_reader(args: dict) -> str:
    """Handle rss reader."""
    action = args.get("action", "fetch")
    handler = _RSS_DISPATCH.get(action)
    if handler:
        return handler(args)

    if action == "fetch":
        return _rss_fetch(args)
    return f"❌ Unknown rss_reader action: {action}"
