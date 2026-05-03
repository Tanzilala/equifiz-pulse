"""Top gainers / losers from Nifty 500 enriched with 20-day average volume.

Pipeline:
  1) GET /api/equity-stockIndices?index=NIFTY%20500 — sort by pChange.
  2) Pick top N gainers + N losers.
  3) For each, fetch ~2 months of daily volumes from Yahoo Finance (NSE
     historical API was retired). Compute mean of last 20 trading-day volumes.
     Step 3 fans out concurrently (semaphore = 4) and is best-effort per stock.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..models import MoversSnapshot, StockMover
from .nse_client import NSEClient, NSEError

NIFTY500_PATH = "/equity-stockIndices?index=NIFTY%20500"
MAX_CONCURRENT_HIST = 4

YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


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


def split_top_movers(payload: dict[str, Any], *, top_n: int) -> tuple[list[StockMover], list[StockMover]]:
    """Pure: split a /equity-stockIndices payload into top N gainers and losers."""
    rows = [r for r in (payload.get("data") or []) if _is_stock_row(r)]
    if not rows:
        raise NSEError("Nifty 500 payload had no stock rows")
    rows.sort(key=lambda r: _to_float(r.get("pChange")) or 0.0)
    losers_raw = rows[:top_n]
    gainers_raw = list(reversed(rows[-top_n:]))
    return [_parse_stock_row(r) for r in gainers_raw], [_parse_stock_row(r) for r in losers_raw]


def compute_20d_avg_volume_from_yahoo(payload: dict[str, Any]) -> Optional[int]:
    """Pure: from a Yahoo `/v8/finance/chart` payload, mean of latest 20 daily volumes."""
    results = payload.get("chart", {}).get("result") or []
    if not results:
        return None
    indicators = (results[0].get("indicators") or {}).get("quote") or []
    if not indicators:
        return None
    vols_raw = indicators[0].get("volume") or []
    vols = [int(v) for v in vols_raw if v not in (None, 0)]
    if len(vols) < 5:
        return None
    sample = vols[-20:]
    return int(sum(sample) / len(sample))


async def _fetch_20d_avg_volume_yahoo(http: httpx.AsyncClient, symbol: str) -> Optional[int]:
    """NSE-listed equities map to `<SYMBOL>.NS` on Yahoo."""
    last_err: Optional[Exception] = None
    for host in YAHOO_HOSTS:
        url = f"https://{host}/v8/finance/chart/{symbol}.NS?range=2mo&interval=1d"
        try:
            r = await http.get(url, timeout=15.0)
            r.raise_for_status()
            return compute_20d_avg_volume_from_yahoo(r.json())
        except (httpx.HTTPError, ValueError, KeyError) as e:
            last_err = e
            continue
    return None


async def _enrich(http: httpx.AsyncClient, sem: asyncio.Semaphore, m: StockMover) -> StockMover:
    async with sem:
        avg = await _fetch_20d_avg_volume_yahoo(http, m.symbol)
    if avg is None or avg == 0:
        return m
    return m.model_copy(
        update={
            "avg_volume_20d": avg,
            "volume_ratio": round(m.volume / avg, 2) if m.volume else None,
        }
    )


async def fetch_movers(
    nse: NSEClient,
    *,
    top_n: int = 5,
    http: Optional[httpx.AsyncClient] = None,
) -> MoversSnapshot:
    payload = await nse.get_json(NIFTY500_PATH)
    gainers, losers = split_top_movers(payload, top_n=top_n)

    owns_http = http is None
    if http is None:
        http = httpx.AsyncClient(headers=YAHOO_HEADERS, follow_redirects=True)

    try:
        sem = asyncio.Semaphore(MAX_CONCURRENT_HIST)
        enriched = await asyncio.gather(
            *(_enrich(http, sem, m) for m in (*gainers, *losers))
        )
    finally:
        if owns_http:
            await http.aclose()

    g = list(enriched[: len(gainers)])
    l = list(enriched[len(gainers) :])

    return MoversSnapshot(
        fetched_at=datetime.now(timezone.utc),
        gainers=g,
        losers=l,
    )
