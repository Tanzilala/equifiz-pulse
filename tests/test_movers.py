from __future__ import annotations

import json
from pathlib import Path

import pytest

from pulse.data.movers import fetch_movers, split_top_movers
from pulse.data.nse_client import NSEClient
from pulse.models import MoversSnapshot

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def nifty500_payload():
    return json.loads((FIXTURES / "nse_nifty500.json").read_text(encoding="utf-8"))


def test_split_top_movers_excludes_index_row(nifty500_payload):
    gainers, losers = split_top_movers(nifty500_payload, top_n=5)
    syms = {m.symbol for m in [*gainers, *losers]}
    assert "NIFTY 500" not in syms


def test_split_top_movers_orders_correctly(nifty500_payload):
    gainers, losers = split_top_movers(nifty500_payload, top_n=5)
    assert [m.symbol for m in gainers] == ["MEGAUP", "BIGGAIN", "MIDGAIN", "OKGAIN", "MINIGAIN"]
    assert [m.symbol for m in losers] == ["ULTRALOSE", "MEGALOSE", "BIGLOSE", "MIDLOSE", "MINILOSE"]
    assert all(gainers[i].change_pct >= gainers[i + 1].change_pct for i in range(len(gainers) - 1))
    assert all(losers[i].change_pct <= losers[i + 1].change_pct for i in range(len(losers) - 1))


def test_split_top_movers_uses_company_name(nifty500_payload):
    gainers, _ = split_top_movers(nifty500_payload, top_n=1)
    assert gainers[0].name == "Mega Upside Industries Ltd"
    assert gainers[0].volume == 5_400_000


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
