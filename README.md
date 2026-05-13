# equifiz-pulse

Daily Indian markets briefing. Pulls from NSE / Yahoo Finance / RBI+SEBI RSS, generates Telegram / WhatsApp variants, ships through n8n webhooks. **No external LLM** — narrative prose is rule-derived from the data itself.

## Status

All six build steps complete. 71 offline tests, 3 live tests gated behind `pytest -m live`.

## Setup

```bash
uv sync
cp .env.example .env       # then edit
```

`.env` keys:
- `N8N_TELEGRAM_WEBHOOK`, `N8N_WHATSAPP_WEBHOOK` — required to actually post.
- `EQUIFIZ_PULSE_URL` — link printed in the Telegram footer (default `https://equifiz.com/pulse`).

## CLI

```bash
# Preview only — never POSTs anything
uv run pulse preview                       # all configured channel formats
uv run pulse preview --only telegram

# Run = post via n8n.  --confirm is REQUIRED to actually send.
uv run pulse run --only telegram           # dry run (prints payload, no POST)
uv run pulse run --only telegram --confirm # actually POSTs to N8N_TELEGRAM_WEBHOOK
uv run pulse run --confirm                 # post to all configured webhooks

# Debug
uv run pulse logs --last 10                # last 10 runs as a table
uv run pulse logs --raw                    # raw JSONL

# Daily business news (separate command — fires at 08:00 IST via cron)
uv run pulse news preview                  # show the news block, no posting
uv run pulse news run                      # dry-run
uv run pulse news run --once-per-day --confirm   # post; skips if already posted today
```

### n8n flows

Importable workflow JSON files live in [`n8n-flows/`](n8n-flows/). Telegram is ready — see [n8n-flows/README.md](n8n-flows/README.md) for setup. WhatsApp flow is TODO.

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

`format` is `markdown` for Telegram and `plain` for WhatsApp. Your n8n flow reads `text` and routes accordingly.

Failed posts return non-zero exit codes (1 = some channels failed, 2 = config error).

## Narrative generation

`hook`, `framing`, and `watch_today` are produced by [src/pulse/format/narrative.py](src/pulse/format/narrative.py) — a small set of priority rules over the briefing data:

- **Hook** picks the most striking signal (VIX spike, FII dump, big Nifty move, or a fallback).
- **Framing** describes flow direction (FII vs DII), breadth (midcaps vs largecaps, banks lagging), and any volatility/direction interplay.
- **Watch today** anchors on Nifty 50's prev close, calls out an upcoming IPO if one's listed, and surfaces USDINR pressure points.

To tune the voice, edit the rules directly. No prompts, no API costs, deterministic output.

## Logging

Every `pulse run` writes one JSON line to `logs/pulse-YYYY-MM.jsonl` with started/finished timestamps, per-source data status (incl. F&O availability), per-channel post results, and exit code.

## Scheduling — daily auto-post

Three ways to run this daily, pick one:

> **Note on GitHub Actions cron:** GitHub's runners live in US/EU datacenters and NSE blocks those IPs (403 anti-bot). **Use Option C (VPS in India).** GitHub Actions still works for manual triggers from the UI but the daily cron is disabled.

### A. GitHub Actions (manual triggers only — cron blocked by NSE)

A workflow lives at [.github/workflows/daily-pulse.yml](.github/workflows/daily-pulse.yml) — fires at **02:50 UTC (08:20 IST)** Mon-Fri, runs `pulse run --only telegram --confirm`.

Setup:

1. Push the repo to GitHub (private is fine).
2. **Settings → Secrets and variables → Actions → New repository secret**, add:
   - `N8N_TELEGRAM_WEBHOOK` (required for default workflow)
   - `N8N_WHATSAPP_WEBHOOK` (when that flow exists)
   - `EQUIFIZ_PULSE_URL` (optional — Telegram footer link)
3. Open **Actions** tab → enable workflows → manually trigger **Daily Pulse** once via *Run workflow* to verify.

GitHub's cron has up to ~15 min drift under load — that's why we schedule for 08:20 IST, leaving a buffer before market open at 09:15.

To enable WhatsApp later, edit the workflow and drop `--only telegram`, or trigger manually with a different `only` input.

### B. VPS cron in India (recommended)

Any always-on Linux box with an Indian IP. Hostinger Mumbai, AWS ap-south-1, Linode India, etc.

```bash
# On the VPS:
curl -sSL https://raw.githubusercontent.com/Tanzilala/equifiz-pulse/main/scripts/deploy-vps.sh | bash
echo 'N8N_TELEGRAM_WEBHOOK=https://your-n8n/webhook/equifiz-pulse-telegram' > /opt/equifiz-pulse/.env
sudo timedatectl set-timezone Asia/Kolkata
crontab -e
# paste the cron block the script printed
```

The cron block schedules pulse every 30 min between 18:00 and 22:30 IST plus a safety-net retry at 08:30 next morning. Pulse uses `--skip-if-stale` and `--once-per-day` so it only posts when fresh FII/DII data is available, and only once per day.

Full walkthrough is in [scripts/deploy-vps.sh](scripts/deploy-vps.sh).

## Skip-if-stale + once-per-day

Two flags that change *when* `pulse run` actually posts:

```bash
# Exit cleanly (no post) if NSE hasn't published today's FII/DII figures yet.
uv run pulse run --only telegram --skip-if-stale --confirm

# Skip if a successful post was already made today (per-channel markers at
# logs/markers/posted-YYYY-MM-DD-<channel>.marker).
uv run pulse run --only telegram --once-per-day --confirm

# Combined — what the cron uses. Run every 30 min in the evening; the first
# tick after NSE publishes posts and writes the marker, the rest skip.
uv run pulse run --only telegram --skip-if-stale --once-per-day --confirm
```

A "stale" run logs `error: stale_fii_data: got 2026-04-30, expected 2026-05-03` and exits 0 (success — nothing to do). Same for "already posted" runs. So scheduled retries don't pollute the log with errors.

To force a re-post on a day, delete the channel's marker:
```bash
rm logs/markers/posted-YYYY-MM-DD-telegram.marker
```
