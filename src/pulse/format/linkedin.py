"""LinkedIn formatter — header, then data sections separated by blank lines."""
from __future__ import annotations

from ..models import PulseBriefing
from .common import (
    crore_net,
    crore_unsigned,
    fmt_num,
    gold_inr_per_10g,
    signed_pct,
    signed_pts,
    to_ist,
    trend_emoji,
)


def _idx_block(name: str, q) -> str:
    em = trend_emoji(q.change_pct)
    return (
        f"{name} {fmt_num(q.last)}\n"
        f"{em} {signed_pts(q.change)} ({signed_pct(q.change_pct)})"
    )


def _mover_line(m) -> str:
    name = m.symbol if len(m.symbol) <= 12 else m.symbol[:11] + "…"
    return f"{trend_emoji(m.change_pct)} {name} {signed_pct(m.change_pct, places=1)}"


def _flow_block(label: str, buy: float, sell: float) -> str:
    net_int = round(buy) - round(sell)
    em = trend_emoji(float(net_int))
    return (
        f"{label} {em} {crore_net(buy, sell)}\n"
        f"   buy {crore_unsigned(buy)} · sell {crore_unsigned(sell)}"
    )


def format_linkedin(b: PulseBriefing) -> str:
    date_str = to_ist(b.fetched_at).strftime("%d %b %Y")
    sections: list[str] = [f"Equifiz Pulse · {date_str}"]

    sections.append(
        "Indices (prev close)\n\n"
        + "\n\n".join(
            _idx_block(name, q)
            for name, q in (
                ("Sensex", b.indices.sensex),
                ("Nifty 50", b.indices.nifty_50),
                ("Bank Nifty", b.indices.bank_nifty),
                ("India VIX", b.indices.india_vix),
            )
        )
    )

    cash = b.flows.cash
    flow_section = (
        f"Flows (₹ cr · {cash.date.strftime('%d %b')})\n\n"
        f"{_flow_block('FII', cash.fii_buy, cash.fii_sell)}\n\n"
        f"{_flow_block('DII', cash.dii_buy, cash.dii_sell)}"
    )
    if b.flows.fno and b.flows.fno.index_futures_net is not None:
        fno_em = trend_emoji(b.flows.fno.index_futures_net)
        flow_section += f"\n\nFII Index Futures {fno_em} {round(b.flows.fno.index_futures_net):+,}"
    sections.append(flow_section)

    gainers_block = "Top Gainers (Nifty 500)"
    for m in b.movers.gainers[:3]:
        gainers_block += "\n" + _mover_line(m)
    sections.append(gainers_block)

    losers_block = "Top Losers (Nifty 500)"
    for m in b.movers.losers[:3]:
        losers_block += "\n" + _mover_line(m)
    sections.append(losers_block)

    mq = b.macro
    gold_inr_10g = mq.gold_inr_per_10g or gold_inr_per_10g(mq.gold.last, mq.usdinr.last)
    sections.append(
        "Macro\n"
        f"• USDINR {fmt_num(mq.usdinr.last)} ({signed_pct(mq.usdinr.change_pct)})\n"
        f"• Dollar Index {fmt_num(mq.dxy.last)} ({signed_pct(mq.dxy.change_pct)})\n"
        f"• Brent ${fmt_num(mq.brent.last)} ({signed_pct(mq.brent.change_pct)})\n"
        f"• Gold ${fmt_num(mq.gold.last)} / ₹{fmt_num(gold_inr_10g, places=0)}/10g ({signed_pct(mq.gold.change_pct)})\n"
        f"• India G-Sec 10Y {fmt_num(mq.india_gsec_10y.last)}% ({signed_pct(mq.india_gsec_10y.change_pct)})"
    )

    return "\n\n\n".join(sections)
