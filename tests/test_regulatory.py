from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from pulse.data.regulatory import _ipo_to_items, _parse_pubdate, parse_rss

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_rss_filters_by_lookback():
    xml = (FIXTURES / "rbi_press_releases.xml").read_text(encoding="utf-8")
    since = datetime(2026, 5, 2, 0, 0, tzinfo=timezone.utc)
    items = parse_rss(xml, "RBI", since=since)
    titles = [i.title for i in items]
    assert any("Master Direction" in t for t in titles)
    assert any("VRRR auction" in t for t in titles)
    assert all("Old item" not in t for t in titles)


def test_parse_rss_attaches_timezone_and_url():
    xml = (FIXTURES / "rbi_press_releases.xml").read_text(encoding="utf-8")
    items = parse_rss(xml, "RBI", since=datetime(2000, 1, 1, tzinfo=timezone.utc))
    for it in items:
        assert it.published.tzinfo is not None
        assert it.url.startswith("https://www.rbi.org.in/")
        assert it.source == "RBI"


def test_parse_rss_skips_malformed_items():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>OK</title><link>https://x</link><pubDate>Sat, 02 May 2026 16:00:00 +0530</pubDate></item>
      <item><title>Missing pubDate</title><link>https://y</link></item>
      <item><title>Bad pubDate</title><link>https://z</link><pubDate>not a date</pubDate></item>
    </channel></rss>"""
    items = parse_rss(xml, "RBI", since=datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert len(items) == 1
    assert items[0].title == "OK"


def test_ipo_to_items_filters_by_horizon():
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)
    payload = {
        "data": [
            {"symbol": "NEXTWK", "companyName": "Next Week IPO Co",
             "issueStartDate": "10-May-2026", "issueEndDate": "12-May-2026"},
            {"symbol": "FARFUTURE", "companyName": "Far Future Co",
             "issueStartDate": "10-Aug-2026", "issueEndDate": "12-Aug-2026"},
        ]
    }
    items = _ipo_to_items(payload, now=now)
    assert len(items) == 1
    assert "Next Week IPO Co" in items[0].title
    assert items[0].source == "NSE-IPO"


def test_parse_pubdate_rfc822():
    dt = _parse_pubdate("Sat, 02 May 2026 16:00:00 +0530")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.day == 2 and dt.month == 5 and dt.year == 2026


def test_parse_pubdate_sebi_format():
    dt = _parse_pubdate("30 Apr, 2026 +0530")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 4 and dt.day == 30


def test_parse_pubdate_naive_fallback():
    dt = _parse_pubdate("2026-04-30")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 4
    assert dt.tzinfo is not None


def test_parse_pubdate_garbage_returns_none():
    assert _parse_pubdate("") is None
    assert _parse_pubdate("not a date") is None


def test_parse_rss_handles_sebi_format():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>SEBI Item</title><link>https://www.sebi.gov.in/x</link><pubDate>30 Apr, 2026 +0530</pubDate></item>
    </channel></rss>"""
    items = parse_rss(xml, "SEBI", since=datetime(2026, 4, 1, tzinfo=timezone.utc))
    assert len(items) == 1
    assert items[0].source == "SEBI"


def test_ipo_to_items_handles_missing_dates():
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)
    payload = {"data": [{"symbol": "TBD", "companyName": "TBD Co"}]}
    items = _ipo_to_items(payload, now=now)
    assert len(items) == 1
    assert items[0].title == "Upcoming IPO: TBD Co (TBD)"
