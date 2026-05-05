"""Telegram formatter — Markdown V1, generous spacing between sections."""
from __future__ import annotations

from ..models import PulseBriefing
from .common import (
    crore,
    crore_net,
    crore_unsigned,
    fmt_num,
    gold_inr_per_10g,
    signed_pct,
    to_ist,
    trend_emoji,
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
    flow_lines = [
        f"*Flows (₹ cr · {cash.date.strftime('%d %b')})*",
        f"• FII   buy `{crore_unsigned(cash.fii_buy)}`   sell `{crore_unsigned(cash.fii_sell)}`",
        f"     net `{crore_net(cash.fii_buy, cash.fii_sell)}`",
        f"• DII   buy `{crore_unsigned(cash.dii_buy)}`   sell `{crore_unsigned(cash.dii_sell)}`",
        f"     net `{crore_net(cash.dii_buy, cash.dii_sell)}`",
    ]
    if b.flows.fno and b.flows.fno.index_futures_net is not None:
        flow_lines.append(f"• FII Idx Fut net: `{crore(b.flows.fno.index_futures_net)}`")
    sections.append("\n".join(flow_lines))

    gainers = "*Top Gainers*"
    for m in b.movers.gainers[:3]:
        gainers += f"\n{trend_emoji(m.change_pct)} `{m.symbol}` {signed_pct(m.change_pct, places=1)}"
    sections.append(gainers)

    losers = "*Top Losers*"
    for m in b.movers.losers[:3]:
        losers += f"\n{trend_emoji(m.change_pct)} `{m.symbol}` {signed_pct(m.change_pct, places=1)}"
    sections.append(losers)

    mq = b.macro
    gold_inr_10g = mq.gold_inr_per_10g or gold_inr_per_10g(mq.gold.last, mq.usdinr.last)
    sections.append(
        "*Macro*\n"
        f"• USDINR {fmt_num(mq.usdinr.last)} ({signed_pct(mq.usdinr.change_pct)})\n"
        f"• Dollar Index {fmt_num(mq.dxy.last)} ({signed_pct(mq.dxy.change_pct)})\n"
        f"• Brent ${fmt_num(mq.brent.last)} ({signed_pct(mq.brent.change_pct)})\n"
        f"• Gold ${fmt_num(mq.gold.last)} / ₹{fmt_num(gold_inr_10g, places=0)}/10g ({signed_pct(mq.gold.change_pct)})\n"
        f"• India G-Sec 10Y {fmt_num(mq.india_gsec_10y.last)}% ({signed_pct(mq.india_gsec_10y.change_pct)})"
    )

    return "\n\n\n".join(sections)
