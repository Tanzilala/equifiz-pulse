"""WhatsApp formatter — plain text, no markdown, no emojis."""
from __future__ import annotations

from ..models import PulseBriefing
from .common import crore, fmt_num, short_ipo_label, signed_pct, to_ist


def format_whatsapp(b: PulseBriefing) -> str:
    date_str = to_ist(b.fetched_at).strftime("%d %b %Y")
    sections: list[str] = [f"EQUIFIZ PULSE · {date_str}"]

    sections.append(
        "INDICES\n"
        f"Sensex: {fmt_num(b.indices.sensex.last)} ({signed_pct(b.indices.sensex.change_pct)})\n"
        f"Nifty 50: {fmt_num(b.indices.nifty_50.last)} ({signed_pct(b.indices.nifty_50.change_pct)})\n"
        f"Bank Nifty: {fmt_num(b.indices.bank_nifty.last)} ({signed_pct(b.indices.bank_nifty.change_pct)})\n"
        f"VIX: {fmt_num(b.indices.india_vix.last)} ({signed_pct(b.indices.india_vix.change_pct)})"
    )

    cash = b.flows.cash
    sections.append(
        f"FLOWS (Rs cr · {cash.date.strftime('%d %b')})\n"
        f"FII {crore(cash.fii_net)} | DII {crore(cash.dii_net)}"
    )

    g = " | ".join(f"{m.symbol} {m.change_pct:+.1f}%" for m in b.movers.gainers[:3])
    l = " | ".join(f"{m.symbol} {m.change_pct:+.1f}%" for m in b.movers.losers[:3])
    sections.append(f"TOP MOVERS\nUp: {g}\nDown: {l}")

    mq = b.macro
    sections.append(
        "MACRO\n"
        f"USDINR {fmt_num(mq.usdinr.last)} | Brent {fmt_num(mq.brent.last)} | "
        f"Gold {fmt_num(mq.gold.last)} | US10Y {fmt_num(mq.us10y.last)}%"
    )

    ipo_lines: list[str] = []
    for it in b.regulatory.items:
        if it.source != "NSE-IPO":
            continue
        label = short_ipo_label(it.title)
        if label:
            ipo_lines.append(label)
        if len(ipo_lines) == 3:
            break
    if ipo_lines:
        sections.append("IPOS\n" + "\n".join(ipo_lines))

    return "\n\n".join(sections)
