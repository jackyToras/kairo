from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

# Allow running directly as `python evals/run_evals.py`
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.agent.router import route_query  # noqa: E402
from app.agent.tools import AGENT_TOOLS  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.db.sqlite import Database  # noqa: E402
from app.memory.embeddings import HybridEmbedder  # noqa: E402
from app.memory.store import MemoryStore  # noqa: E402
from app.memory.temporal import parse_temporal_query, resolve_timezone  # noqa: E402
from app.search.cache import SearchCache  # noqa: E402
from app.search.web_search import WebSearchService  # noqa: E402


async def eval_temporal_memory() -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "eval_mem.db")
        await db.init()
        embedder = HybridEmbedder("http://127.0.0.1:59999", "nomic-embed-text")
        store = MemoryStore(db=db, embedder=embedder)

        tz = resolve_timezone("Asia/Kolkata")
        now = datetime(2026, 11, 10, 18, 0, 0, tzinfo=tz)

        seeded = [
            ("s1", "How does Rust borrow checker work?", "Ownership & lifetimes prevent data races.", now - timedelta(days=5)),
            ("s1", "What is FastAPI lifespan?", "Async context manager for startup and shutdown.", now - timedelta(days=2)),
            ("s2", "Compare Groq vs Gemini free tier", "Groq offers ultra-fast Llama inference; Gemini offers 2.5 Flash.", now - timedelta(days=1, hours=4)),  # yesterday 14:00
            ("s2", "Best SQLite FTS5 indexing tips", "Use standalone FTS5 table with BM25 ranking.", now - timedelta(days=1, hours=10)),  # yesterday 08:00
            ("s3", "How to optimize Rust PyO3 bindings?", "Use Maturin and minimize Python GIL crossings.", now - timedelta(hours=3)),  # today 15:00
        ]

        for sid, q, a, ts in seeded:
            await store.save_turn(
                session_id=sid,
                user_query=q,
                assistant_answer=a,
                timestamp=ts,
                allow_remote_embed=False,
            )

        cases = [
            {
                "name": "yesterday_afternoon_window",
                "query": "What did I ask you yesterday afternoon?",
                "check": lambda mems: len(mems) >= 1 and "Groq" in mems[0].user_query,
            },
            {
                "name": "earliest_topic_recall",
                "query": "When did I first ask about Rust?",
                "check": lambda mems: len(mems) >= 1 and "borrow checker" in mems[0].user_query,
            },
            {
                "name": "relative_days_ago",
                "query": "What did I ask 2 days ago?",
                "check": lambda mems: len(mems) == 1 and "FastAPI lifespan" in mems[0].user_query,
            },
            {
                "name": "today_topic_recall",
                "query": "What did I ask earlier today about Rust?",
                "check": lambda mems: len(mems) >= 1 and "PyO3" in mems[0].user_query,
            },
            {
                "name": "negative_abstention_check",
                "query": "Did I ever ask about quantum computing?",
                "check": lambda mems: len(mems) == 0,
            },
        ]

        latencies: list[float] = []
        passed = 0
        details = []
        for c in cases:
            res = await store.recall(
                query=c["query"],
                tz_name="Asia/Kolkata",
                now=now,
                allow_remote_embed=False,
            )
            latencies.append(res.elapsed_ms)
            ok = bool(c["check"](res.memories))
            if ok:
                passed += 1
            details.append({"case": c["name"], "passed": ok, "elapsed_ms": res.elapsed_ms, "hits": len(res.memories)})

        return {
            "passed": passed,
            "total": len(cases),
            "accuracy_pct": round(100.0 * passed / len(cases), 1),
            "p50_ms": round(statistics.median(latencies), 2),
            "p95_ms": round(max(latencies), 2),
            "details": details,
        }


def eval_router_and_tool_invariant() -> dict:
    assert len(AGENT_TOOLS) == 1 and AGENT_TOOLS[0]["function"]["name"] == "web_search"
    tz = resolve_timezone("Asia/Kolkata")
    now = datetime(2026, 11, 10, 18, 0, 0, tzinfo=tz)

    cases = [
        ("Hi!", False, "direct"),
        ("Thanks!", False, "direct"),
        ("What did I ask you yesterday?", True, "memory_recall"),
        ("When did I first ask about Rust?", True, "memory_recall"),
        ("Check the current stock price of the company I asked about yesterday", True, "hybrid_memory_web"),
        ("What is the latest FastAPI version today?", False, "web_search"),
        ("Who won the 2026 World Series?", False, "web_search"),
        ("Explain Python asyncio event loop", False, "direct"),
        ("Compare Python 3.13 vs 3.12 benchmark performance?", False, "web_search"),
    ]

    passed = 0
    latencies: list[float] = []
    for query, has_mem, expected in cases:
        plan = parse_temporal_query(query, now=now)
        dec = route_query(query, plan, has_memories=has_mem)
        latencies.append(dec.elapsed_ms)
        if dec.mode == expected:
            passed += 1

    return {
        "single_tool_invariant": len(AGENT_TOOLS) == 1 and AGENT_TOOLS[0]["function"]["name"] == "web_search",
        "passed": passed,
        "total": len(cases),
        "accuracy_pct": round(100.0 * passed / len(cases), 1),
        "p50_ms": round(statistics.median(latencies), 3),
    }


async def eval_live_web_search() -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "eval_search.db")
        await db.init()
        cfg = Settings(database_path=str(Path(tmpdir) / "eval_search.db"))
        cache = SearchCache(db=db)
        svc = WebSearchService(settings=cfg, cache=cache)

        t0 = time.perf_counter()
        out1 = await svc.execute("FastAPI Python framework", freshness="any", deep_extract=True)
        uncached_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        t1 = time.perf_counter()
        out2 = await svc.execute("FastAPI Python framework", freshness="any", deep_extract=True)
        cached_ms = round((time.perf_counter() - t1) * 1000.0, 2)

        return {
            "provider": out1.provider,
            "sources_returned": len(out1.sources),
            "extracted_excerpts": sum(1 for s in out1.sources if s.excerpt),
            "uncached_ms": uncached_ms,
            "cached_ms": cached_ms,
            "cache_hit_verified": out2.cache_hit,
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run Kairo evaluation suite.")
    parser.add_argument("--live", action="store_true", help="Include live DuckDuckGo web_search benchmark.")
    args = parser.parse_args()

    mem_res = await eval_temporal_memory()
    router_res = eval_router_and_tool_invariant()
    report = {
        "temporal_memory_eval": mem_res,
        "router_and_invariant_eval": router_res,
    }
    if args.live:
        report["live_web_search_eval"] = await eval_live_web_search()

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
