"""equifiz-pulse CLI."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
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
    format_linkedin,
    format_news,
    format_telegram,
    format_whatsapp,
)
from .observability import RunLogger, build_run_entry

# Pre-load .env so ANTHROPIC_API_KEY etc. are available before commands run.
def _load_env() -> None:
    """Load .env, but treat empty strings in os.environ as unset.

    Some shells/harnesses inject empty `ANTHROPIC_API_KEY=""` etc. With
    `override=False`, plain load_dotenv would refuse to overwrite the empty,
    so the .env value never wins. We manually copy values from .env when the
    current env entry is empty or whitespace.
    """
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
def indices() -> None:
    """Print today's index snapshot (live NSE) for debugging."""
    from .smoke import main as smoke_main

    raise SystemExit(smoke_main())


@main.command()
@click.option(
    "--only",
    type=click.Choice(["linkedin", "telegram", "whatsapp"], case_sensitive=False),
    default=None,
    help="Render only one channel.",
)
def preview(only: str | None) -> None:
    """Generate today's briefing and print all three channel formats."""
    console = Console(force_terminal=True, width=160, legacy_windows=False)
    try:
        briefing = asyncio.run(build_briefing())
    except Exception as e:
        console.print(f"[red]Pulse fetch failed:[/] {type(e).__name__}: {e}")
        raise SystemExit(1)

    selections = (
        [only.lower()] if only else ["linkedin", "telegram", "whatsapp"]
    )

    if "linkedin" in selections:
        text = format_linkedin(briefing)
        console.print(Panel(text, title=f"LinkedIn ({len(text)} chars)", expand=True))

    if "telegram" in selections:
        text = format_telegram(briefing)
        console.print(Panel(text, title=f"Telegram ({len(text)} chars)", expand=True))

    if "whatsapp" in selections:
        text = format_whatsapp(briefing)
        console.print(Panel(text, title=f"WhatsApp ({len(text)} chars)", expand=True))


CHANNEL_TO_ENV = {
    "linkedin": "N8N_LINKEDIN_WEBHOOK",
    "telegram": "N8N_TELEGRAM_WEBHOOK",
    "whatsapp": "N8N_WHATSAPP_WEBHOOK",
}


def _ist_today() -> "date":
    from datetime import date, timezone
    from zoneinfo import ZoneInfo
    return datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date()


def _marker_path(ist_today: "date") -> Path:
    return Path("logs") / "markers" / f"posted-{ist_today.isoformat()}.marker"


VALID_CHANNELS = ("linkedin", "telegram", "whatsapp")


@main.command()
@click.option(
    "--only",
    default=None,
    help=(
        "Channel(s) to send to. Comma-separated for multiple, e.g. "
        "'telegram,linkedin'. Default: all three configured channels."
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

    # `--once-per-day` short-circuits before fetching: if we already posted today,
    # no point hammering NSE/Yahoo just to throw the result away.
    if once_per_day and confirm:
        marker = _marker_path(ist_today)
        if marker.exists():
            console.print(
                f"[yellow]SKIP (already posted):[/] marker {marker.name} exists. "
                f"Delete it to force a re-post."
            )
            logger.write(build_run_entry(
                started_at=started_at, finished_at=datetime.now(timezone.utc),
                confirm=confirm, only=only, narrative_source="-",
                briefing=None, posts=[],
                error=f"already_posted_today: {marker.name}", exit_code=0,
            ))
            return

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

    # Write the once-per-day marker only if all targeted posts succeeded —
    # partial success leaves the day unmarked so the next cron tick can retry.
    if once_per_day and confirm and exit_code == 0:
        marker = _marker_path(ist_today)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(datetime.now(timezone.utc).isoformat() + "\n")

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


def _find_uv() -> str | None:
    p = shutil.which("uv") or shutil.which("uv.exe")
    if p:
        return p
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            base = Path(local) / "Microsoft" / "WinGet" / "Packages"
            if base.exists():
                for cand in base.rglob("uv.exe"):
                    return str(cand)
    return None


@main.command("install-schedule")
@click.option("--time", "time_", default="08:30", help="Local HH:MM (default 08:30).")
@click.option("--task-name", default="EquifizPulseDaily")
@click.option("--apply", "apply_", is_flag=True, help="Actually create the task. Without this, just prints the command.")
@click.option("--uv-path", "uv_path", default=None, help="Override the uv.exe path.")
def install_schedule(time_: str, task_name: str, apply_: bool, uv_path: str | None) -> None:
    """Install a Windows scheduled task to run `pulse run --confirm` daily."""
    console = Console(force_terminal=True, legacy_windows=False)
    project_dir = str(Path.cwd())
    uv = uv_path or _find_uv()
    if not uv:
        console.print(
            "[red]uv not found.[/] Pass [bold]--uv-path C:\\path\\to\\uv.exe[/] "
            "or restart your shell so winget's PATH update takes effect."
        )
        raise SystemExit(2)

    if sys.platform != "win32":
        cron_line = f"30 8 * * 1-5 cd {project_dir} && {uv} run pulse run --confirm >> logs/cron.log 2>&1"
        console.print("Add this line to your crontab (assumes server clock is IST):")
        console.print(f"[bold]{cron_line}[/]")
        return

    tr = f'"{uv}" run --project "{project_dir}" pulse run --confirm'
    cmd = [
        "schtasks", "/Create", "/SC", "DAILY",
        "/TN", task_name,
        "/TR", tr,
        "/ST", time_,
        "/F",
    ]
    console.print("Will run:")
    console.print(f"[bold]{' '.join(cmd)}[/]")
    if not apply_:
        console.print("[yellow]Dry run — pass --apply to actually create the task.[/]")
        return
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        console.print(f"[red]schtasks not available:[/] {e}")
        raise SystemExit(2)
    if result.returncode != 0:
        console.print(f"[red]schtasks failed (exit {result.returncode}):[/] {result.stderr.strip()}")
        raise SystemExit(result.returncode)
    console.print(f"[green]Task {task_name!r} created — fires daily at {time_} local time.[/]")
    console.print("[dim]Inspect with: schtasks /Query /TN " + task_name + "[/]")


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
