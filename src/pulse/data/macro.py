"""Macro snapshot: USDINR, Dollar Index, Brent, Gold via Yahoo;
Indian G-Sec 10Y via investing.com (Yahoo doesn't index Indian sovereign yields).
"""
from __future__ import annotations

import asyncio
import re
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

# Yahoo-backed tickers (DXY = ICE Dollar Index).
TICKERS: tuple[tuple[str, str, str], ...] = (
    ("INR=X", "USDINR", "usdinr"),
    ("DX-Y.NYB", "Dollar Index", "dxy"),
    ("BZ=F", "Brent", "brent"),
    ("GC=F", "Gold (USD/oz)", "gold"),
)

INVESTING_INDIA_10Y_URL = (
    "https://www.investing.com/rates-bonds/india-10-year-bond-yield"
)
_INVESTING_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_INVESTING_LAST = re.compile(
    r'data-test="instrument-price-last"[^>]*>([\d.]+)<'
)
_INVESTING_PCT = re.compile(
    r'data-test="instrument-price-change-percent"[^>]*>\s*\(?\s*(-?\+?[\d.]+)%?\s*\)?\s*<'
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


def parse_investing_yield(html: str) -> MacroQuote:
    """Pure: extract current yield + day-change-% from an investing.com page."""
    m_last = _INVESTING_LAST.search(html)
    if not m_last:
        raise MacroError("investing.com: no instrument-price-last in HTML")
    last = float(m_last.group(1))
    m_pct = _INVESTING_PCT.search(html)
    pct = float(m_pct.group(1).replace("+", "")) if m_pct else 0.0
    prev = last / (1 + pct / 100.0) if pct != 0 else last
    return MacroQuote(
        symbol="IN10Y",
        name="India G-Sec 10Y (%)",
        last=last,
        prev_close=prev,
        change=last - prev,
        change_pct=pct,
        as_of=datetime.now(timezone.utc),
    )


async def _fetch_one_yahoo(http: httpx.AsyncClient, symbol: str, name: str) -> MacroQuote:
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


async def _fetch_india_gsec(http: httpx.AsyncClient) -> MacroQuote:
    r = await http.get(
        INVESTING_INDIA_10Y_URL, headers=_INVESTING_HEADERS, timeout=15.0
    )
    r.raise_for_status()
    return parse_investing_yield(r.text)


async def fetch_macro(http: Optional[httpx.AsyncClient] = None) -> MacroSnapshot:
    owns = http is None
    if http is None:
        http = httpx.AsyncClient(headers=HEADERS, follow_redirects=True)
    try:
        yahoo_results, india_gsec = await asyncio.gather(
            asyncio.gather(*(_fetch_one_yahoo(http, sym, name) for sym, name, _ in TICKERS)),
            _fetch_india_gsec(http),
        )
    finally:
        if owns:
            await http.aclose()
    by_attr = {attr: q for (sym, _name, attr), q in zip(TICKERS, yahoo_results)}
    return MacroSnapshot(
        fetched_at=datetime.now(timezone.utc),
        usdinr=by_attr["usdinr"],
        dxy=by_attr["dxy"],
        brent=by_attr["brent"],
        gold=by_attr["gold"],
        india_gsec_10y=india_gsec,
    )
