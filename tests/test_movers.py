from __future__ import annotations

import json
from pathlib import Path

import pytest

from pulse.data.movers import (
    compute_20d_avg_volume_from_yahoo,
    fetch_movers,
    split_top_movers,
)
from pulse.data.nse_client import NSEClient
from pulse.models import MoversSnapshot

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def nifty500_payload():
    return json.loads((FIXTURES / "nse_nifty500.json").read_text(encoding="utf-8"))


@pytest.fixture
def yahoo_volume_payload():
    return json.loads((FIXTURES / "yahoo_chart_volume.json").read_text(encoding="utf-8"))


def test_split_top_movers_excludes_index_row(nifty500_payload):
    gainers, losers = split_top_movers(nifty500_payload, top_n=5)
    syms = {m.symbol for m in [*gainers, *losers]}
    assert "NIFTY 500" not in syms


def test_split_top_movers_orders_correctly(nifty500_payload):
    gainers, losers = split_top_movers(nifty500_payload, top_n=5)
    assert [m.symbol for m in gainers] == ["MEGAUP", "BIGGAIN", "MIDGAIN", "OKGAIN", "MINIGAIN"]
    assert [m.symbol for m in losers] == ["ULTRALOSE", "MEGALOSE", "BIGLOSE", "MIDLOSE", "MINILOSE"]
    # Gainers descending
    assert all(gainers[i].change_pct >= gainers[i + 1].change_pct for i in range(len(gainers) - 1))
    # Losers ascending (most negative first)
    assert all(losers[i].change_pct <= losers[i + 1].change_pct for i in range(len(losers) - 1))


def test_split_top_movers_uses_company_name(nifty500_payload):
    gainers, _ = split_top_movers(nifty500_payload, top_n=1)
    assert gainers[0].name == "Mega Upside Industries Ltd"
    assert gainers[0].volume == 5_400_000


def test_compute_20d_avg_volume_from_yahoo(yahoo_volume_payload):
    avg = compute_20d_avg_volume_from_yahoo(yahoo_volume_payload)
    assert avg is not None
    raw = yahoo_volume_payload["chart"]["result"][0]["indicators"]["quote"][0]["volume"]
    nonnull = [v for v in raw[-20:] if v]
    expected = sum(nonnull) // len(nonnull)
    assert abs(avg - expected) <= 1


def test_compute_20d_avg_volume_handles_nulls():
    payload = {"chart": {"result": [{"indicators": {"quote": [{"volume": [None, 100, None, 200, 300, 100, 200]}]}}]}}
    avg = compute_20d_avg_volume_from_yahoo(payload)
    assert avg == (100 + 200 + 300 + 100 + 200) // 5


def test_compute_20d_avg_volume_too_few_samples():
    payload = {"chart": {"result": [{"indicators": {"quote": [{"volume": [100, 200]}]}}]}}
    assert compute_20d_avg_volume_from_yahoo(payload) is None


def test_compute_20d_avg_volume_empty():
    payload = {"chart": {"result": [{"indicators": {"quote": [{"volume": []}]}}]}}
    assert compute_20d_avg_volume_from_yahoo(payload) is None
    assert compute_20d_avg_volume_from_yahoo({"chart": {"result": []}}) is None


@pytest.mark.live
async def test_fetch_movers_live_smoke():
    async with NSEClient() as nse:
        snap = await fetch_movers(nse, top_n=3)
    assert isinstance(snap, MoversSnapshot)
    assert len(snap.gainers) == 3
    assert len(snap.losers) == 3
    for m in [*snap.gainers, *snap.losers]:
        assert m.symbol
        assert m.last > 0
    # At least some of the 6 stocks should have 20-day vol enrichment via Yahoo.
    enriched_count = sum(1 for m in [*snap.gainers, *snap.losers] if m.avg_volume_20d)
    assert enriched_count >= 1
