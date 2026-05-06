from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from pulse.format import (
    format_linkedin,
    format_telegram,
    format_whatsapp,
)
from pulse.format.common import (
    crore,
    fmt_num,
    short_ipo_label,
    signed_pct,
    trend_arrow_unicode,
    trend_emoji,
    vol_ratio,
)
from pulse.models import (
    FIIDIICash,
    FlowsSnapshot,
    IndexQuote,
    IndicesSnapshot,
    MacroQuote,
    MacroSnapshot,
    MoversSnapshot,
    PulseBriefing,
    RegulatoryItem,
    RegulatorySnapshot,
    StockMover,
)


def _q(symbol, name, last, prev, pct) -> IndexQuote:
    return IndexQuote(
        symbol=symbol, name=name, last=last,
        change=last - prev, change_pct=pct,
        prev_close=prev, timestamp=datetime(2026, 5, 3, tzinfo=timezone.utc),
        open=prev * 1.001, high=last * 1.005, low=last * 0.995,
    )


def _macro_q(sym, name, last, prev) -> MacroQuote:
    return MacroQuote(
        symbol=sym, name=name, last=last, prev_close=prev,
        change=last - prev, change_pct=(last - prev) / prev * 100,
        as_of=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )


@pytest.fixture
def briefing() -> PulseBriefing:
    indices = IndicesSnapshot(
        fetched_at=datetime(2026, 5, 3, 3, 0, tzinfo=timezone.utc),
        sensex=_q("^BSESN", "Sensex", 81234.50, 81490.30, -0.31),
        nifty_50=_q("NIFTY 50", "Nifty 50", 23997.55, 24177.65, -0.74),
        bank_nifty=_q("NIFTY BANK", "Bank Nifty", 54863.35, 55403.60, -0.98),
        india_vix=_q("INDIA VIX", "India VIX", 18.46, 17.44, 5.86),
    )
    movers = MoversSnapshot(
        fetched_at=datetime(2026, 5, 3, 3, 0, tzinfo=timezone.utc),
        gainers=[
            StockMover(symbol="CEMPRO", name="Cemindia Projects", last=815.25,
                       change_pct=20.0, volume=19_766_290, avg_volume_20d=1_350_000, volume_ratio=14.64),
            StockMover(symbol="MEESHO", name="Meesho", last=194.0,
                       change_pct=12.35, volume=150_000_000, avg_volume_20d=17_000_000, volume_ratio=8.82),
            StockMover(symbol="SYNGENE", name="Syngene", last=468.05,
                       change_pct=8.31, volume=59_000_000, avg_volume_20d=3_900_000, volume_ratio=15.17),
        ],
        losers=[
            StockMover(symbol="WAAREEENER", name="Waaree Energies", last=3129.9,
                       change_pct=-10.65, volume=8_109_147, avg_volume_20d=2_135_000, volume_ratio=3.80),
            StockMover(symbol="HEG", name="HEG Ltd", last=594.0,
                       change_pct=-9.78, volume=5_840_973, avg_volume_20d=2_835_000, volume_ratio=2.06),
            StockMover(symbol="EMMVEE", name="Emmvee Photovoltaic", last=262.49,
                       change_pct=-9.75, volume=13_098_890, avg_volume_20d=5_796_000, volume_ratio=2.26),
        ],
    )
    flows = FlowsSnapshot(
        fetched_at=datetime(2026, 5, 3, 3, 0, tzinfo=timezone.utc),
        cash=FIIDIICash(date=date(2026, 4, 30), fii_buy=15049.55, fii_sell=23097.41,
                        fii_net=-8047.86, dii_buy=18252.89, dii_sell=14765.79, dii_net=3487.10),
        fno=None,
        fno_unavailable_reason="HTTP 404",
    )
    macro = MacroSnapshot(
        fetched_at=datetime(2026, 5, 3, 3, 0, tzinfo=timezone.utc),
        usdinr=_macro_q("INR=X", "USDINR", 94.88, 94.9166),
        dxy=_macro_q("DX-Y.NYB", "Dollar Index", 98.31, 98.16),
        brent=_macro_q("BZ=F", "Brent", 108.17, 108.10),
        gold=_macro_q("GC=F", "Gold (USD/oz)", 4644.50, 4629.90),
        india_gsec_10y=_macro_q("IN10Y", "India G-Sec 10Y (%)", 7.02, 7.05),
    )
    regulatory = RegulatorySnapshot(
        fetched_at=datetime(2026, 5, 3, 3, 0, tzinfo=timezone.utc),
        items=[
            RegulatoryItem(source="NSE-IPO",
                           title="Upcoming IPO: Bagmane Prime Office REIT (BAGMANE) — opens 05-May-2026, closes 07-May-2026",
                           url="https://nse.com/x", published=datetime(2026, 5, 3, 3, 0, tzinfo=timezone.utc)),
        ],
        unavailable_sources=[],
    )
    return PulseBriefing(
        fetched_at=datetime(2026, 5, 3, 3, 0, tzinfo=timezone.utc),
        indices=indices, movers=movers, flows=flows,
        regulatory=regulatory, macro=macro,
    )


# ---------- common helpers ----------

def test_signed_pct():
    assert signed_pct(1.234) == "+1.23%"
    assert signed_pct(-0.5) == "-0.50%"
    assert signed_pct(0.0) == "+0.00%"


def test_crore_signed():
    assert crore(1234.6) == "+1,235"
    assert crore(-8047.86) == "-8,048"
    assert crore(0) == "+0"


def test_vol_ratio():
    assert vol_ratio(None) == ""
    assert vol_ratio(2.345) == " (2.3x avg vol)"


def test_trend_arrow_unicode():
    assert trend_arrow_unicode(0.5) == "↑"
    assert trend_arrow_unicode(-0.5) == "↓"
    assert trend_arrow_unicode(0.0) == "→"


def test_trend_emoji():
    assert trend_emoji(0.5) == "🟢"
    assert trend_emoji(-0.5) == "🔴"
    assert trend_emoji(0.0) == "⚪"


def test_short_ipo_label_strips_limited():
    label = short_ipo_label("Upcoming IPO: Foo Ventures Limited (FOO) — opens 30-Apr-2026, closes 02-May-2026")
    assert label == "Foo Ventures (FOO) · opens 30 Apr"


def test_short_ipo_label_returns_none_on_unmatchable():
    assert short_ipo_label("Some random title") is None


# ---------- LinkedIn ----------

def test_linkedin_starts_with_pulse_header(briefing):
    text = format_linkedin(briefing)
    assert text.startswith("Equifiz Pulse · ")


def test_linkedin_no_commentary(briefing):
    """No hook/framing/'what to watch' — just header + data sections."""
    text = format_linkedin(briefing)
    assert "Watch" not in text
    assert "FIIs sold heavily" not in text
    assert "Foreign sellers" not in text


def test_linkedin_indices_in_correct_order(briefing):
    text = format_linkedin(briefing)
    pos_sensex = text.find("Sensex")
    pos_nifty = text.find("Nifty 50")
    pos_bank = text.find("Bank Nifty")
    pos_vix = text.find("India VIX")
    assert 0 < pos_sensex < pos_nifty < pos_bank < pos_vix


def test_linkedin_includes_sensex(briefing):
    text = format_linkedin(briefing)
    assert "Sensex 81,234.50" in text


def test_linkedin_no_midcap(briefing):
    text = format_linkedin(briefing)
    assert "Midcap" not in text


def test_linkedin_length_within_band(briefing):
    text = format_linkedin(briefing)
    assert 500 <= len(text) <= 1200, f"unexpected length {len(text)}"


def test_linkedin_movers_have_no_volume(briefing):
    """Volume ratio (e.g. '14.6x') should be removed from movers display."""
    text = format_linkedin(briefing)
    assert "x)" not in text
    assert "avg vol" not in text


def test_linkedin_movers_split_into_gainers_losers(briefing):
    text = format_linkedin(briefing)
    assert "Top Gainers" in text
    assert "Top Losers" in text
    assert "Top movers" not in text
    # Gainers come before losers
    assert text.find("Top Gainers") < text.find("Top Losers")


def test_linkedin_drops_ipo_section(briefing):
    """IPOs were intentionally removed from the briefing."""
    text = format_linkedin(briefing)
    assert "Upcoming IPOs" not in text
    assert "[NSE-IPO]" not in text


def test_linkedin_shows_full_fii_dii(briefing):
    text = format_linkedin(briefing)
    # FII fixture: buy=15049.55  sell=23097.41 → rounded 15,050 - 23,097 = -8,047
    assert "buy 15,050" in text
    assert "sell 23,097" in text
    assert "-8,047" in text  # net consistent with displayed buy − sell


def test_linkedin_net_is_signed(briefing):
    """Net keeps both + (positive) and − (negative) signs for clarity."""
    text = format_linkedin(briefing)
    assert "+3,487" in text  # DII positive net
    assert "-8,047" in text  # FII negative net


def test_linkedin_flow_block_format(briefing):
    """Flows: institution + emoji + bold net on first line, buy/sell indented below."""
    text = format_linkedin(briefing)
    # FII block: red emoji + signed net, then indented buy/sell
    assert "FII 🔴 -8,047\n   buy 15,050 · sell 23,097" in text
    # DII block: green emoji + signed net, then indented buy/sell
    assert "DII 🟢 +3,487\n   buy 18,253 · sell 14,766" in text


def test_linkedin_indices_show_point_change(briefing):
    """Each index line shows absolute point change alongside %."""
    text = format_linkedin(briefing)
    # Nifty 50: 23997.55 - 24177.65 = -180.10
    assert "Nifty 50 23,997.55" in text
    assert "-180.10" in text
    assert "(-0.74%)" in text


def test_linkedin_indices_use_color_emoji(briefing):
    """Indices show color emoji (🟢/🔴) before the change."""
    text = format_linkedin(briefing)
    # Nifty 50 fell -0.74% → 🔴
    assert "🔴 -180.10" in text
    # India VIX rose +5.86% → 🟢
    assert "🟢 +1.02" in text


def test_linkedin_shows_dollar_index(briefing):
    text = format_linkedin(briefing)
    assert "Dollar Index" in text
    assert "98.31" in text


def test_linkedin_shows_india_gsec_not_us(briefing):
    text = format_linkedin(briefing)
    assert "India G-Sec 10Y" in text
    assert "7.02" in text
    assert "US 10Y" not in text


def test_linkedin_falls_back_to_computed_gold_inr_when_ibja_unavailable(briefing):
    """gold_inr_per_10g is None in fixture → format_linkedin computes from
    USD × USDINR (Gold $4644.50 × 94.88 / 31.1035 × 10 ≈ ₹141,679)."""
    text = format_linkedin(briefing)
    assert "₹141,679/10g" in text


def test_linkedin_prefers_ibja_gold_when_available(briefing):
    """If IBJA's official rate is fetched, use that instead of computing from USD."""
    enriched = briefing.model_copy(update={
        "macro": briefing.macro.model_copy(update={"gold_inr_per_10g": 148100.0})
    })
    text = format_linkedin(enriched)
    assert "₹148,100/10g" in text
    assert "₹141,679/10g" not in text


def test_linkedin_section_separation_uses_double_blank(briefing):
    text = format_linkedin(briefing)
    # Triple newline = two blank lines between sections
    assert "\n\n\n" in text


# ---------- Telegram ----------

def test_telegram_starts_with_pulse_header(briefing):
    text = format_telegram(briefing)
    assert text.startswith("*Equifiz Pulse · ")


def test_telegram_uses_color_indicators(briefing):
    text = format_telegram(briefing)
    # Briefing has both gainers (positive %) and losers (negative %)
    assert "🟢" in text
    assert "🔴" in text
    # No more red-triangle artefacts
    assert "🔺" not in text
    assert "🔻" not in text


def test_telegram_no_commentary(briefing):
    text = format_telegram(briefing)
    assert "Watch" not in text
    assert "Foreign sellers" not in text


def test_telegram_indices_order(briefing):
    text = format_telegram(briefing)
    pos_sensex = text.find("Sensex")
    pos_nifty = text.find("Nifty 50")
    assert 0 < pos_sensex < pos_nifty


def test_telegram_excludes_full_version_link(briefing):
    text = format_telegram(briefing)
    assert "Read full version" not in text
    assert "equifiz.com" not in text


# ---------- WhatsApp ----------

def test_whatsapp_starts_with_pulse_header(briefing):
    text = format_whatsapp(briefing)
    assert text.startswith("EQUIFIZ PULSE · ")


def test_whatsapp_no_markdown(briefing):
    text = format_whatsapp(briefing)
    for ch in ("*", "`", "_"):
        assert ch not in text


def test_whatsapp_no_emojis(briefing):
    text = format_whatsapp(briefing)
    for ch in ("🟢", "🔴", "⚪", "🔺", "🔻", "📈", "💸", "🌐", "📊", "📜", "👀", "🚀"):
        assert ch not in text


def test_whatsapp_no_commentary(briefing):
    text = format_whatsapp(briefing)
    assert "WATCH" not in text
    assert "Foreign sellers" not in text


def test_whatsapp_includes_sensex(briefing):
    text = format_whatsapp(briefing)
    assert "Sensex 81,234.50" in text


def test_whatsapp_shorter_than_others(briefing):
    w = format_whatsapp(briefing)
    li = format_linkedin(briefing)
    tg = format_telegram(briefing)
    assert len(w) < len(li)
    assert len(w) < len(tg)
