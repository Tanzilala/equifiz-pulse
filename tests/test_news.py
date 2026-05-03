from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pulse.data.news import NewsItem, NewsSnapshot, parse_news_rss
from pulse.format.news import format_news

FIXTURES = Path(__file__).parent / "fixtures"


def _xml() -> str:
    return (FIXTURES / "news_rss.xml").read_text(encoding="utf-8")


def test_parse_news_rss_takes_top_n_skipping_malformed():
    items = parse_news_rss(_xml(), "Business Standard", limit=3)
    assert len(items) == 3
    titles = [i.title for i in items]
    assert titles[0].startswith("India, New Zealand")
    # the 4th item with empty title was skipped
    assert "" not in titles


def test_parse_news_rss_attaches_pubdate_with_tz():
    items = parse_news_rss(_xml(), "Business Standard", limit=1)
    assert items[0].published is not None
    assert items[0].published.tzinfo is not None


def test_parse_news_rss_carries_source():
    items = parse_news_rss(_xml(), "Mint", limit=2)
    for it in items:
        assert it.source == "Mint"


def test_parse_news_rss_decodes_html_entities():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Inflation &amp; growth: RBI flag supply risks</title><link>https://x</link></item>
      <item><title>Stock under &#8377;100 hits circuit</title><link>https://y</link></item>
    </channel></rss>"""
    items = parse_news_rss(xml, "Test", limit=5)
    assert items[0].title == "Inflation & growth: RBI flag supply risks"
    assert "₹" in items[1].title


def test_format_news_matches_template():
    fa = datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)
    snap = NewsSnapshot(
        fetched_at=fa,
        by_source={
            "Business Standard": [
                NewsItem(source="Business Standard", title="BS one", url="https://x/1"),
                NewsItem(source="Business Standard", title="BS two", url="https://x/2"),
            ],
            "Economic Times": [
                NewsItem(source="Economic Times", title="ET one", url="https://x/3"),
            ],
            "Mint": [
                NewsItem(source="Mint", title="Mint one", url="https://x/4"),
                NewsItem(source="Mint", title="Mint two", url="https://x/5"),
            ],
        },
        unavailable_sources=[],
    )
    text = format_news(snap)
    assert text.startswith("*News Headlines from Business News Agencies:*")
    assert "*Business Standard*" in text
    assert "*Economic Times*" in text
    assert "*Mint*" in text
    assert "📝 BS one" in text
    assert "📝 ET one" in text
    assert "📝 Mint one" in text
    # source order preserved (BS → ET → Mint)
    assert text.find("Business Standard") < text.find("Economic Times") < text.find("Mint")


def test_format_news_omits_empty_sources():
    fa = datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)
    snap = NewsSnapshot(
        fetched_at=fa,
        by_source={
            "Business Standard": [
                NewsItem(source="Business Standard", title="BS solo", url="https://x"),
            ],
        },
        unavailable_sources=["Economic Times: HTTPError", "Mint: HTTPError"],
    )
    text = format_news(snap)
    assert "*Business Standard*" in text
    assert "*Economic Times*" not in text
    assert "*Mint*" not in text


def test_format_news_caps_per_source():
    fa = datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)
    snap = NewsSnapshot(
        fetched_at=fa,
        by_source={
            "Business Standard": [
                NewsItem(source="Business Standard", title=f"item {i}", url=f"https://x/{i}")
                for i in range(20)
            ],
        },
        unavailable_sources=[],
    )
    text = format_news(snap, per_source=11)
    assert text.count("📝") == 11
