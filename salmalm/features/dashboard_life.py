"""Life Dashboard — one-page overview of personal data from existing tools.

Aggregates finance, calendar, reminders, routines, pomodoro, notes/thoughts,
mood, and saved links into a single dashboard view (JSON + HTML + chat commands).
"""
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from salmalm.constants import BASE_DIR, KST
from salmalm import log

_DB_PATH = BASE_DIR / 'personal.db'
_DIGEST_PATH = Path.home() / '.salmalm' / 'digest.json'
_db_lock = threading.Lock()


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class LifeDashboard:
    """Aggregates data from personal tools into a unified dashboard."""

    def generate_dashboard(self) -> dict:
        return {
            'finance': self._get_finance_summary(),
            'calendar': self._get_upcoming_events(),
            'tasks': self._get_pending_reminders(),
            'habits': self._get_routine_stats(),
            'thoughts': self._get_recent_thoughts(),
            'mood': self._get_mood_trend(),
            'productivity': self._get_pomodoro_stats(),
            'links': self._get_saved_links(limit=5),
            'generated_at': datetime.now(KST).isoformat(),
        }

    # ── Finance ──────────────────────────────────────────────

    def _get_finance_summary(self) -> dict:
        now = datetime.now(KST)
        month_start = now.replace(day=1).strftime('%Y-%m-%d')
        month_end = (now.replace(day=28) + timedelta(days=4)).replace(day=1).strftime('%Y-%m-%d')
        try:
            with _db_lock:
                conn = _get_db()
                rows = conn.execute(
                    "SELECT amount, category FROM expenses WHERE date >= ? AND date < ?",
                    (month_start, month_end)
                ).fetchall()
                conn.close()
        except Exception:
            return {'total_expense': 0, 'by_category': {}, 'count': 0}

        total = 0.0
        by_cat: Dict[str, float] = {}
        for r in rows:
            amt = float(r['amount'])
            cat = r['category'] or '기타'
            total += amt
            by_cat[cat] = by_cat.get(cat, 0) + amt
        return {'total_expense': total, 'by_category': by_cat, 'count': len(rows)}

    # ── Calendar ─────────────────────────────────────────────

    def _get_upcoming_events(self) -> list:
        """Return upcoming events from calendar. Since calendar uses Google API,
        we return a placeholder that the web handler can fill via tools."""
        return []  # Filled by API integration at runtime

    # ── Reminders ────────────────────────────────────────────

    def _get_pending_reminders(self) -> list:
        try:
            reminders_path = BASE_DIR / 'reminders.json'
            if not reminders_path.exists():
                return []
            with open(reminders_path) as f:
                data = json.load(f)
            pending = []
            now = datetime.now(KST).isoformat()
            for r in data if isinstance(data, list) else data.get('reminders', []):
                if not r.get('done', False):
                    pending.append({
                        'text': r.get('text', r.get('message', '')),
                        'time': r.get('time', r.get('remind_at', '')),
                    })
            return pending[:20]
        except Exception:
            return []

    # ── Routines ─────────────────────────────────────────────

    def _get_routine_stats(self) -> dict:
        try:
            config_path = Path.home() / '.salmalm' / 'routines.json'
            if not config_path.exists():
                return {'routines': [], 'completion_rate': 0}
            with open(config_path) as f:
                routines = json.load(f)
            return {
                'routines': list(routines.keys()),
                'count': len(routines),
            }
        except Exception:
            return {'routines': [], 'count': 0}

    # ── Thoughts / Notes ─────────────────────────────────────

    def _get_recent_thoughts(self, limit: int = 5) -> list:
        try:
            with _db_lock:
                conn = _get_db()
                rows = conn.execute(
                    "SELECT id, content, tags, created_at FROM notes ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
                conn.close()
            return [{'id': r['id'], 'content': r['content'][:200],
                     'tags': r['tags'], 'created_at': r['created_at']} for r in rows]
        except Exception:
            return []

    # ── Mood ─────────────────────────────────────────────────

    def _get_mood_trend(self) -> list:
        """Mood tracking from notes with mood tags."""
        try:
            week_ago = (datetime.now(KST) - timedelta(days=7)).isoformat()
            with _db_lock:
                conn = _get_db()
                rows = conn.execute(
                    "SELECT content, tags, created_at FROM notes WHERE tags LIKE '%mood%' AND created_at >= ? ORDER BY created_at",
                    (week_ago,)
                ).fetchall()
                conn.close()
            return [{'tags': r['tags'], 'created_at': r['created_at']} for r in rows]
        except Exception:
            return []

    # ── Pomodoro ─────────────────────────────────────────────

    def _get_pomodoro_stats(self) -> dict:
        try:
            with _db_lock:
                conn = _get_db()
                week_ago = (datetime.now(KST) - timedelta(days=7)).isoformat()
                total = conn.execute(
                    "SELECT COUNT(*) as c FROM pomodoro_sessions WHERE started_at >= ?",
                    (week_ago,)
                ).fetchone()['c']
                completed = conn.execute(
                    "SELECT COUNT(*) as c FROM pomodoro_sessions WHERE started_at >= ? AND completed = 1",
                    (week_ago,)
                ).fetchone()['c']
                conn.close()
            return {'total': total, 'completed': completed,
                    'rate': round(completed / total * 100, 1) if total else 0}
        except Exception:
            return {'total': 0, 'completed': 0, 'rate': 0}

    # ── Links ────────────────────────────────────────────────

    def _get_saved_links(self, limit: int = 5) -> list:
        try:
            with _db_lock:
                conn = _get_db()
                rows = conn.execute(
                    "SELECT id, url, title, saved_at FROM saved_links ORDER BY saved_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
                conn.close()
            return [{'url': r['url'], 'title': r['title'], 'saved_at': r['saved_at']} for r in rows]
        except Exception:
            return []

    # ── Text Summary ─────────────────────────────────────────

    def text_summary(self, section: Optional[str] = None) -> str:
        data = self.generate_dashboard()
        if section == 'finance':
            return self._format_finance(data['finance'])
        if section == 'week':
            return self._format_week(data)
        return self._format_full(data)

    def _format_finance(self, fin: dict) -> str:
        lines = ['💰 **이번 달 재정 현황**']
        lines.append(f'총 지출: {fin["total_expense"]:,.0f}원 ({fin["count"]}건)')
        for cat, amt in sorted(fin.get('by_category', {}).items(), key=lambda x: -x[1]):
            lines.append(f'  • {cat}: {amt:,.0f}원')
        return '\n'.join(lines) if fin['count'] else '💰 이번 달 지출 기록이 없습니다.'

    def _format_week(self, data: dict) -> str:
        lines = ['📊 **주간 종합 리포트**', '']
        lines.append(self._format_finance(data['finance']))
        lines.append('')
        pomo = data['productivity']
        lines.append(f'🍅 포모도로: {pomo["completed"]}/{pomo["total"]} 완료 ({pomo["rate"]}%)')
        tasks = data['tasks']
        lines.append(f'📋 미완료 리마인더: {len(tasks)}개')
        lines.append(f'📝 최근 메모: {len(data["thoughts"])}개')
        return '\n'.join(lines)

    def _format_full(self, data: dict) -> str:
        lines = ['🏠 **Life Dashboard**', '']
        # Finance
        fin = data['finance']
        lines.append(f'💰 지출: {fin["total_expense"]:,.0f}원 ({fin["count"]}건)')
        # Tasks
        tasks = data['tasks']
        lines.append(f'📋 할 일: {len(tasks)}개')
        for t in tasks[:3]:
            lines.append(f'  • {t["text"][:50]}')
        # Pomodoro
        pomo = data['productivity']
        lines.append(f'🍅 포모도로: {pomo["completed"]}/{pomo["total"]} ({pomo["rate"]}%)')
        # Notes
        thoughts = data['thoughts']
        lines.append(f'📝 최근 메모: {len(thoughts)}개')
        # Links
        links = data['links']
        if links:
            lines.append(f'🔗 저장된 링크: {len(links)}개')
        return '\n'.join(lines)

    # ── HTML Dashboard ───────────────────────────────────────

    def render_html(self) -> str:
        data = self.generate_dashboard()
        fin = data['finance']
        pomo = data['productivity']
        tasks = data['tasks']
        thoughts = data['thoughts']
        links = data['links']

        task_items = ''.join(f'<li>{_esc(t["text"][:80])}</li>' for t in tasks[:10])
        thought_items = ''.join(
            f'<li>{_esc(t["content"][:120])}<br><small>{_esc(t.get("created_at",""))}</small></li>'
            for t in thoughts
        )
        link_items = ''.join(
            f'<li><a href="{_esc(l["url"])}">{_esc(l["title"] or l["url"][:40])}</a></li>'
            for l in links
        )
        cat_rows = ''.join(
            f'<tr><td>{_esc(c)}</td><td>{a:,.0f}원</td></tr>'
            for c, a in sorted(fin.get('by_category', {}).items(), key=lambda x: -x[1])
        )

        return f'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Life Dashboard</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f0f2f5;padding:16px;color:#333}}
h1{{text-align:center;margin-bottom:20px;color:#1a1a2e}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;max-width:1200px;margin:0 auto}}
.card{{background:#fff;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
.card h2{{font-size:1.1em;margin-bottom:12px;color:#16213e}}
.card ul{{list-style:none;padding:0}}.card li{{padding:4px 0;border-bottom:1px solid #f0f0f0}}
table{{width:100%;border-collapse:collapse}}td{{padding:4px 8px}}
.stat{{font-size:2em;font-weight:bold;color:#0f3460}}
.sub{{color:#888;font-size:.85em}}
a{{color:#0f3460;text-decoration:none}}
</style></head><body>
<h1>🏠 Life Dashboard</h1>
<div class="grid">
  <div class="card"><h2>💰 이번 달 지출</h2>
    <div class="stat">{fin["total_expense"]:,.0f}원</div>
    <div class="sub">{fin["count"]}건</div>
    <table>{cat_rows}</table></div>
  <div class="card"><h2>🍅 포모도로 (주간)</h2>
    <div class="stat">{pomo["completed"]}/{pomo["total"]}</div>
    <div class="sub">완료율 {pomo["rate"]}%</div></div>
  <div class="card"><h2>📋 할 일</h2>
    <ul>{task_items or '<li>없음</li>'}</ul></div>
  <div class="card"><h2>📝 최근 메모</h2>
    <ul>{thought_items or '<li>없음</li>'}</ul></div>
  <div class="card"><h2>🔗 저장 링크</h2>
    <ul>{link_items or '<li>없음</li>'}</ul></div>
</div>
<script>setTimeout(()=>location.reload(),30000)</script>
</body></html>'''


def _esc(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


# ── Proactive Digest ─────────────────────────────────────────

class ProactiveDigest:
    """Generates morning/evening digest messages."""

    def __init__(self):
        self.dashboard = LifeDashboard()
        self._config = self._load_config()

    def _load_config(self) -> dict:
        from salmalm.config_manager import ConfigManager
        return ConfigManager.load('digest', defaults={'enabled': True, 'morning': '08:00', 'evening': '20:00'})

    def morning_digest(self) -> str:
        data = self.dashboard.generate_dashboard()
        lines = ['☀️ **좋은 아침! 오늘의 브리핑**', '']
        tasks = data['tasks']
        lines.append(f'📋 할 일: {len(tasks)}개')
        for t in tasks[:5]:
            lines.append(f'  • {t["text"][:60]}')
        habits = data['habits']
        if habits.get('routines'):
            lines.append(f'🔄 루틴: {", ".join(habits["routines"][:3])}')
        return '\n'.join(lines)

    def evening_digest(self) -> str:
        data = self.dashboard.generate_dashboard()
        lines = ['🌙 **오늘 하루 정리**', '']
        fin = data['finance']
        lines.append(f'💰 오늘 지출: {fin["total_expense"]:,.0f}원')
        pomo = data['productivity']
        lines.append(f'🍅 포모도로: {pomo["completed"]}개 완료')
        return '\n'.join(lines)

    def should_send(self, hour: int) -> Optional[str]:
        if not self._config.get('enabled', True):
            return None
        morning_h = int(self._config.get('morning', '08:00').split(':')[0])
        evening_h = int(self._config.get('evening', '20:00').split(':')[0])
        if hour == morning_h:
            return 'morning'
        if hour == evening_h:
            return 'evening'
        return None


# ── Singleton ────────────────────────────────────────────────

_dashboard = LifeDashboard()
_digest = ProactiveDigest()


def get_dashboard() -> LifeDashboard:
    return _dashboard


def get_digest() -> ProactiveDigest:
    return _digest
