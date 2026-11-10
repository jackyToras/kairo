from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1, max_length=8000)
    tz_name: str | None = None
    tz_offset_minutes: int | None = None
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None


class SessionCreateRequest(BaseModel):
    title: str = Field(default="New Chat", min_length=1, max_length=100)


class SessionItem(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


class MessageItem(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    created_ts: float
    local_date: str
    citations: list[dict[str, Any]]
    trace: dict[str, Any]


class MemoryTimelineItem(BaseModel):
    id: str
    session_id: str
    user_query: str
    assistant_summary: str
    topics: list[str]
    created_at: str
    created_ts: float
    local_date: str
    formatted_time: str


class HealthResponse(BaseModel):
    status: str
    app_name: str
    llm_provider: str
    llm_model: str
    is_free_tier: bool
    is_local: bool
    search_provider: str
    tool_count: int
    tool_names: list[str]
    ollama_reachable: bool | None = None


class ProviderPreset(BaseModel):
    id: str
    label: str
    default_model: str
    requires_key: bool
    cost: str
    notes: str


class ConfigResponse(BaseModel):
    active_provider: str
    active_model: str
    is_free_tier: bool
    is_local: bool
    search_provider: str
    configured_keys: dict[str, bool]
    presets: list[ProviderPreset]
