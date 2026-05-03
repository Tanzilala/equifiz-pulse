"""Business news headlines from Business Standard / Economic Times / Mint.

All three publish RSS 2.0 feeds. We fetch in parallel, take the top N items
from each (RSS lists newest-first), and degrade gracefully if any source is
unavailable.
"""
from __future__ import annotations

import asyncio
import html
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree as ET

import httpx
from pydantic import BaseModel, ConfigDict

from .regulatory import _parse_pubdate

# Full browser fingerprint — Business Standard rejects plain UAs and even
# Chrome UA without client hints. With these extras it returns 200.
_NEWS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/rss+xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}

SOURCES: dict[str, str] = {
    "Business Standard": "https://www.business-standard.com/rss/latest.rss",
    "Economic Times": "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
    "Mint": "https://www.livemint.com/rss/markets",
}

DEFAULT_PER_SOURCE = 11


class NewsItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    title: str
    url: str
    published: Optional[datetime] = None


class NewsSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    fetched_at: datetime
    by_source: dict[str, list[NewsItem]]
    unavailable_sources: list[str]

    def total_items(self) -> int:
        return sum(len(v) for v in self.by_source.values())


def _clean_title(s: str) -> str:
    """Decode HTML entities (`&amp;`, `&#8377;`, etc.) and collapse whitespace."""
    return " ".join(html.unescape(s).split())


def parse_news_rss(xml_text: str, source: str, *, limit: int) -> list[NewsItem]:
    """Pure: take the first `limit` items from an RSS 2.0 feed."""
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []
    for it in root.findall(".//item"):
        raw_title = (it.findtext("title") or "").strip()
        title = _clean_title(raw_title)
        link = (it.findtext("link") or "").strip()
        if not (title and link):
            continue
        pubdate_raw = it.findtext("pubDate") or ""
        pub = _parse_pubdate(pubdate_raw) if pubdate_raw else None
        items.append(NewsItem(source=source, title=title, url=link, published=pub))
        if len(items) >= limit:
            break
    return items


async def _fetch_one(
    http: httpx.AsyncClient, source: str, url: str, limit: int
) -> tuple[str, list[NewsItem] | Exception]:
    try:
        r = await http.get(url, timeout=15.0)
        r.raise_for_status()
        return source, parse_news_rss(r.text, source, limit=limit)
    except (httpx.HTTPError, ET.ParseError, ValueError) as e:
        return source, e


async def fetch_news(
    *,
    per_source: int = DEFAULT_PER_SOURCE,
    http: Optional[httpx.AsyncClient] = None,
) -> NewsSnapshot:
    owns_http = http is None
    if http is None:
        http = httpx.AsyncClient(
            headers=_NEWS_HEADERS, follow_redirects=True, timeout=15.0
        )

    by_source: dict[str, list[NewsItem]] = {}
    unavailable: list[str] = []

    try:
        results = await asyncio.gather(
            *(_fetch_one(http, src, url, per_source) for src, url in SOURCES.items())
        )
        for source, result in results:
            if isinstance(result, Exception):
                unavailable.append(f"{source}: {type(result).__name__}: {result}")
            elif result:
                by_source[source] = result
            else:
                unavailable.append(f"{source}: returned 0 items")
    finally:
        if owns_http:
            await http.aclose()

    return NewsSnapshot(
        fetched_at=datetime.now(timezone.utc),
        by_source=by_source,
        unavailable_sources=unavailable,
    )
