"""Pydantic request/response schemas for SalmAlm API."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    """Base model: extra fields forbidden (mass-assignment protection)."""
    model_config = ConfigDict(extra="ignore")  # silently ignore unknown fields


# ── Chat ──────────────────────────────────────────────────────
class ChatRequest(_StrictModel):
    message: str = Field(..., description="User message")
    session_id: str = Field("web", description="Session ID")
    model: Optional[str] = Field(None, description="Model override (e.g. 'anthropic/claude-sonnet-4-6')")
    stream: bool = Field(False, description="SSE streaming response")

class ChatResponse(_StrictModel):
    content: str
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    session_id: str = "web"


# ── Auth ──────────────────────────────────────────────────────
class LoginRequest(_StrictModel):
    username: str
    password: str

class LoginResponse(_StrictModel):
    token: str
    expires_in: int
    role: str

class UnlockRequest(_StrictModel):
    password: str

class UnlockResponse(_StrictModel):
    success: bool
    message: str


# ── Sessions ──────────────────────────────────────────────────
class SessionInfo(_StrictModel):
    id: str
    created_at: Optional[str] = None
    message_count: int = 0
    model_override: Optional[str] = None

class SessionListResponse(_StrictModel):
    sessions: List[SessionInfo]

class CreateSessionRequest(_StrictModel):
    session_id: Optional[str] = None
    model: Optional[str] = None


# ── Engine Settings ───────────────────────────────────────────
class EngineSettingsRequest(_StrictModel):
    compaction_threshold: Optional[int] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    planning_enabled: Optional[bool] = None
    reflection_enabled: Optional[bool] = None
    tool_iterations: Optional[int] = None
    cost_cap_daily: Optional[float] = None

class EngineSettingsResponse(_StrictModel):
    compaction_threshold: int
    max_tokens: int
    temperature: float
    planning_enabled: bool
    reflection_enabled: bool
    tool_iterations: int
    cost_cap_daily: Optional[float] = None


# ── Models ────────────────────────────────────────────────────
class ModelInfo(_StrictModel):
    id: str
    provider: str
    available: bool = True

class ModelsResponse(_StrictModel):
    models: List[ModelInfo]

class RoutingConfig(_StrictModel):
    simple: Optional[str] = None
    chat: Optional[str] = None
    complex: Optional[str] = None


# ── Users ─────────────────────────────────────────────────────
class UserCreate(_StrictModel):
    username: str
    password: str
    role: str = "user"

class UserResponse(_StrictModel):
    id: str
    username: str
    role: str
    created_at: Optional[str] = None


# ── Generic ───────────────────────────────────────────────────
class SuccessResponse(_StrictModel):
    success: bool = True
    message: Optional[str] = None

class ErrorResponse(_StrictModel):
    error: str
    detail: Optional[str] = None
