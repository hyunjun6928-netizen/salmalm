"""User-friendly error messages — bilingual KR/EN mapping."""

from __future__ import annotations

# ── Error type → friendly message mapping ──
_ERROR_MAP = {
    "AttributeError": "⚠️ 일시적 내부 오류가 발생했습니다. 다시 시도해주세요.\n(Internal error — please retry.)",
    "KeyError": "⚠️ 설정 오류가 감지되었습니다. `/status`로 상태를 확인해주세요.\n(Configuration error — check `/status`.)",
    "ConnectionError": "🌐 AI 서버에 연결할 수 없습니다. 인터넷 연결을 확인해주세요.\n(Cannot reach AI server — check your connection.)",
    "TimeoutError": "⏰ 응답 시간이 초과되었습니다. 다시 시도해주세요.\n(Response timed out — please retry.)",
    "AuthenticationError": "🔑 API 키가 유효하지 않습니다. 설정에서 확인해주세요.\n(Invalid API key — check Settings.)",
    "RateLimitError": "🚦 요청 한도에 도달했습니다. 잠시 후 다시 시도해주세요.\n(Rate limited — please wait a moment.)",
    "InsufficientQuotaError": "💳 API 크레딧이 부족합니다. 제공사 대시보드를 확인해주세요.\n(Insufficient API credits.)",
}

_GENERIC_ERROR = "⚠️ 처리 중 오류가 발생했습니다. 다시 시도해주세요.\n(An error occurred — please retry.)"


def friendly_error(exc: Exception) -> str:
    """Convert raw exception to user-friendly bilingual error message.

    Checks exception type name, MRO chain, then common patterns in message text.
    """
    exc_type = type(exc).__name__
    if exc_type in _ERROR_MAP:
        return _ERROR_MAP[exc_type]
    for cls in type(exc).__mro__:
        if cls.__name__ in _ERROR_MAP:
            return _ERROR_MAP[cls.__name__]
    msg_lower = str(exc).lower()
    if "api key" in msg_lower or "authentication" in msg_lower or "401" in msg_lower:
        return _ERROR_MAP["AuthenticationError"]
    if "rate limit" in msg_lower or "429" in msg_lower:
        return _ERROR_MAP["RateLimitError"]
    if "timeout" in msg_lower:
        return _ERROR_MAP["TimeoutError"]
    if "connection" in msg_lower or "unreachable" in msg_lower:
        return _ERROR_MAP["ConnectionError"]
    return _GENERIC_ERROR
