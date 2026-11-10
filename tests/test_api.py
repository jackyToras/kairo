import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from app.agent.llm import LLMStreamEvent, ToolCallRequest
from app.core.config import Settings
from app.main import create_app


class FakeLLMClient:
    """Deterministic fake LLM for testing SSE streaming, tool loop, and memory persistence."""

    def __init__(self) -> None:
        self.calls = 0

    async def stream_chat(
        self,
        config,
        messages,
        tools=None,
        temperature=0.2,
        tool_choice="auto",
    ) -> AsyncIterator[LLMStreamEvent]:
        self.calls += 1
        has_tool_result = any(m.get("role") == "tool" for m in messages)

        if tools and not has_tool_result:
            yield LLMStreamEvent(
                kind="tool_calls",
                tool_calls=[
                    ToolCallRequest(
                        id="call_1",
                        name="web_search",
                        arguments={"query": "FastAPI latest version", "freshness": "month"},
                    )
                ],
            )
            return

        if has_tool_result:
            for tok in ["FastAPI ", "latest ", "is verified [1]."]:
                yield LLMStreamEvent(kind="token", text=tok)
            yield LLMStreamEvent(kind="done", raw_content="FastAPI latest is verified [1].")
            return

        # Direct / memory recall response
        sys_prompt = messages[0]["content"]
        if "FastAPI" in sys_prompt:
            ans = "You asked about FastAPI earlier."
        else:
            ans = "Hello! I am Kairo."
        yield LLMStreamEvent(kind="token", text=ans)
        yield LLMStreamEvent(kind="done", raw_content=ans)


@pytest.mark.asyncio
async def test_api_health_sessions_and_sse_chat_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "api_test.db"
    cfg = Settings(database_path=str(db_path), enable_page_extraction=False)
    app = create_app(cfg)

    fake_results = [
        {
            "title": "FastAPI PyPI",
            "url": "https://pypi.org/project/fastapi/",
            "snippet": "FastAPI framework release history.",
            "published_date": "2026-11-01",
        }
    ]
    async def async_fake_ddgs(*args, **kwargs):
        return fake_results

    monkeypatch.setattr("app.search.web_search._search_ddg_html", async_fake_ddgs)

    async with app.router.lifespan_context(app):
        app.state.orchestrator.llm_client = FakeLLMClient()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            h = await client.get("/api/health")
            assert h.status_code == 200
            h_json = h.json()
            assert h_json["tool_count"] == 1
            assert h_json["tool_names"] == ["web_search"]

            # Chat turn 1: triggers web_search tool + citations + background memory save
            resp = await client.post(
                "/api/chat",
                json={"message": "What is the latest FastAPI version?", "tz_name": "Asia/Kolkata"},
            )
            assert resp.status_code == 200
            body = resp.text
            assert "event: route" in body
            assert "event: citations" in body
            assert "event: token" in body
            assert "event: done" in body
            assert "pypi.org" in body

            # Wait for background memory indexing task
            await app.state.orchestrator.drain_background_tasks()

            # Check memory timeline recorded what & when
            mems = await client.get("/api/memories")
            assert mems.status_code == 200
            mem_list = mems.json()
            assert len(mem_list) == 1
            assert mem_list[0]["user_query"] == "What is the latest FastAPI version?"

            # New session memory-recall query (fast path, 0 web searches)
            resp2 = await client.post(
                "/api/chat",
                json={"message": "What did I ask you earlier today?", "tz_name": "Asia/Kolkata"},
            )
            assert resp2.status_code == 200
            assert "memory_recall" in resp2.text
            assert "FastAPI" in resp2.text

            # Sessions list & messages check
            sess_res = await client.get("/api/sessions")
            assert sess_res.status_code == 200
            sessions = sess_res.json()
            assert len(sessions) == 2

            # Parse done payload from first stream to get session_id
            done_line = [ln for ln in body.splitlines() if ln.startswith("data: ")][-1]
            sid1 = json.loads(done_line[6:])["session_id"]
            msgs = await client.get(f"/api/sessions/{sid1}/messages")
            assert msgs.status_code == 200
            assert len(msgs.json()) == 2
