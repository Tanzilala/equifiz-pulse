#!/usr/bin/env bash
# Deploy equifiz-pulse on a Linux VPS with Indian IP (e.g. Hostinger India).
#
# Usage on a fresh VPS (Ubuntu/Debian):
#   curl -sSL https://raw.githubusercontent.com/Tanzilala/equifiz-pulse/main/scripts/deploy-vps.sh | bash
# Or after `git clone`:
#   bash scripts/deploy-vps.sh
#
# After this finishes you'll need to:
#   1. echo 'N8N_TELEGRAM_WEBHOOK=https://...' >> /opt/equifiz-pulse/.env
#   2. crontab -e  →  paste the line printed at the end of this script
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/equifiz-pulse}"
REPO_URL="${REPO_URL:-https://github.com/Tanzilala/equifiz-pulse.git}"

echo "==> Ensuring git, curl, build deps"
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq git curl ca-certificates
fi

echo "==> Installing uv (Astral) — Python manager"
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # uv installs to ~/.local/bin
    export PATH="$HOME/.local/bin:$PATH"
fi
UV="$(command -v uv)"
echo "    uv at: $UV"

echo "==> Cloning / updating repo at $INSTALL_DIR"
if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR"
    git pull --ff-only
else
    sudo mkdir -p "$(dirname "$INSTALL_DIR")"
    sudo git clone "$REPO_URL" "$INSTALL_DIR"
    sudo chown -R "$USER":"$USER" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo "==> Installing project dependencies"
"$UV" sync --frozen

echo "==> Smoke-testing the data layer (NSE + Yahoo, no posting)"
if "$UV" run pulse preview --only telegram >/dev/null 2>&1; then
    echo "    OK — NSE + Yahoo reachable from this VPS"
else
    echo "    !! preview failed — investigate before scheduling. Run:"
    echo "       cd $INSTALL_DIR && $UV run pulse preview --only telegram"
    exit 1
fi

# Cron strategy: pulse run every 30 min in the evening + once next morning as
# a safety net.  --skip-if-stale exits cleanly until NSE publishes today's
# FII/DII figures (typically ~19:00–20:00 IST).  --once-per-day uses a marker
# file so only the first successful run actually posts.
CRON_BLOCK="# equifiz-pulse — daily Indian markets briefing
*/30 18-22 * * 1-5 cd $INSTALL_DIR && $UV run pulse run --only telegram --skip-if-stale --once-per-day --confirm >> $INSTALL_DIR/logs/cron.log 2>&1
30 8 * * 2-6 cd $INSTALL_DIR && $UV run pulse run --only telegram --skip-if-stale --once-per-day --confirm >> $INSTALL_DIR/logs/cron.log 2>&1"

cat <<EOF

==> NEXT STEPS (manual, ~30 sec)

1. Set the webhook URL — create $INSTALL_DIR/.env and add:

   N8N_TELEGRAM_WEBHOOK=<your n8n production webhook URL>

   Quick way:
     echo 'N8N_TELEGRAM_WEBHOOK=https://n8n.srv1247302.hstgr.cloud/webhook/equifiz-pulse-telegram' > $INSTALL_DIR/.env

2. Verify timezone is IST so cron's "8:30" actually means market-time:
     timedatectl set-timezone Asia/Kolkata

3. Install the cron block — run:
     crontab -e
   then paste this block and save:

$CRON_BLOCK

4. (Optional) test the run command manually right now:
     cd $INSTALL_DIR && $UV run pulse run --only telegram --confirm

   It should send a Telegram message and print "OK telegram sent ...".

How the schedule works:
  • Mon-Fri 18:00–22:30 IST: every 30 min, pulse checks whether today's
    FII/DII data has published. If not, it logs and exits 0. As soon as
    NSE publishes (usually ~19:00 IST), pulse posts and writes a marker
    so subsequent ticks that day skip.
  • Tue-Sat 08:30 IST: safety-net retry covering the case where evening
    runs all hit a degraded NSE. Same marker logic — skips if already
    posted yesterday evening.

EOF
