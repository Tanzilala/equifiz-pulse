"""Shared number/date formatting helpers used by all three channel formatters."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# 1 troy ounce = 31.1034768 grams. Indian gold market quotes ₹/10g.
_GRAMS_PER_OZ = 31.1034768


def to_ist(dt: datetime) -> datetime:
    return dt.astimezone(IST)


def fmt_num(v: float, places: int = 2) -> str:
    return f"{v:,.{places}f}"


def signed_pct(pct: float, places: int = 2) -> str:
    return f"{pct:+.{places}f}%"


def signed_pts(v: float, places: int = 2) -> str:
    """Format an absolute change-in-points figure with sign and 2dp."""
    return f"{v:+,.{places}f}"


def crore(v: float) -> str:
    """Format a ₹ crore figure: rounds to integer, comma-separated, signed."""
    return f"{v:+,.0f}"


def crore_unsigned(v: float) -> str:
    """Format a ₹ crore figure as a positive magnitude (for buy/sell columns)."""
    return f"{v:,.0f}"


def crore_net(buy: float, sell: float) -> str:
    """Net = displayed_buy − displayed_sell so the row always reconciles.
    Always signed (+ for positive, − for negative).
    """
    net_int = round(buy) - round(sell)
    return f"{net_int:+,}"


def gold_inr_per_10g(usd_per_oz: float, usdinr_rate: float) -> float:
    """Convert COMEX gold (USD/oz) to the Indian wholesale equivalent in ₹/10g."""
    return (usd_per_oz * usdinr_rate / _GRAMS_PER_OZ) * 10


def trend_emoji(pct: float) -> str:
    """Color-coded trend marker — green for up, red for down."""
    if pct > 0.05:
        return "🟢"
    if pct < -0.05:
        return "🔴"
    return "⚪"
