from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MONTH_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

WEEKDAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

MEMORY_META_PATTERNS = [
    r"\bwhat did i (?:just )?ask\b",
    r"\bwhat have i asked\b",
    r"\bwhat (?:did we|have we) (?:talk|chat|discuss)\b",
    r"\bwhat did you (?:say|tell|answer)\b",
    r"\bwhen did i\b",
    r"\bwhen was the (?:first|last) time\b",
    r"\b(?:did|have) i (?:ever )?ask(?:ed)?\b",
    r"\b(?:company|topic|thing|question|one|it|that|what) i (?:just |previously |earlier )?asked\b",
    r"\bi asked (?:you )?(?:about|earlier|yesterday|before)\b",
    r"\bremember (?:when|what) i\b",
    r"\bremind me (?:what|when) i\b",
    r"\bmy (?:past|previous|earlier|recent) (?:question|questions|query|queries|prompt|prompts|chat|history)\b",
    r"\bearlier (?:today|this week|conversation|chat|session)\b",
    r"\bprevious (?:session|chat|conversation|turn)\b",
    r"\blast time we\b",
    r"\bsummarize (?:our|my) (?:chat|conversation|questions|history)\b",
    r"\bwhat all did i ask\b",
]

STOPWORDS = {
    "what", "when", "where", "which", "who", "did", "do", "does", "have", "has",
    "i", "me", "my", "we", "our", "you", "your", "asked", "ask", "asking",
    "tell", "told", "say", "said", "talk", "talked", "about", "earlier",
    "previously", "before", "last", "first", "time", "today", "yesterday",
    "ago", "this", "morning", "afternoon", "evening", "night", "week", "month",
    "on", "in", "at", "for", "the", "a", "an", "and", "or", "of", "to", "ever",
    "remind", "remember", "please", "can", "could", "summarize", "summary",
    "history", "chat", "conversation", "session", "question", "questions",
    "query", "queries", "prompt", "prompts", "just", "was", "were", "is", "are",
}

NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "couple": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


@dataclass(frozen=True)
class TemporalQueryPlan:
    is_memory_meta_query: bool
    has_time_constraint: bool
    start_ts: float | None
    end_ts: float | None
    sort_order: Literal["relevance", "asc", "desc"]
    matched_expression: str | None
    cleaned_topic_query: str


def resolve_timezone(tz_name: str | None = None, tz_offset_minutes: int | None = None) -> tzinfo:
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            pass
    if tz_offset_minutes is not None:
        # JS getTimezoneOffset() is UTC - local (e.g. -330 for IST +05:30).
        # We accept standard signed minutes east of UTC when positive or auto-handle IST fallback.
        return timezone(timedelta(minutes=tz_offset_minutes))
    if tz_name == "Asia/Kolkata":
        return timezone(timedelta(hours=5, minutes=30), name="IST")
    return UTC


def format_timestamp_for_context(ts: float, now_ts: float, tz: tzinfo) -> str:
    dt = datetime.fromtimestamp(ts, tz=tz)
    now_dt = datetime.fromtimestamp(now_ts, tz=tz)
    delta_sec = max(0, int(now_ts - ts))

    if delta_sec < 60:
        rel = f"{delta_sec}s ago"
    elif delta_sec < 3600:
        rel = f"{delta_sec // 60}m ago"
    elif delta_sec < 86400 and dt.date() == now_dt.date():
        hours = delta_sec // 3600
        mins = (delta_sec % 3600) // 60
        rel = f"today, {hours}h {mins}m ago" if mins else f"today, {hours}h ago"
    elif (now_dt.date() - dt.date()).days == 1:
        rel = "yesterday"
    else:
        days = (now_dt.date() - dt.date()).days
        rel = f"{days} days ago"

    tz_label = dt.tzname() or dt.strftime("%z")
    return f"{dt.strftime('%Y-%m-%d %H:%M')} {tz_label} ({rel})".strip()


def _day_bounds(day: datetime) -> tuple[float, float]:
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start.timestamp(), end.timestamp()


def _extract_count(token: str) -> int | None:
    token = token.lower().strip()
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def _strip_meta_and_time_words(text: str, matched_expr: str | None) -> str:
    cleaned = text
    if matched_expr:
        cleaned = re.sub(re.escape(matched_expr), " ", cleaned, flags=re.IGNORECASE)
    tokens = re.findall(r"[A-Za-z0-9_.\-+#]+", cleaned)
    kept = [t for t in tokens if t.lower() not in STOPWORDS]
    return " ".join(kept).strip()


def parse_temporal_query(
    query: str,
    now: datetime | None = None,
    tz_name: str | None = "Asia/Kolkata",
    tz_offset_minutes: int | None = None,
) -> TemporalQueryPlan:
    tz = resolve_timezone(tz_name, tz_offset_minutes)
    local_now = (now.astimezone(tz) if now else datetime.now(tz))
    lower = query.lower().strip()

    is_meta = any(re.search(pat, lower) for pat in MEMORY_META_PATTERNS)

    sort_order: Literal["relevance", "asc", "desc"] = "relevance"
    if re.search(r"\b(first time|first ask(?:ed)?|earliest|very first|oldest)\b", lower) or (
        is_meta and re.search(r"\bfirst\b", lower)
    ):
        sort_order = "asc"
    elif re.search(r"\b(last time|last ask(?:ed)?|most recent|latest question|just asked|just now|recent)\b", lower):
        sort_order = "desc"

    start_ts: float | None = None
    end_ts: float | None = None
    matched_expr: str | None = None

    # 1. Explicit ISO date: YYYY-MM-DD
    iso_match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", lower)
    if iso_match:
        try:
            y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            target = local_now.replace(year=y, month=m, day=d)
            start_ts, end_ts = _day_bounds(target)
            matched_expr = iso_match.group(0)
        except ValueError:
            pass

    # 2. Month Day (e.g. "nov 8", "november 8, 2026", "8 november")
    if start_ts is None:
        md_match = re.search(
            r"\b(?:on\s+)?([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(20\d{2}))?\b",
            lower,
        )
        if md_match and md_match.group(1) in MONTH_MAP:
            try:
                m = MONTH_MAP[md_match.group(1)]
                d = int(md_match.group(2))
                y = int(md_match.group(3)) if md_match.group(3) else local_now.year
                target = local_now.replace(year=y, month=m, day=d)
                if not md_match.group(3) and target.date() > local_now.date():
                    target = target.replace(year=y - 1)
                start_ts, end_ts = _day_bounds(target)
                matched_expr = md_match.group(0)
            except ValueError:
                pass

    if start_ts is None:
        dm_match = re.search(
            r"\b(?:on\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)(?:,?\s*(20\d{2}))?\b",
            lower,
        )
        if dm_match and dm_match.group(2) in MONTH_MAP:
            try:
                d = int(dm_match.group(1))
                m = MONTH_MAP[dm_match.group(2)]
                y = int(dm_match.group(3)) if dm_match.group(3) else local_now.year
                target = local_now.replace(year=y, month=m, day=d)
                if not dm_match.group(3) and target.date() > local_now.date():
                    target = target.replace(year=y - 1)
                start_ts, end_ts = _day_bounds(target)
                matched_expr = dm_match.group(0)
            except ValueError:
                pass

    # 3. Relative N units ago / past N units
    if start_ts is None:
        ago_match = re.search(
            r"\b(\d+|a|an|one|two|couple|three|four|five|six|seven|eight|nine|ten)\s+"
            r"(minute|minutes|min|mins|hour|hours|hr|hrs|day|days|week|weeks)\s+ago\b",
            lower,
        )
        if ago_match:
            count = _extract_count(ago_match.group(1))
            unit = ago_match.group(2)
            if count is not None:
                matched_expr = ago_match.group(0)
                if unit.startswith(("min",)):
                    center = local_now - timedelta(minutes=count)
                    start_ts = (center - timedelta(minutes=15)).timestamp()
                    end_ts = (center + timedelta(minutes=15)).timestamp()
                elif unit.startswith(("hour", "hr")):
                    center = local_now - timedelta(hours=count)
                    start_ts = (center - timedelta(hours=1)).timestamp()
                    end_ts = (center + timedelta(hours=1)).timestamp()
                elif unit.startswith("day"):
                    target = local_now - timedelta(days=count)
                    start_ts, end_ts = _day_bounds(target)
                elif unit.startswith("week"):
                    target = local_now - timedelta(weeks=count)
                    start_ts = (target - timedelta(days=3)).timestamp()
                    end_ts = (target + timedelta(days=3)).timestamp()

    if start_ts is None:
        last_n_match = re.search(
            r"\b(?:in the\s+)?(?:last|past)\s+"
            r"(\d+|a|an|one|two|couple|three|four|five|six|seven|eight|nine|ten)\s+"
            r"(minute|minutes|min|mins|hour|hours|hr|hrs|day|days|week|weeks)\b",
            lower,
        )
        if last_n_match:
            count = _extract_count(last_n_match.group(1))
            unit = last_n_match.group(2)
            if count is not None:
                matched_expr = last_n_match.group(0)
                end_ts = local_now.timestamp()
                if unit.startswith("min"):
                    start_ts = (local_now - timedelta(minutes=count)).timestamp()
                elif unit.startswith(("hour", "hr")):
                    start_ts = (local_now - timedelta(hours=count)).timestamp()
                elif unit.startswith("day"):
                    start_ts = (local_now - timedelta(days=count)).timestamp()
                elif unit.startswith("week"):
                    start_ts = (local_now - timedelta(weeks=count)).timestamp()

    # 4. Day & part-of-day phrases
    if start_ts is None:
        if re.search(r"\bday before yesterday\b", lower):
            start_ts, end_ts = _day_bounds(local_now - timedelta(days=2))
            matched_expr = "day before yesterday"
        elif re.search(r"\byesterday morning\b", lower):
            yday = local_now - timedelta(days=1)
            start_ts = yday.replace(hour=5, minute=0, second=0, microsecond=0).timestamp()
            end_ts = yday.replace(hour=12, minute=0, second=0, microsecond=0).timestamp()
            matched_expr = "yesterday morning"
        elif re.search(r"\byesterday afternoon\b", lower):
            yday = local_now - timedelta(days=1)
            start_ts = yday.replace(hour=12, minute=0, second=0, microsecond=0).timestamp()
            end_ts = yday.replace(hour=17, minute=0, second=0, microsecond=0).timestamp()
            matched_expr = "yesterday afternoon"
        elif re.search(r"\byesterday evening\b", lower):
            yday = local_now - timedelta(days=1)
            start_ts = yday.replace(hour=17, minute=0, second=0, microsecond=0).timestamp()
            end_ts = yday.replace(hour=22, minute=0, second=0, microsecond=0).timestamp()
            matched_expr = "yesterday evening"
        elif re.search(r"\blast night\b", lower):
            yday = local_now - timedelta(days=1)
            start_ts = yday.replace(hour=19, minute=0, second=0, microsecond=0).timestamp()
            end_ts = local_now.replace(hour=5, minute=0, second=0, microsecond=0).timestamp()
            matched_expr = "last night"
        elif re.search(r"\byesterday\b", lower):
            start_ts, end_ts = _day_bounds(local_now - timedelta(days=1))
            matched_expr = "yesterday"
        elif re.search(r"\bthis morning\b", lower):
            start_ts = local_now.replace(hour=5, minute=0, second=0, microsecond=0).timestamp()
            end_ts = local_now.replace(hour=12, minute=0, second=0, microsecond=0).timestamp()
            matched_expr = "this morning"
        elif re.search(r"\bthis afternoon\b", lower):
            start_ts = local_now.replace(hour=12, minute=0, second=0, microsecond=0).timestamp()
            end_ts = local_now.replace(hour=17, minute=0, second=0, microsecond=0).timestamp()
            matched_expr = "this afternoon"
        elif re.search(r"\bthis evening\b", lower):
            start_ts = local_now.replace(hour=17, minute=0, second=0, microsecond=0).timestamp()
            end_ts = local_now.replace(hour=22, minute=0, second=0, microsecond=0).timestamp()
            matched_expr = "this evening"
        elif re.search(r"\b(?:earlier\s+)?today\b", lower):
            start_ts, end_ts = _day_bounds(local_now)
            matched_expr = "today"
        elif re.search(r"\b(?:this|past)\s+week\b", lower):
            start_ts = (local_now - timedelta(days=7)).timestamp()
            end_ts = local_now.timestamp()
            matched_expr = "this week"
        elif re.search(r"\blast\s+week\b", lower):
            start_ts = (local_now - timedelta(days=14)).timestamp()
            end_ts = (local_now - timedelta(days=7)).timestamp()
            matched_expr = "last week"
        elif re.search(r"\b(?:this|past)\s+month\b", lower):
            start_ts = (local_now - timedelta(days=30)).timestamp()
            end_ts = local_now.timestamp()
            matched_expr = "this month"

    # 5. Weekdays ("on monday", "last tuesday")
    if start_ts is None:
        wd_match = re.search(
            r"\b(?:(last|on|this)\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            lower,
        )
        if wd_match:
            target_wd = WEEKDAY_MAP[wd_match.group(2)]
            days_back = (local_now.weekday() - target_wd) % 7
            if days_back == 0 and wd_match.group(1) == "last":
                days_back = 7
            target = local_now - timedelta(days=days_back)
            start_ts, end_ts = _day_bounds(target)
            matched_expr = wd_match.group(0)

    has_time = start_ts is not None
    if has_time and sort_order == "relevance" and is_meta:
        sort_order = "desc"

    cleaned_topic = _strip_meta_and_time_words(query, matched_expr)

    return TemporalQueryPlan(
        is_memory_meta_query=is_meta,
        has_time_constraint=has_time,
        start_ts=start_ts,
        end_ts=end_ts,
        sort_order=sort_order,
        matched_expression=matched_expr,
        cleaned_topic_query=cleaned_topic,
    )
