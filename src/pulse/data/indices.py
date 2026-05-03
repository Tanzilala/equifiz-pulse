"""Sensex (BSE) + Nifty 50 / Bank Nifty / India VIX (NSE).

Sensex is fetched from Yahoo Finance (`^BSESN`) — BSE's own JSON endpoint
is unreliable. The other three come from NSE's `/api/allIndices`.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..models import IndexQuote, IndicesSnapshot
from .nse_client import NSEClient, NSEError

INDEX_KEYS: dict[str, str] = {
    "NIFTY 50": "nifty_50",
    "NIFTY BANK": "bank_nifty",
    "INDIA VIX": "india_vix",
}

DISPLAY_NAMES: dict[str, str] = {
    "NIFTY 50": "Nifty 50",
    "NIFTY BANK": "Bank Nifty",
    "INDIA VIX": "India VIX",
}

YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _f(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse(raw: dict[str, Any]) -> IndexQuote:
    last = _f(raw.get("last"))
    prev = _f(raw.get("previousClose"))
    if last is None or prev is None:
        raise NSEError(f"index row missing last/previousClose: {raw.get('index')!r}")
    return IndexQuote(
        symbol=raw["index"],
        name=DISPLAY_NAMES.get(raw["index"], raw["index"]),
        last=last,
        change=_f(raw.get("variation")) or (last - prev),
        change_pct=_f(raw.get("percentChange")) or 0.0,
        open=_f(raw.get("open")),
        high=_f(raw.get("high")),
        low=_f(raw.get("low")),
        prev_close=prev,
        timestamp=datetime.now(timezone.utc),
    )


def parse_all_indices(payload: dict[str, Any]) -> dict[str, IndexQuote]:
    """Pure parser — used by tests with fixture data."""
    rows = payload.get("data") or []
    by_symbol = {row.get("index"): row for row in rows if row.get("index")}
    missing = [k for k in INDEX_KEYS if k not in by_symbol]
    if missing:
        raise NSEError(f"NSE allIndices missing required indices: {missing}")
    return {INDEX_KEYS[sym]: _parse(by_symbol[sym]) for sym in INDEX_KEYS}


def parse_yahoo_index(payload: dict[str, Any], *, ticker: str, name: str) -> IndexQuote:
    err = payload.get("chart", {}).get("error")
    if err:
        raise NSEError(f"Yahoo error for {ticker}: {err}")
    results = payload.get("chart", {}).get("result") or []
    if not results:
        raise NSEError(f"Yahoo returned no result for {ticker}")
    meta = results[0].get("meta") or {}
    last = _f(meta.get("regularMarketPrice"))
    prev = _f(meta.get("chartPreviousClose")) or _f(meta.get("previousClose"))
    if last is None or prev is None:
        raise NSEError(f"Yahoo meta missing price fields for {ticker}: {meta}")
    return IndexQuote(
        symbol=ticker,
        name=name,
        last=last,
        change=last - prev,
        change_pct=((last - prev) / prev * 100.0) if prev else 0.0,
        open=_f(meta.get("regularMarketOpen") or meta.get("chartPreviousClose")),
        high=_f(meta.get("regularMarketDayHigh")),
        low=_f(meta.get("regularMarketDayLow")),
        prev_close=prev,
        timestamp=datetime.now(timezone.utc),
    )


async def _fetch_yahoo_index(http: httpx.AsyncClient, *, ticker: str, name: str) -> IndexQuote:
    last_err: Optional[Exception] = None
    for host in YAHOO_HOSTS:
        url = f"https://{host}/v8/finance/chart/{ticker}?range=2d&interval=1d"
        try:
            r = await http.get(url, timeout=15.0)
            r.raise_for_status()
            return parse_yahoo_index(r.json(), ticker=ticker, name=name)
        except (httpx.HTTPError, ValueError, NSEError) as e:
            last_err = e
            continue
    raise NSEError(f"Yahoo fetch for {ticker} failed: {last_err}")


async def fetch_indices(
    nse: NSEClient, *, http: Optional[httpx.AsyncClient] = None
) -> IndicesSnapshot:
    owns_http = http is None
    if http is None:
        http = httpx.AsyncClient(headers=YAHOO_HEADERS, follow_redirects=True)

    try:
        nse_payload, sensex = await asyncio.gather(
            nse.get_json("/allIndices"),
            _fetch_yahoo_index(http, ticker="^BSESN", name="Sensex"),
        )
    finally:
        if owns_http:
            await http.aclose()

    parsed = parse_all_indices(nse_payload)
    return IndicesSnapshot(
        fetched_at=datetime.now(timezone.utc),
        sensex=sensex,
        nifty_50=parsed["nifty_50"],
        bank_nifty=parsed["bank_nifty"],
        india_vix=parsed["india_vix"],
    )
