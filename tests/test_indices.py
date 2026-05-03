from __future__ import annotations

import httpx
import pytest

from pulse.data.indices import (
    INDEX_KEYS,
    fetch_indices,
    parse_all_indices,
    parse_yahoo_index,
)
from pulse.data.nse_client import NSEClient, NSEError
from pulse.models import IndicesSnapshot


def test_parse_all_indices_returns_required_three(all_indices_payload):
    parsed = parse_all_indices(all_indices_payload)
    assert set(parsed) == set(INDEX_KEYS.values())
    assert parsed["nifty_50"].symbol == "NIFTY 50"
    assert parsed["bank_nifty"].symbol == "NIFTY BANK"
    assert parsed["india_vix"].symbol == "INDIA VIX"


def test_parse_all_indices_field_values(all_indices_payload):
    n50 = parse_all_indices(all_indices_payload)["nifty_50"]
    assert n50.name == "Nifty 50"
    assert n50.last == pytest.approx(24587.50)
    assert n50.prev_close == pytest.approx(24707.80)
    assert n50.change == pytest.approx(-120.30)
    assert n50.change_pct == pytest.approx(-0.49)


def test_parse_all_indices_raises_on_missing_required(all_indices_payload):
    payload = {"data": [r for r in all_indices_payload["data"] if r["index"] != "INDIA VIX"]}
    with pytest.raises(NSEError, match="missing required indices.*INDIA VIX"):
        parse_all_indices(payload)


def test_parse_all_indices_handles_missing_optional_fields():
    payload = {
        "data": [
            {"index": "NIFTY 50", "last": 100.0, "previousClose": 99.0,
             "variation": 1.0, "percentChange": 1.01, "open": "", "high": "-", "low": None},
            {"index": "NIFTY BANK", "last": 200.0, "previousClose": 199.0,
             "variation": 1.0, "percentChange": 0.5},
            {"index": "INDIA VIX", "last": 14.0, "previousClose": 14.0,
             "variation": 0.0, "percentChange": 0.0},
        ]
    }
    parsed = parse_all_indices(payload)
    assert parsed["nifty_50"].open is None
    assert parsed["nifty_50"].high is None
    assert parsed["nifty_50"].low is None


def test_parse_all_indices_derives_change_when_variation_missing():
    payload = {
        "data": [
            {"index": "NIFTY 50", "last": 100.0, "previousClose": 95.0, "percentChange": 5.26},
            {"index": "NIFTY BANK", "last": 200.0, "previousClose": 199.0,
             "variation": 1.0, "percentChange": 0.5},
            {"index": "INDIA VIX", "last": 14.0, "previousClose": 14.0,
             "variation": 0.0, "percentChange": 0.0},
        ]
    }
    n50 = parse_all_indices(payload)["nifty_50"]
    assert n50.change == pytest.approx(5.0)


def test_parse_yahoo_index_basic():
    payload = {
        "chart": {
            "result": [{"meta": {
                "regularMarketPrice": 81234.5,
                "chartPreviousClose": 81000.0,
                "regularMarketDayHigh": 81450.0,
                "regularMarketDayLow": 80800.0,
                "regularMarketOpen": 81100.0,
            }}],
            "error": None,
        }
    }
    q = parse_yahoo_index(payload, ticker="^BSESN", name="Sensex")
    assert q.symbol == "^BSESN"
    assert q.name == "Sensex"
    assert q.last == pytest.approx(81234.5)
    assert q.prev_close == pytest.approx(81000.0)
    assert q.change == pytest.approx(234.5)
    assert q.change_pct == pytest.approx(0.2895, abs=1e-3)
    assert q.high == pytest.approx(81450.0)


def test_parse_yahoo_index_missing_meta_raises():
    payload = {"chart": {"result": [{"meta": {}}], "error": None}}
    with pytest.raises(NSEError, match="missing price fields"):
        parse_yahoo_index(payload, ticker="^BSESN", name="Sensex")


@pytest.mark.live
async def test_fetch_indices_live_smoke():
    """Hits real NSE + Yahoo. Skipped unless `pytest -m live`."""
    async with NSEClient() as client:
        snap = await fetch_indices(client)
    assert isinstance(snap, IndicesSnapshot)
    for q in snap.all():
        assert q.last > 0
        assert q.prev_close > 0
    assert snap.sensex.symbol == "^BSESN"
