"""AI Journal — AI 일지, 감정 분석, 하루 요약.

stdlib-only. SQLite 저장, mood.py 연동.
"""

from __future__ import annotations

import logging
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from salmalm.constants import KST, BASE_DIR
from salmalm.utils.db import connect as _connect_db

log = logging.getLogger(__name__)

JOURNAL_DB = BASE_DIR / "journal.db"

# Simple mood keywords for analysis
_MOOD_KEYWORDS = {
    "happy": ["기쁘", "좋아", "행복", "최고", "감사", "happy", "great", "awesome", "love", "신나", "ㅋㅋ", "ㅎㅎ"],
    "sad": ["슬프", "우울", "힘들", "외로", "sad", "depressed", "lonely", "ㅠㅠ", "ㅜㅜ"],
    "angry": ["화나", "짜증", "열받", "angry", "furious", "annoyed"],
    "anxious": ["걱정", "불안", "초조", "anxious", "worried", "stressed"],
    "tired": ["피곤", "졸려", "지친", "tired", "exhausted"],
    "excited": ["기대", "설레", "신나", "excited", "thrilled"],
    "neutral": [],
}


def _get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = _connect_db(db_path or JOURNAL_DB, wal=True)
    conn.execute("""CREATE TABLE IF NOT EXISTS journal_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        content TEXT NOT NULL,
        mood TEXT DEFAULT 'neutral',
        mood_score REAL DEFAULT 0.5,
        auto_generated INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    conn.commit()
    return conn


def _detect_mood(text: str) -> tuple:
    """Simple keyword-based mood detection. Returns (mood, score)."""
    text_lower = text.lower()
    scores = {}
    for mood, keywords in _MOOD_KEYWORDS.items():
        if not keywords:
            continue
        count = sum(1 for kw in keywords if kw in text_lower)
        if count:
            scores[mood] = count

    if not scores:
        return "neutral", 0.5

    best = max(scores, key=scores.get)
    # Score: positive moods > 0.5, negative < 0.5
    mood_valence = {
        "happy": 0.9,
        "excited": 0.85,
        "neutral": 0.5,
        "tired": 0.35,
        "anxious": 0.3,
        "sad": 0.2,
        "angry": 0.15,
    }
    return best, mood_valence.get(best, 0.5)


class JournalManager:
    """AI 일지 관리자."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = _get_db(self._db_path)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def write(self, text: str, date: Optional[str] = None) -> str:
        """일지 작성."""
        text = text.strip()
        if not text:
            return "❌ 일지 내용을 입력하세요."

        today = date or datetime.now(KST).strftime("%Y-%m-%d")
        now = datetime.now(KST).isoformat()
        mood, score = _detect_mood(text)

        self.conn.execute(
            "INSERT INTO journal_entries (date, content, mood, mood_score, auto_generated, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (today, text, mood, score, now),
        )
        self.conn.commit()

        mood_emoji = {
            "happy": "😊",
            "sad": "😢",
            "angry": "😡",
            "anxious": "😰",
            "tired": "😴",
            "excited": "🤩",
            "neutral": "😐",
        }
        emoji = mood_emoji.get(mood, "📝")
        return f"📝 일지 작성 완료! {emoji} 감정: {mood} ({score:.0%})"

    def review(self, date: str) -> str:
        """특정 날짜 일지 조회."""
        rows = self.conn.execute(
            "SELECT content, mood, mood_score, created_at, auto_generated "
            "FROM journal_entries WHERE date=? ORDER BY created_at",
            (date,),
        ).fetchall()

        if not rows:
            return f"📖 {date}의 일지가 없습니다."

        lines = [f"📖 **{date} 일지**\n"]
        for content, mood, score, created, auto in rows:
            tag = "🤖 자동" if auto else "✍️"
            mood_emoji = {
                "happy": "😊",
                "sad": "😢",
                "angry": "😡",
                "anxious": "😰",
                "tired": "😴",
                "excited": "🤩",
                "neutral": "😐",
            }.get(mood, "📝")
            lines.append(f"{tag} {mood_emoji} {content[:200]}")
        return "\n".join(lines)

    def today(self) -> str:
        """오늘 일지 조회."""
        today = datetime.now(KST).strftime("%Y-%m-%d")
        return self.review(today)

    def generate_today_summary(self, conversations: Optional[List[str]] = None) -> str:
        """오늘의 대화 기반 자동 일지 생성."""
        today = datetime.now(KST).strftime("%Y-%m-%d")
        now = datetime.now(KST).isoformat()

        # Get existing entries for today
        rows = self.conn.execute("SELECT content FROM journal_entries WHERE date=?", (today,)).fetchall()

        if not rows and not conversations:
            return "📝 오늘 기록된 일지가 없습니다."

        all_text = " ".join(r[0] for r in rows)
        if conversations:
            all_text += " " + " ".join(conversations)

        mood, score = _detect_mood(all_text)
        entry_count = len(rows)

        summary = f"오늘 {entry_count}개의 일지를 작성했습니다. 전반적 감정: {mood}."
        self.conn.execute(
            "INSERT INTO journal_entries (date, content, mood, mood_score, auto_generated, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (today, summary, mood, score, now),
        )
        self.conn.commit()

        return f"🤖 **오늘의 자동 일지**\n{summary}"

    def mood_trend(self, days: int = 14) -> str:
        """감정 트렌드 차트 (텍스트 기반)."""
        today = datetime.now(KST)
        lines = ["📊 **감정 트렌드** (최근 {0}일)\n".format(days)]

        mood_counts = Counter()
        daily_scores = []

        for i in range(days - 1, -1, -1):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            rows = self.conn.execute("SELECT mood, mood_score FROM journal_entries WHERE date=?", (date,)).fetchall()

            if rows:
                avg_score = sum(r[1] for r in rows) / len(rows)
                moods = [r[0] for r in rows]
                for m in moods:
                    mood_counts[m] += 1
                daily_scores.append((date, avg_score, moods[0]))
            else:
                daily_scores.append((date, None, None))

        # Text chart
        for date, score, mood in daily_scores:
            day_label = date[-5:]  # MM-DD
            if score is not None:
                bar_len = int(score * 10)
                bar = "█" * bar_len + "░" * (10 - bar_len)
                emoji = {
                    "happy": "😊",
                    "sad": "😢",
                    "angry": "😡",
                    "anxious": "😰",
                    "tired": "😴",
                    "excited": "🤩",
                    "neutral": "😐",
                }.get(mood, "📝")
                lines.append(f"{day_label} {bar} {emoji} {score:.0%}")
            else:
                lines.append(f"{day_label} {'·' * 10} (기록 없음)")

        # Summary
        if mood_counts:
            top = mood_counts.most_common(3)
            summary = ", ".join(f"{m}({c}회)" for m, c in top)
            lines.append(f"\n📈 주요 감정: {summary}")

        return "\n".join(lines)

    def mood_from_mood_py(self, text: str) -> Optional[str]:
        """기존 mood.py 연동."""
        try:
            from salmalm.features.mood import detect_mood

            result = detect_mood(text)
            if result:
                return result.get("mood", "neutral")
        except (ImportError, Exception):
            pass
        return None

    def get_entries_for_date(self, date: str) -> List[Dict]:
        """특정 날짜 엔트리 (API용)."""
        rows = self.conn.execute(
            "SELECT id, content, mood, mood_score, auto_generated, created_at "
            "FROM journal_entries WHERE date=? ORDER BY created_at",
            (date,),
        ).fetchall()
        return [
            {"id": r[0], "content": r[1], "mood": r[2], "mood_score": r[3], "auto": bool(r[4]), "created_at": r[5]}
            for r in rows
        ]


# ── Singleton ──
_journal: Optional[JournalManager] = None


def get_journal(db_path: Optional[Path] = None) -> JournalManager:
    global _journal
    if _journal is None:
        _journal = JournalManager(db_path)
    return _journal


# ── Command handler ──


async def handle_journal_command(cmd: str, session=None, **kw) -> Optional[str]:
    """Handle /journal commands."""
    parts = cmd.strip().split(maxsplit=2)
    if len(parts) < 2:
        return get_journal().today()

    sub = parts[1].lower()
    arg = parts[2].strip() if len(parts) > 2 else ""

    j = get_journal()

    if sub == "write":
        if not arg:
            return "사용법: `/journal write <내용>`"
        return j.write(arg)
    elif sub == "today":
        return j.today()
    elif sub == "review":
        if not arg:
            return "사용법: `/journal review <YYYY-MM-DD>`"
        return j.review(arg)
    elif sub == "mood":
        days = 14
        if arg and arg.isdigit():
            days = int(arg)
        return j.mood_trend(days)
    elif sub == "summary":
        return j.generate_today_summary()
    else:
        return (
            "**일지 명령어:**\n"
            "`/journal write <text>` — 일지 작성\n"
            "`/journal today` — 오늘 일지\n"
            "`/journal review <date>` — 날짜별 조회\n"
            "`/journal mood` — 감정 트렌드\n"
            "`/journal summary` — 오늘 자동 요약"
        )


# ── Registration ──


def register_journal_commands(command_router):
    """Register /journal command."""
    from salmalm.features.commands import COMMAND_DEFS

    COMMAND_DEFS["/journal"] = "AI Journal (write|today|review|mood|summary)"
    if hasattr(command_router, "_prefix_handlers"):
        command_router._prefix_handlers.append(("/journal", handle_journal_command))


def register_journal_tools():
    """Register journal tools."""
    from salmalm.tools.tool_registry import register_dynamic

    async def _journal_tool(args):
        sub = args.get("subcommand", "today")
        text = args.get("text", "")
        cmd = f"/journal {sub} {text}".strip()
        return await handle_journal_command(cmd)

    register_dynamic(
        "ai_journal",
        _journal_tool,
        {
            "name": "ai_journal",
            "description": "AI Journal - write entries, review, mood trends",
            "parameters": {
                "type": "object",
                "properties": {
                    "subcommand": {
                        "type": "string",
                        "enum": ["write", "today", "review", "mood", "summary"],
                    },
                    "text": {"type": "string", "description": "Journal text or date"},
                },
                "required": ["subcommand"],
            },
        },
    )
