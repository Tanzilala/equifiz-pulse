"""Regulatory feed: RBI + SEBI RSS, plus upcoming IPOs from NSE.

Each source is independent — one failing degrades the snapshot but doesn't
abort the run. Failed sources are listed in `unavailable_sources`.
"""
from __future__ import annotations

import asyncio
import email.utils
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.etree import ElementTree as ET

import httpx

from ..models import RegulatoryItem, RegulatorySnapshot, RegulatorySource
from .nse_client import NSEClient, NSEError

RBI_FEEDS = (
    ("RBI", "https://www.rbi.org.in/PressReleases_RSS.xml"),
    ("RBI", "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"),  # fallback: HTML, not parsed
)
SEBI_FEEDS = (
    ("SEBI", "https://www.sebi.gov.in/sebirss.xml"),
)
NSE_IPO_PATH = "/all-upcoming-issues?category=ipo"

DEFAULT_LOOKBACK = timedelta(hours=72)  # covers Friday→Monday gap for the morning brief
UPCOMING_IPO_WINDOW = timedelta(days=14)

_RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; equifiz-pulse/0.1; +https://equifiz.com)",
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


_TZ_TAIL = re.compile(r"\s*[+-]\d{4}\s*$")


def _parse_pubdate(raw: str) -> Optional[datetime]:
    """Tolerant pubDate parser. Handles RFC-822 (RBI) and SEBI's non-standard
    '30 Apr, 2026 +0530' format."""
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


def parse_rss(xml_text: str, source: RegulatorySource, *, since: datetime) -> list[RegulatoryItem]:
    """Pure: parse an RSS 2.0 feed and return items published since `since`."""
    root = ET.fromstring(xml_text)
    items: list[RegulatoryItem] = []
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pubdate_raw = it.findtext("pubDate") or ""
        if not (title and link and pubdate_raw):
            continue
        pub = _parse_pubdate(pubdate_raw)
        if pub is None:
            continue
        if pub < since:
            continue
        desc = (it.findtext("description") or "").strip() or None
        items.append(
            RegulatoryItem(source=source, title=title, url=link, published=pub, summary=desc)
        )
    return items


async def _fetch_rss(http: httpx.AsyncClient, url: str, source: RegulatorySource, since: datetime) -> list[RegulatoryItem]:
    r = await http.get(url, headers=_RSS_HEADERS, timeout=15.0)
    r.raise_for_status()
    return parse_rss(r.text, source, since=since)


def _ipo_to_items(payload, *, now: datetime) -> list[RegulatoryItem]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("data") or []
    else:
        rows = []
    out: list[RegulatoryItem] = []
    horizon = now + UPCOMING_IPO_WINDOW
    for r in rows:
        symbol = r.get("symbol") or r.get("companyName") or "IPO"
        company = r.get("companyName") or symbol
        start = r.get("issueStartDate") or ""
        end = r.get("issueEndDate") or ""
        try:
            start_dt = datetime.strptime(start, "%d-%b-%Y").replace(tzinfo=timezone.utc) if start else None
        except ValueError:
            start_dt = None
        if start_dt and start_dt > horizon:
            continue
        title = f"Upcoming IPO: {company} ({symbol})"
        if start and end:
            title += f" — opens {start}, closes {end}"
        elif start:
            title += f" — opens {start}"
        out.append(
            RegulatoryItem(
                source="NSE-IPO",
                title=title,
                url="https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
                published=now,
                summary=r.get("series") or None,
            )
        )
    return out


async def fetch_regulatory(
    *,
    nse: NSEClient,
    http: Optional[httpx.AsyncClient] = None,
    lookback: timedelta = DEFAULT_LOOKBACK,
) -> RegulatorySnapshot:
    now = datetime.now(timezone.utc)
    since = now - lookback

    owns_http = http is None
    if http is None:
        http = httpx.AsyncClient(headers=_RSS_HEADERS, timeout=15.0, follow_redirects=True)

    items: list[RegulatoryItem] = []
    unavailable: list[str] = []

    rss_jobs: list[tuple[str, str]] = [
        ("RBI", "https://www.rbi.org.in/PressReleases_RSS.xml"),
        ("RBI-NOTIF", "https://www.rbi.org.in/Notifications_RSS.xml"),
        ("SEBI", "https://www.sebi.gov.in/sebirss.xml"),
    ]

    async def run_rss(label: str, url: str) -> tuple[str, list[RegulatoryItem] | Exception]:
        try:
            src: RegulatorySource = "SEBI" if label.startswith("SEBI") else "RBI"
            return label, await _fetch_rss(http, url, src, since)
        except (httpx.HTTPError, ET.ParseError, ValueError) as e:
            return label, e

    async def run_ipo() -> tuple[str, list[RegulatoryItem] | Exception]:
        try:
            payload = await nse.get_json(NSE_IPO_PATH, cache_ttl=600.0)
            return "NSE-IPO", _ipo_to_items(payload, now=now)
        except (NSEError, ValueError, TypeError, AttributeError, KeyError) as e:
            return "NSE-IPO", e

    try:
        results = await asyncio.gather(*(run_rss(l, u) for l, u in rss_jobs), run_ipo())
        for label, result in results:
            if isinstance(result, Exception):
                unavailable.append(f"{label}: {type(result).__name__}: {result}")
            else:
                items.extend(result)
    finally:
        if owns_http:
            await http.aclose()

    items.sort(key=lambda i: i.published, reverse=True)
    return RegulatorySnapshot(
        fetched_at=now,
        items=items,
        unavailable_sources=unavailable,
    )
