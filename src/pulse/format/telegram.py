"""Telegram formatter — Markdown V1, generous spacing between sections."""
from __future__ import annotations

from ..models import PulseBriefing
from .common import (
    crore,
    fmt_num,
    short_ipo_label,
    signed_pct,
    to_ist,
    trend_emoji,
    vol_ratio,
)


def _idx_md(name: str, q) -> str:
    em = trend_emoji(q.change_pct)
    return f"• {name}: `{fmt_num(q.last)}` {em} {signed_pct(q.change_pct)}"


def format_telegram(b: PulseBriefing) -> str:
    date_str = to_ist(b.fetched_at).strftime("%d %b %Y")
    sections: list[str] = [f"*Equifiz Pulse · {date_str}*"]

    sections.append(
        "*Indices*\n"
        + "\n".join(
            _idx_md(name, q)
            for name, q in (
                ("Sensex", b.indices.sensex),
                ("Nifty 50", b.indices.nifty_50),
                ("Bank Nifty", b.indices.bank_nifty),
                ("India VIX", b.indices.india_vix),
            )
        )
    )

    cash = b.flows.cash
    flows = (
        f"*Flows (₹ cr · {cash.date.strftime('%d %b')})*\n"
        f"• FII `{crore(cash.fii_net)}`   • DII `{crore(cash.dii_net)}`"
    )
    if b.flows.fno and b.flows.fno.index_futures_net is not None:
        flows += f"\n• FII Idx Fut: `{crore(b.flows.fno.index_futures_net)}`"
    sections.append(flows)

    movers = "*Top movers*"
    for m in b.movers.gainers[:3]:
        movers += f"\n🔺 `{m.symbol}` {signed_pct(m.change_pct, places=1)}{vol_ratio(m.volume_ratio)}"
    for m in b.movers.losers[:3]:
        movers += f"\n🔻 `{m.symbol}` {signed_pct(m.change_pct, places=1)}{vol_ratio(m.volume_ratio)}"
    sections.append(movers)

    mq = b.macro
    sections.append(
        "*Macro*\n"
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
        sections.append("*Upcoming IPOs*\n" + "\n".join(ipo_lines))

    return "\n\n\n".join(sections)
