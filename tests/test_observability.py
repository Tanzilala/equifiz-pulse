from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from pulse.distribute import PostResult
from pulse.models import (
    FIIDIICash,
    FIIFnoNet,
    FlowsSnapshot,
    IndexQuote,
    IndicesSnapshot,
    MacroQuote,
    MacroSnapshot,
    MoversSnapshot,
    PulseBriefing,
    StockMover,
)
from pulse.observability import RunLogger, build_run_entry, derive_source_statuses


def _q(symbol, name, last, prev, pct) -> IndexQuote:
    return IndexQuote(symbol=symbol, name=name, last=last, change=last - prev,
                      change_pct=pct, prev_close=prev,
                      timestamp=datetime(2026, 5, 3, tzinfo=timezone.utc))


def _macro(s, n, l, p) -> MacroQuote:
    return MacroQuote(symbol=s, name=n, last=l, prev_close=p,
                      change=l - p, change_pct=(l - p) / p * 100,
                      as_of=datetime(2026, 5, 3, tzinfo=timezone.utc))


@pytest.fixture
def briefing(request) -> PulseBriefing:
    fa = datetime(2026, 5, 3, 3, 0, tzinfo=timezone.utc)
    fno = getattr(request, "param", "missing")
    flows = FlowsSnapshot(
        fetched_at=fa,
        cash=FIIDIICash(date=date(2026, 4, 30), fii_buy=1, fii_sell=1, fii_net=0,
                        dii_buy=1, dii_sell=1, dii_net=0),
        fno=FIIFnoNet(date=date(2026, 4, 30), index_futures_net=100.0) if fno == "present" else None,
        fno_unavailable_reason=None if fno == "present" else "HTTP 404",
    )
    return PulseBriefing(
        fetched_at=fa,
        indices=IndicesSnapshot(
            fetched_at=fa,
            sensex=_q("BSESN", "Sensex", 1, 1, 0),
            nifty_50=_q("N50", "Nifty 50", 1, 1, 0),
            bank_nifty=_q("BN", "Bank Nifty", 1, 1, 0),
            india_vix=_q("VIX", "VIX", 1, 1, 0),
        ),
        movers=MoversSnapshot(
            fetched_at=fa,
            gainers=[
                StockMover(symbol="A", name="A", last=1, change_pct=1, volume=10),
                StockMover(symbol="B", name="B", last=1, change_pct=1, volume=10),
            ],
            losers=[
                StockMover(symbol="Y", name="Y", last=1, change_pct=-1, volume=10),
                StockMover(symbol="Z", name="Z", last=1, change_pct=-1, volume=10),
            ],
        ),
        flows=flows,
        macro=MacroSnapshot(
            fetched_at=fa,
            usdinr=_macro("INR=X", "USDINR", 1, 1),
            dxy=_macro("DX-Y.NYB", "DXY", 1, 1),
            brent=_macro("BZ=F", "Brent", 1, 1),
            gold=_macro("GC=F", "Gold", 1, 1),
            india_gsec_10y=_macro("IN10Y", "India 10Y", 1, 1),
        ),
    )


def test_derive_source_statuses_fno_missing(briefing):
    s = derive_source_statuses(briefing)
    assert s["indices"] == "ok"
    assert s["movers"] == "ok"
    assert s["flows"]["cash"] == "ok"
    assert "HTTP 404" in s["flows"]["fno"]


@pytest.mark.parametrize("briefing", ["present"], indirect=True)
def test_derive_source_statuses_fno_present(briefing):
    s = derive_source_statuses(briefing)
    assert s["flows"]["fno"] == "ok"


def test_run_logger_writes_jsonl(tmp_path, briefing):
    logger = RunLogger(tmp_path / "logs")
    entry = build_run_entry(
        started_at=datetime(2026, 5, 3, 3, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 5, 3, 3, 0, 5, tzinfo=timezone.utc),
        confirm=True, only="telegram", narrative_source="rule_based",
        briefing=briefing,
        posts=[PostResult(channel="telegram", status="sent", http_status=200,
                          duration_ms=120, payload_chars=900)],
        error=None, exit_code=0,
    )
    path = logger.write(entry)
    assert path.exists()

    with path.open("r", encoding="utf-8") as f:
        line = f.readline().strip()
    parsed = json.loads(line)
    assert parsed["exit_code"] == 0
    assert parsed["args"]["only"] == "telegram"
    assert parsed["sources"]["indices"] == "ok"
    assert parsed["posts"][0]["status"] == "sent"


def test_run_logger_tail(tmp_path, briefing):
    logger = RunLogger(tmp_path / "logs")
    for i in range(5):
        logger.write({"started_at": f"2026-05-0{i+1}T00:00:00Z", "exit_code": i})
    last3 = logger.tail(3)
    assert len(last3) == 3
    assert [e["exit_code"] for e in last3] == [2, 3, 4]


def test_run_logger_tail_handles_missing_file(tmp_path):
    logger = RunLogger(tmp_path / "fresh")
    assert logger.tail(5) == []


def test_marker_path_format(tmp_path, monkeypatch):
    """The once-per-day marker uses the IST date in the filename."""
    from datetime import date

    from pulse.cli import _marker_path

    monkeypatch.chdir(tmp_path)
    p = _marker_path(date(2026, 5, 7))
    assert p.parts[-1] == "posted-2026-05-07.marker"
    assert "markers" in p.parts


def test_ist_today_returns_date(monkeypatch):
    """_ist_today returns an IST-anchored date (no off-by-one near UTC midnight)."""
    from datetime import date

    from pulse.cli import _ist_today

    today = _ist_today()
    assert isinstance(today, date)
    # Sanity: should be within ±1 day of UTC's idea of today
    from datetime import datetime, timezone
    utc_today = datetime.now(timezone.utc).date()
    assert abs((today - utc_today).days) <= 1
