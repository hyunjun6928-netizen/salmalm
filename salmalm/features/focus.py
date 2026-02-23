"""Focus Mode — 집중 모드.

특정 주제/프로젝트에 대해서만 응답, off-topic 차단.
stdlib-only.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional


log = logging.getLogger(__name__)


class FocusSession:
    """Single focus session data."""

    def __init__(self, topic: str) -> None:
        """Init  ."""
        self.topic = topic
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.on_topic_count = 0
        self.off_topic_count = 0
        self.total_messages = 0

    @property
    def active(self) -> bool:
        """Active."""
        return self.end_time is None

    @property
    def duration_seconds(self) -> float:
        """Duration seconds."""
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def duration_str(self) -> str:
        """Duration str."""
        s = int(self.duration_seconds)
        h, m = divmod(s, 3600)
        m, sec = divmod(m, 60)
        if h:
            return f"{h}시간 {m}분"
        elif m:
            return f"{m}분 {sec}초"
        return f"{sec}초"

    def end(self) -> None:
        """End."""
        self.end_time = time.time()

    def to_dict(self) -> Dict:
        """To dict."""
        return {
            "topic": self.topic,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "on_topic": self.on_topic_count,
            "off_topic": self.off_topic_count,
            "total": self.total_messages,
            "duration": self.duration_str,
        }


class FocusManager:
    """집중 모드 관리자."""

    def __init__(self) -> None:
        """Init  ."""
        self._sessions: Dict[str, FocusSession] = {}  # user_id -> session
        self._history: list = []

    def start(self, topic: str, user_id: str = "default") -> str:
        """집중 모드 시작."""
        topic = topic.strip()
        if not topic:
            return "❌ 집중할 주제를 입력하세요."

        if user_id in self._sessions and self._sessions[user_id].active:
            old = self._sessions[user_id]
            old.end()
            self._history.append(old)

        session = FocusSession(topic)
        self._sessions[user_id] = session
        return f"🎯 **집중 모드 시작**: {topic}\n관련 없는 메시지는 차단됩니다."

    def end(self, user_id: str = "default") -> str:
        """집중 모드 종료."""
        session = self._sessions.get(user_id)
        if not session or not session.active:
            return "ℹ️ 현재 집중 모드가 아닙니다."

        session.end()
        self._history.append(session)
        stats = session.to_dict()

        return (
            f"🏁 **집중 모드 종료**: {session.topic}\n"
            f"⏱️ 소요 시간: {stats['duration']}\n"
            f"📊 메시지: {stats['total']}개 (관련 {stats['on_topic']} / 차단 {stats['off_topic']})"
        )

    def is_focused(self, user_id: str = "default") -> bool:
        """현재 집중 모드인지."""
        session = self._sessions.get(user_id)
        return session is not None and session.active

    def get_topic(self, user_id: str = "default") -> Optional[str]:
        """현재 집중 주제."""
        session = self._sessions.get(user_id)
        if session and session.active:
            return session.topic
        return None

    def check_message(self, message: str, user_id: str = "default") -> Optional[str]:
        """메시지가 주제와 관련 있는지 체크.

        Returns None if on-topic or not focused, otherwise returns block message.
        """
        session = self._sessions.get(user_id)
        if not session or not session.active:
            return None

        session.total_messages += 1

        # Check if message is related to topic
        if self._is_on_topic(message, session.topic):
            session.on_topic_count += 1
            return None  # Allow
        else:
            session.off_topic_count += 1
            return f"🎯 현재 **{session.topic}**에 집중 중입니다. 관련 주제로 질문해주세요."

    def _is_on_topic(self, message: str, topic: str) -> bool:
        """주제 관련성 검사 (키워드 기반)."""
        msg_lower = message.lower()
        topic_lower = topic.lower()

        # Direct topic mention
        if topic_lower in msg_lower:
            return True

        # Topic words overlap
        topic_words = set(topic_lower.split())
        msg_words = set(msg_lower.split())
        if topic_words & msg_words:
            return True

        # Commands are always on-topic
        if message.strip().startswith("/"):
            return True

        # Short messages (< 3 words) might be continuations
        if len(msg_words) < 3:
            return True

        return False

    def status(self, user_id: str = "default") -> str:
        """현재 상태."""
        session = self._sessions.get(user_id)
        if not session or not session.active:
            return "ℹ️ 집중 모드 비활성. `/focus start <주제>`로 시작하세요."

        stats = session.to_dict()
        return (
            f"🎯 **집중 모드**: {session.topic}\n"
            f"⏱️ 경과: {stats['duration']}\n"
            f"📊 메시지: {stats['total']}개 (관련 {stats['on_topic']} / 차단 {stats['off_topic']})"
        )

    def history_summary(self) -> str:
        """세션 히스토리."""
        if not self._history:
            return "📜 집중 세션 히스토리가 없습니다."

        lines = ["📜 **집중 세션 히스토리**\n"]
        for s in self._history[-10:]:
            d = s.to_dict()
            lines.append(f"• **{d['topic']}** — {d['duration']} (메시지 {d['total']}개, 차단 {d['off_topic']}개)")
        return "\n".join(lines)


# ── Singleton ──
_manager: Optional[FocusManager] = None


def get_focus_manager() -> FocusManager:
    """Get focus manager."""
    global _manager
    if _manager is None:
        _manager = FocusManager()
    return _manager


# ── Command handler ──


async def handle_focus_command(cmd: str, session=None, **kw) -> Optional[str]:
    """Handle /focus commands."""
    parts = cmd.strip().split(maxsplit=2)
    if len(parts) < 2:
        return get_focus_manager().status()

    sub = parts[1].lower()
    arg = parts[2].strip() if len(parts) > 2 else ""
    user_id = kw.get("user_id", "default")

    fm = get_focus_manager()

    if sub == "start":
        if not arg:
            return "사용법: `/focus start <주제>`"
        return fm.start(arg, user_id)
    elif sub == "end" or sub == "stop":
        return fm.end(user_id)
    elif sub == "status":
        return fm.status(user_id)
    elif sub == "history":
        return fm.history_summary()
    else:
        return (
            "**집중 모드 명령어:**\n"
            "`/focus start <topic>` — 집중 모드 시작\n"
            "`/focus end` — 종료\n"
            "`/focus status` — 현재 상태\n"
            "`/focus history` — 세션 히스토리"
        )


# ── Registration ──


def register_focus_commands(command_router) -> None:
    """Register /focus command."""
    from salmalm.features.commands import COMMAND_DEFS

    COMMAND_DEFS["/focus"] = "Focus mode (start|end|status|history)"
    if hasattr(command_router, "_prefix_handlers"):
        command_router._prefix_handlers.append(("/focus", handle_focus_command))


def register_focus_tools():
    """Register focus tools."""
    from salmalm.tools.tool_registry import register_dynamic

    async def _focus_tool(args):
        """Focus tool."""
        sub = args.get("subcommand", "status")
        topic = args.get("topic", "")
        cmd = f"/focus {sub} {topic}".strip()
        return await handle_focus_command(cmd)

    register_dynamic(
        "focus_mode",
        _focus_tool,
        {
            "name": "focus_mode",
            "description": "Focus mode - restrict responses to a specific topic",
            "parameters": {
                "type": "object",
                "properties": {
                    "subcommand": {
                        "type": "string",
                        "enum": ["start", "end", "status", "history"],
                    },
                    "topic": {"type": "string", "description": "Topic for focus mode"},
                },
                "required": ["subcommand"],
            },
        },
    )
