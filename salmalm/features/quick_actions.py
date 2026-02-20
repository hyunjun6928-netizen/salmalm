"""Quick Actions — 자주 사용하는 작업을 단축키로 등록.

stdlib-only. SQLite 저장, 매크로 체인 지원.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from salmalm.constants import KST, BASE_DIR
from salmalm.utils.db import connect as _connect_db

log = logging.getLogger(__name__)

QA_DB = BASE_DIR / "quick_actions.db"


def _get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = _connect_db(db_path or QA_DB, wal=True)
    conn.execute("""CREATE TABLE IF NOT EXISTS quick_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        commands TEXT NOT NULL,
        description TEXT DEFAULT '',
        usage_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    conn.commit()
    return conn


class QuickActionManager:
    """단축 액션 관리자."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._command_dispatcher: Optional[Callable] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = _get_db(self._db_path)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def set_dispatcher(self, dispatcher: Callable):
        """Set command dispatcher for executing chains."""
        self._command_dispatcher = dispatcher

    def add(self, name: str, commands: str, description: str = "") -> str:
        """단축 액션 등록."""
        name = name.strip()
        commands = commands.strip()
        if not name:
            return "❌ 액션 이름을 입력하세요."
        if not commands:
            return "❌ 명령어를 입력하세요."

        now = datetime.now(KST).isoformat()
        try:
            self.conn.execute(
                "INSERT INTO quick_actions (name, commands, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, commands, description, now, now))
            self.conn.commit()
            cmd_count = len(self._parse_chain(commands))
            return f"✅ 액션 '{name}' 등록 ({cmd_count}개 명령어)"
        except sqlite3.IntegrityError:
            self.conn.execute(
                "UPDATE quick_actions SET commands=?, description=?, updated_at=? WHERE name=?",
                (commands, description, now, name))
            self.conn.commit()
            return f"✅ 액션 '{name}' 업데이트됨"

    def remove(self, name: str) -> str:
        """액션 삭제."""
        name = name.strip()
        cur = self.conn.execute("SELECT id FROM quick_actions WHERE name=?", (name,))
        if not cur.fetchone():
            return f"❌ '{name}' 액션을 찾을 수 없습니다."
        self.conn.execute("DELETE FROM quick_actions WHERE name=?", (name,))
        self.conn.commit()
        return f"🗑️ 액션 '{name}' 삭제됨."

    def get(self, name: str) -> Optional[Dict]:
        """액션 조회."""
        row = self.conn.execute(
            "SELECT name, commands, description, usage_count, created_at "
            "FROM quick_actions WHERE name=?",
            (name,)).fetchone()
        if not row:
            return None
        return {
            "name": row[0], "commands": row[1], "description": row[2],
            "usage_count": row[3], "created_at": row[4],
        }

    def list_all(self) -> str:
        """목록."""
        rows = self.conn.execute(
            "SELECT name, commands, description, usage_count "
            "FROM quick_actions ORDER BY usage_count DESC").fetchall()

        if not rows:
            return "📋 등록된 액션이 없습니다. `/qa add <name> <command>`로 추가하세요."

        lines = ["⚡ **Quick Actions**\n"]
        for name, commands, desc, count in rows:
            cmd_preview = commands[:50]
            desc_str = f" — {desc}" if desc else ""
            lines.append(f"• **{name}**{desc_str}\n  `{cmd_preview}` (사용 {count}회)")
        return "\n".join(lines)

    async def run(self, name: str, dispatcher=None) -> str:
        """액션 실행."""
        name = name.strip()
        action = self.get(name)
        if not action:
            return f"❌ '{name}' 액션을 찾을 수 없습니다."

        # Update usage count
        self.conn.execute(
            "UPDATE quick_actions SET usage_count = usage_count + 1 WHERE name=?",
            (name,))
        self.conn.commit()

        commands = self._parse_chain(action["commands"])
        dispatch = dispatcher or self._command_dispatcher

        results = []
        for cmd in commands:
            cmd = cmd.strip()
            if not cmd:
                continue
            if dispatch:
                try:
                    import asyncio
                    result = dispatch(cmd)
                    if asyncio.iscoroutine(result):
                        result = await result
                    if result:
                        results.append(f"▶ `{cmd}`\n{result}")
                    else:
                        results.append(f"▶ `{cmd}` — (응답 없음)")
                except Exception as e:
                    results.append(f"▶ `{cmd}` — ❌ {e}")
            else:
                results.append(f"▶ `{cmd}` — (디스패처 미설정)")

        if not results:
            return f"⚡ '{name}' 실행 완료 (명령어 없음)"

        return f"⚡ **{name}** 실행 결과:\n\n" + "\n\n".join(results)

    @staticmethod
    def _parse_chain(commands: str) -> List[str]:
        """Parse command chain. Supports && and quoted strings."""
        # Split by && but respect quotes
        parts = []
        current = ""
        in_quote = False
        quote_char = ""

        for ch in commands:
            if ch in ('"', "'") and not in_quote:
                in_quote = True
                quote_char = ch
                # Don't add quote char to current for commands starting with quote
                continue
            elif ch == quote_char and in_quote:
                in_quote = False
                continue
            elif ch == '&' and not in_quote and current.endswith('&'):
                # Found &&
                current = current[:-1]  # Remove trailing &
                if current.strip():
                    parts.append(current.strip())
                current = ""
                continue
            current += ch

        if current.strip():
            parts.append(current.strip())

        return parts

    def rename(self, old_name: str, new_name: str) -> str:
        """액션 이름 변경."""
        if not self.get(old_name):
            return f"❌ '{old_name}' 액션을 찾을 수 없습니다."
        now = datetime.now(KST).isoformat()
        try:
            self.conn.execute(
                "UPDATE quick_actions SET name=?, updated_at=? WHERE name=?",
                (new_name, now, old_name))
            self.conn.commit()
            return f"✅ '{old_name}' → '{new_name}' 이름 변경됨."
        except sqlite3.IntegrityError:
            return f"❌ '{new_name}' 이름이 이미 존재합니다."


# ── Singleton ──
_qa: Optional[QuickActionManager] = None


def get_qa(db_path: Optional[Path] = None) -> QuickActionManager:
    global _qa
    if _qa is None:
        _qa = QuickActionManager(db_path)
    return _qa


# ── Command handler ──

async def handle_qa_command(cmd: str, session=None, **kw) -> Optional[str]:
    """Handle /qa commands."""
    parts = cmd.strip().split(maxsplit=3)
    if len(parts) < 2:
        return get_qa().list_all()

    sub = parts[1].lower()
    qa = get_qa()

    if sub == "add":
        if len(parts) < 4:
            return "사용법: `/qa add <name> <command(s)>`\n예: `/qa add morning \"/briefing && /habit remind\"`"
        name = parts[2]
        commands = parts[3]
        return qa.add(name, commands)
    elif sub == "remove" or sub == "delete":
        if len(parts) < 3:
            return "사용법: `/qa remove <name>`"
        return qa.remove(parts[2])
    elif sub == "run":
        if len(parts) < 3:
            return "사용법: `/qa run <name>`"
        dispatcher = kw.get("dispatcher")
        return await qa.run(parts[2], dispatcher)
    elif sub == "list":
        return qa.list_all()
    elif sub == "show":
        if len(parts) < 3:
            return "사용법: `/qa show <name>`"
        action = qa.get(parts[2])
        if not action:
            return f"❌ '{parts[2]}' 액션을 찾을 수 없습니다."
        return (
            f"⚡ **{action['name']}**\n"
            f"명령어: `{action['commands']}`\n"
            f"사용 횟수: {action['usage_count']}\n"
            f"등록: {action['created_at']}"
        )
    elif sub == "rename":
        if len(parts) < 4:
            return "사용법: `/qa rename <old> <new>`"
        return qa.rename(parts[2], parts[3])
    else:
        return (
            "**Quick Actions 명령어:**\n"
            "`/qa add <name> <command>` — 액션 등록\n"
            "`/qa run <name>` — 실행\n"
            "`/qa list` — 목록\n"
            "`/qa show <name>` — 상세\n"
            "`/qa remove <name>` — 삭제\n"
            "`/qa rename <old> <new>` — 이름 변경"
        )


# ── Registration ──

def register_qa_commands(command_router):
    """Register /qa command."""
    from salmalm.features.commands import COMMAND_DEFS
    COMMAND_DEFS['/qa'] = 'Quick actions (add|run|list|show|remove|rename)'
    if hasattr(command_router, '_prefix_handlers'):
        command_router._prefix_handlers.append(('/qa', handle_qa_command))


def register_qa_tools():
    """Register qa tools."""
    from salmalm.tools.tool_registry import register_dynamic

    async def _qa_tool(args):
        sub = args.get("subcommand", "list")
        name = args.get("name", "")
        commands = args.get("commands", "")
        cmd = f"/qa {sub} {name} {commands}".strip()
        return await handle_qa_command(cmd)

    register_dynamic("quick_actions", _qa_tool, {
        "name": "quick_actions",
        "description": "Quick actions - register and run command shortcuts/macros",
        "parameters": {
            "type": "object",
            "properties": {
                "subcommand": {
                    "type": "string",
                    "enum": ["add", "run", "list", "show", "remove"],
                },
                "name": {"type": "string"},
                "commands": {"type": "string", "description": "Commands for add"},
            },
            "required": ["subcommand"]
        }
    })
