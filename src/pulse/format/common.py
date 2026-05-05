"""Shared number/date formatting helpers used by all three channel formatters."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_IPO_TITLE_RE = re.compile(
    r"Upcoming IPO:\s*(?P<name>.+?)\s*\((?P<sym>[^)]+)\)\s*—\s*opens\s*(?P<open>\d{2}-\w{3}-\d{4})"
)
_COMPANY_SUFFIX_RE = re.compile(r"\s+(Limited|Ltd\.?|Pvt\.?\s*Ltd\.?)\s*$", re.IGNORECASE)


def short_ipo_label(title: str) -> Optional[str]:
    """'Upcoming IPO: Foo Limited (FOO) — opens 30-Apr-2026, closes ...'
    becomes 'Foo (FOO) · opens 30 Apr'. Returns None if title doesn't match."""
    m = _IPO_TITLE_RE.search(title)
    if not m:
        return None
    name = _COMPANY_SUFFIX_RE.sub("", m.group("name").strip())
    sym = m.group("sym").strip()
    try:
        d, mon, _ = m.group("open").split("-")
        when = f"{int(d):02d} {mon}"
    except (ValueError, AttributeError):
        when = m.group("open")
    return f"{name} ({sym}) · opens {when}"


def to_ist(dt: datetime) -> datetime:
    return dt.astimezone(IST)


def fmt_int(v: float) -> str:
    return f"{int(round(v)):,}"


def fmt_num(v: float, places: int = 2) -> str:
    return f"{v:,.{places}f}"


def signed_pct(pct: float, places: int = 2) -> str:
    return f"{pct:+.{places}f}%"


def signed_num(v: float, places: int = 2) -> str:
    return f"{v:+,.{places}f}"


def crore(v: float) -> str:
    """Format a ₹ crore figure: rounds to integer, comma-separated, signed."""
    return f"{v:+,.0f}"


def crore_unsigned(v: float) -> str:
    """Format a ₹ crore figure as a positive magnitude (for buy/sell columns)."""
    return f"{v:,.0f}"


def crore_net(buy: float, sell: float) -> str:
    """Net = displayed_buy − displayed_sell so the row always reconciles.
    No '+' prefix on positives; '-' prefix on negatives.
    """
    net_int = round(buy) - round(sell)
    return f"{net_int:,}"


# 1 troy ounce = 31.1034768 grams. Indian gold market quotes ₹/10g.
_GRAMS_PER_OZ = 31.1034768


def gold_inr_per_10g(usd_per_oz: float, usdinr_rate: float) -> float:
    """Convert COMEX gold (USD/oz) to the Indian wholesale equivalent in ₹/10g."""
    return (usd_per_oz * usdinr_rate / _GRAMS_PER_OZ) * 10


def vol_ratio(ratio: float | None) -> str:
    if ratio is None:
        return ""
    return f" ({ratio:.1f}x avg vol)"


def trend_arrow_text(pct: float) -> str:
    """ASCII-safe trend arrow."""
    if pct > 0.05:
        return "^"
    if pct < -0.05:
        return "v"
    return "~"


def trend_arrow_unicode(pct: float) -> str:
    if pct > 0.05:
        return "↑"
    if pct < -0.05:
        return "↓"
    return "→"


def trend_emoji(pct: float) -> str:
    """Color-coded trend marker — green for up, red for down.

    Plain Unicode arrows aren't green/red anywhere; emoji triangles like
    🔺/🔻 are both red. Colored circles paired with the signed % give the
    cleanest "green = up / red = down" read across LinkedIn and Telegram.
    """
    if pct > 0.05:
        return "🟢"
    if pct < -0.05:
        return "🔴"
    return "⚪"
