# equifiz-pulse

Daily Indian markets briefing. Pulls from NSE / Yahoo Finance / RBI+SEBI RSS, generates LinkedIn / Telegram / WhatsApp variants, ships through n8n webhooks. **No external LLM** — narrative prose is rule-derived from the data itself.

## Status

All six build steps complete. 71 offline tests, 3 live tests gated behind `pytest -m live`.

## Setup

```bash
uv sync
cp .env.example .env       # then edit
```

`.env` keys:
- `N8N_LINKEDIN_WEBHOOK`, `N8N_TELEGRAM_WEBHOOK`, `N8N_WHATSAPP_WEBHOOK` — required to actually post.
- `EQUIFIZ_PULSE_URL` — link printed in the Telegram footer (default `https://equifiz.com/pulse`).

## CLI

```bash
# Preview only — never POSTs anything
uv run pulse preview                       # all three channel formats
uv run pulse preview --only telegram

# Run = post via n8n.  --confirm is REQUIRED to actually send.
uv run pulse run --only telegram           # dry run (prints payload, no POST)
uv run pulse run --only telegram --confirm # actually POSTs to N8N_TELEGRAM_WEBHOOK
uv run pulse run --confirm                 # post to all three webhooks

# Debug
uv run pulse indices                       # NSE indices snapshot only
uv run pulse logs --last 10                # last 10 runs as a table
uv run pulse logs --raw                    # raw JSONL
```

### n8n flows

Importable workflow JSON files live in [`n8n-flows/`](n8n-flows/). Telegram is ready — see [n8n-flows/README.md](n8n-flows/README.md) for setup. LinkedIn + WhatsApp flows are TODO.

### n8n payload shape

Each POST is a JSON envelope:

```json
{
  "channel": "telegram",
  "text": "<rendered message>",
  "format": "markdown",
  "generated_at": "2026-05-03T03:00:00+00:00"
}
```

`format` is `markdown` for Telegram and `plain` for LinkedIn / WhatsApp. Your n8n flow reads `text` and routes accordingly.

Failed posts return non-zero exit codes (1 = some channels failed, 2 = config error).

## Narrative generation

`hook`, `framing`, and `watch_today` are produced by [src/pulse/format/narrative.py](src/pulse/format/narrative.py) — a small set of priority rules over the briefing data:

- **Hook** picks the most striking signal (VIX spike, FII dump, big Nifty move, or a fallback).
- **Framing** describes flow direction (FII vs DII), breadth (midcaps vs largecaps, banks lagging), and any volatility/direction interplay.
- **Watch today** anchors on Nifty 50's prev close, calls out an upcoming IPO if one's listed, and surfaces USDINR pressure points.

To tune the voice, edit the rules directly. No prompts, no API costs, deterministic output.

## Logging

Every `pulse run` writes one JSON line to `logs/pulse-YYYY-MM.jsonl` with started/finished timestamps, per-source data status (incl. F&O availability and regulatory unavailable_sources), volume-enriched mover ratio, per-channel post results, and exit code.

## Scheduling — daily auto-post

Three ways to run this daily, pick one:

### A. GitHub Actions (recommended for cloud)

A workflow lives at [.github/workflows/daily-pulse.yml](.github/workflows/daily-pulse.yml) — fires at **02:50 UTC (08:20 IST)** Mon-Fri, runs `pulse run --only telegram --confirm`.

Setup:

1. Push the repo to GitHub (private is fine).
2. **Settings → Secrets and variables → Actions → New repository secret**, add:
   - `N8N_TELEGRAM_WEBHOOK` (required for default workflow)
   - `N8N_LINKEDIN_WEBHOOK`, `N8N_WHATSAPP_WEBHOOK` (when those flows exist)
   - `EQUIFIZ_PULSE_URL` (optional — Telegram footer link)
3. Open **Actions** tab → enable workflows → manually trigger **Daily Pulse** once via *Run workflow* to verify.

GitHub's cron has up to ~15 min drift under load — that's why we schedule for 08:20 IST, leaving a buffer before market open at 09:15.

To enable LinkedIn and WhatsApp later, edit the workflow and drop `--only telegram`, or trigger manually with a different `only` input.

### B. Local Windows Task Scheduler

Only good if your laptop is on/awake at 08:30 every weekday. If it sleeps, the task silently misses.

```powershell
uv run pulse install-schedule --time 08:30           # prints the schtasks command
uv run pulse install-schedule --time 08:30 --apply   # creates the task
```

Installs a Windows Scheduled Task `EquifizPulseDaily`.

### C. VPS cron

Any always-on Linux box ($5/mo Hetzner / DigitalOcean works). After cloning the repo and running `uv sync`:

```cron
50 2 * * 1-5 cd /path/to/equifiz-pulse && /usr/local/bin/uv run pulse run --confirm >> logs/cron.log 2>&1
```

(02:50 UTC = 08:20 IST. Set system TZ to IST and use `30 8 * * 1-5` for cleaner local-time editing.)
