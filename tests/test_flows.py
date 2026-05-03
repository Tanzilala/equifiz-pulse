from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from pulse.data.flows import parse_cash, parse_fno
from pulse.data.nse_client import NSEError

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cash_payload():
    return json.loads((FIXTURES / "nse_fii_dii_cash.json").read_text(encoding="utf-8"))


def test_parse_cash_basic(cash_payload):
    c = parse_cash(cash_payload)
    assert c.date == date(2026, 4, 30)
    assert c.fii_buy == pytest.approx(12345.67)
    assert c.fii_sell == pytest.approx(11000.12)
    assert c.fii_net == pytest.approx(1345.55)
    assert c.dii_net == pytest.approx(1111.11)


def test_parse_cash_handles_numeric_values():
    payload = [
        {"category": "FII", "date": "30-Apr-2026", "buyValue": 100.5, "sellValue": 90.5, "netValue": 10.0},
        {"category": "DII", "date": "30-Apr-2026", "buyValue": 50.0, "sellValue": 40.0, "netValue": 10.0},
    ]
    c = parse_cash(payload)
    assert c.fii_net == pytest.approx(10.0)


def test_parse_cash_raises_on_missing_category():
    payload = [
        {"category": "FII/FPI", "date": "30-Apr-2026", "buyValue": 1, "sellValue": 1, "netValue": 0}
    ]
    with pytest.raises(NSEError, match="missing rows"):
        parse_cash(payload)


def test_parse_cash_raises_on_empty():
    with pytest.raises(NSEError):
        parse_cash([])


def test_parse_fno_returns_nones_when_unrecognized_keys():
    payload = [
        {"instrument": "INDEX FUTURES", "netVal": "150.5", "date": "30-Apr-2026"},
        {"instrument": "STOCK OPTIONS", "netVal": "-12.3", "date": "30-Apr-2026"},
    ]
    f = parse_fno(payload)
    assert f.index_futures_net == pytest.approx(150.5)
    assert f.stock_options_net == pytest.approx(-12.3)
    assert f.index_options_net is None
    assert f.stock_futures_net is None


def test_parse_fno_unrecognized_payload_raises():
    with pytest.raises(NSEError, match="unrecognized"):
        parse_fno("not a list or dict")  # type: ignore[arg-type]
