"""One-shot live fetch — prints all data sources via Rich.

    uv run python -m pulse.smoke
"""
from __future__ import annotations

import asyncio
import sys
from typing import Iterable

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table

# Windows cp1252 console can't render ₹/Δ — force UTF-8 if available.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass

from .briefing import build_briefing
from .models import (
    FlowsSnapshot,
    IndicesSnapshot,
    MacroSnapshot,
    MoversSnapshot,
    PulseBriefing,
    RegulatorySnapshot,
)


def _color(v: float) -> str:
    return "red" if v < 0 else ("green" if v > 0 else "white")


def _fmt(v: float | None, *, places: int = 2) -> str:
    return "-" if v is None else f"{v:,.{places}f}"


def _indices_table(s: IndicesSnapshot) -> Table:
    t = Table(title=f"NSE indices @ {s.fetched_at:%Y-%m-%d %H:%M:%S} UTC", expand=True)
    for col in ("Index", "Last", "Chg", "Chg %", "Prev", "Open", "High", "Low"):
        t.add_column(col, justify="right" if col != "Index" else "left", no_wrap=True)
    for q in s.all():
        c = _color(q.change_pct)
        t.add_row(
            q.name, _fmt(q.last), f"[{c}]{q.change:+,.2f}[/]",
            f"[{c}]{q.change_pct:+.2f}%[/]",
            _fmt(q.prev_close), _fmt(q.open), _fmt(q.high), _fmt(q.low),
        )
    return t


def _movers_table(s: MoversSnapshot) -> Table:
    t = Table(title=f"Top movers ({s.universe})", expand=True)
    for col in ("Side", "Symbol", "Name", "Last", "Chg %", "Volume", "vs 20d avg"):
        t.add_column(col, justify="right" if col not in ("Side", "Symbol", "Name") else "left", no_wrap=True)
    def _add(side: str, rows: Iterable):
        for m in rows:
            c = _color(m.change_pct)
            ratio = "-" if m.volume_ratio is None else f"{m.volume_ratio:.2f}x"
            t.add_row(side, m.symbol, m.name[:32],
                      _fmt(m.last), f"[{c}]{m.change_pct:+.2f}%[/]",
                      f"{m.volume:,}", ratio)
    _add("[green]GAIN[/]", s.gainers)
    _add("[red]LOSE[/]", s.losers)
    return t


def _flows_panel(s: FlowsSnapshot) -> Panel:
    c = s.cash
    body_lines = [
        f"Cash market — {c.date:%d %b %Y}  (₹ crore)",
        f"  FII   buy {c.fii_buy:>10,.2f}   sell {c.fii_sell:>10,.2f}   "
        f"net [{_color(c.fii_net)}]{c.fii_net:+,.2f}[/]",
        f"  DII   buy {c.dii_buy:>10,.2f}   sell {c.dii_sell:>10,.2f}   "
        f"net [{_color(c.dii_net)}]{c.dii_net:+,.2f}[/]",
    ]
    if s.fno is not None:
        body_lines.append("")
        body_lines.append(f"F&O FII net (₹ cr) — {s.fno.date:%d %b %Y}")
        for label, val in (
            ("Index Futures", s.fno.index_futures_net),
            ("Index Options", s.fno.index_options_net),
            ("Stock Futures", s.fno.stock_futures_net),
            ("Stock Options", s.fno.stock_options_net),
        ):
            if val is None:
                body_lines.append(f"  {label:<14} -")
            else:
                body_lines.append(f"  {label:<14} [{_color(val)}]{val:+,.2f}[/]")
    elif s.fno_unavailable_reason:
        body_lines.append("")
        body_lines.append(f"[yellow]F&O unavailable:[/] {s.fno_unavailable_reason}")
    return Panel("\n".join(body_lines), title="FII / DII flows", expand=True)


def _regulatory_panel(s: RegulatorySnapshot) -> Panel:
    if not s.items:
        body = "[dim]no items in window[/dim]"
    else:
        lines = []
        for it in s.items[:12]:
            ts = it.published.strftime("%Y-%m-%d %H:%M")
            lines.append(f"[bold]{it.source}[/]  {ts}  {it.title[:80]}")
        body = "\n".join(lines)
    if s.unavailable_sources:
        body += "\n\n[yellow]Unavailable:[/] " + " | ".join(s.unavailable_sources)
    return Panel(body, title=f"Regulatory ({len(s.items)} items, last 24h)", expand=True)


def _macro_table(s: MacroSnapshot) -> Table:
    t = Table(title="Macro", expand=True)
    for col in ("Symbol", "Name", "Last", "Chg %", "Prev"):
        t.add_column(col, justify="right" if col not in ("Symbol", "Name") else "left", no_wrap=True)
    for q in s.all():
        c = _color(q.change_pct)
        places = 4 if q.symbol == "INR=X" else 2
        t.add_row(q.symbol, q.name, _fmt(q.last, places=places),
                  f"[{c}]{q.change_pct:+.2f}%[/]", _fmt(q.prev_close, places=places))
    return t


def render(b: PulseBriefing) -> Group:
    return Group(
        _indices_table(b.indices),
        _movers_table(b.movers),
        _flows_panel(b.flows),
        _macro_table(b.macro),
        _regulatory_panel(b.regulatory),
    )


async def _run() -> int:
    console = Console(force_terminal=True, width=160, legacy_windows=False)
    try:
        briefing = await build_briefing()
    except Exception as e:
        console.print(f"[red]Pulse fetch failed:[/] {type(e).__name__}: {e}")
        return 1
    console.print(render(briefing))
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
