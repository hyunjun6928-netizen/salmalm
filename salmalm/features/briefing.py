"""Daily Briefing — morning/evening summary generator.

매일 아침 자동 요약: 날씨, 일정, 이메일, 미완료 작업.
"""

from salmalm.security.crypto import log
from datetime import datetime
from salmalm.constants import KST

# Default config
_DEFAULT_CONFIG = {
    "morning_time": "07:30",
    "evening_time": "22:00",
    "timezone": "Asia/Seoul",
    "include": ["weather", "calendar", "email", "tasks", "reminders"],
    "weather_location": "Seoul",
    "greeting": True,
}


from salmalm.config_manager import ConfigManager


def _load_config() -> dict:
    """Load briefing config from ~/.salmalm/briefing.json or defaults."""
    return ConfigManager.load("briefing", defaults=_DEFAULT_CONFIG)


def _save_config(config: dict):
    """Save config."""
    ConfigManager.save("briefing", config)


class DailyBriefing:
    """Generate daily briefing summaries."""

    def __init__(self) -> None:
        """Init  ."""
        self.config = _load_config()

    def generate(self, sections: list = None) -> str:
        """Generate a full briefing. sections: list of section names to include."""
        config = _load_config()
        include = sections or config.get("include", _DEFAULT_CONFIG["include"])
        now = datetime.now(KST)
        parts = []

        # Greeting
        if config.get("greeting", True):
            _GREETINGS = [(12, "🌅 좋은 아침이에요!"), (18, "☀️ 좋은 오후예요!"), (24, "🌙 좋은 저녁이에요!")]
            greeting = next(g for h, g in _GREETINGS if now.hour < h)
            parts.append(f"{greeting}\n📋 **{now.strftime('%Y년 %m월 %d일 %A')}** 브리핑\n")

        # Weather
        if "weather" in include:
            try:
                from salmalm.tools.tool_registry import execute_tool

                location = config.get("weather_location", "Seoul")
                result = execute_tool("weather", {"location": location, "format": "full", "lang": "ko"})
                parts.append(f"**🌤️ 날씨**\n{result}\n")
            except Exception as e:
                parts.append(f"**🌤️ 날씨** — 조회 실패: {e}\n")

        # Calendar
        if "calendar" in include:
            try:
                from salmalm.tools.tool_registry import execute_tool

                result = execute_tool("calendar_list", {"period": "today"})
                parts.append(f"**📅 오늘 일정**\n{result}\n")
            except Exception as e:
                parts.append(f"**📅 일정** — 조회 실패: {e}\n")

        # Email
        if "email" in include:
            try:
                from salmalm.tools.tool_registry import execute_tool

                result = execute_tool("email_inbox", {"count": 5})
                parts.append(f"**📧 최근 이메일**\n{result}\n")
            except Exception as e:
                parts.append(f"**📧 이메일** — 조회 실패: {e}\n")

        # Tasks (incomplete reminders)
        if "tasks" in include or "reminders" in include:
            try:
                from salmalm.tools.tool_registry import execute_tool

                result = execute_tool("reminder", {"action": "list"})
                if "⏰ No active" not in result:
                    parts.append(f"**⏰ 활성 리마인더**\n{result}\n")
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")

        # Notes summary (recent)
        if "notes" in include:
            try:
                from salmalm.tools.tool_registry import execute_tool

                result = execute_tool("note", {"action": "list", "count": 3})
                if "📝 No notes" not in result:
                    parts.append(f"**📝 최근 메모**\n{result}\n")
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")

        # Expenses today
        if "expenses" in include:
            try:
                from salmalm.tools.tool_registry import execute_tool

                result = execute_tool("expense", {"action": "today"})
                if "💰 No expenses" not in result:
                    parts.append(f"**💸 오늘 지출**\n{result}\n")
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")

        if not parts:
            return "📋 브리핑 항목이 없습니다."

        return "\n".join(parts)

    def configure(self, key: str, value: str) -> str:
        """Update briefing config."""
        config = _load_config()
        if key == "include" and isinstance(value, str):
            value = [v.strip() for v in value.split(",")]
        config[key] = value
        _save_config(config)
        self.config = config
        return f"✅ 브리핑 설정 업데이트: {key} = {value}"


# Singleton
daily_briefing = DailyBriefing()
