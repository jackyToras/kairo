from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from app.core.config import Settings
from app.db.sqlite import Database
from app.search.cache import SearchCache
from app.search.web_search import WebSearchService


@pytest.mark.asyncio
async def test_search_cache_hit_and_ttl(tmp_path: Path):
    db = Database(tmp_path / "cache.db")
    await db.init()
    cache = SearchCache(db=db, default_ttl=3600, breaking_ttl=300)

    assert cache.ttl_for_freshness("day", "any query") == 300
    assert cache.ttl_for_freshness("any", "Bitcoin price today") == 300
    assert cache.ttl_for_freshness("any", "FastAPI docs") == 3600

    sample = [{"title": "FastAPI", "url": "https://fastapi.tiangolo.com", "snippet": "Modern API framework"}]
    await cache.set("  FastAPI docs?! ", "any", sample)

    # Normalized key should match slightly different casing/punctuation
    hit = await cache.get("fastapi docs", "any")
    assert hit is not None
    assert hit[0]["url"] == "https://fastapi.tiangolo.com"


@pytest.mark.asyncio
async def test_web_search_service_uses_cache_and_ddg_fallback(tmp_path: Path):
    db = Database(tmp_path / "search.db")
    await db.init()
    cfg = Settings(database_path=str(tmp_path / "search.db"), enable_page_extraction=False)
    cache = SearchCache(db=db)
    svc = WebSearchService(settings=cfg, cache=cache)

    fake_ddg = [
        {"title": "Python 3.13 Release", "url": "https://www.python.org/downloads/", "snippet": "Python release info"},
        {"title": "Other blog", "url": "https://example.com/post", "snippet": "Blog post"},
    ]

    with patch("app.search.web_search._search_ddg_html", new=AsyncMock(return_value=fake_ddg)) as mock_ddg:
        out1 = await svc.execute("python 3.13 release", freshness="any", deep_extract=False)
        assert out1.cache_hit is False
        assert out1.provider == "duckduckgo"
        assert len(out1.sources) == 2
        # python.org has high-trust domain boost so it stays rank #1
        assert out1.sources[0].domain == "python.org"
        assert mock_ddg.await_count == 1

        # Second call hits SQLite cache without invoking DDG
        out2 = await svc.execute("Python 3.13 Release?", freshness="any", deep_extract=False)
        assert out2.cache_hit is True
        assert out2.provider == "cache"
        assert mock_ddg.await_count == 1
