"""WhatsApp formatter — plain text, no markdown, no emojis."""
from __future__ import annotations

from ..models import PulseBriefing
from .common import crore, crore_unsigned, fmt_num, gold_inr_per_10g, signed_pct, to_ist


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
        f"FII  buy {crore_unsigned(cash.fii_buy)} | sell {crore_unsigned(cash.fii_sell)} | net {crore(cash.fii_net)}\n"
        f"DII  buy {crore_unsigned(cash.dii_buy)} | sell {crore_unsigned(cash.dii_sell)} | net {crore(cash.dii_net)}"
    )

    g = " | ".join(f"{m.symbol} {m.change_pct:+.1f}%" for m in b.movers.gainers[:3])
    l = " | ".join(f"{m.symbol} {m.change_pct:+.1f}%" for m in b.movers.losers[:3])
    sections.append(f"TOP MOVERS\nUp: {g}\nDown: {l}")

    mq = b.macro
    gold_inr_10g = gold_inr_per_10g(mq.gold.last, mq.usdinr.last)
    sections.append(
        "MACRO\n"
        f"USDINR {fmt_num(mq.usdinr.last)} | DXY {fmt_num(mq.dxy.last)} | "
        f"Brent {fmt_num(mq.brent.last)}\n"
        f"Gold ${fmt_num(mq.gold.last)} / Rs {fmt_num(gold_inr_10g, places=0)}/10g | "
        f"India G-Sec 10Y {fmt_num(mq.india_gsec_10y.last)}%"
    )

    return "\n\n".join(sections)
