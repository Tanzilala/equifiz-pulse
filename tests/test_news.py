from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pulse.data.news import (
    NewsItem,
    NewsSnapshot,
    dedup_across_sources,
    is_clickbait,
    parse_news_rss,
)
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
    # Markdown link form (rendered as tappable link in Telegram)
    assert "📝 [BS one](https://x/1)" in text
    assert "📝 [ET one](https://x/3)" in text
    assert "📝 [Mint one](https://x/4)" in text
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


def test_format_news_uses_markdown_links():
    fa = datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)
    snap = NewsSnapshot(
        fetched_at=fa,
        by_source={
            "Business Standard": [
                NewsItem(source="Business Standard", title="ADB launches power push",
                         url="https://www.business-standard.com/x"),
            ],
        },
        unavailable_sources=[],
    )
    text = format_news(snap)
    assert "📝 [ADB launches power push](https://www.business-standard.com/x)" in text


def test_format_news_strips_brackets_in_link_text():
    fa = datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)
    snap = NewsSnapshot(
        fetched_at=fa,
        by_source={
            "Business Standard": [
                NewsItem(source="Business Standard",
                         title="RBI [draft] for upper layer NBFCs",
                         url="https://x.com/p"),
            ],
        },
        unavailable_sources=[],
    )
    text = format_news(snap)
    # Square brackets in title would break Markdown link parsing.
    assert "[RBI (draft) for upper layer NBFCs]" in text


def test_is_clickbait_catches_listicles():
    assert is_clickbait("10 penny stocks surged up to 490% in 6 months. Do you own any?")
    assert is_clickbait("Stocks to buy under ₹100 on Monday")
    assert is_clickbait("Buy or sell: 3 picks for the week")
    assert is_clickbait("Top 10 seats to watch in Kerala election")
    assert is_clickbait("Sumeet Bagadia recommends three stocks to buy")
    assert is_clickbait("Should you invest in mid-caps now?")
    assert is_clickbait("₹12.50 to ₹1630: Multibagger penny stock turns ₹1 lakh into ₹1.30 crore in nine years")
    assert is_clickbait("Assembly elections 2026: A tale of three voter turnouts")
    assert is_clickbait("CSK vs MI: who's winning today")
    assert is_clickbait("Sir Alex Ferguson rushed to hospital before MUN vs LIV")


def test_is_clickbait_passes_real_news():
    assert not is_clickbait("RBI holds repo rate, flags supply chain risks")
    assert not is_clickbait("Air India CEO Campbell Wilson steps down")
    assert not is_clickbait("Vedanta faces ₹233 crore notice over river water extraction")
    assert not is_clickbait("ADB launches $70 bn push to connect Asia's power grids")


def test_parse_news_rss_drops_clickbait_inline():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>RBI holds repo rate at 6.5%</title><link>https://x/1</link></item>
      <item><title>10 penny stocks surged 490%. Do you own any?</title><link>https://x/2</link></item>
      <item><title>Air India to meet on May 7</title><link>https://x/3</link></item>
      <item><title>Buy or sell: 3 stocks Monday picks</title><link>https://x/4</link></item>
    </channel></rss>"""
    items = parse_news_rss(xml, "Test", limit=10)
    titles = [i.title for i in items]
    assert "RBI holds repo rate at 6.5%" in titles
    assert "Air India to meet on May 7" in titles
    assert all("penny stocks" not in t for t in titles)
    assert all("Buy or sell" not in t for t in titles)


def test_dedup_drops_near_duplicates():
    bs_item = NewsItem(source="Business Standard",
                       title="Mcap of four of top-10 most valued firms surges by Rs 2.20 lakh cr; Reliance biggest winner",
                       url="https://bs/x")
    et_dup = NewsItem(source="Economic Times",
                      title="Mcap of four of top-10 most valued firms surges by ₹2.20 lakh crore; Reliance biggest winner",
                      url="https://et/x")
    et_unique = NewsItem(source="Economic Times",
                         title="Air India CEO meeting scheduled for May 7",
                         url="https://et/y")
    out = dedup_across_sources(
        {"Business Standard": [bs_item], "Economic Times": [et_dup, et_unique]},
        per_source=11,
    )
    assert len(out["Business Standard"]) == 1
    assert len(out["Economic Times"]) == 1
    assert out["Economic Times"][0].title.startswith("Air India CEO")


def test_dedup_keeps_distinct_stories():
    rbi1 = NewsItem(source="Business Standard",
                    title="RBI holds repo rate at 6.5%",
                    url="https://bs/1")
    rbi2 = NewsItem(source="Economic Times",
                    title="RBI may keep rates unchanged, focus on rupee stability",
                    url="https://et/2")
    out = dedup_across_sources(
        {"Business Standard": [rbi1], "Economic Times": [rbi2]},
        per_source=11,
    )
    # Different angles on RBI — both should pass through
    assert len(out["Business Standard"]) == 1
    assert len(out["Economic Times"]) == 1


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
