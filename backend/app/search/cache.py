from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from app.db.sqlite import Database


def normalize_cache_query(query: str) -> str:
    cleaned = re.sub(r"\s+", " ", query.strip().lower())
    return cleaned.strip("?!. ")


def make_cache_key(query: str, freshness: str) -> str:
    raw = f"{normalize_cache_query(query)}|{freshness or 'any'}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SearchCache:
    """SQLite TTL-based cache for web_search results."""

    def __init__(
        self,
        db: Database,
        default_ttl: int = 3600,
        breaking_ttl: int = 300,
    ) -> None:
        self.db = db
        self.default_ttl = default_ttl
        self.breaking_ttl = breaking_ttl

    def ttl_for_freshness(self, freshness: str, query: str) -> int:
        lower = query.lower()
        if freshness == "day" or any(
            kw in lower for kw in ("today", "live", "score", "price", "breaking", "latest news", "weather")
        ):
            return self.breaking_ttl
        return self.default_ttl

    async def get(self, query: str, freshness: str = "any") -> list[dict[str, Any]] | None:
        key = make_cache_key(query, freshness)
        now = time.time()
        async with self.db.connect() as conn:
            cursor = await conn.execute(
                "SELECT results_json, expires_ts FROM search_cache WHERE cache_key = ?",
                (key,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            results_json, expires_ts = row
            if expires_ts <= now:
                await conn.execute("DELETE FROM search_cache WHERE cache_key = ?", (key,))
                await conn.commit()
                return None
            return json.loads(results_json)

    async def set(self, query: str, freshness: str, results: list[dict[str, Any]]) -> None:
        key = make_cache_key(query, freshness)
        now = time.time()
        ttl = self.ttl_for_freshness(freshness, query)
        expires_ts = now + ttl
        async with self.db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO search_cache (cache_key, query, freshness, results_json, created_ts, expires_ts)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    results_json = excluded.results_json,
                    created_ts = excluded.created_ts,
                    expires_ts = excluded.expires_ts
                """,
                (key, query, freshness, json.dumps(results), now, expires_ts),
            )
            await conn.execute("DELETE FROM search_cache WHERE expires_ts <= ?", (now,))
            await conn.commit()
