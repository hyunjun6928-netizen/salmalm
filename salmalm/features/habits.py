"""Habit Tracker — 일일 습관 추적기.

stdlib-only. SQLite 저장, 이모지 진행바, streak 계산.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from salmalm.constants import KST, BASE_DIR
from salmalm.utils.db import connect as _connect_db

log = logging.getLogger(__name__)

HABIT_DB = BASE_DIR / "habits.db"


def _get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get db."""
    conn = _connect_db(db_path or HABIT_DB, wal=True)
    conn.execute("""CREATE TABLE IF NOT EXISTS habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        active INTEGER DEFAULT 1
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS habit_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        habit_name TEXT NOT NULL,
        check_date TEXT NOT NULL,
        checked_at TEXT NOT NULL,
        UNIQUE(habit_name, check_date)
    )""")
    conn.commit()
    return conn


class HabitTracker:
    """습관 추적기."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Init  ."""
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Conn."""
        if self._conn is None:
            self._conn = _get_db(self._db_path)
        return self._conn

    def close(self) -> None:
        """Close."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def add_habit(self, name: str) -> str:
        """습관 등록."""
        name = name.strip()
        if not name:
            return "❌ 습관 이름을 입력하세요."
        try:
            now = datetime.now(KST).isoformat()
            self.conn.execute("INSERT INTO habits (name, created_at) VALUES (?, ?)", (name, now))
            self.conn.commit()
            return f"✅ 습관 '{name}' 등록 완료!"
        except sqlite3.IntegrityError:
            # Maybe it was deactivated, reactivate
            self.conn.execute("UPDATE habits SET active=1 WHERE name=?", (name,))
            self.conn.commit()
            return f"✅ 습관 '{name}' 다시 활성화!"

    def remove_habit(self, name: str) -> str:
        """습관 삭제 (비활성화)."""
        name = name.strip()
        cur = self.conn.execute("SELECT id FROM habits WHERE name=? AND active=1", (name,))
        if not cur.fetchone():
            return f"❌ '{name}' 습관을 찾을 수 없습니다."
        self.conn.execute("UPDATE habits SET active=0 WHERE name=?", (name,))
        self.conn.commit()
        return f"🗑️ 습관 '{name}' 삭제됨."

    def check_habit(self, name: str, date: Optional[str] = None) -> str:
        """오늘 완료 표시."""
        name = name.strip()
        cur = self.conn.execute("SELECT id FROM habits WHERE name=? AND active=1", (name,))
        if not cur.fetchone():
            return f"❌ '{name}' 습관을 찾을 수 없습니다."

        today = date or datetime.now(KST).strftime("%Y-%m-%d")
        now = datetime.now(KST).isoformat()
        try:
            self.conn.execute(
                "INSERT INTO habit_checks (habit_name, check_date, checked_at) VALUES (?, ?, ?)", (name, today, now)
            )
            self.conn.commit()
            streak = self._calc_streak(name, today)
            return f"✅ '{name}' 완료! 🔥 {streak}일 연속"
        except sqlite3.IntegrityError:
            return f"ℹ️ '{name}'은 이미 오늘 완료했습니다."

    def uncheck_habit(self, name: str, date: Optional[str] = None) -> str:
        """완료 취소."""
        today = date or datetime.now(KST).strftime("%Y-%m-%d")
        self.conn.execute("DELETE FROM habit_checks WHERE habit_name=? AND check_date=?", (name, today))
        self.conn.commit()
        return f"↩️ '{name}' 완료 취소됨."

    def _calc_streak(self, name: str, from_date: Optional[str] = None) -> int:
        """연속 일수 계산."""
        today = from_date or datetime.now(KST).strftime("%Y-%m-%d")
        streak = 0
        cur_date = datetime.strptime(today, "%Y-%m-%d")
        while True:
            ds = cur_date.strftime("%Y-%m-%d")
            row = self.conn.execute(
                "SELECT 1 FROM habit_checks WHERE habit_name=? AND check_date=?", (name, ds)
            ).fetchone()
            if row:
                streak += 1
                cur_date -= timedelta(days=1)
            else:
                break
        return streak

    def get_habits(self) -> List[str]:
        """활성 습관 목록."""
        rows = self.conn.execute("SELECT name FROM habits WHERE active=1 ORDER BY name").fetchall()
        return [r[0] for r in rows]

    def stats(self, days: int = 7) -> str:
        """주간/월간 통계 + streak."""
        habits = self.get_habits()
        if not habits:
            return "📋 등록된 습관이 없습니다. `/habit add <name>`으로 추가하세요."

        today = datetime.now(KST).strftime("%Y-%m-%d")
        lines = [f"📊 **습관 통계** (최근 {days}일)\n"]

        for h in habits:
            streak = self._calc_streak(h, today)
            # Count completions in period
            start = (datetime.now(KST) - timedelta(days=days - 1)).strftime("%Y-%m-%d")
            rows = self.conn.execute(
                "SELECT COUNT(*) FROM habit_checks WHERE habit_name=? AND check_date BETWEEN ? AND ?", (h, start, today)
            ).fetchone()
            count = rows[0] if rows else 0
            rate = count / days
            bar = self._progress_bar(rate)
            lines.append(f"**{h}** {bar} {count}/{days}일 | 🔥 {streak}일 연속")

        return "\n".join(lines)

    def monthly_stats(self) -> str:
        """월간 통계."""
        return self.stats(days=30)

    def remind(self) -> str:
        """미완료 습관 알림."""
        habits = self.get_habits()
        if not habits:
            return "📋 등록된 습관이 없습니다."

        today = datetime.now(KST).strftime("%Y-%m-%d")
        unchecked = []
        checked = []
        for h in habits:
            row = self.conn.execute(
                "SELECT 1 FROM habit_checks WHERE habit_name=? AND check_date=?", (h, today)
            ).fetchone()
            if row:
                checked.append(h)
            else:
                unchecked.append(h)

        lines = [f"📋 **오늘의 습관** ({today})\n"]
        for h in checked:
            lines.append(f"  ✅ {h}")
        for h in unchecked:
            lines.append(f"  ⬜ {h}")

        if unchecked:
            lines.append(f"\n⏰ 아직 {len(unchecked)}개 미완료!")
        else:
            lines.append("\n🎉 오늘 모든 습관 완료!")

        return "\n".join(lines)

    @staticmethod
    def _progress_bar(rate: float, length: int = 10) -> str:
        """이모지 진행바."""
        filled = int(rate * length)
        filled = min(filled, length)
        return "🟩" * filled + "⬜" * (length - filled)

    def today_summary(self) -> Dict:
        """오늘 요약 (다른 모듈 연동용)."""
        habits = self.get_habits()
        today = datetime.now(KST).strftime("%Y-%m-%d")
        done = []
        pending = []
        for h in habits:
            row = self.conn.execute(
                "SELECT 1 FROM habit_checks WHERE habit_name=? AND check_date=?", (h, today)
            ).fetchone()
            if row:
                done.append(h)
            else:
                pending.append(h)
        return {"done": done, "pending": pending, "total": len(habits)}


# ── Singleton ──
_tracker: Optional[HabitTracker] = None


def get_tracker(db_path: Optional[Path] = None) -> HabitTracker:
    """Get tracker."""
    global _tracker
    if _tracker is None:
        _tracker = HabitTracker(db_path)
    return _tracker


# ── Command handler ──


async def handle_habit_command(cmd: str, session=None, **kw) -> Optional[str]:
    """Handle /habit commands."""
    parts = cmd.strip().split(maxsplit=2)
    # /habit -> show remind
    if len(parts) < 2:
        return get_tracker().remind()

    sub = parts[1].lower()
    arg = parts[2].strip() if len(parts) > 2 else ""

    t = get_tracker()
    if sub == "add":
        if not arg:
            return "사용법: `/habit add <이름>`"
        return t.add_habit(arg)
    elif sub == "remove" or sub == "delete":
        if not arg:
            return "사용법: `/habit remove <이름>`"
        return t.remove_habit(arg)
    elif sub == "check" or sub == "done":
        if not arg:
            return "사용법: `/habit check <이름>`"
        return t.check_habit(arg)
    elif sub == "uncheck":
        if not arg:
            return "사용법: `/habit uncheck <이름>`"
        return t.uncheck_habit(arg)
    elif sub == "stats":
        if arg and arg.isdigit():
            return t.stats(int(arg))
        return t.stats()
    elif sub == "monthly":
        return t.monthly_stats()
    elif sub == "remind":
        return t.remind()
    elif sub == "list":
        habits = t.get_habits()
        if not habits:
            return "📋 등록된 습관이 없습니다."
        return "📋 **습관 목록**\n" + "\n".join(f"  • {h}" for h in habits)
    else:
        return (
            "**습관 명령어:**\n"
            "`/habit add <name>` — 습관 등록\n"
            "`/habit check <name>` — 완료 표시\n"
            "`/habit uncheck <name>` — 완료 취소\n"
            "`/habit stats` — 주간 통계\n"
            "`/habit monthly` — 월간 통계\n"
            "`/habit remind` — 미완료 알림\n"
            "`/habit list` — 목록\n"
            "`/habit remove <name>` — 삭제"
        )


# ── Registration ──


def register_habit_commands(command_router) -> None:
    """Register /habit command with the command router."""
    from salmalm.features.commands import COMMAND_DEFS

    COMMAND_DEFS["/habit"] = "Habit tracker (add|check|stats|remind|list|remove)"
    if hasattr(command_router, "_prefix_handlers"):
        command_router._prefix_handlers.append(("/habit", handle_habit_command))


def register_habit_tools():
    """Register habit tools with the tool registry."""
    from salmalm.tools.tool_registry import register_dynamic

    async def _habit_tool(args):
        """Habit tool."""
        sub = args.get("subcommand", "remind")
        name = args.get("name", "")
        cmd = f"/habit {sub} {name}".strip()
        return await handle_habit_command(cmd)

    register_dynamic(
        "habit_tracker",
        _habit_tool,
        {
            "name": "habit_tracker",
            "description": "Track daily habits (add, check, stats, remind, list, remove)",
            "parameters": {
                "type": "object",
                "properties": {
                    "subcommand": {
                        "type": "string",
                        "enum": ["add", "check", "uncheck", "stats", "monthly", "remind", "list", "remove"],
                        "description": "Habit subcommand",
                    },
                    "name": {"type": "string", "description": "Habit name (for add/check/remove)"},
                },
                "required": ["subcommand"],
            },
        },
    )
