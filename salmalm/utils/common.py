"""Common helpers — 날짜, JSON, 파일 I/O 공통 유틸."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

log = logging.getLogger(__name__)


# ── Date / Time ──────────────────────────────────────────────────────
def now_kst() -> datetime:
    """Return current datetime in KST."""
    from salmalm.constants import KST
    return datetime.now(KST)


def today_str(fmt: str = "%Y-%m-%d") -> str:
    """Return today's date string in KST."""
    return now_kst().strftime(fmt)


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a datetime object."""
    return dt.strftime(fmt)


# ── JSON ─────────────────────────────────────────────────────────────
def json_loads_safe(text: Union[str, bytes], default: Any = None) -> Any:
    """Parse JSON with fallback to *default* on error."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def json_dumps(obj: Any, *, ensure_ascii: bool = False, **kw) -> str:
    """Compact JSON dump (default ensure_ascii=False for Korean)."""
    return json.dumps(obj, ensure_ascii=ensure_ascii, **kw)


# ── File I/O ─────────────────────────────────────────────────────────
def read_text_safe(path: Union[str, Path], default: str = "") -> str:
    """Read a text file; return *default* if missing or unreadable."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return default


def write_text_atomic(path: Union[str, Path], content: str) -> None:
    """Write text to file, creating parent dirs if needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
