"""Code Playground — 안전한 코드 실행 환경.

stdlib-only. subprocess 기반 격리, 히스토리 저장.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from salmalm.constants import KST, BASE_DIR
from salmalm.utils.db import connect as _connect_db

log = logging.getLogger(__name__)

PLAYGROUND_DB = BASE_DIR / "playground.db"
EXEC_TIMEOUT = 10  # seconds
MAX_OUTPUT = 4096  # chars


def _get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = _connect_db(db_path or PLAYGROUND_DB, wal=True)
    conn.execute("""CREATE TABLE IF NOT EXISTS play_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lang TEXT NOT NULL,
        code TEXT NOT NULL,
        output TEXT,
        error TEXT,
        exit_code INTEGER,
        exec_time_ms REAL,
        memory_kb INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    conn.commit()
    return conn


class CodePlayground:
    """격리된 코드 실행 환경."""

    def __init__(self, db_path: Optional[Path] = None, timeout: int = EXEC_TIMEOUT):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self.timeout = timeout

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = _get_db(self._db_path)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def run_python(self, code: str) -> Dict:
        """Python 코드 실행 (subprocess 격리)."""
        if not code.strip():
            return {"error": "코드를 입력하세요.", "exit_code": 1}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            tmp_path = f.name

        try:
            start = time.monotonic()
            result = subprocess.run(
                [sys.executable, "-u", tmp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                cwd=tempfile.gettempdir(),
            )
            elapsed = (time.monotonic() - start) * 1000  # ms

            output = result.stdout[:MAX_OUTPUT]
            error = result.stderr[:MAX_OUTPUT]

            record = {
                "lang": "python",
                "code": code,
                "output": output,
                "error": error,
                "exit_code": result.returncode,
                "exec_time_ms": round(elapsed, 2),
                "memory_kb": 0,
            }
            self._save_history(record)
            return record

        except subprocess.TimeoutExpired:
            record = {
                "lang": "python",
                "code": code,
                "output": "",
                "error": f"⏰ 시간 초과 ({self.timeout}초)",
                "exit_code": -1,
                "exec_time_ms": self.timeout * 1000,
                "memory_kb": 0,
            }
            self._save_history(record)
            return record
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def run_js(self, code: str) -> Dict:
        """Node.js 코드 실행."""
        node = shutil.which("node")
        if not node:
            return {"error": "❌ Node.js가 설치되어 있지 않습니다.", "exit_code": -1}

        if not code.strip():
            return {"error": "코드를 입력하세요.", "exit_code": 1}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(code)
            tmp_path = f.name

        try:
            start = time.monotonic()
            result = subprocess.run(
                [node, tmp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=tempfile.gettempdir(),
            )
            elapsed = (time.monotonic() - start) * 1000

            output = result.stdout[:MAX_OUTPUT]
            error = result.stderr[:MAX_OUTPUT]

            record = {
                "lang": "javascript",
                "code": code,
                "output": output,
                "error": error,
                "exit_code": result.returncode,
                "exec_time_ms": round(elapsed, 2),
                "memory_kb": 0,
            }
            self._save_history(record)
            return record

        except subprocess.TimeoutExpired:
            record = {
                "lang": "javascript",
                "code": code,
                "output": "",
                "error": f"⏰ 시간 초과 ({self.timeout}초)",
                "exit_code": -1,
                "exec_time_ms": self.timeout * 1000,
                "memory_kb": 0,
            }
            self._save_history(record)
            return record
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _save_history(self, record: Dict):
        try:
            now = datetime.now(KST).isoformat()
            self.conn.execute(
                "INSERT INTO play_history (lang, code, output, error, exit_code, exec_time_ms, memory_kb, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record["lang"],
                    record["code"],
                    record.get("output", ""),
                    record.get("error", ""),
                    record.get("exit_code", 0),
                    record.get("exec_time_ms", 0),
                    record.get("memory_kb", 0),
                    now,
                ),
            )
            self.conn.commit()
        except Exception as e:
            log.warning(f"Play history save failed: {e}")

    def history(self, limit: int = 10) -> str:
        """실행 히스토리."""
        rows = self.conn.execute(
            "SELECT lang, code, output, error, exit_code, exec_time_ms, created_at "
            "FROM play_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

        if not rows:
            return "📜 실행 히스토리가 비어있습니다."

        lines = ["📜 **코드 실행 히스토리**\n"]
        for r in reversed(rows):
            lang, code, output, error, exit_code, exec_ms, created = r
            status = "✅" if exit_code == 0 else "❌"
            code_preview = code[:60].replace("\n", " ")
            lines.append(f"{status} [{lang}] `{code_preview}` — {exec_ms:.0f}ms")
        return "\n".join(lines)

    def clear_history(self) -> str:
        """히스토리 삭제."""
        self.conn.execute("DELETE FROM play_history")
        self.conn.commit()
        return "🗑️ 히스토리 삭제 완료."

    @staticmethod
    def format_result(record: Dict) -> str:
        """실행 결과 포맷."""
        lang = record.get("lang", "?")
        exit_code = record.get("exit_code", -1)
        status = "✅ 성공" if exit_code == 0 else f"❌ 실패 (exit {exit_code})"
        exec_ms = record.get("exec_time_ms", 0)

        lines = [f"🎮 **{lang.upper()}** 실행 결과 — {status}"]
        lines.append(f"⏱️ {exec_ms:.0f}ms")

        output = record.get("output", "").strip()
        error = record.get("error", "").strip()

        if output:
            lines.append(f"\n```\n{output[:2000]}\n```")
        if error:
            lines.append(f"\n⚠️ stderr:\n```\n{error[:1000]}\n```")
        if not output and not error and exit_code == 0:
            lines.append("\n(출력 없음)")

        return "\n".join(lines)


# ── Singleton ──
_playground: Optional[CodePlayground] = None


def get_playground(db_path: Optional[Path] = None) -> CodePlayground:
    global _playground
    if _playground is None:
        _playground = CodePlayground(db_path)
    return _playground


# ── Command handler ──


async def handle_play_command(cmd: str, session=None, **kw) -> Optional[str]:
    """Handle /play commands."""
    parts = cmd.strip().split(maxsplit=2)
    if len(parts) < 2:
        return (
            "**코드 실행:**\n"
            "`/play python <code>` — Python 실행\n"
            "`/play js <code>` — JavaScript 실행\n"
            "`/play history` — 히스토리\n"
            "`/play clear` — 히스토리 삭제"
        )

    sub = parts[1].lower()
    code = parts[2] if len(parts) > 2 else ""

    pg = get_playground()

    if sub in ("python", "py"):
        if not code:
            return "사용법: `/play python <code>`"
        result = pg.run_python(code)
        return pg.format_result(result)
    elif sub in ("js", "javascript", "node"):
        if not code:
            return "사용법: `/play js <code>`"
        result = pg.run_js(code)
        return pg.format_result(result)
    elif sub == "history":
        limit = 10
        if code and code.isdigit():
            limit = int(code)
        return pg.history(limit)
    elif sub == "clear":
        return pg.clear_history()
    else:
        # Treat as python by default
        code = " ".join(parts[1:])
        result = pg.run_python(code)
        return pg.format_result(result)


# ── Registration ──


def register_play_commands(command_router):
    """Register /play command."""
    from salmalm.features.commands import COMMAND_DEFS

    COMMAND_DEFS["/play"] = "Code playground (python|js|history|clear)"
    if hasattr(command_router, "_prefix_handlers"):
        command_router._prefix_handlers.append(("/play", handle_play_command))


def register_play_tools():
    """Register play tools."""
    from salmalm.tools.tool_registry import register_dynamic

    async def _play_tool(args):
        lang = args.get("language", "python")
        code = args.get("code", "")
        cmd = f"/play {lang} {code}"
        return await handle_play_command(cmd)

    register_dynamic(
        "code_playground",
        _play_tool,
        {
            "name": "code_playground",
            "description": "Execute code in a sandboxed environment (Python, JavaScript)",
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {"type": "string", "enum": ["python", "js"], "description": "Programming language"},
                    "code": {"type": "string", "description": "Code to execute"},
                },
                "required": ["language", "code"],
            },
        },
    )
