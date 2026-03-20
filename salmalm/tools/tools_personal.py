"""Personal assistant tools — notes, expenses, saved links, pomodoro, routines, briefing.

All data stored in SQLite DB at BASE_DIR/personal.db.
Pure stdlib only.
"""

import json
import re
import sqlite3
import threading
import time
import secrets
import urllib.request
from datetime import datetime, timedelta
from salmalm.tools.tool_registry import register
from salmalm.constants import KST, BASE_DIR, DATA_DIR
from salmalm.security.crypto import log
from salmalm.utils.db import connect as _connect_db

# ── Database ─────────────────────────────────────────────────

_DB_PATH = BASE_DIR / "personal.db"
_db_lock = threading.Lock()


def _get_db() -> sqlite3.Connection:
    """Get db."""
    return _connect_db(_DB_PATH, wal=True, row_factory=True, check_same_thread=False)


def _init_db():
    """Init db."""
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id TEXT PRIMARY KEY,
            amount REAL NOT NULL,
            category TEXT DEFAULT '기타',
            description TEXT DEFAULT '',
            date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS saved_links (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            content TEXT DEFAULT '',
            saved_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pomodoro_sessions (
            id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            type TEXT DEFAULT 'focus',
            completed INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()


_init_db()


# ── Notes (Personal Knowledge Base) ─────────────────────────


@register("note")
def handle_note(args: dict) -> str:
    """Personal notes / knowledge base."""
    action = args.get("action", "save")

    if action == "save":
        content = args.get("content", "")
        if not content:
            return "❌ content is required"
        tags = args.get("tags", "")
        now = datetime.now(KST).isoformat()
        nid = secrets.token_hex(4)
        with _db_lock:
            conn = _get_db()
            conn.execute(
                "INSERT INTO notes (id, content, tags, created_at, updated_at) VALUES (?,?,?,?,?)",
                (nid, content, tags, now, now),
            )
            conn.commit()
            conn.close()
        tag_str = f" 🏷️ {tags}" if tags else ""
        return f"📝 메모 저장됨 [{nid}]{tag_str}\n{content[:100]}"

    elif action == "search":
        query = args.get("query", "")
        if not query:
            return "❌ query is required"
        with _db_lock:
            conn = _get_db()
            rows = conn.execute(
                "SELECT id, content, tags, created_at FROM notes WHERE content LIKE ? OR tags LIKE ? ORDER BY created_at DESC LIMIT 10",
                (f"%{query}%", f"%{query}%"),
            ).fetchall()
            conn.close()
        if not rows:
            return f'🔍 "{query}" 관련 메모가 없습니다.'
        lines = [f'🔍 **메모 검색: "{query}" ({len(rows)}건)**']
        for r in rows:
            tag_str = f" 🏷️{r['tags']}" if r["tags"] else ""
            lines.append(f"  📝 [{r['id']}] {r['content'][:80]}{tag_str}")
            lines.append(f"     {r['created_at'][:16]}")
        return "\n".join(lines)

    elif action == "list":
        count = int(args.get("count", 10))
        with _db_lock:
            conn = _get_db()
            rows = conn.execute(
                "SELECT id, content, tags, created_at FROM notes ORDER BY created_at DESC LIMIT ?", (count,)
            ).fetchall()
            conn.close()
        if not rows:
            return "📝 No notes yet."
        lines = [f"📝 **최근 메모 ({len(rows)}건)**"]
        for r in rows:
            tag_str = f" 🏷️{r['tags']}" if r["tags"] else ""
            lines.append(f"  📝 [{r['id']}] {r['content'][:80]}{tag_str}")
        return "\n".join(lines)

    elif action == "delete":
        note_id = args.get("note_id", "")
        if not note_id:
            return "❌ note_id is required"
        with _db_lock:
            conn = _get_db()
            cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            conn.commit()
            conn.close()
        if cur.rowcount:
            return f"📝 메모 삭제됨: {note_id}"
        return f"❌ 메모를 찾을 수 없습니다: {note_id}"

    return f"❌ Unknown note action: {action}"


# ── Expense Tracker ──────────────────────────────────────────

_EXPENSE_CATEGORIES = {
    "식비": [
        "점심",
        "저녁",
        "아침",
        "식사",
        "밥",
        "커피",
        "음식",
        "카페",
        "치킨",
        "피자",
        "배달",
        "food",
        "lunch",
        "dinner",
        "coffee",
    ],
    "교통": ["택시", "버스", "지하철", "주유", "기름", "교통", "taxi", "bus", "subway", "gas", "transport"],
    "쇼핑": ["옷", "신발", "쇼핑", "구매", "shopping", "clothes"],
    "구독": ["구독", "넷플릭스", "유튜브", "멜론", "netflix", "youtube", "spotify", "subscription"],
    "의료": ["병원", "약국", "약", "치료", "hospital", "pharmacy", "medical"],
    "생활": ["마트", "편의점", "생활", "세탁", "mart", "grocery"],
}


def _auto_categorize(description: str) -> str:
    """Auto categorize."""
    desc_lower = description.lower()
    for category, keywords in _EXPENSE_CATEGORIES.items():
        for kw in keywords:
            if kw in desc_lower:
                return category
    return "기타"


@register("expense")
def handle_expense(args: dict) -> str:
    """Expense tracker."""
    action = args.get("action", "add")

    if action == "add":
        amount = args.get("amount")
        if amount is None:
            return "❌ amount is required"
        try:
            amount = float(str(amount).replace(",", "").replace("원", ""))
        except ValueError:
            return "❌ Invalid amount"
        description = args.get("description", "")
        category = args.get("category", "") or _auto_categorize(description)
        date = args.get("date", datetime.now(KST).strftime("%Y-%m-%d"))
        eid = secrets.token_hex(4)
        now = datetime.now(KST).isoformat()
        with _db_lock:
            conn = _get_db()
            conn.execute(
                "INSERT INTO expenses (id, amount, category, description, date, created_at) VALUES (?,?,?,?,?,?)",
                (eid, amount, category, description, date, now),
            )
            conn.commit()
            conn.close()
        return f"💰 지출 기록: {description} {amount:,.0f}원 ({category}) [{date}]"

    elif action == "today":
        today = datetime.now(KST).strftime("%Y-%m-%d")
        with _db_lock:
            conn = _get_db()
            rows = conn.execute(
                "SELECT id, amount, category, description FROM expenses WHERE date = ? ORDER BY created_at", (today,)
            ).fetchall()
            total = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE date = ?", (today,)).fetchone()[0]
            conn.close()
        if not rows:
            return f"💰 No expenses today ({today})."
        lines = [f"💰 **오늘 지출 ({today})**"]
        for r in rows:
            lines.append(f"  • {r['description'] or '?'} — {r['amount']:,.0f}원 ({r['category']})")
        lines.append(f"\n  **합계: {total:,.0f}원**")
        return "\n".join(lines)

    elif action == "month":
        month = args.get("month", datetime.now(KST).strftime("%Y-%m"))
        with _db_lock:
            conn = _get_db()
            rows = conn.execute(
                "SELECT category, SUM(amount) as total, COUNT(*) as cnt FROM expenses WHERE date LIKE ? GROUP BY category ORDER BY total DESC",
                (f"{month}%",),
            ).fetchall()
            grand_total = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE date LIKE ?", (f"{month}%",)
            ).fetchone()[0]
            conn.close()
        if not rows:
            return f"💰 No expenses in {month}."
        lines = [f"💰 **{month} 월별 요약**"]
        for r in rows:
            pct = (r["total"] / grand_total * 100) if grand_total else 0
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"  {r['category']}: {r['total']:,.0f}원 ({r['cnt']}건) {pct:.0f}%")
            lines.append(f"  {bar}")
        lines.append(f"\n  **총 합계: {grand_total:,.0f}원**")
        return "\n".join(lines)

    elif action == "delete":
        expense_id = args.get("expense_id", "")
        if not expense_id:
            return "❌ expense_id is required"
        with _db_lock:
            conn = _get_db()
            cur = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            conn.commit()
            conn.close()
        if cur.rowcount:
            return f"💰 지출 삭제됨: {expense_id}"
        return f"❌ 지출을 찾을 수 없습니다: {expense_id}"

    return f"❌ Unknown expense action: {action}"


# ── Saved Links (Read Later) ────────────────────────────────


@register("save_link")
def _save_link_impl(args: dict) -> str:
    """Save a link with auto-fetched title."""
    url = args.get("url", "")
    if not url:
        return "❌ url is required"
    title = args.get("title", "")
    summary, tags, content = args.get("summary", ""), args.get("tags", ""), ""
    if not title:
        try:
            from salmalm.tools.tools_common import _is_private_url_follow_redirects
            blocked, reason, _ = _is_private_url_follow_redirects(url)
            if blocked:
                return f"❌ Blocked URL (SSRF protection): {reason}"
            req = urllib.request.Request(url, headers={"User-Agent": "SalmAlm/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")[:50000]
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            if m:
                title = re.sub(r"\s+", " ", m.group(1)).strip()[:200]
            content = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()[:5000]
        except Exception:
            title = url[:100]
    lid = secrets.token_hex(4)
    now = datetime.now(KST).isoformat()
    with _db_lock:
        conn = _get_db()
        conn.execute(
            "INSERT INTO saved_links (id, url, title, summary, tags, content, saved_at) VALUES (?,?,?,?,?,?,?)",
            (lid, url, title, summary, tags, content, now),
        )
        conn.commit()
        conn.close()
    return f"🔖 링크 저장됨 [{lid}]\n  **{title}**\n  {url}"


def handle_save_link(args: dict) -> str:
    """Save a link/article for later reading."""
    action = args.get("action", "save")

    if action == "save":
        return _save_link_impl(args)

    elif action == "list":
        count = int(args.get("count", 10))
        with _db_lock:
            conn = _get_db()
            rows = conn.execute(
                "SELECT id, url, title, tags, saved_at FROM saved_links ORDER BY saved_at DESC LIMIT ?", (count,)
            ).fetchall()
            conn.close()
        if not rows:
            return "🔖 저장된 링크가 없습니다."
        lines = [f"🔖 **저장된 링크 ({len(rows)}건)**"]
        for r in rows:
            tag_str = f" 🏷️{r['tags']}" if r["tags"] else ""
            lines.append(f"  🔗 [{r['id']}] **{r['title'][:60]}**{tag_str}")
            lines.append(f"     {r['url'][:80]}")
        return "\n".join(lines)

    elif action == "search":
        query = args.get("query", "")
        if not query:
            return "❌ query is required"
        with _db_lock:
            conn = _get_db()
            rows = conn.execute(
                "SELECT id, url, title, summary, tags FROM saved_links WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? ORDER BY saved_at DESC LIMIT 10",
                (f"%{query}%", f"%{query}%", f"%{query}%"),
            ).fetchall()
            conn.close()
        if not rows:
            return f'🔍 "{query}" 관련 링크가 없습니다.'
        lines = [f'🔍 **링크 검색: "{query}" ({len(rows)}건)**']
        for r in rows:
            lines.append(f"  🔗 [{r['id']}] **{r['title'][:60]}**")
            lines.append(f"     {r['url'][:80]}")
        return "\n".join(lines)

    elif action == "delete":
        link_id = args.get("link_id", "")
        if not link_id:
            return "❌ link_id is required"
        with _db_lock:
            conn = _get_db()
            cur = conn.execute("DELETE FROM saved_links WHERE id = ?", (link_id,))
            conn.commit()
            conn.close()
        if cur.rowcount:
            return f"🔖 링크 삭제됨: {link_id}"
        return f"❌ 링크를 찾을 수 없습니다: {link_id}"

    return f"❌ Unknown save_link action: {action}"


# ── Pomodoro Timer ───────────────────────────────────────────

_pomodoro_state = {
    "active": False,
    "type": None,  # 'focus' or 'break'
    "start_time": None,
    "duration_minutes": 25,
    "session_id": None,
    "timer_thread": None,
}
_pomodoro_lock = threading.Lock()


def _pomodoro_timer_func(session_id: str, duration_min: int, ptype: str):
    """Background timer that sends notification when done."""
    time.sleep(duration_min * 60)
    with _pomodoro_lock:
        if _pomodoro_state.get("session_id") != session_id:
            return  # Was stopped or replaced
        _pomodoro_state["active"] = False

    # Record completion
    now = datetime.now(KST).isoformat()
    with _db_lock:
        conn = _get_db()
        conn.execute("UPDATE pomodoro_sessions SET ended_at = ?, completed = 1 WHERE id = ?", (now, session_id))
        conn.commit()
        conn.close()

    # Send notification
    try:
        from salmalm.tools.tools_misc import _send_notification_impl

        if ptype == "focus":
            _send_notification_impl("🍅 포모도로 완료! 휴식 시간이에요.", title="Pomodoro")
        else:
            _send_notification_impl("☕ 휴식 끝! 다시 집중할 시간이에요.", title="Pomodoro")
    except Exception as e:
        log.error(f"Pomodoro notification failed: {e}")


@register("pomodoro")
def handle_pomodoro(args: dict) -> str:
    """Pomodoro timer."""
    action = args.get("action", "status")

    if action == "start":
        duration = int(args.get("duration", 25))
        with _pomodoro_lock:
            if _pomodoro_state["active"]:
                return "🍅 포모도로가 이미 진행 중입니다. /pomodoro stop 으로 중지하세요."
            sid = secrets.token_hex(4)
            now = datetime.now(KST)
            _pomodoro_state.update(
                {
                    "active": True,
                    "type": "focus",
                    "start_time": now.isoformat(),
                    "duration_minutes": duration,
                    "session_id": sid,
                }
            )
        with _db_lock:
            conn = _get_db()
            conn.execute(
                "INSERT INTO pomodoro_sessions (id, started_at, type) VALUES (?,?,?)", (sid, now.isoformat(), "focus")
            )
            conn.commit()
            conn.close()
        t = threading.Thread(target=_pomodoro_timer_func, args=(sid, duration, "focus"), daemon=True)
        t.start()
        _pomodoro_state["timer_thread"] = t
        end_time = now + timedelta(minutes=duration)
        return f"🍅 포모도로 시작! {duration}분 집중\n⏰ 종료 예정: {end_time.strftime('%H:%M')}"

    elif action == "break":
        duration = int(args.get("duration", 5))
        with _pomodoro_lock:
            if _pomodoro_state["active"]:
                return "🍅 타이머가 이미 진행 중입니다."
            sid = secrets.token_hex(4)
            now = datetime.now(KST)
            _pomodoro_state.update(
                {
                    "active": True,
                    "type": "break",
                    "start_time": now.isoformat(),
                    "duration_minutes": duration,
                    "session_id": sid,
                }
            )
        with _db_lock:
            conn = _get_db()
            conn.execute(
                "INSERT INTO pomodoro_sessions (id, started_at, type) VALUES (?,?,?)", (sid, now.isoformat(), "break")
            )
            conn.commit()
            conn.close()
        t = threading.Thread(target=_pomodoro_timer_func, args=(sid, duration, "break"), daemon=True)
        t.start()
        _pomodoro_state["timer_thread"] = t
        end_time = now + timedelta(minutes=duration)
        return f"☕ 휴식 시작! {duration}분\n⏰ 종료 예정: {end_time.strftime('%H:%M')}"

    elif action == "stop":
        with _pomodoro_lock:
            if not _pomodoro_state["active"]:
                return "🍅 진행 중인 포모도로가 없습니다."
            sid = _pomodoro_state["session_id"]
            _pomodoro_state["active"] = False
            _pomodoro_state["session_id"] = None
        now = datetime.now(KST).isoformat()
        with _db_lock:
            conn = _get_db()
            conn.execute("UPDATE pomodoro_sessions SET ended_at = ? WHERE id = ?", (now, sid))
            conn.commit()
            conn.close()
        return "🍅 포모도로 중지됨."

    elif action in ("status", "stats"):
        today = datetime.now(KST).strftime("%Y-%m-%d")
        with _db_lock:
            conn = _get_db()
            completed = conn.execute(
                "SELECT COUNT(*) FROM pomodoro_sessions WHERE started_at LIKE ? AND type='focus' AND completed=1",
                (f"{today}%",),
            ).fetchone()[0]
            conn.close()
        lines = [f"🍅 **포모도로 통계 ({today})**"]
        lines.append(f"  완료: {completed}회")
        with _pomodoro_lock:
            if _pomodoro_state["active"]:
                ptype = "집중" if _pomodoro_state["type"] == "focus" else "휴식"
                start = datetime.fromisoformat(_pomodoro_state["start_time"])
                elapsed = (datetime.now(KST) - start).seconds // 60
                remaining = _pomodoro_state["duration_minutes"] - elapsed
                lines.append(f"  현재: {ptype} 중 (남은 시간: {remaining}분)")
            else:
                lines.append("  현재: 대기 중")
        return "\n".join(lines)

    return f"❌ Unknown pomodoro action: {action}"


# ── Routines ─────────────────────────────────────────────────

_DEFAULT_ROUTINES = {
    "morning": {
        "name": "아침 루틴",
        "steps": [
            {"type": "briefing", "label": "📋 데일리 브리핑"},
            {"type": "message", "label": "💪 동기부여", "content": "오늘도 화이팅! 하루를 멋지게 시작해봐요. 🚀"},
        ],
    },
    "evening": {
        "name": "저녁 루틴",
        "steps": [
            {"type": "expense_today", "label": "💰 오늘 지출 정리"},
            {
                "type": "message",
                "label": "📔 감사일기",
                "content": "오늘 하루 감사한 일 3가지를 떠올려보세요:\n1. \n2. \n3. ",
            },
            {"type": "message", "label": "🌙 내일 준비", "content": "내일 가장 중요한 일 1가지는 무엇인가요?"},
        ],
    },
}


def _load_routines() -> dict:
    """Load routines."""
    config_path = DATA_DIR / "routines.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")
    return dict(_DEFAULT_ROUTINES)


@register("routine")
def handle_routine(args: dict) -> str:
    """Morning/evening routine automation."""
    action = args.get("action", "morning")
    routines = _load_routines()

    if action == "list":
        lines = ["🔄 **루틴 목록**"]
        for key, routine in routines.items():
            steps_str = ", ".join(s.get("label", s.get("type", "?")) for s in routine.get("steps", []))
            lines.append(f"  • **{routine.get('name', key)}** ({key}): {steps_str}")
        return "\n".join(lines)

    routine = routines.get(action)
    if not routine:
        return f"❌ Unknown routine: {action}. Available: {', '.join(routines.keys())}"

    parts = [f"🔄 **{routine.get('name', action)}**\n"]
    for step in routine.get("steps", []):
        step_type = step.get("type", "")
        label = step.get("label", step_type)

        if step_type == "briefing":
            from salmalm.features.briefing import daily_briefing

            result = daily_briefing.generate()
            parts.append(result)
        elif step_type == "expense_today":
            try:
                result = handle_expense({"action": "today"})
                parts.append(result)
            except Exception as e:  # noqa: broad-except
                parts.append(f"{label}: 조회 실패")
        elif step_type == "message":
            parts.append(f"{label}\n{step.get('content', '')}")
        elif step_type == "tool":
            try:
                from salmalm.tools.tool_registry import execute_tool

                result = execute_tool(step.get("tool", ""), step.get("args", {}))
                parts.append(f"{label}\n{result}")
            except Exception as e:
                parts.append(f"{label}: 실행 실패 — {e}")

    return "\n\n".join(parts)


# ── Briefing Tool ────────────────────────────────────────────


@register("briefing")
def handle_briefing(args: dict) -> str:
    """Generate daily briefing."""
    from salmalm.features.briefing import daily_briefing

    sections = args.get("sections")
    if sections and isinstance(sections, str):
        sections = [s.strip() for s in sections.split(",")]
    return daily_briefing.generate(sections)
