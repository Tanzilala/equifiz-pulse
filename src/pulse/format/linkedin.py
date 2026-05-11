"""LinkedIn formatter — compact, emoji-led sections, hashtag footer.

LinkedIn columns are wider than mobile chat, so single-line layouts work
fine here. Goal: visually distinct from the Telegram look, scannable in
~10 seconds, ends with hashtag footer for reach.
"""
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

HASHTAGS = (
    "#IndianStockMarket #NSE #BSE #Nifty #Sensex "
    "#DalalStreet #Markets #FII #DII #Equifiz"
)


def _idx_line(name: str, q) -> str:
    """🔴 Sensex 76,015.28 (-1,312.91, -1.70%)"""
    em = trend_emoji(q.change_pct)
    return (
        f"{em} {name} {fmt_num(q.last)} "
        f"({signed_pts(q.change)}, {signed_pct(q.change_pct)})"
    )


def _mover_inline(movers) -> str:
    return " · ".join(
        f"{m.symbol} {signed_pct(m.change_pct, places=1)}" for m in movers[:3]
    )


def format_linkedin(b: PulseBriefing) -> str:
    date_str = to_ist(b.fetched_at).strftime("%d %b %Y")
    sections: list[str] = [f"Equifiz Pulse · {date_str}"]

    sections.append(
        "📊 Indices\n"
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
    fii_em = trend_emoji(float(round(cash.fii_buy) - round(cash.fii_sell)))
    dii_em = trend_emoji(float(round(cash.dii_buy) - round(cash.dii_sell)))
    sections.append(
        f"💸 Flows (₹ cr · {cash.date.strftime('%d %b')})\n"
        f"{fii_em} FII {crore_net(cash.fii_buy, cash.fii_sell)} "
        f"(buy {crore_unsigned(cash.fii_buy)} · sell {crore_unsigned(cash.fii_sell)})\n"
        f"{dii_em} DII {crore_net(cash.dii_buy, cash.dii_sell)} "
        f"(buy {crore_unsigned(cash.dii_buy)} · sell {crore_unsigned(cash.dii_sell)})"
    )

    sections.append(
        "🚀 Top Movers (Nifty 500)\n"
        f"🟢 {_mover_inline(b.movers.gainers)}\n"
        f"🔴 {_mover_inline(b.movers.losers)}"
    )

    mq = b.macro
    gold_inr_10g = mq.gold_inr_per_10g or gold_inr_per_10g(mq.gold.last, mq.usdinr.last)
    sections.append(
        "🌐 Macro\n"
        f"USDINR {fmt_num(mq.usdinr.last)} ({signed_pct(mq.usdinr.change_pct)}) · "
        f"DXY {fmt_num(mq.dxy.last)} ({signed_pct(mq.dxy.change_pct)})\n"
        f"Brent ${fmt_num(mq.brent.last)} ({signed_pct(mq.brent.change_pct)}) · "
        f"India 10Y G-Sec {fmt_num(mq.india_gsec_10y.last)}% ({signed_pct(mq.india_gsec_10y.change_pct)})\n"
        f"Gold ${fmt_num(mq.gold.last)} / ₹{fmt_num(gold_inr_10g, places=0)}/10g "
        f"({signed_pct(mq.gold.change_pct)})"
    )

    sections.append(HASHTAGS)

    return "\n\n".join(sections)
