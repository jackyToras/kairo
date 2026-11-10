from datetime import datetime, timedelta

from app.memory.temporal import format_timestamp_for_context, parse_temporal_query, resolve_timezone


def test_parse_yesterday_and_today():
    tz = resolve_timezone("Asia/Kolkata")
    now = datetime(2026, 11, 10, 15, 30, 0, tzinfo=tz)

    plan_y = parse_temporal_query("What did I ask you yesterday?", now=now, tz_name="Asia/Kolkata")
    assert plan_y.is_memory_meta_query is True
    assert plan_y.has_time_constraint is True
    assert plan_y.matched_expression == "yesterday"
    assert plan_y.start_ts is not None and plan_y.end_ts is not None
    y_start = datetime.fromtimestamp(plan_y.start_ts, tz=tz)
    y_end = datetime.fromtimestamp(plan_y.end_ts, tz=tz)
    assert y_start.day == 9 and y_start.hour == 0
    assert y_end.day == 9 and y_end.hour == 23

    plan_t = parse_temporal_query("What did I ask earlier today?", now=now, tz_name="Asia/Kolkata")
    assert plan_t.is_memory_meta_query is True
    assert plan_t.has_time_constraint is True
    assert datetime.fromtimestamp(plan_t.start_ts, tz=tz).day == 10


def test_parse_first_vs_last_order_and_topic_extraction():
    tz = resolve_timezone("Asia/Kolkata")
    now = datetime(2026, 11, 10, 15, 30, 0, tzinfo=tz)

    plan_first = parse_temporal_query(
        "When did I first ask about FastAPI streaming?",
        now=now,
        tz_name="Asia/Kolkata",
    )
    assert plan_first.is_memory_meta_query is True
    assert plan_first.sort_order == "asc"
    assert "fastapi" in plan_first.cleaned_topic_query.lower()
    assert "streaming" in plan_first.cleaned_topic_query.lower()
    assert "when" not in plan_first.cleaned_topic_query.lower()


def test_parse_explicit_and_relative_dates():
    tz = resolve_timezone("Asia/Kolkata")
    now = datetime(2026, 11, 10, 18, 0, 0, tzinfo=tz)

    plan_iso = parse_temporal_query("What did we discuss on 2026-11-05?", now=now, tz_name="Asia/Kolkata")
    assert plan_iso.has_time_constraint is True
    assert datetime.fromtimestamp(plan_iso.start_ts, tz=tz).date().isoformat() == "2026-11-05"

    plan_month = parse_temporal_query("Did I ask about Docker on Nov 8?", now=now, tz_name="Asia/Kolkata")
    assert plan_month.has_time_constraint is True
    assert datetime.fromtimestamp(plan_month.start_ts, tz=tz).day == 8
    assert "docker" in plan_month.cleaned_topic_query.lower()

    plan_ago = parse_temporal_query("What did I ask 2 days ago?", now=now, tz_name="Asia/Kolkata")
    assert plan_ago.has_time_constraint is True
    assert datetime.fromtimestamp(plan_ago.start_ts, tz=tz).day == 8


def test_format_relative_timestamp():
    tz = resolve_timezone("Asia/Kolkata")
    now = datetime(2026, 11, 10, 18, 0, 0, tzinfo=tz)
    yesterday = now - timedelta(days=1)
    label = format_timestamp_for_context(yesterday.timestamp(), now.timestamp(), tz)
    assert "2026-11-09" in label
    assert "yesterday" in label
