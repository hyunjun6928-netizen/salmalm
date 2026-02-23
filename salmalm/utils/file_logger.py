"""Structured file logger — JSON Lines format.

구조화 파일 로그 — JSON Lines 형식.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional
from salmalm.constants import DATA_DIR

KST = timezone(timedelta(hours=9))


class FileLogger:
    """JSON Lines 파일 로거."""

    LOG_DIR = DATA_DIR / "logs"

    def __init__(self, log_dir: Optional[Path] = None):
        if log_dir is not None:
            self.LOG_DIR = log_dir
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)

    def log(self, level: str, category: str, message: str, **extra) -> None:
        """JSON 라인 로그 기록."""
        now = datetime.now(KST)
        entry = {
            "ts": now.isoformat(),
            "level": level.upper(),
            "category": category,
            "message": message,
            **extra,
        }
        log_file = self.LOG_DIR / f"salmalm-{now.strftime('%Y-%m-%d')}.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def tail(self, lines: int = 50, level: Optional[str] = None) -> List[dict]:
        """최근 로그 조회."""
        all_entries: List[dict] = []
        log_files = sorted(self.LOG_DIR.glob("salmalm-*.log"), reverse=True)
        for lf in log_files:
            try:
                with open(lf, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if level and entry.get("level", "").upper() != level.upper():
                                continue
                            all_entries.append(entry)
                        except json.JSONDecodeError:
                            continue
            except OSError:
                continue
            if len(all_entries) >= lines * 3:
                break
        # Return most recent entries
        return all_entries[-lines:]

    def search(self, query: str, days: int = 7) -> List[dict]:
        """로그 검색."""
        results: List[dict] = []
        now = datetime.now(KST)
        query_lower = query.lower()
        for day_offset in range(days):
            dt = now - timedelta(days=day_offset)
            log_file = self.LOG_DIR / f"salmalm-{dt.strftime('%Y-%m-%d')}.log"
            if not log_file.exists():
                continue
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if query_lower in line.lower():
                            try:
                                results.append(json.loads(line.strip()))
                            except json.JSONDecodeError:
                                continue
            except OSError:
                continue
        return results

    def cleanup(self, retain_days: int = 30) -> int:
        """오래된 로그 삭제. Returns number of files removed."""
        now = datetime.now(KST)
        removed = 0
        for lf in self.LOG_DIR.glob("salmalm-*.log"):
            try:
                # Parse date from filename
                date_str = lf.stem.replace("salmalm-", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=KST)
                if (now - file_date).days > retain_days:
                    lf.unlink()
                    removed += 1
            except (ValueError, OSError):
                continue
        return removed


# Singleton
file_logger = FileLogger()
