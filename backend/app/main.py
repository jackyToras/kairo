from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent.llm import LLMClient
from app.agent.orchestrator import AgentOrchestrator
from app.api.routes import router as api_router
from app.core.config import Settings, get_settings
from app.core.logging import logger
from app.db.sqlite import Database
from app.memory.embeddings import HybridEmbedder
from app.memory.store import MemoryStore
from app.search.cache import SearchCache
from app.search.web_search import WebSearchService


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(cfg.db_file)
        await db.init()

        embedder = HybridEmbedder(
            ollama_base_url=cfg.ollama_base_url,
            embed_model=cfg.ollama_embed_model,
        )
        memory_store = MemoryStore(db=db, embedder=embedder)
        search_cache = SearchCache(
            db=db,
            default_ttl=cfg.search_cache_ttl_seconds,
            breaking_ttl=cfg.breaking_cache_ttl_seconds,
        )
        search_service = WebSearchService(settings=cfg, cache=search_cache)
        llm_client = LLMClient(timeout_seconds=cfg.llm_timeout_seconds)
        orchestrator = AgentOrchestrator(
            settings=cfg,
            memory_store=memory_store,
            search_service=search_service,
            llm_client=llm_client,
        )

        app.state.settings = cfg
        app.state.db = db
        app.state.memory_store = memory_store
        app.state.search_service = search_service
        app.state.orchestrator = orchestrator

        llm_cfg = cfg.resolve_llm()
        logger.info(
            "Kairo initialized | llm=%s (%s) | search=%s | db=%s",
            llm_cfg.provider,
            llm_cfg.model,
            cfg.resolve_search_provider(),
            cfg.db_file,
        )
        yield
        await orchestrator.drain_background_tasks()

    app = FastAPI(
        title="Kairo — Single-Tool Grounded Chat Agent",
        version="0.1.0",
        description="Fast, source-grounded chat agent with strictly one tool (web_search) and hybrid temporal-semantic memory.",
        lifespan=lifespan,
    )

    origins = [o.strip() for o in cfg.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Session-Id"],
    )

    app.include_router(api_router)

    # Serve built React SPA if frontend/dist exists (single-command production run)
    repo_root = Path(__file__).resolve().parents[2]
    dist_dir = repo_root / "frontend" / "dist"
    if dist_dir.is_dir():
        assets_dir = dist_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API endpoint not found")
            target = dist_dir / full_path
            if full_path and target.is_file():
                return FileResponse(target)
            return FileResponse(dist_dir / "index.html")

    return app


app = create_app()
