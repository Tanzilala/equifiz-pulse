"""Top gainers / losers from Nifty 500 — % move only.

Single GET to /api/equity-stockIndices?index=NIFTY%20500, sort by pChange,
take top N from each end. (20-day average volume enrichment was removed
when the volume column was dropped from the post.)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ..models import MoversSnapshot, StockMover
from .nse_client import NSEClient, NSEError

NIFTY500_PATH = "/equity-stockIndices?index=NIFTY%20500"


def _to_int(v: Any) -> Optional[int]:
    if v in (None, "", "-"):
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> Optional[float]:
    if v in (None, "", "-"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _is_stock_row(row: dict[str, Any]) -> bool:
    if row.get("priority") == 1:
        return False
    if row.get("meta") in (None, {}, ""):
        return False
    return bool(row.get("symbol"))


def _parse_stock_row(row: dict[str, Any]) -> StockMover:
    meta = row.get("meta") or {}
    last = _to_float(row.get("lastPrice")) or 0.0
    pct = _to_float(row.get("pChange")) or 0.0
    vol = _to_int(row.get("totalTradedVolume")) or 0
    return StockMover(
        symbol=row["symbol"],
        name=meta.get("companyName") or row["symbol"],
        last=last,
        change_pct=pct,
        volume=vol,
    )


def split_top_movers(
    payload: dict[str, Any], *, top_n: int
) -> tuple[list[StockMover], list[StockMover]]:
    """Pure: split a /equity-stockIndices payload into top N gainers and losers."""
    rows = [r for r in (payload.get("data") or []) if _is_stock_row(r)]
    if not rows:
        raise NSEError("Nifty 500 payload had no stock rows")
    rows.sort(key=lambda r: _to_float(r.get("pChange")) or 0.0)
    losers_raw = rows[:top_n]
    gainers_raw = list(reversed(rows[-top_n:]))
    return [_parse_stock_row(r) for r in gainers_raw], [_parse_stock_row(r) for r in losers_raw]


async def fetch_movers(nse: NSEClient, *, top_n: int = 5) -> MoversSnapshot:
    payload = await nse.get_json(NIFTY500_PATH)
    gainers, losers = split_top_movers(payload, top_n=top_n)
    return MoversSnapshot(
        fetched_at=datetime.now(timezone.utc),
        gainers=gainers,
        losers=losers,
    )
