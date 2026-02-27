"""Pydantic request/response schemas for SalmAlm API."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Chat ──────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: str = Field("web", description="Session ID")
    model: Optional[str] = Field(None, description="Model override (e.g. 'anthropic/claude-sonnet-4-6')")
    stream: bool = Field(False, description="SSE streaming response")

class ChatResponse(BaseModel):
    content: str
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    session_id: str = "web"


# ── Auth ──────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str
    expires_in: int
    role: str

class UnlockRequest(BaseModel):
    password: str

class UnlockResponse(BaseModel):
    success: bool
    message: str


# ── Sessions ──────────────────────────────────────────────────
class SessionInfo(BaseModel):
    id: str
    created_at: Optional[str] = None
    message_count: int = 0
    model_override: Optional[str] = None

class SessionListResponse(BaseModel):
    sessions: List[SessionInfo]

class CreateSessionRequest(BaseModel):
    session_id: Optional[str] = None
    model: Optional[str] = None


# ── Engine Settings ───────────────────────────────────────────
class EngineSettingsRequest(BaseModel):
    compaction_threshold: Optional[int] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    planning_enabled: Optional[bool] = None
    reflection_enabled: Optional[bool] = None
    tool_iterations: Optional[int] = None
    cost_cap_daily: Optional[float] = None

class EngineSettingsResponse(BaseModel):
    compaction_threshold: int
    max_tokens: int
    temperature: float
    planning_enabled: bool
    reflection_enabled: bool
    tool_iterations: int
    cost_cap_daily: Optional[float] = None


# ── Models ────────────────────────────────────────────────────
class ModelInfo(BaseModel):
    id: str
    provider: str
    available: bool = True

class ModelsResponse(BaseModel):
    models: List[ModelInfo]

class RoutingConfig(BaseModel):
    simple: Optional[str] = None
    chat: Optional[str] = None
    complex: Optional[str] = None


# ── Users ─────────────────────────────────────────────────────
class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"

class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    created_at: Optional[str] = None


# ── Generic ───────────────────────────────────────────────────
class SuccessResponse(BaseModel):
    success: bool = True
    message: Optional[str] = None

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
