"""USDINR, Brent, gold, US 10Y via Yahoo Finance chart endpoint.

Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/<symbol>?range=2d&interval=1d
We need only `meta.regularMarketPrice` and `meta.chartPreviousClose`.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx

from ..models import MacroQuote, MacroSnapshot

YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# (yahoo_symbol, display_name, attribute_on_snapshot)
TICKERS: tuple[tuple[str, str, str], ...] = (
    ("INR=X", "USDINR", "usdinr"),
    ("BZ=F", "Brent", "brent"),
    ("GC=F", "Gold (USD/oz)", "gold"),
    ("^TNX", "US 10Y Yield (%)", "us10y"),
)


class MacroError(RuntimeError):
    pass


def parse_chart(payload: dict, *, symbol: str, name: str) -> MacroQuote:
    err = payload.get("chart", {}).get("error")
    if err:
        raise MacroError(f"Yahoo chart error for {symbol}: {err}")
    results = payload.get("chart", {}).get("result") or []
    if not results:
        raise MacroError(f"Yahoo chart empty for {symbol}: {payload}")
    meta = results[0].get("meta") or {}
    last = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    ts = meta.get("regularMarketTime")
    if last is None or prev is None:
        raise MacroError(f"Yahoo chart missing price fields for {symbol}: meta={meta}")
    last_f = float(last)
    prev_f = float(prev)
    change = last_f - prev_f
    change_pct = (change / prev_f * 100.0) if prev_f else 0.0
    as_of = (
        datetime.fromtimestamp(int(ts), tz=timezone.utc)
        if ts
        else datetime.now(timezone.utc)
    )
    return MacroQuote(
        symbol=symbol,
        name=name,
        last=last_f,
        prev_close=prev_f,
        change=change,
        change_pct=change_pct,
        as_of=as_of,
    )


async def _fetch_one(http: httpx.AsyncClient, symbol: str, name: str) -> MacroQuote:
    last_err: Optional[Exception] = None
    for host in YAHOO_HOSTS:
        url = f"https://{host}/v8/finance/chart/{symbol}?range=2d&interval=1d"
        try:
            r = await http.get(url, timeout=15.0)
            r.raise_for_status()
            return parse_chart(r.json(), symbol=symbol, name=name)
        except (httpx.HTTPError, ValueError, MacroError) as e:
            last_err = e
            continue
    raise MacroError(f"All Yahoo hosts failed for {symbol}: {last_err}")


async def fetch_macro(http: Optional[httpx.AsyncClient] = None) -> MacroSnapshot:
    owns = http is None
    if http is None:
        http = httpx.AsyncClient(headers=HEADERS, follow_redirects=True)
    try:
        quotes = await asyncio.gather(
            *(_fetch_one(http, sym, name) for sym, name, _ in TICKERS)
        )
    finally:
        if owns:
            await http.aclose()
    by_attr = {attr: q for (sym, _name, attr), q in zip(TICKERS, quotes)}
    return MacroSnapshot(
        fetched_at=datetime.now(timezone.utc),
        usdinr=by_attr["usdinr"],
        brent=by_attr["brent"],
        gold=by_attr["gold"],
        us10y=by_attr["us10y"],
    )
