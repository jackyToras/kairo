from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

NOISE_TAGS = ("script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "form", "iframe")


def sanitize_untrusted_text(text: str) -> str:
    """Neutralize XML/instruction boundary markers in untrusted web content."""
    if not text:
        return ""
    # Strip ASCII control characters except whitespace
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Neutralize boundary tags that could spoof system/tool framing
    cleaned = re.sub(r"</?\s*(source|system|assistant|user|tool_call|instructions?)\b[^>]*>", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_publish_date(soup: BeautifulSoup) -> str | None:
    meta_selectors = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"property": "og:updated_time"}),
        ("meta", {"name": "pubdate"}),
        ("meta", {"name": "publish_date"}),
        ("meta", {"name": "date"}),
        ("meta", {"name": "DC.date.issued"}),
    ]
    for tag_name, attrs in meta_selectors:
        tag = soup.find(tag_name, attrs=attrs)
        if tag and tag.get("content"):
            val = str(tag["content"]).strip()
            if val:
                return val[:32]
    time_tag = soup.find("time")
    if time_tag:
        dt = time_tag.get("datetime") or time_tag.get_text(strip=True)
        if dt:
            return str(dt).strip()[:32]
    return None


def parse_html_article(html: str, max_chars: int = 1100) -> tuple[str, str | None]:
    """Extract clean article text and optional publish date from HTML."""
    soup = BeautifulSoup(html, "lxml")
    pub_date = _extract_publish_date(soup)

    for tag_name in NOISE_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()

    container = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs: list[str] = []
    for p in container.find_all(["p", "li", "h1", "h2", "h3"]):
        txt = p.get_text(" ", strip=True)
        if len(txt) >= 35:
            paragraphs.append(txt)

    text = " ".join(paragraphs) if paragraphs else container.get_text(" ", strip=True)
    text = sanitize_untrusted_text(text)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0].strip() + "..."
    return text, pub_date


@dataclass
class ExtractedPage:
    url: str
    excerpt: str | None
    published_date: str | None


async def fetch_and_extract_one(
    client: httpx.AsyncClient,
    url: str,
    max_chars: int = 1100,
) -> ExtractedPage:
    try:
        resp = await client.get(url, follow_redirects=True)
        if resp.status_code >= 400:
            return ExtractedPage(url=url, excerpt=None, published_date=None)
        ctype = resp.headers.get("content-type", "").lower()
        if "text/html" not in ctype and "application/xhtml" not in ctype and "text/plain" not in ctype:
            return ExtractedPage(url=url, excerpt=None, published_date=None)

        raw_text = resp.text[:300_000]
        if "text/plain" in ctype:
            cleaned = sanitize_untrusted_text(raw_text)[:max_chars]
            return ExtractedPage(url=url, excerpt=cleaned, published_date=None)

        excerpt, pub_date = parse_html_article(raw_text, max_chars=max_chars)
        if len(excerpt) < 60:
            return ExtractedPage(url=url, excerpt=None, published_date=pub_date)
        return ExtractedPage(url=url, excerpt=excerpt, published_date=pub_date)
    except Exception:
        return ExtractedPage(url=url, excerpt=None, published_date=None)


async def enrich_results_with_content(
    results: list[dict[str, Any]],
    max_urls: int = 3,
    timeout_seconds: float = 1.8,
) -> list[dict[str, Any]]:
    """Concurrently fetch and extract readable text for top search results."""
    targets = [r for r in results[:max_urls] if r.get("url")]
    if not targets:
        return results

    timeout = httpx.Timeout(timeout_seconds, connect=min(1.0, timeout_seconds))
    async with httpx.AsyncClient(timeout=timeout, headers=DEFAULT_HEADERS) as client:
        extracted_list = await asyncio.gather(
            *(fetch_and_extract_one(client, item["url"]) for item in targets),
            return_exceptions=True,
        )

    by_url: dict[str, ExtractedPage] = {}
    for item in extracted_list:
        if isinstance(item, ExtractedPage):
            by_url[item.url] = item

    enriched: list[dict[str, Any]] = []
    for row in results:
        copy = dict(row)
        ext = by_url.get(copy.get("url", ""))
        if ext:
            if ext.excerpt:
                copy["excerpt"] = ext.excerpt
            if ext.published_date and not copy.get("published_date"):
                copy["published_date"] = ext.published_date
        enriched.append(copy)
    return enriched
