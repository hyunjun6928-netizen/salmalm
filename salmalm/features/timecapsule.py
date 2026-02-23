"""Time Capsule — schedule messages to your future self."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from salmalm.constants import KST, DATA_DIR
CAPSULE_DB = DATA_DIR / "capsules.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS capsules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_note TEXT NOT NULL,
    delivery_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    delivered INTEGER DEFAULT 0,
    delivery_channel TEXT DEFAULT ''
);
"""


def _parse_capsule_date(text: str) -> datetime:
    """Parse date for capsule delivery. Supports ISO, Korean relative, English relative."""
    s = text.strip()
    now = datetime.now(tz=KST)

    # ISO date
    m = re.match(r"^(\d{4}-\d{2}-\d{2})$", s)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=KST)

    # Korean relative: N개월후, N년후, N일후, N주후
    m = re.search(r"(\d+)\s*개월\s*후", s)
    if m:
        months = int(m.group(1))
        target = now.replace(month=now.month + months % 12, year=now.year + (now.month + months - 1) // 12)
        try:
            return target
        except ValueError:
            return target.replace(day=28)

    m = re.search(r"(\d+)\s*년\s*후", s)
    if m:
        return now.replace(year=now.year + int(m.group(1)))

    m = re.search(r"(\d+)\s*일\s*후", s)
    if m:
        return now + timedelta(days=int(m.group(1)))

    m = re.search(r"(\d+)\s*주\s*후", s)
    if m:
        return now + timedelta(weeks=int(m.group(1)))

    # English: in N months/days/weeks/years
    m = re.search(r"in\s+(\d+)\s*(months?|days?|weeks?|years?)", s.lower())
    if m:
        val = int(m.group(1))
        unit = m.group(2)[0]
        if unit == "m":
            target_month = now.month + val
            return now.replace(month=(target_month - 1) % 12 + 1, year=now.year + (target_month - 1) // 12)
        elif unit == "d":
            return now + timedelta(days=val)
        elif unit == "w":
            return now + timedelta(weeks=val)
        elif unit == "y":
            return now.replace(year=now.year + val)

    # 내년 (next year)
    if "내년" in s:
        return now.replace(year=now.year + 1)

    raise ValueError(f"날짜를 파싱할 수 없습니다: {text}")


class TimeCapsule:
    """Manages time capsules stored in SQLite."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or CAPSULE_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    # -- CRUD -----------------------------------------------------------------

    def create(self, date_text: str, message: str, channel: str = "") -> dict:
        """Create a new time capsule."""
        delivery = _parse_capsule_date(date_text)
        now = datetime.now(tz=KST)
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO capsules (sender_note, delivery_date, created_at, delivered, delivery_channel) "
                "VALUES (?, ?, ?, 0, ?)",
                (message, delivery.strftime("%Y-%m-%d"), now.isoformat(), channel),
            )
            cid = cur.lastrowid
        return {
            "id": cid,
            "delivery_date": delivery.strftime("%Y-%m-%d"),
            "message": f"📦 타임캡슐 #{cid} 생성! 배달 예정: {delivery.strftime('%Y-%m-%d')}",
        }

    def list_pending(self) -> List[Tuple]:
        """List capsules not yet delivered."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, sender_note, delivery_date, created_at FROM capsules "
                "WHERE delivered = 0 ORDER BY delivery_date"
            ).fetchall()
        return rows

    def list_delivered(self) -> List[Tuple]:
        """List already delivered capsules."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, sender_note, delivery_date, created_at FROM capsules "
                "WHERE delivered = 1 ORDER BY delivery_date DESC"
            ).fetchall()
        return rows

    def peek(self, capsule_id: int) -> Optional[dict]:
        """Peek at a capsule (spoiler warning)."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, sender_note, delivery_date, created_at, delivered FROM capsules WHERE id = ?", (capsule_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "message": row[1],
            "delivery_date": row[2],
            "created_at": row[3],
            "delivered": bool(row[4]),
        }

    def cancel(self, capsule_id: int) -> bool:
        """Cancel (delete) a pending capsule."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM capsules WHERE id = ? AND delivered = 0", (capsule_id,))
        return cur.rowcount > 0

    def get_due_capsules(self, today: Optional[str] = None) -> List[Tuple]:
        """Get capsules due for delivery today."""
        if today is None:
            today = datetime.now(tz=KST).strftime("%Y-%m-%d")
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, sender_note, delivery_date, created_at, delivery_channel "
                "FROM capsules WHERE delivered = 0 AND delivery_date <= ? "
                "ORDER BY delivery_date",
                (today,),
            ).fetchall()
        return rows

    def mark_delivered(self, capsule_id: int) -> None:
        """Mark a capsule as delivered."""
        with self._conn() as conn:
            conn.execute("UPDATE capsules SET delivered = 1 WHERE id = ?", (capsule_id,))

    def deliver_due(self, send_fn=None, today: Optional[str] = None) -> List[dict]:
        """Deliver all due capsules. Returns list of delivery results."""
        due = self.get_due_capsules(today)
        results = []
        for row in due:
            cid, note, ddate, created, channel = row
            msg = f"📬 타임캡슐이 도착했습니다!\n작성일: {created[:10]}\n---\n{note}\n---\n과거의 나로부터."
            if send_fn:
                send_fn(msg, channel)
            self.mark_delivered(cid)
            results.append({"id": cid, "message": msg, "channel": channel})
        return results

    # -- command dispatch -----------------------------------------------------

    def handle_command(self, args: str, channel: str = "") -> str:
        """Handle /capsule subcommands."""
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "list"
        rest = parts[1] if len(parts) > 1 else ""

        if sub == "list":
            rows = self.list_pending()
            if not rows:
                return "📭 예정된 타임캡슐이 없습니다."
            lines = ["📦 예정된 타임캡슐:"]
            for r in rows:
                lines.append(f"  #{r[0]} | {r[2]} | {r[1][:30]}...")
            return "\n".join(lines)

        elif sub == "delivered":
            rows = self.list_delivered()
            if not rows:
                return "📭 전달된 타임캡슐이 없습니다."
            lines = ["📬 전달된 타임캡슐:"]
            for r in rows:
                lines.append(f"  #{r[0]} | {r[2]} | {r[1][:30]}...")
            return "\n".join(lines)

        elif sub == "peek":
            try:
                cid = int(rest.strip())
            except (ValueError, IndexError):
                return "사용법: /capsule peek <id>"
            cap = self.peek(cid)
            if not cap:
                return f"캡슐 #{cid}를 찾을 수 없습니다."
            return f"⚠️ 스포일러 주의!\n캡슐 #{cap['id']} (배달: {cap['delivery_date']})\n---\n{cap['message']}\n---"

        elif sub == "cancel":
            try:
                cid = int(rest.strip())
            except (ValueError, IndexError):
                return "사용법: /capsule cancel <id>"
            if self.cancel(cid):
                return f"🗑️ 캡슐 #{cid} 취소됨."
            return f"캡슐 #{cid}를 취소할 수 없습니다 (이미 배달되었거나 없음)."

        else:
            # Treat as: <date> <message>
            # sub is part of the date, rest is potentially more date + message
            full = args.strip()
            # Try to split date and message
            # Check if first token is a date-like pattern
            date_text, message = _split_date_message(full)
            if not message:
                return "사용법: /capsule <날짜> <메시지>\n예: /capsule 2026-08-15 미래의 나에게"
            try:
                result = self.create(date_text, message, channel)
                return result["message"]
            except ValueError as e:
                return str(e)


def _split_date_message(text: str) -> Tuple[str, str]:
    """Split combined date+message text."""
    # ISO date at start
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(.+)", text, re.DOTALL)
    if m:
        return m.group(1), m.group(2)

    # Korean relative date patterns
    for pattern in [
        r"^(\d+\s*개월\s*후)\s+",
        r"^(\d+\s*년\s*후)\s+",
        r"^(\d+\s*일\s*후)\s+",
        r"^(\d+\s*주\s*후)\s+",
        r"^(내년[^\s]*)\s+",
    ]:
        m = re.match(pattern, text)
        if m:
            return m.group(1), text[m.end() :]

    # English: "in N units message"
    m = re.match(r"^(in\s+\d+\s+\w+)\s+(.+)", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)

    return text, ""
