"""Enhanced reminder tools — natural language time parsing (KR+EN), recurring reminders.

Strengthens the existing reminder system in tools_misc.py with:
- Better Korean time parsing: "내일 3시에", "30분 후에", "매주 월요일 9시"
- English: "in 2 hours", "next friday at 3pm"
- Relative time: "3일 후", "다음주 수요일"
- Recurring: daily, weekly, monthly, custom cron-like
"""
import re
from datetime import datetime, timedelta


# Korean weekday names
_KR_WEEKDAYS = {'월요일': 0, '화요일': 1, '수요일': 2, '목요일': 3,
                '금요일': 4, '토요일': 5, '일요일': 6,
                '월': 0, '화': 1, '수': 2, '목': 3, '금': 4, '토': 5, '일': 6}

_EN_WEEKDAYS = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                'friday': 4, 'saturday': 5, 'sunday': 6,
                'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}


def parse_natural_time(text: str) -> datetime:
    """Parse natural language time expression into datetime.

    Supports Korean and English expressions:
    - "내일 오후 3시" → tomorrow 15:00
    - "30분 후" → now + 30min
    - "in 2 hours" → now + 2h
    - "매주 월요일 9시" → next Monday 9:00
    - "3일 후 오전 10시" → 3 days later 10:00
    - "다음주 수요일" → next Wednesday
    - "next friday at 3pm" → next Friday 15:00
    - "모레 저녁" → day after tomorrow 18:00
    """
    now = datetime.now()
    s = text.strip()
    s_lower = s.lower()

    # === Relative Korean: N분/시간/일/주 후 ===
    m = re.search(r'(\d+)\s*(분|시간|일|주)\s*후', s)
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        deltas = {'분': timedelta(minutes=val), '시간': timedelta(hours=val),
                  '일': timedelta(days=val), '주': timedelta(weeks=val)}
        base = now + deltas[unit]
        # Check if there's also a specific time
        hour, minute = _extract_time_kr(s)
        if hour is not None:
            base = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return base

    # === Relative English: in N minutes/hours/days/weeks ===
    m = re.search(r'in\s+(\d+)\s*(min(?:ute)?s?|hours?|days?|weeks?)', s_lower)
    if m:
        val = int(m.group(1))
        unit = m.group(2)[0]
        deltas = {'m': timedelta(minutes=val), 'h': timedelta(hours=val),
                  'd': timedelta(days=val), 'w': timedelta(weeks=val)}
        base = now + deltas.get(unit, timedelta(minutes=val))
        hour, minute = _extract_time_en(s_lower)
        if hour is not None:
            base = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return base

    # === Day reference ===
    day_offset = _parse_day_offset(s, s_lower, now)

    # === Time extraction ===
    hour_kr, min_kr = _extract_time_kr(s)
    hour_en, min_en = _extract_time_en(s_lower)
    hour = hour_kr if hour_kr is not None else hour_en
    minute = min_kr if hour_kr is not None else (min_en if hour_en is not None else 0)

    # Apply period keywords if no specific time
    if hour is None:
        if '아침' in s or 'morning' in s_lower:
            hour, minute = 8, 0
        elif '점심' in s or 'lunch' in s_lower or 'noon' in s_lower:
            hour, minute = 12, 0
        elif '저녁' in s or 'evening' in s_lower:
            hour, minute = 18, 0
        elif '밤' in s or 'night' in s_lower:
            hour, minute = 21, 0

    if day_offset is not None or hour is not None:
        target = now + timedelta(days=day_offset or 0)
        if hour is not None:
            target = target.replace(hour=hour, minute=minute or 0, second=0, microsecond=0)
        elif day_offset and day_offset > 0:
            target = target.replace(hour=9, minute=0, second=0, microsecond=0)
        return target

    # Fallback: try ISO format
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass

    raise ValueError(f'시간을 파싱할 수 없습니다: {text}')


def _parse_day_offset(s: str, s_lower: str, now: datetime) -> int:
    """Parse day offset from text."""
    if '오늘' in s or 'today' in s_lower:
        return 0
    if '내일' in s or 'tomorrow' in s_lower:
        return 1
    if '모레' in s:
        return 2
    if 'day after tomorrow' in s_lower:
        return 2

    # N일 후 (already handled above, but just in case)
    m = re.search(r'(\d+)\s*일\s*후', s)
    if m:
        return int(m.group(1))

    # 다음주 + weekday
    if '다음주' in s or '다음 주' in s or 'next week' in s_lower:
        for wd_name, wd_idx in _KR_WEEKDAYS.items():
            if wd_name in s:
                return _days_until_weekday(now, wd_idx, next_week=True)
        for wd_name, wd_idx in _EN_WEEKDAYS.items():
            if wd_name in s_lower:
                return _days_until_weekday(now, wd_idx, next_week=True)
        return 7  # just "next week" without specific day

    # "next friday", "next monday"
    m = re.search(r'next\s+(\w+)', s_lower)
    if m:
        wd_name = m.group(1)
        if wd_name in _EN_WEEKDAYS:
            return _days_until_weekday(now, _EN_WEEKDAYS[wd_name], next_week=True)

    # Just weekday name (이번주)
    for wd_name, wd_idx in _KR_WEEKDAYS.items():
        if wd_name in s and '다음' not in s:
            days = _days_until_weekday(now, wd_idx, next_week=False)
            if days > 0:
                return days

    return None


def _days_until_weekday(now: datetime, target_wd: int, next_week: bool = False) -> int:
    """Calculate days until target weekday."""
    current_wd = now.weekday()
    days_ahead = (target_wd - current_wd) % 7
    if days_ahead == 0:
        days_ahead = 7
    if next_week and days_ahead <= 7:
        # Ensure it's actually next week
        if days_ahead <= (6 - current_wd):
            days_ahead += 7
    return days_ahead


def _extract_time_kr(s: str):
    """Extract time from Korean text. Returns (hour, minute) or (None, None)."""
    # "오후 3시 30분", "오전 10시", "3시", "15시 30분"
    m = re.search(r'(오전|오후)?\s*(\d{1,2})\s*시\s*(\d{1,2})?\s*분?', s)
    if m:
        period = m.group(1)
        hour = int(m.group(2))
        minute = int(m.group(3) or 0)
        if period == '오후' and hour < 12:
            hour += 12
        elif period == '오전' and hour == 12:
            hour = 0
        elif not period and hour < 12:
            # Contextual: if 저녁/밤 mentioned, assume PM
            if '저녁' in s or '밤' in s or '오후' in s:
                hour += 12
        return hour, minute
    return None, None


def _extract_time_en(s: str):
    """Extract time from English text. Returns (hour, minute) or (None, None)."""
    # "at 3pm", "at 3:30pm", "3:00", "15:30"
    m = re.search(r'(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', s)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        period = m.group(3)
        if period == 'pm' and hour < 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
        return hour, minute
    return None, None


def parse_repeat_pattern(text: str) -> str:
    """Parse repeat pattern from text.

    Returns: 'daily', 'weekly', 'monthly', or None.
    """
    s = text.strip().lower()
    if '매일' in text or 'every day' in s or 'daily' in s:
        return 'daily'
    if '매주' in text or 'every week' in s or 'weekly' in s:
        return 'weekly'
    if '매달' in text or '매월' in text or 'every month' in s or 'monthly' in s:
        return 'monthly'
    return None
