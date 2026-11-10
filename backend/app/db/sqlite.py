from __future__ import annotations

from pathlib import Path

import aiosqlite

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_ts REAL NOT NULL,
    local_date TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    trace_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_messages_session_ts ON messages(session_id, created_ts);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id TEXT NOT NULL,
    user_query TEXT NOT NULL,
    assistant_summary TEXT NOT NULL,
    topics_json TEXT NOT NULL DEFAULT '[]',
    embedding_model TEXT NOT NULL DEFAULT 'hash-v1',
    embedding_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    created_ts REAL NOT NULL,
    local_date TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_created_ts ON memories(created_ts DESC);
CREATE INDEX IF NOT EXISTS idx_memories_session_ts ON memories(session_id, created_ts DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    memory_id UNINDEXED,
    user_query,
    assistant_summary,
    topics
);

CREATE TABLE IF NOT EXISTS search_cache (
    cache_key TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    freshness TEXT NOT NULL,
    results_json TEXT NOT NULL,
    created_ts REAL NOT NULL,
    expires_ts REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_search_cache_expires ON search_cache(expires_ts);
"""


class Database:
    """Async SQLite manager with WAL mode and FTS5 support."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with self.connect() as conn:
            await conn.executescript(SCHEMA_SQL)
            await conn.commit()

    def connect(self) -> aiosqlite.Connection:
        return aiosqlite.connect(self.db_path)
