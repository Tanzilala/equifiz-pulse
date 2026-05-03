from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from pulse.data.macro import MacroError, fetch_macro, parse_chart
from pulse.models import MacroSnapshot

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def yahoo_payload():
    return json.loads((FIXTURES / "yahoo_chart.json").read_text(encoding="utf-8"))


def test_parse_chart_basic(yahoo_payload):
    q = parse_chart(yahoo_payload, symbol="INR=X", name="USDINR")
    assert q.symbol == "INR=X"
    assert q.name == "USDINR"
    assert q.last == pytest.approx(84.4250)
    assert q.prev_close == pytest.approx(84.2100)
    assert q.change == pytest.approx(0.2150)
    assert q.change_pct == pytest.approx(0.2553, abs=1e-3)


def test_parse_chart_uses_previous_close_fallback():
    payload = {
        "chart": {
            "result": [
                {"meta": {"regularMarketPrice": 100.0, "previousClose": 99.0}}
            ],
            "error": None,
        }
    }
    q = parse_chart(payload, symbol="X", name="X")
    assert q.prev_close == pytest.approx(99.0)


def test_parse_chart_raises_on_error():
    with pytest.raises(MacroError, match="Yahoo chart error"):
        parse_chart({"chart": {"error": {"code": "Not Found"}, "result": None}}, symbol="X", name="X")


def test_parse_chart_raises_on_missing_meta():
    with pytest.raises(MacroError, match="missing price fields"):
        parse_chart({"chart": {"result": [{"meta": {}}], "error": None}}, symbol="X", name="X")


@pytest.mark.live
async def test_fetch_macro_live_smoke():
    snap = await fetch_macro()
    assert isinstance(snap, MacroSnapshot)
    for q in snap.all():
        assert q.last > 0
        assert q.prev_close > 0
