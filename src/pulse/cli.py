"""equifiz-pulse CLI."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from dotenv import dotenv_values, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .briefing import build_briefing
from .data.news import fetch_news
from .distribute import (
    ChannelPost,
    PostResult,
    build_channel_post,
    post_to_n8n,
)
from .format import (
    format_news,
    format_telegram,
    format_whatsapp,
)
from .observability import RunLogger, build_run_entry


def _load_env() -> None:
    """Load .env, treating empty strings in os.environ as unset (some harnesses
    inject empty values that would otherwise block override=False)."""
    env_path = Path(".env")
    if not env_path.exists():
        return
    load_dotenv(env_path, override=False, encoding="utf-8-sig")
    file_values = dotenv_values(env_path, encoding="utf-8-sig")
    for k, v in file_values.items():
        if v is None:
            continue
        current = os.environ.get(k, "").strip()
        if not current:
            os.environ[k] = v


_load_env()


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass


@click.group()
def main() -> None:
    """equifiz-pulse — daily Indian markets briefing."""


@main.command()
@click.option(
    "--only",
    type=click.Choice(["telegram", "whatsapp"], case_sensitive=False),
    default=None,
    help="Render only one channel.",
)
def preview(only: str | None) -> None:
    """Generate today's briefing and print channel formats."""
    console = Console(force_terminal=True, width=160, legacy_windows=False)
    try:
        briefing = asyncio.run(build_briefing())
    except Exception as e:
        console.print(f"[red]Pulse fetch failed:[/] {type(e).__name__}: {e}")
        raise SystemExit(1)

    selections = [only.lower()] if only else ["telegram", "whatsapp"]

    if "telegram" in selections:
        text = format_telegram(briefing)
        console.print(Panel(text, title=f"Telegram ({len(text)} chars)", expand=True))

    if "whatsapp" in selections:
        text = format_whatsapp(briefing)
        console.print(Panel(text, title=f"WhatsApp ({len(text)} chars)", expand=True))


CHANNEL_TO_ENV = {
    "telegram": "N8N_TELEGRAM_WEBHOOK",
    "whatsapp": "N8N_WHATSAPP_WEBHOOK",
}


def _ist_today() -> "date":
    from datetime import date, timezone
    from zoneinfo import ZoneInfo
    return datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date()


def _marker_path(ist_today: "date", channel: str) -> Path:
    """Per-channel daily marker. A channel that posted successfully today gets
    skipped on subsequent runs, even if other channels failed."""
    return Path("logs") / "markers" / f"posted-{ist_today.isoformat()}-{channel}.marker"


VALID_CHANNELS = ("telegram", "whatsapp")


@main.command()
@click.option(
    "--only",
    default=None,
    help=(
        "Channel(s) to send to. Comma-separated for multiple, e.g. "
        "'telegram,whatsapp'. Default: all configured channels."
    ),
)
@click.option(
    "--confirm",
    is_flag=True,
    help="Actually POST to webhooks. Without this flag, the command is a dry run.",
)
@click.option(
    "--skip-if-stale",
    is_flag=True,
    help="Exit cleanly (no post) if FII/DII data isn't dated to today's IST session.",
)
@click.option(
    "--once-per-day",
    is_flag=True,
    help="Exit cleanly if we've already posted successfully today (uses logs/markers/).",
)
def run(only: str | None, confirm: bool, skip_if_stale: bool, once_per_day: bool) -> None:
    """Build today's briefing and post to n8n webhooks."""
    console = Console(force_terminal=True, width=160, legacy_windows=False)
    logger = RunLogger()
    started_at = datetime.now(timezone.utc)

    if only:
        requested = [c.strip().lower() for c in only.split(",") if c.strip()]
        invalid = [c for c in requested if c not in VALID_CHANNELS]
        if invalid:
            console.print(
                f"[red]Invalid channel(s):[/] {invalid}. "
                f"Valid: {', '.join(VALID_CHANNELS)}"
            )
            raise SystemExit(2)
        channels = requested
    else:
        channels = list(VALID_CHANNELS)

    missing: list[str] = []
    webhooks: dict[str, str] = {}
    for ch in channels:
        env_key = CHANNEL_TO_ENV[ch]
        url = os.environ.get(env_key, "").strip()
        if url:
            webhooks[ch] = url
        else:
            missing.append(env_key)
    if missing and confirm:
        console.print(
            f"[red]Cannot --confirm: missing webhook env vars:[/] {', '.join(missing)}\n"
            "[dim]Set them in .env or run without --confirm for a dry run.[/]"
        )
        logger.write(build_run_entry(
            started_at=started_at, finished_at=datetime.now(timezone.utc),
            confirm=confirm, only=only, narrative_source="-",
            briefing=None, posts=[],
            error=f"missing webhook env vars: {missing}", exit_code=2,
        ))
        raise SystemExit(2)

    if not confirm:
        console.print(
            "[yellow]DRY RUN[/] — payloads built but not POSTed. "
            "Pass [bold]--confirm[/] to send."
        )

    ist_today = _ist_today()

    # `--once-per-day` is per-channel: skip channels that already posted today,
    # only attempt the remaining ones. Short-circuit entirely if none remain so
    # we don't hammer NSE/Yahoo for a no-op.
    if once_per_day and confirm:
        already_done = [ch for ch in channels if _marker_path(ist_today, ch).exists()]
        pending = [ch for ch in channels if ch not in already_done]
        if not pending:
            console.print(
                f"[yellow]SKIP (already posted today):[/] {', '.join(already_done)}. "
                f"Delete logs/markers/posted-{ist_today.isoformat()}-*.marker to force re-post."
            )
            logger.write(build_run_entry(
                started_at=started_at, finished_at=datetime.now(timezone.utc),
                confirm=confirm, only=only, narrative_source="-",
                briefing=None, posts=[],
                error=f"already_posted_today: {','.join(already_done)}", exit_code=0,
            ))
            return
        if already_done:
            console.print(
                f"[dim]Skipping already-posted: {', '.join(already_done)}. "
                f"Attempting: {', '.join(pending)}.[/]"
            )
        channels = pending
        webhooks = {ch: webhooks[ch] for ch in pending}

    try:
        briefing = asyncio.run(build_briefing())
    except Exception as e:
        console.print(f"[red]Pulse fetch failed:[/] {type(e).__name__}: {e}")
        logger.write(build_run_entry(
            started_at=started_at, finished_at=datetime.now(timezone.utc),
            confirm=confirm, only=only, narrative_source="-",
            briefing=None, posts=[],
            error=f"{type(e).__name__}: {e}", exit_code=1,
        ))
        raise SystemExit(1)

    if skip_if_stale and briefing.flows.cash.date != ist_today:
        console.print(
            f"[yellow]SKIP (stale data):[/] FII/DII data is from "
            f"{briefing.flows.cash.date}, expected {ist_today}. "
            f"NSE typically publishes today's figures by ~19:30 IST after close."
        )
        logger.write(build_run_entry(
            started_at=started_at, finished_at=datetime.now(timezone.utc),
            confirm=confirm, only=only, narrative_source="-",
            briefing=briefing, posts=[],
            error=f"stale_fii_data: got {briefing.flows.cash.date}, expected {ist_today}",
            exit_code=0,
        ))
        return

    narrative_source = "none"

    posts: list[ChannelPost] = []
    for ch in channels:
        url = webhooks.get(ch, "<dry-run-no-url>")
        posts.append(build_channel_post(ch, briefing, webhook_url=url))

    results: list[PostResult]
    if not confirm:
        for p in posts:
            console.print(
                Panel(
                    p.payload["text"],
                    title=f"{p.channel} → {p.webhook_url} ({len(p.payload['text'])} chars)",
                    expand=True,
                )
            )
        results = [
            PostResult(channel=p.channel, status="dry_run", payload_chars=len(p.payload["text"]))
            for p in posts
        ]
        logger.write(build_run_entry(
            started_at=started_at, finished_at=datetime.now(timezone.utc),
            confirm=confirm, only=only, narrative_source=narrative_source,
            briefing=briefing, posts=results, error=None, exit_code=0,
        ))
        return

    results = asyncio.run(_post_all(posts))
    failed = 0
    for res in results:
        if res.status == "sent":
            console.print(
                f"[green]OK {res.channel}[/] sent in {res.duration_ms}ms "
                f"(HTTP {res.http_status}, {res.payload_chars} chars)"
            )
        else:
            failed += 1
            console.print(
                f"[red]FAIL {res.channel}[/] {res.status} after {res.duration_ms}ms — "
                f"{res.error or 'unknown'}"
            )

    exit_code = 1 if failed else 0

    # Per-channel markers: each successful post gets its own marker so a single
    # failed channel doesn't trigger duplicate posts on the next cron tick for
    # the channels that already succeeded.
    if once_per_day and confirm:
        for res in results:
            if res.status == "sent":
                m = _marker_path(ist_today, res.channel)
                m.parent.mkdir(parents=True, exist_ok=True)
                m.write_text(datetime.now(timezone.utc).isoformat() + "\n")

    logger.write(build_run_entry(
        started_at=started_at, finished_at=datetime.now(timezone.utc),
        confirm=confirm, only=only, narrative_source=narrative_source,
        briefing=briefing, posts=results,
        error=(f"{failed} channel(s) failed" if failed else None), exit_code=exit_code,
    ))
    if failed:
        raise SystemExit(1)


@main.command()
@click.option("--last", "n", type=int, default=10, help="Number of recent runs to show.")
@click.option("--raw", is_flag=True, help="Print raw JSONL instead of a table.")
def logs(n: int, raw: bool) -> None:
    """Show recent run logs from logs/pulse-YYYY-MM.jsonl."""
    console = Console(force_terminal=True, width=160, legacy_windows=False)
    logger = RunLogger()
    entries = logger.tail(n)
    if not entries:
        console.print("[dim]No log entries for this month.[/]")
        return
    if raw:
        import json as _json
        for e in entries:
            console.print(_json.dumps(e))
        return
    table = Table(title=f"Last {len(entries)} pulse runs", expand=True)
    for col in ("Started (UTC)", "Dur ms", "Confirm", "Narr", "Channels (status)", "Exit", "Error"):
        table.add_column(col, no_wrap=False)
    for e in entries:
        ch_lines = []
        for p in e.get("posts") or []:
            ch_lines.append(f"{p['channel']}: {p['status']}")
        table.add_row(
            (e.get("started_at") or "")[:19],
            str(e.get("duration_ms", "")),
            "Y" if e.get("args", {}).get("confirm") else "N",
            (e.get("narrative") or "-")[:8],
            "\n".join(ch_lines) or "-",
            str(e.get("exit_code", "")),
            (e.get("error") or "")[:40],
        )
    console.print(table)


async def _post_all(posts: list[ChannelPost]) -> list[PostResult]:
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as http:
        return list(await asyncio.gather(*(post_to_n8n(p, http=http) for p in posts)))


# ---------- pulse news -------------------------------------------------------

def _news_marker_path(ist_today: "date") -> Path:
    return Path("logs") / "markers" / f"news-posted-{ist_today.isoformat()}.marker"


@main.group()
def news() -> None:
    """Daily business news headlines (Business Standard / Economic Times / Mint)."""


@news.command("preview")
def news_preview() -> None:
    """Print the news block without posting."""
    console = Console(force_terminal=True, width=160, legacy_windows=False)
    try:
        snap = asyncio.run(fetch_news())
    except Exception as e:
        console.print(f"[red]News fetch failed:[/] {type(e).__name__}: {e}")
        raise SystemExit(1)
    text = format_news(snap)
    console.print(Panel(text, title=f"News ({snap.total_items()} items, {len(text)} chars)", expand=True))
    if snap.unavailable_sources:
        console.print(f"[yellow]Unavailable:[/] {snap.unavailable_sources}")


@news.command("run")
@click.option("--confirm", is_flag=True, help="Actually POST. Without this, dry-run only.")
@click.option("--once-per-day", is_flag=True, help="Skip if news was already posted today.")
def news_run(confirm: bool, once_per_day: bool) -> None:
    """Build today's news headlines and POST to N8N_TELEGRAM_WEBHOOK."""
    console = Console(force_terminal=True, width=160, legacy_windows=False)
    logger = RunLogger()
    started_at = datetime.now(timezone.utc)
    ist_today = _ist_today()

    webhook = os.environ.get("N8N_TELEGRAM_WEBHOOK", "").strip()
    if confirm and not webhook:
        console.print("[red]N8N_TELEGRAM_WEBHOOK not set; cannot --confirm.[/]")
        raise SystemExit(2)

    if once_per_day and confirm:
        marker = _news_marker_path(ist_today)
        if marker.exists():
            console.print(f"[yellow]SKIP (already posted news today):[/] {marker.name}")
            logger.write({
                "started_at": started_at.isoformat(),
                "command": "news-run",
                "args": {"confirm": confirm},
                "skipped": "already_posted",
                "exit_code": 0,
            })
            return

    if not confirm:
        console.print("[yellow]DRY RUN[/] — payload built but not POSTed.")

    try:
        snap = asyncio.run(fetch_news())
    except Exception as e:
        console.print(f"[red]News fetch failed:[/] {type(e).__name__}: {e}")
        logger.write({
            "started_at": started_at.isoformat(),
            "command": "news-run",
            "args": {"confirm": confirm},
            "error": f"{type(e).__name__}: {e}",
            "exit_code": 1,
        })
        raise SystemExit(1)

    if snap.total_items() == 0:
        console.print(f"[red]All news sources unavailable:[/] {snap.unavailable_sources}")
        logger.write({
            "started_at": started_at.isoformat(),
            "command": "news-run",
            "args": {"confirm": confirm},
            "error": f"all sources unavailable: {snap.unavailable_sources}",
            "exit_code": 1,
        })
        raise SystemExit(1)

    text = format_news(snap)

    if not confirm:
        console.print(Panel(text, title=f"News dry-run ({len(text)} chars)", expand=True))
        if snap.unavailable_sources:
            console.print(f"[yellow]Unavailable:[/] {snap.unavailable_sources}")
        return

    payload = {
        "channel": "telegram",
        "kind": "news",
        "text": text,
        "format": "markdown",
        "generated_at": started_at.isoformat(),
    }
    post = ChannelPost(channel="telegram", webhook_url=webhook, payload=payload)
    result = asyncio.run(_post_all([post]))[0]

    if result.status == "sent":
        console.print(
            f"[green]OK news[/] sent in {result.duration_ms}ms "
            f"(HTTP {result.http_status}, {result.payload_chars} chars)"
        )
        marker = _news_marker_path(ist_today)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(datetime.now(timezone.utc).isoformat() + "\n")
        logger.write({
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "command": "news-run",
            "args": {"confirm": confirm},
            "items": snap.total_items(),
            "unavailable": snap.unavailable_sources,
            "post": result.model_dump(),
            "exit_code": 0,
        })
    else:
        console.print(
            f"[red]FAIL news[/] {result.status} after {result.duration_ms}ms — "
            f"{result.error or 'unknown'}"
        )
        logger.write({
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "command": "news-run",
            "args": {"confirm": confirm},
            "post": result.model_dump(),
            "exit_code": 1,
        })
        raise SystemExit(1)


if __name__ == "__main__":
    main()
