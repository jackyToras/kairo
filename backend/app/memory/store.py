from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.db.sqlite import Database
from app.memory.embeddings import HybridEmbedder, cosine_similarity, hash_embed
from app.memory.extractor import extract_topics, summarize_assistant_response
from app.memory.temporal import (
    TemporalQueryPlan,
    format_timestamp_for_context,
    parse_temporal_query,
    resolve_timezone,
)


@dataclass
class RetrievedMemory:
    id: str
    session_id: str
    user_query: str
    assistant_summary: str
    topics: list[str]
    created_at: str
    created_ts: float
    formatted_time: str
    score: float
    match_reasons: list[str]


@dataclass
class RecallResult:
    plan: TemporalQueryPlan
    memories: list[RetrievedMemory]
    elapsed_ms: float


def _sanitize_fts_query(text: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]+", text)
    filtered = [t.lower() for t in tokens if len(t) >= 2]
    if not filtered:
        return ""
    # Deduplicate preserving order
    unique = list(dict.fromkeys(filtered))[:10]
    return " OR ".join(f'"{tok}"' for tok in unique)


class MemoryStore:
    """Hybrid temporal + FTS5 + semantic episodic memory over SQLite."""

    def __init__(self, db: Database, embedder: HybridEmbedder) -> None:
        self.db = db
        self.embedder = embedder

    async def ensure_session(self, session_id: str | None = None, title: str = "New Chat") -> str:
        sid = session_id or str(uuid.uuid4())
        now_iso = datetime.now(UTC).isoformat()
        async with self.db.connect() as conn:
            cursor = await conn.execute("SELECT id FROM sessions WHERE id = ?", (sid,))
            row = await cursor.fetchone()
            if row is None:
                await conn.execute(
                    "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (sid, title[:80], now_iso, now_iso),
                )
                await conn.commit()
        return sid

    async def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self.db.connect() as conn:
            conn.row_factory = lambda c, r: {col[0]: r[i] for i, col in enumerate(c.description)}
            cursor = await conn.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       COUNT(m.id) AS message_count
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return await cursor.fetchall()

    async def get_session_messages(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        async with self.db.connect() as conn:
            conn.row_factory = lambda c, r: {col[0]: r[i] for i, col in enumerate(c.description)}
            cursor = await conn.execute(
                """
                SELECT id, session_id, role, content, created_at, created_ts, local_date,
                       citations_json, trace_json
                FROM messages
                WHERE session_id = ?
                ORDER BY created_ts ASC
                LIMIT ?
                """,
                (session_id, limit),
            )
            rows = await cursor.fetchall()
        for r in rows:
            r["citations"] = json.loads(r.pop("citations_json", "[]") or "[]")
            r["trace"] = json.loads(r.pop("trace_json", "{}") or "{}")
        return rows

    async def delete_session(self, session_id: str) -> bool:
        async with self.db.connect() as conn:
            # Also clean FTS5 entries belonging to this session's memories
            await conn.execute(
                """
                DELETE FROM memories_fts
                WHERE memory_id IN (SELECT id FROM memories WHERE session_id = ?)
                """,
                (session_id,),
            )
            cur = await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await conn.commit()
            return cur.rowcount > 0

    async def get_recent_session_messages(
        self,
        session_id: str,
        limit: int = 8,
    ) -> list[dict[str, str]]:
        async with self.db.connect() as conn:
            cursor = await conn.execute(
                """
                SELECT role, content
                FROM messages
                WHERE session_id = ?
                ORDER BY created_ts DESC
                LIMIT ?
                """,
                (session_id, limit),
            )
            rows = await cursor.fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    async def save_turn(
        self,
        session_id: str,
        user_query: str,
        assistant_answer: str,
        citations: list[dict[str, Any]] | None = None,
        trace: dict[str, Any] | None = None,
        tz_name: str | None = "Asia/Kolkata",
        tz_offset_minutes: int | None = None,
        timestamp: datetime | None = None,
        allow_remote_embed: bool = True,
    ) -> str:
        tz = resolve_timezone(tz_name, tz_offset_minutes)
        now_utc = (timestamp.astimezone(UTC) if timestamp else datetime.now(UTC))
        now_local = now_utc.astimezone(tz)
        user_ts = now_utc.timestamp()
        assistant_ts = user_ts + 0.001
        iso_user = now_utc.isoformat()
        iso_assistant = datetime.fromtimestamp(assistant_ts, tz=UTC).isoformat()
        local_date = now_local.strftime("%Y-%m-%d")

        title_snippet = user_query.strip().splitlines()[0][:64] or "New Chat"
        await self.ensure_session(session_id, title=title_snippet)

        user_msg_id = str(uuid.uuid4())
        asst_msg_id = str(uuid.uuid4())
        mem_id = str(uuid.uuid4())

        topics = extract_topics(user_query, assistant_answer)
        summary = summarize_assistant_response(assistant_answer)
        embed_text = f"Question: {user_query}\nTopics: {', '.join(topics)}\nSummary: {summary}"
        embed_model, embed_vec = await self.embedder.embed(embed_text, allow_remote=allow_remote_embed)

        async with self.db.connect() as conn:
            # Update session title if it still has default title
            await conn.execute(
                """
                UPDATE sessions
                SET updated_at = ?,
                    title = CASE WHEN title = 'New Chat' THEN ? ELSE title END
                WHERE id = ?
                """,
                (iso_assistant, title_snippet, session_id),
            )
            await conn.execute(
                """
                INSERT INTO messages (
                    id, session_id, role, content, created_at, created_ts, local_date,
                    citations_json, trace_json
                ) VALUES (?, ?, 'user', ?, ?, ?, ?, '[]', '{}')
                """,
                (user_msg_id, session_id, user_query, iso_user, user_ts, local_date),
            )
            await conn.execute(
                """
                INSERT INTO messages (
                    id, session_id, role, content, created_at, created_ts, local_date,
                    citations_json, trace_json
                ) VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?, ?)
                """,
                (
                    asst_msg_id,
                    session_id,
                    assistant_answer,
                    iso_assistant,
                    assistant_ts,
                    local_date,
                    json.dumps(citations or []),
                    json.dumps(trace or {}),
                ),
            )
            await conn.execute(
                """
                INSERT INTO memories (
                    id, session_id, message_id, user_query, assistant_summary,
                    topics_json, embedding_model, embedding_json,
                    created_at, created_ts, local_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mem_id,
                    session_id,
                    user_msg_id,
                    user_query,
                    summary,
                    json.dumps(topics),
                    embed_model,
                    json.dumps(embed_vec),
                    iso_user,
                    user_ts,
                    local_date,
                ),
            )
            await conn.execute(
                """
                INSERT INTO memories_fts (memory_id, user_query, assistant_summary, topics)
                VALUES (?, ?, ?, ?)
                """,
                (mem_id, user_query, summary, " ".join(topics)),
            )
            await conn.commit()

        return mem_id

    async def recall(
        self,
        query: str,
        tz_name: str | None = "Asia/Kolkata",
        tz_offset_minutes: int | None = None,
        limit: int | None = None,
        now: datetime | None = None,
        allow_remote_embed: bool = False,
    ) -> RecallResult:
        import time

        t0 = time.perf_counter()
        tz = resolve_timezone(tz_name, tz_offset_minutes)
        now_dt = (now.astimezone(UTC) if now else datetime.now(UTC))
        now_ts = now_dt.timestamp()

        plan = parse_temporal_query(
            query=query,
            now=now_dt,
            tz_name=tz_name,
            tz_offset_minutes=tz_offset_minutes,
        )
        effective_limit = limit or (12 if plan.is_memory_meta_query else 6)

        topic_query = plan.cleaned_topic_query or query
        fts_expr = _sanitize_fts_query(topic_query)

        async with self.db.connect() as conn:
            conn.row_factory = lambda c, r: {col[0]: r[i] for i, col in enumerate(c.description)}

            # Signal 1: Temporal window / recency candidate pool
            where_clauses: list[str] = []
            params: list[Any] = []
            if plan.start_ts is not None:
                where_clauses.append("created_ts >= ?")
                params.append(plan.start_ts)
            if plan.end_ts is not None:
                where_clauses.append("created_ts <= ?")
                params.append(plan.end_ts)

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            order_dir = "ASC" if plan.sort_order == "asc" else "DESC"
            pool_cursor = await conn.execute(
                f"""
                SELECT id, session_id, user_query, assistant_summary, topics_json,
                       embedding_model, embedding_json, created_at, created_ts
                FROM memories
                {where_sql}
                ORDER BY created_ts {order_dir}
                LIMIT 120
                """,
                tuple(params),
            )
            pool_rows = await pool_cursor.fetchall()

            # Signal 2: FTS5 lexical match
            fts_ranks: dict[str, int] = {}
            if fts_expr:
                try:
                    fts_cursor = await conn.execute(
                        """
                        SELECT memory_id, bm25(memories_fts) AS rank_score
                        FROM memories_fts
                        WHERE memories_fts MATCH ?
                        ORDER BY rank_score ASC
                        LIMIT 40
                        """,
                        (fts_expr,),
                    )
                    fts_rows = await fts_cursor.fetchall()
                    for idx, row in enumerate(fts_rows):
                        fts_ranks[row["memory_id"]] = idx + 1
                except Exception:
                    pass

            # If time constraint + topic both exist, ensure any FTS matches inside time window are loaded
            rows_by_id = {r["id"]: r for r in pool_rows} if pool_rows else {}

            missing_fts_ids = [mid for mid in fts_ranks if mid not in rows_by_id]
            if missing_fts_ids and not plan.has_time_constraint:
                placeholders = ",".join("?" for _ in missing_fts_ids)
                extra_cursor = await conn.execute(
                    f"""
                    SELECT id, session_id, user_query, assistant_summary, topics_json,
                           embedding_model, embedding_json, created_at, created_ts
                    FROM memories
                    WHERE id IN ({placeholders})
                    """,
                    tuple(missing_fts_ids),
                )
                for row in await extra_cursor.fetchall():
                    rows_by_id[row["id"]] = row

        if not rows_by_id:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return RecallResult(plan=plan, memories=[], elapsed_ms=round(elapsed, 2))

        # Signal 3: Vector similarity (matching embedding model)
        query_hash_vec = hash_embed(topic_query)
        remote_model = ""
        remote_vec: list[float] = []
        if allow_remote_embed:
            remote_model, remote_vec = await self.embedder.embed(topic_query, allow_remote=True)

        sem_scores: list[tuple[str, float]] = []
        for mid, row in rows_by_id.items():
            emb_model = row.get("embedding_model", "hash-v1")
            emb_vec = json.loads(row.get("embedding_json") or "[]")
            if emb_model == "hash-v1":
                sim = cosine_similarity(query_hash_vec, emb_vec)
            elif remote_vec and emb_model == remote_model:
                sim = cosine_similarity(remote_vec, emb_vec)
            else:
                # Cross-model fallback using deterministic hash on stored text
                sim = cosine_similarity(query_hash_vec, hash_embed(row["user_query"]))
            sem_scores.append((mid, sim))

        sem_scores.sort(key=lambda x: x[1], reverse=True)
        sem_ranks = {mid: idx + 1 for idx, (mid, sim) in enumerate(sem_scores) if sim > 0.08}
        sem_sim_map = dict(sem_scores)

        # Temporal ordering rank inside filtered pool
        ordered_pool_ids = list(rows_by_id.keys())
        if plan.sort_order == "asc":
            ordered_pool_ids.sort(key=lambda mid: rows_by_id[mid]["created_ts"])
        else:
            ordered_pool_ids.sort(key=lambda mid: rows_by_id[mid]["created_ts"], reverse=True)
        time_ranks = {mid: idx + 1 for idx, mid in enumerate(ordered_pool_ids)}

        # If this is a topic-specific memory meta-query ("Did I ever ask about quantum?")
        # without a time window, avoid returning unrelated chronological turns when nothing matched the topic.
        strict_topic_only = bool(
            plan.is_memory_meta_query and plan.cleaned_topic_query and not plan.has_time_constraint
        )

        # Fuse with Reciprocal Rank Fusion (RRF)
        rrf_k = 20.0
        scored: list[RetrievedMemory] = []
        for mid, row in rows_by_id.items():
            score = 0.0
            reasons: list[str] = []

            has_topic_match = (mid in fts_ranks) or (sem_sim_map.get(mid, 0.0) >= 0.22)

            if plan.has_time_constraint:
                score += 1.6 / (rrf_k + time_ranks[mid])
                reasons.append("time_window")
            elif plan.is_memory_meta_query and (not strict_topic_only or has_topic_match):
                score += 1.1 / (rrf_k + time_ranks[mid])
                reasons.append("chronological")

            if mid in fts_ranks:
                score += 1.5 / (rrf_k + fts_ranks[mid])
                reasons.append("fts5_keyword")

            if mid in sem_ranks and (not strict_topic_only or sem_sim_map.get(mid, 0.0) >= 0.22):
                score += (1.2 + sem_sim_map[mid]) / (rrf_k + sem_ranks[mid])
                reasons.append("semantic_vector")

            # Small recency tie-breaker for general non-chronological queries
            if not reasons and not plan.is_memory_meta_query:
                # Only include general context if it has meaningful similarity or is very recent
                age_hours = max(0.0, (now_ts - row["created_ts"]) / 3600.0)
                if age_hours < 24.0:
                    score += 0.35 / (rrf_k + time_ranks[mid])
                    reasons.append("recent_context")

            if score <= 0:
                continue

            # If user asked specifically for chronological first/last with a topic, boost matching topic
            if (
                plan.sort_order in ("asc", "desc")
                and plan.cleaned_topic_query
                and (mid in fts_ranks or sem_sim_map.get(mid, 0.0) > 0.15)
            ):
                score += 0.08

            scored.append(
                RetrievedMemory(
                    id=mid,
                    session_id=row["session_id"],
                    user_query=row["user_query"],
                    assistant_summary=row["assistant_summary"],
                    topics=json.loads(row.get("topics_json") or "[]"),
                    created_at=row["created_at"],
                    created_ts=row["created_ts"],
                    formatted_time=format_timestamp_for_context(row["created_ts"], now_ts, tz),
                    score=round(score, 5),
                    match_reasons=reasons,
                )
            )

        if plan.sort_order == "asc" and plan.is_memory_meta_query:
            # Put topic-matched items first if topic specified, sorted chronologically oldest-first
            scored.sort(
                key=lambda m: (
                    0 if ("fts5_keyword" in m.match_reasons or sem_sim_map.get(m.id, 0.0) > 0.15) else 1,
                    m.created_ts,
                )
            )
        elif plan.has_time_constraint and plan.is_memory_meta_query and not plan.cleaned_topic_query:
            # Pure time-window summary ("what did I ask yesterday?"): sort chronologically
            scored.sort(key=lambda m: m.created_ts, reverse=(plan.sort_order != "asc"))
        else:
            scored.sort(key=lambda m: m.score, reverse=True)

        elapsed = (time.perf_counter() - t0) * 1000.0
        return RecallResult(
            plan=plan,
            memories=scored[:effective_limit],
            elapsed_ms=round(elapsed, 2),
        )

    async def list_timeline(
        self,
        limit: int = 100,
        query: str | None = None,
        tz_name: str | None = "Asia/Kolkata",
        tz_offset_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        tz = resolve_timezone(tz_name, tz_offset_minutes)
        now_ts = datetime.now(UTC).timestamp()

        async with self.db.connect() as conn:
            conn.row_factory = lambda c, r: {col[0]: r[i] for i, col in enumerate(c.description)}
            if query and query.strip():
                fts_expr = _sanitize_fts_query(query)
                if fts_expr:
                    cursor = await conn.execute(
                        """
                        SELECT m.id, m.session_id, m.user_query, m.assistant_summary,
                               m.topics_json, m.created_at, m.created_ts, m.local_date
                        FROM memories m
                        JOIN memories_fts f ON f.memory_id = m.id
                        WHERE memories_fts MATCH ?
                        ORDER BY m.created_ts DESC
                        LIMIT ?
                        """,
                        (fts_expr, limit),
                    )
                    rows = await cursor.fetchall()
                else:
                    rows = []
            else:
                cursor = await conn.execute(
                    """
                    SELECT id, session_id, user_query, assistant_summary,
                           topics_json, created_at, created_ts, local_date
                    FROM memories
                    ORDER BY created_ts DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = await cursor.fetchall()

        result = []
        for r in rows:
            result.append(
                {
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "user_query": r["user_query"],
                    "assistant_summary": r["assistant_summary"],
                    "topics": json.loads(r.get("topics_json") or "[]"),
                    "created_at": r["created_at"],
                    "created_ts": r["created_ts"],
                    "local_date": r["local_date"],
                    "formatted_time": format_timestamp_for_context(r["created_ts"], now_ts, tz),
                }
            )
        return result
