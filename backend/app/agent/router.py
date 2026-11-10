from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Literal

from app.memory.temporal import TemporalQueryPlan

RouteMode = Literal["direct", "memory_recall", "web_search", "hybrid_memory_web"]

GREETING_OR_META_RE = re.compile(
    r"^\s*(?:hi+|hello+|hey+|yo|sup|good\s+(?:morning|afternoon|evening)|"
    r"thanks?(?:\s+you)?|thank\s+you|ok(?:ay)?|cool|nice|got\s+it|bye|goodbye)\s*[!.]*\s*$",
    re.I,
)

LIVE_WEB_INDICATORS = (
    r"\b(?:latest|newest|current|currently|today|tonight|now|live|breaking|recent|recently)\b",
    r"\b(?:news|weather|forecast|stock|share\s+price|crypto|bitcoin|btc|eth|score|match|standings)\b",
    r"\b(?:price|cost|release\s+date|version|changelog|update|updated)\b",
    r"\b(?:who\s+(?:is|was|created|founded|invented|built|wrote|owns|won))\b",
    r"\b(?:what\s+happened|when\s+did\s+(?!i\b|we\b)[a-z]+|where\s+is)\b",
    r"\b202[4-9]\b",
    r"\b(?:search|look\s+up|google|verify|check\s+online|find\s+out|sources?)\b",
)

SELF_CONTAINED_PATTERNS = (
    r"^\s*(?:write|refactor|debug|fix|explain|convert|format|rewrite|shorten|translate)\b",
    r"^\s*(?:calculate|compute|solve)\s+[\d\s+\-*/().^=]+",
    r"\b(?:hello|how\s+are\s+you|who\s+are\s+you|what\s+can\s+you\s+do)\b",
)


@dataclass(frozen=True)
class RouteDecision:
    mode: RouteMode
    allow_search: bool
    force_search_hint: bool
    reason: str
    elapsed_ms: float


def route_query(
    query: str,
    temporal_plan: TemporalQueryPlan,
    has_memories: bool,
) -> RouteDecision:
    """Sub-5ms deterministic query router balancing latency and factual grounding."""
    t0 = time.perf_counter()
    stripped = query.strip()
    lower = stripped.lower()

    needs_live_web = any(re.search(p, lower) for p in LIVE_WEB_INDICATORS)

    # 1. Temporal/episodic memory meta-query ("what did I ask yesterday?", "when did I ask about X?")
    if temporal_plan.is_memory_meta_query:
        # Check if user ALSO asks to look up fresh web info based on remembered topic
        if any(
            re.search(p, lower)
            for p in (
                r"\b(?:check|search|look\s+up|update|verify|latest|today's|current\s+price|now)\b",
            )
        ):
            return RouteDecision(
                mode="hybrid_memory_web",
                allow_search=True,
                force_search_hint=True,
                reason="memory_recall_plus_live_verification",
                elapsed_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            )
        return RouteDecision(
            mode="memory_recall",
            allow_search=False,
            force_search_hint=False,
            reason="temporal_memory_meta_query",
            elapsed_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    # 2. Pure conversational greeting / acknowledgement -> instant direct response
    if GREETING_OR_META_RE.match(stripped):
        return RouteDecision(
            mode="direct",
            allow_search=False,
            force_search_hint=False,
            reason="conversational_greeting",
            elapsed_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    # 3. Clear live/external factual markers -> web_search (or hybrid if time/memory referenced)
    if needs_live_web:
        mode: RouteMode = (
            "hybrid_memory_web"
            if (has_memories and (temporal_plan.has_time_constraint or temporal_plan.is_memory_meta_query))
            else "web_search"
        )
        return RouteDecision(
            mode=mode,
            allow_search=True,
            force_search_hint=True,
            reason="live_or_time_sensitive_query",
            elapsed_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    # 4. Self-contained coding/writing/math prompts without live markers
    if any(re.search(p, lower) for p in SELF_CONTAINED_PATTERNS) and "?" not in lower:
        return RouteDecision(
            mode="direct",
            allow_search=False,
            force_search_hint=False,
            reason="self_contained_task",
            elapsed_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    # 5. Question or entity/factual prompt -> allow web_search (with optional memory context)
    if "?" in stripped or len(stripped.split()) >= 4:
        mode: RouteMode = "hybrid_memory_web" if has_memories else "web_search"
        return RouteDecision(
            mode=mode,
            allow_search=True,
            force_search_hint=False,
            reason="factual_or_open_question_search_enabled",
            elapsed_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    return RouteDecision(
        mode="direct",
        allow_search=False,
        force_search_hint=False,
        reason="short_conversational_turn",
        elapsed_ms=round((time.perf_counter() - t0) * 1000.0, 2),
    )
