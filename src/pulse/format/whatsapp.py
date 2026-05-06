"""WhatsApp formatter — plain text, no markdown, no emojis."""
from __future__ import annotations

from ..models import PulseBriefing
from .common import crore_net, crore_unsigned, fmt_num, gold_inr_per_10g, signed_pct, signed_pts, to_ist


def _idx_block(name: str, q) -> str:
    return (
        f"{name} {fmt_num(q.last)}\n"
        f"{signed_pts(q.change)} ({signed_pct(q.change_pct)})"
    )


def format_whatsapp(b: PulseBriefing) -> str:
    date_str = to_ist(b.fetched_at).strftime("%d %b %Y")
    sections: list[str] = [f"EQUIFIZ PULSE · {date_str}"]

    sections.append(
        "INDICES\n\n"
        + "\n\n".join(
            _idx_block(name, q)
            for name, q in (
                ("Sensex", b.indices.sensex),
                ("Nifty 50", b.indices.nifty_50),
                ("Bank Nifty", b.indices.bank_nifty),
                ("VIX", b.indices.india_vix),
            )
        )
    )

    cash = b.flows.cash
    sections.append(
        f"FLOWS (Rs cr · {cash.date.strftime('%d %b')})\n\n"
        f"FII  {crore_net(cash.fii_buy, cash.fii_sell)}\n"
        f"   buy {crore_unsigned(cash.fii_buy)} | sell {crore_unsigned(cash.fii_sell)}\n\n"
        f"DII  {crore_net(cash.dii_buy, cash.dii_sell)}\n"
        f"   buy {crore_unsigned(cash.dii_buy)} | sell {crore_unsigned(cash.dii_sell)}"
    )

    gainers_lines = "\n".join(
        f"{m.symbol} {m.change_pct:+.1f}%" for m in b.movers.gainers[:3]
    )
    losers_lines = "\n".join(
        f"{m.symbol} {m.change_pct:+.1f}%" for m in b.movers.losers[:3]
    )
    sections.append(f"TOP GAINERS\n{gainers_lines}")
    sections.append(f"TOP LOSERS\n{losers_lines}")

    mq = b.macro
    gold_inr_10g = mq.gold_inr_per_10g or gold_inr_per_10g(mq.gold.last, mq.usdinr.last)
    sections.append(
        "MACRO\n"
        f"USDINR {fmt_num(mq.usdinr.last)} | DXY {fmt_num(mq.dxy.last)} | "
        f"Brent {fmt_num(mq.brent.last)}\n"
        f"Gold ${fmt_num(mq.gold.last)} / Rs {fmt_num(gold_inr_10g, places=0)}/10g | "
        f"India G-Sec 10Y {fmt_num(mq.india_gsec_10y.last)}%"
    )

    return "\n\n".join(sections)
