"""Token Usage Tracking (사용량 추적) — LibreChat style."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from salmalm.constants import KST, DATA_DIR
from salmalm.security.crypto import log


class UsageTracker:
    """Per-user, per-model token usage tracking with daily/monthly reports."""

    def __init__(self) -> None:
        """Init  ."""
        self._db_path = DATA_DIR / "salmalm.db"

    def _get_db(self):
        """Get db."""
        from salmalm.core import _get_db

        conn = _get_db()
        conn.execute("""CREATE TABLE IF NOT EXISTS usage_detail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            session_id TEXT,
            model TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cost REAL DEFAULT 0.0,
            intent TEXT DEFAULT ''
        )""")
        conn.commit()
        return conn

    def record(self, session_id: str, model: str, input_tokens: int, output_tokens: int, cost: float, intent: str = "") -> None:
        """Record."""
        try:
            conn = self._get_db()
            now = datetime.now(KST).isoformat()
            conn.execute(
                "INSERT INTO usage_detail (ts, session_id, model, input_tokens, output_tokens, cost, intent) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now, session_id, model, input_tokens, output_tokens, cost, intent),
            )
            conn.commit()
        except Exception as e:
            log.warning(f"Usage tracking error: {e}")

    def daily_report(self, days: int = 7) -> List[Dict]:
        """Daily report."""
        try:
            conn = self._get_db()
            cutoff = (datetime.now(KST) - timedelta(days=days)).isoformat()
            rows = conn.execute(
                "SELECT substr(ts,1,10) as day, model, "
                "SUM(input_tokens) as inp, SUM(output_tokens) as out, "
                "SUM(cost) as total_cost, COUNT(*) as calls "
                "FROM usage_detail WHERE ts >= ? "
                "GROUP BY day, model ORDER BY day DESC",
                (cutoff,),
            ).fetchall()
            return [
                {
                    "date": r[0],
                    "model": r[1],
                    "input_tokens": r[2],
                    "output_tokens": r[3],
                    "cost": round(r[4], 6),
                    "calls": r[5],
                }
                for r in rows
            ]
        except Exception as e:  # noqa: broad-except
            return []

    def monthly_report(self, months: int = 3) -> List[Dict]:
        """Monthly report."""
        try:
            conn = self._get_db()
            cutoff = (datetime.now(KST) - timedelta(days=months * 30)).isoformat()
            rows = conn.execute(
                "SELECT substr(ts,1,7) as month, model, "
                "SUM(input_tokens) as inp, SUM(output_tokens) as out, "
                "SUM(cost) as total_cost, COUNT(*) as calls "
                "FROM usage_detail WHERE ts >= ? "
                "GROUP BY month, model ORDER BY month DESC",
                (cutoff,),
            ).fetchall()
            return [
                {
                    "month": r[0],
                    "model": r[1],
                    "input_tokens": r[2],
                    "output_tokens": r[3],
                    "cost": round(r[4], 6),
                    "calls": r[5],
                }
                for r in rows
            ]
        except Exception as e:  # noqa: broad-except
            return []

    def model_breakdown(self) -> Dict[str, float]:
        """Model breakdown."""
        try:
            conn = self._get_db()
            rows = conn.execute("SELECT model, SUM(cost) FROM usage_detail GROUP BY model").fetchall()
            return {r[0]: round(r[1], 6) for r in rows}
        except Exception as e:  # noqa: broad-except
            return {}


usage_tracker = UsageTracker()
