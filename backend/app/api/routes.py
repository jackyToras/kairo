from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.agent.orchestrator import AgentOrchestrator
from app.agent.tools import AGENT_TOOLS
from app.api.schemas import (
    ChatRequest,
    ConfigResponse,
    HealthResponse,
    MemoryTimelineItem,
    MessageItem,
    ProviderPreset,
    SessionCreateRequest,
    SessionItem,
)
from app.core.config import Settings
from app.memory.store import MemoryStore

router = APIRouter(prefix="/api", tags=["kairo"])


def _get_store(request: Request) -> MemoryStore:
    return request.app.state.memory_store


def _get_orchestrator(request: Request) -> AgentOrchestrator:
    return request.app.state.orchestrator


def _get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def _check_ollama(base_url: str) -> bool:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    try:
        async with httpx.AsyncClient(timeout=1.2) as client:
            resp = await client.get(f"{root}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = _get_settings(request)
    llm_cfg = settings.resolve_llm()
    ollama_ok = await _check_ollama(settings.ollama_base_url) if llm_cfg.is_local else None
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        llm_provider=llm_cfg.provider,
        llm_model=llm_cfg.model,
        is_free_tier=llm_cfg.is_free_tier,
        is_local=llm_cfg.is_local,
        search_provider=settings.resolve_search_provider(),
        tool_count=len(AGENT_TOOLS),
        tool_names=[t["function"]["name"] for t in AGENT_TOOLS],
        ollama_reachable=ollama_ok,
    )


@router.get("/config", response_model=ConfigResponse)
async def get_config(request: Request) -> ConfigResponse:
    settings = _get_settings(request)
    llm_cfg = settings.resolve_llm()
    return ConfigResponse(
        active_provider=llm_cfg.provider,
        active_model=llm_cfg.model,
        is_free_tier=llm_cfg.is_free_tier,
        is_local=llm_cfg.is_local,
        search_provider=settings.resolve_search_provider(),
        configured_keys={
            "groq": bool(settings.groq_api_key.strip()),
            "gemini": bool(settings.gemini_api_key.strip()),
            "openrouter": bool(settings.openrouter_api_key.strip()),
            "tavily": bool(settings.tavily_api_key.strip()),
            "brave": bool(settings.brave_api_key.strip()),
        },
        presets=[
            ProviderPreset(
                id="ollama",
                label="Ollama (Local, Zero-Key)",
                default_model=settings.ollama_model,
                requires_key=False,
                cost="$0 (Local)",
                notes="Runs locally with zero API keys.",
            ),
            ProviderPreset(
                id="groq",
                label="Groq Free Tier (Fastest)",
                default_model=settings.groq_model,
                requires_key=True,
                cost="$0 Free Tier",
                notes="Sub-second cloud inference with free API key.",
            ),
            ProviderPreset(
                id="gemini",
                label="Google Gemini Free Tier",
                default_model=settings.gemini_model,
                requires_key=True,
                cost="$0 Free Tier",
                notes="Fast Gemini Flash with reliable tool calling.",
            ),
            ProviderPreset(
                id="openrouter",
                label="OpenRouter Free Models",
                default_model=settings.openrouter_model,
                requires_key=True,
                cost="$0 (:free models)",
                notes="Access free open-weight models via OpenRouter.",
            ),
        ],
    )


@router.post("/chat")
async def chat_stream(body: ChatRequest, request: Request) -> StreamingResponse:
    orchestrator = _get_orchestrator(request)
    store = _get_store(request)
    session_id = await store.ensure_session(body.session_id)

    async def event_generator() -> AsyncIterator[str]:
        async for ev in orchestrator.run_stream(
            session_id=session_id,
            user_message=body.message,
            tz_name=body.tz_name,
            tz_offset_minutes=body.tz_offset_minutes,
            override_provider=body.provider,
            override_model=body.model,
            override_api_key=body.api_key,
        ):
            event_name = ev["event"]
            payload = json.dumps(ev["data"], ensure_ascii=False)
            yield f"event: {event_name}\ndata: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session_id,
        },
    )


@router.get("/sessions", response_model=list[SessionItem])
async def list_sessions(request: Request) -> list[SessionItem]:
    store = _get_store(request)
    rows = await store.list_sessions()
    return [SessionItem(**r) for r in rows]


@router.post("/sessions", response_model=SessionItem)
async def create_session(body: SessionCreateRequest, request: Request) -> SessionItem:
    store = _get_store(request)
    sid = str(uuid.uuid4())
    await store.ensure_session(sid, title=body.title)
    sessions = await store.list_sessions()
    created = next((s for s in sessions if s["id"] == sid), None)
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create session")
    return SessionItem(**created)


@router.get("/sessions/{session_id}/messages", response_model=list[MessageItem])
async def get_messages(session_id: str, request: Request) -> list[MessageItem]:
    store = _get_store(request)
    rows = await store.get_session_messages(session_id)
    return [MessageItem(**r) for r in rows]


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict[str, bool]:
    store = _get_store(request)
    deleted = await store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True}


@router.get("/memories", response_model=list[MemoryTimelineItem])
async def list_memories(
    request: Request,
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
    tz_name: str | None = Query(default=None),
    tz_offset_minutes: int | None = Query(default=None),
) -> list[MemoryTimelineItem]:
    store = _get_store(request)
    settings = _get_settings(request)
    rows = await store.list_timeline(
        limit=limit,
        query=q,
        tz_name=tz_name or settings.default_timezone,
        tz_offset_minutes=tz_offset_minutes,
    )
    return [MemoryTimelineItem(**r) for r in rows]
