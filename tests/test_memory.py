from datetime import datetime, timedelta
from pathlib import Path

import pytest
from app.db.sqlite import Database
from app.memory.embeddings import HybridEmbedder
from app.memory.store import MemoryStore
from app.memory.temporal import resolve_timezone


@pytest.mark.asyncio
async def test_cross_session_temporal_and_topic_recall(tmp_path: Path):
    db = Database(tmp_path / "mem.db")
    await db.init()
    embedder = HybridEmbedder("http://127.0.0.1:59999", "nomic-embed-text")
    store = MemoryStore(db=db, embedder=embedder)

    tz = resolve_timezone("Asia/Kolkata")
    now = datetime(2026, 11, 10, 18, 0, 0, tzinfo=tz)

    # Session 1: 3 days ago (Rust)
    await store.save_turn(
        session_id="sess-1",
        user_query="Why is Rust memory safe without garbage collection?",
        assistant_answer="Rust uses ownership, borrowing, and lifetimes checked at compile time.",
        timestamp=now - timedelta(days=3),
        allow_remote_embed=False,
    )
    # Session 2: Yesterday (Nvidia stock)
    await store.save_turn(
        session_id="sess-2",
        user_query="What is Nvidia's market cap?",
        assistant_answer="Nvidia is valued around several trillion dollars.",
        timestamp=now - timedelta(days=1),
        allow_remote_embed=False,
    )
    # Session 3: Today morning (FastAPI + Rust)
    await store.save_turn(
        session_id="sess-3",
        user_query="Can I combine FastAPI with Rust extensions using PyO3?",
        assistant_answer="Yes, Maturin and PyO3 let you build fast Rust modules for FastAPI.",
        timestamp=now.replace(hour=9, minute=15),
        allow_remote_embed=False,
    )

    # 1. Ask about yesterday specifically
    res_yday = await store.recall(
        query="What did I ask you yesterday?",
        tz_name="Asia/Kolkata",
        now=now,
        allow_remote_embed=False,
    )
    assert len(res_yday.memories) == 1
    assert "Nvidia" in res_yday.memories[0].user_query
    assert "yesterday" in res_yday.memories[0].formatted_time

    # 2. Ask when FIRST asked about Rust -> oldest Rust turn (3 days ago) should rank first!
    res_first_rust = await store.recall(
        query="When did I first ask about Rust?",
        tz_name="Asia/Kolkata",
        now=now,
        allow_remote_embed=False,
    )
    assert len(res_first_rust.memories) >= 1
    assert "ownership" in res_first_rust.memories[0].assistant_summary or "memory safe" in res_first_rust.memories[0].user_query

    # 3. FTS5 punctuation safety check ("C++ vs Rust?!:")
    res_punct = await store.recall(
        query='Did I ever ask about "C++ vs Rust"?!:',
        tz_name="Asia/Kolkata",
        now=now,
        allow_remote_embed=False,
    )
    assert len(res_punct.memories) >= 1


@pytest.mark.asyncio
async def test_memory_timeline_and_session_deletion(tmp_path: Path):
    db = Database(tmp_path / "timeline.db")
    await db.init()
    embedder = HybridEmbedder("http://127.0.0.1:59999", "nomic-embed-text")
    store = MemoryStore(db=db, embedder=embedder)

    await store.save_turn(
        session_id="s-del",
        user_query="Explain SQLite FTS5 ranking",
        assistant_answer="FTS5 uses BM25 ranking by default.",
        allow_remote_embed=False,
    )
    timeline = await store.list_timeline(query="SQLite")
    assert len(timeline) == 1
    assert timeline[0]["user_query"] == "Explain SQLite FTS5 ranking"

    deleted = await store.delete_session("s-del")
    assert deleted is True
    assert await store.list_timeline(query="SQLite") == []
