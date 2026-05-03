"""LinkedIn formatter — header, then data sections separated by blank lines."""
from __future__ import annotations

from ..models import PulseBriefing
from .common import (
    crore,
    fmt_num,
    short_ipo_label,
    signed_pct,
    to_ist,
    trend_emoji,
)


def _idx_line(name: str, q) -> str:
    return f"• {name}: {fmt_num(q.last)} ({signed_pct(q.change_pct)})"


def _mover_line(m) -> str:
    name = m.symbol if len(m.symbol) <= 12 else m.symbol[:11] + "…"
    ratio = "" if m.volume_ratio is None else f" ({m.volume_ratio:.1f}x)"
    return f"{trend_emoji(m.change_pct)} {name} {signed_pct(m.change_pct, places=1)}{ratio}"


def format_linkedin(b: PulseBriefing) -> str:
    date_str = to_ist(b.fetched_at).strftime("%d %b %Y")
    sections: list[str] = [f"Equifiz Pulse · {date_str}"]

    sections.append(
        "Indices (prev close)\n"
        + "\n".join(
            _idx_line(name, q)
            for name, q in (
                ("Sensex", b.indices.sensex),
                ("Nifty 50", b.indices.nifty_50),
                ("Bank Nifty", b.indices.bank_nifty),
                ("India VIX", b.indices.india_vix),
            )
        )
    )

    cash = b.flows.cash
    flow = (
        f"Flows (₹ cr · {cash.date.strftime('%d %b')})\n"
        f"• FII {crore(cash.fii_net)}   • DII {crore(cash.dii_net)}"
    )
    if b.flows.fno and b.flows.fno.index_futures_net is not None:
        flow += f"\n• FII Index Futures: {crore(b.flows.fno.index_futures_net)}"
    sections.append(flow)

    mover_block = "Top movers (Nifty 500)"
    for m in b.movers.gainers[:3]:
        mover_block += "\n" + _mover_line(m)
    for m in b.movers.losers[:3]:
        mover_block += "\n" + _mover_line(m)
    sections.append(mover_block)

    mq = b.macro
    sections.append(
        "Macro\n"
        f"• USDINR {fmt_num(mq.usdinr.last)} ({signed_pct(mq.usdinr.change_pct)})\n"
        f"• Brent ${fmt_num(mq.brent.last)} ({signed_pct(mq.brent.change_pct)})\n"
        f"• Gold ${fmt_num(mq.gold.last)} ({signed_pct(mq.gold.change_pct)})\n"
        f"• US 10Y {fmt_num(mq.us10y.last)}% ({signed_pct(mq.us10y.change_pct)})"
    )

    ipo_lines: list[str] = []
    for it in b.regulatory.items:
        if it.source != "NSE-IPO":
            continue
        label = short_ipo_label(it.title)
        if label:
            ipo_lines.append(f"• {label}")
        if len(ipo_lines) == 3:
            break
    if ipo_lines:
        sections.append("Upcoming IPOs\n" + "\n".join(ipo_lines))

    return "\n\n\n".join(sections)
