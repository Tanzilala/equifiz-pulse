from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from pulse.format import (
    format_telegram,
    format_whatsapp,
)
from pulse.format.common import (
    crore,
    fmt_num,
    signed_pct,
    trend_emoji,
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
                       change_pct=20.0, volume=19_766_290),
            StockMover(symbol="MEESHO", name="Meesho", last=194.0,
                       change_pct=12.35, volume=150_000_000),
            StockMover(symbol="SYNGENE", name="Syngene", last=468.05,
                       change_pct=8.31, volume=59_000_000),
        ],
        losers=[
            StockMover(symbol="WAAREEENER", name="Waaree Energies", last=3129.9,
                       change_pct=-10.65, volume=8_109_147),
            StockMover(symbol="HEG", name="HEG Ltd", last=594.0,
                       change_pct=-9.78, volume=5_840_973),
            StockMover(symbol="EMMVEE", name="Emmvee Photovoltaic", last=262.49,
                       change_pct=-9.75, volume=13_098_890),
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
    return PulseBriefing(
        fetched_at=datetime(2026, 5, 3, 3, 0, tzinfo=timezone.utc),
        indices=indices, movers=movers, flows=flows, macro=macro,
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


def test_trend_emoji():
    assert trend_emoji(0.5) == "🟢"
    assert trend_emoji(-0.5) == "🔴"
    assert trend_emoji(0.0) == "⚪"


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


def test_whatsapp_shorter_than_telegram(briefing):
    w = format_whatsapp(briefing)
    tg = format_telegram(briefing)
    assert len(w) < len(tg)
