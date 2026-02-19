"""SalmAlm exception hierarchy.

공통 예외 계층 — 모든 모듈에서 사용하는 커스텀 예외.
"""


class SalmAlmError(Exception):
    """Base exception for all SalmAlm errors."""


class LLMError(SalmAlmError, ValueError):
    """LLM API call or response errors."""


class ToolError(SalmAlmError):
    """Tool execution errors."""


class AuthError(SalmAlmError, ValueError):
    """Authentication / authorization errors."""


class ConfigError(SalmAlmError, ValueError):
    """Configuration loading / validation errors."""


class SessionError(SalmAlmError, ValueError):
    """Session management errors."""
