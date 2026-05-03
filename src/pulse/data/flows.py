"""FII / DII flows.

Cash market is the primary signal — fails loud if NSE returns no rows.
F&O is best-effort: NSE has rotated their endpoints multiple times; we try a
known JSON API, and if it's gone we mark `fno_unavailable_reason` and continue.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from ..models import FIIDIICash, FIIFnoNet, FlowsSnapshot
from .nse_client import NSEClient, NSEError

CASH_PATH = "/fiidiiTradeReact"
FNO_CANDIDATE_PATHS = (
    "/fii-derivatives-statistics",
    "/fii-derivatives-statistics?type=daily",
)

_FII_KEYS = ("FII", "FPI")
_DII_KEYS = ("DII",)


def _f(v: Any) -> Optional[float]:
    if v in (None, "", "-"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _parse_dmy(s: str) -> date:
    # NSE returns dates like '02-May-2026'
    return datetime.strptime(s.strip(), "%d-%b-%Y").date()


def _category_matches(cat: str, keys: tuple[str, ...]) -> bool:
    upper = (cat or "").upper()
    return any(k in upper for k in keys)


def parse_cash(payload: Any) -> FIIDIICash:
    rows = payload if isinstance(payload, list) else (payload.get("data") if isinstance(payload, dict) else None)
    if not rows:
        raise NSEError(f"FII/DII cash payload empty / unrecognized: {payload!r}")

    fii_row = next((r for r in rows if _category_matches(r.get("category", ""), _FII_KEYS)), None)
    dii_row = next((r for r in rows if _category_matches(r.get("category", ""), _DII_KEYS)), None)
    if not fii_row or not dii_row:
        raise NSEError(
            f"FII/DII cash missing rows — got categories: "
            f"{[r.get('category') for r in rows]}"
        )

    fii_buy = _f(fii_row.get("buyValue"))
    fii_sell = _f(fii_row.get("sellValue"))
    fii_net = _f(fii_row.get("netValue"))
    dii_buy = _f(dii_row.get("buyValue"))
    dii_sell = _f(dii_row.get("sellValue"))
    dii_net = _f(dii_row.get("netValue"))
    if None in (fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net):
        raise NSEError(f"FII/DII cash: missing numeric fields. fii={fii_row} dii={dii_row}")

    raw_date = fii_row.get("date") or dii_row.get("date")
    try:
        d = _parse_dmy(raw_date) if raw_date else datetime.now(timezone.utc).date()
    except ValueError:
        d = datetime.now(timezone.utc).date()

    return FIIDIICash(
        date=d,
        fii_buy=fii_buy,    # type: ignore[arg-type]
        fii_sell=fii_sell,  # type: ignore[arg-type]
        fii_net=fii_net,    # type: ignore[arg-type]
        dii_buy=dii_buy,    # type: ignore[arg-type]
        dii_sell=dii_sell,  # type: ignore[arg-type]
        dii_net=dii_net,    # type: ignore[arg-type]
    )


def parse_fno(payload: Any) -> FIIFnoNet:
    """Best-effort parse — returns NaN-ish FIIFnoNet (Nones) if shape unknown.

    NSE fii-derivatives-statistics historically returns rows keyed by
    instrument like "INDEX FUTURES", "INDEX OPTIONS", "STOCK FUTURES",
    "STOCK OPTIONS" with `netVal` (₹ crore notional).
    """
    rows: list[dict[str, Any]]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        rows = payload["data"]
    else:
        raise NSEError(f"F&O payload unrecognized: {type(payload).__name__}")

    def _net_for(name_substr: str) -> Optional[float]:
        for r in rows:
            label = (r.get("instrument") or r.get("Instrument") or r.get("category") or "").upper()
            if name_substr in label:
                for k in ("netVal", "netValue", "net", "NetValue"):
                    if k in r:
                        return _f(r[k])
        return None

    raw_date = next(
        (r.get("date") or r.get("Date") for r in rows if r.get("date") or r.get("Date")),
        None,
    )
    try:
        d = _parse_dmy(raw_date) if raw_date else datetime.now(timezone.utc).date()
    except (ValueError, TypeError):
        d = datetime.now(timezone.utc).date()

    return FIIFnoNet(
        date=d,
        index_futures_net=_net_for("INDEX FUT"),
        index_options_net=_net_for("INDEX OPT"),
        stock_futures_net=_net_for("STOCK FUT"),
        stock_options_net=_net_for("STOCK OPT"),
    )


async def fetch_cash(client: NSEClient) -> FIIDIICash:
    payload = await client.get_json(CASH_PATH, cache_ttl=120.0)
    return parse_cash(payload)


async def fetch_fno(client: NSEClient) -> Optional[FIIFnoNet]:
    last_status: Optional[str] = None
    for path in FNO_CANDIDATE_PATHS:
        try:
            payload = await client.get_json(path, cache_ttl=120.0)
            return parse_fno(payload)
        except (NSEError, KeyError, ValueError, TypeError) as e:
            msg = str(e)
            for code in ("404", "503", "500", "403"):
                if code in msg:
                    last_status = f"HTTP {code}"
                    break
            else:
                last_status = type(e).__name__
            continue
    raise NSEError(f"F&O endpoints unavailable ({last_status})")


async def fetch_flows(client: NSEClient) -> FlowsSnapshot:
    cash = await fetch_cash(client)  # required — raises on miss
    try:
        fno = await fetch_fno(client)
        return FlowsSnapshot(
            fetched_at=datetime.now(timezone.utc), cash=cash, fno=fno, fno_unavailable_reason=None
        )
    except NSEError as e:
        return FlowsSnapshot(
            fetched_at=datetime.now(timezone.utc),
            cash=cash,
            fno=None,
            fno_unavailable_reason=str(e),
        )
