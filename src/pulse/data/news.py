"""Business news headlines from Business Standard / Economic Times / Mint.

All three publish RSS 2.0 feeds. We fetch in parallel, take the top N items
from each (RSS lists newest-first), and degrade gracefully if any source is
unavailable.
"""
from __future__ import annotations

import asyncio
import email.utils
import html
import re
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree as ET

import httpx
from pydantic import BaseModel, ConfigDict

_TZ_TAIL = re.compile(r"\s*[+-]\d{4}\s*$")


def _parse_pubdate(raw: str) -> Optional[datetime]:
    """Tolerant pubDate parser. Handles RFC-822 (RBI) and SEBI's non-standard
    '30 Apr, 2026 +0530' format. Used to filter feed items by published date."""
    s = raw.strip()
    if not s:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(s)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except (TypeError, ValueError):
        pass
    cleaned = _TZ_TAIL.sub("", s).replace(",", "").strip()
    for fmt in ("%d %b %Y %H:%M:%S", "%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None

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
    "Business Standard": "https://www.business-standard.com/rss/companies-101.rss",
    "Economic Times": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Mint": "https://www.livemint.com/rss/companies",
}

# Order matters for dedup: when two sources cover the same story, the
# earlier source in this tuple keeps the headline.
SOURCE_ORDER = ("Business Standard", "Economic Times", "Mint")

DEFAULT_PER_SOURCE = 11
FETCH_BUFFER = 9  # over-fetch so dedup + clickbait filter still leaves N items

# Phrases / patterns that signal listicle / stock-tip clickbait, not news.
_CLICKBAIT_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        # Stock-tip listicles
        r"\bdo you own\b",
        r"\bbuy or sell\b",
        r"\bstocks? to buy\b",
        r"\bstocks? to sell\b",
        r"\brecommends?\s+\w+\s+stocks?\b",
        r"\bcheck (?:the )?full list\b",
        r"\bcheck (?:the )?list\b",
        r"\b\d+ (?:penny|largecap|smallcap|midcap|multibagger) stocks?\b",
        r"\bshould you (?:buy|sell|invest|hold)\b",
        # "X up/down N%" — drop trailing \b (\b after % never matches because %/space are both non-word).
        r"\b(?:rally|surged?|soared?|jumped?|gained?|cracked?|tanked?|spiked?) up to \d+%",
        r"\b\d+ stocks? (?:rally|surge|jump|soar|gain|crack|tank) up to \d+%",
        r"\bstocks? rally up to\b",
        r"\bportfolio check\b",
        r"\bconcurrent gainers?\b",
        # "₹1 lakh became ₹1 crore" promo headlines
        r"\bmultibagger\s+(?:penny\s+)?stocks?\b",
        r"\bturns? .{0,3}₹[\d,.]+\s+(?:lakh|crore)\s+into\b",
        # Election listicles & non-business sports
        r"\btop \d+ seats?\b",
        r"\bassembly elections?\b",
        r"\bcricket\b",
        r"\b(?:CSK|RCB|MI|KKR|DC|GT|LSG|PBKS|SRH|RR)\s+vs\b",
        r"\bMUN\s+vs\s+LIV\b",
    )
]

# Stopwords for Jaccard tokenization in cross-source dedup.
_STOPWORDS = {
    "the", "a", "an", "of", "in", "at", "on", "to", "for", "and", "or",
    "is", "are", "be", "by", "with", "as", "from", "this", "that", "it",
    "its", "has", "have", "will", "may", "after", "amid", "over", "up",
    "down", "out", "into", "onto",
}


def is_clickbait(title: str) -> bool:
    """True if the headline matches any known clickbait pattern."""
    return any(p.search(title) for p in _CLICKBAIT_PATTERNS)


def _tokenize(s: str) -> set[str]:
    """Significant words for similarity comparison: lowercased letters only,
    drop stopwords, drop short tokens (<=2 chars)."""
    return {
        w
        for w in re.findall(r"[a-zA-Z]+", s.lower())
        if len(w) > 2 and w not in _STOPWORDS
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


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
    """Pure: take the first `limit` non-clickbait items from an RSS 2.0 feed."""
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []
    for it in root.findall(".//item"):
        raw_title = (it.findtext("title") or "").strip()
        title = _clean_title(raw_title)
        link = (it.findtext("link") or "").strip()
        if not (title and link):
            continue
        if is_clickbait(title):
            continue
        pubdate_raw = it.findtext("pubDate") or ""
        pub = _parse_pubdate(pubdate_raw) if pubdate_raw else None
        items.append(NewsItem(source=source, title=title, url=link, published=pub))
        if len(items) >= limit:
            break
    return items


def dedup_across_sources(
    by_source: dict[str, list[NewsItem]],
    *,
    per_source: int,
    threshold: float = 0.5,
) -> dict[str, list[NewsItem]]:
    """Drop near-duplicate stories from later sources (per SOURCE_ORDER).

    Two titles are considered the same story if their token-set Jaccard
    similarity is at or above `threshold`. The first occurrence (earlier
    source) wins; subsequent matches are dropped.
    """
    seen: list[set[str]] = []
    out: dict[str, list[NewsItem]] = {}
    for source in SOURCE_ORDER:
        items = by_source.get(source, [])
        kept: list[NewsItem] = []
        for item in items:
            tokens = _tokenize(item.title)
            if any(_jaccard(tokens, prev) >= threshold for prev in seen):
                continue
            seen.append(tokens)
            kept.append(item)
            if len(kept) >= per_source:
                break
        out[source] = kept
    return out


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
    """Fetch + clickbait-filter + cross-source dedup.

    We over-fetch by FETCH_BUFFER per source so that the dedup pass can
    backfill: if BS and ET both cover a story, ET drops it but still has
    enough items to reach `per_source` from its remaining queue.
    """
    fetch_n = per_source + FETCH_BUFFER

    owns_http = http is None
    if http is None:
        http = httpx.AsyncClient(
            headers=_NEWS_HEADERS, follow_redirects=True, timeout=15.0
        )

    raw_by_source: dict[str, list[NewsItem]] = {}
    unavailable: list[str] = []

    try:
        results = await asyncio.gather(
            *(_fetch_one(http, src, url, fetch_n) for src, url in SOURCES.items())
        )
        for source, result in results:
            if isinstance(result, Exception):
                unavailable.append(f"{source}: {type(result).__name__}: {result}")
            elif result:
                raw_by_source[source] = result
            else:
                unavailable.append(f"{source}: returned 0 items")
    finally:
        if owns_http:
            await http.aclose()

    by_source = dedup_across_sources(raw_by_source, per_source=per_source)

    return NewsSnapshot(
        fetched_at=datetime.now(timezone.utc),
        by_source=by_source,
        unavailable_sources=unavailable,
    )
