# n8n flows

One workflow per channel. Each takes the JSON envelope from `pulse run` and forwards it to the channel's API.

| File | Status |
|---|---|
| [telegram.json](telegram.json) | Ready |
| `linkedin.json` | TODO (Step 5 wiring) |
| `whatsapp.json` | TODO (Step 5 wiring) |

## Telegram setup (10 minutes)

### 1. Create a bot

In Telegram, open `@BotFather` → `/newbot` → follow prompts.

You get back two things:
- **Bot token**: looks like `7891234567:ABCxYzAbC...` — keep it secret
- **Bot username**: e.g. `@equifizpulse_bot`

### 2. Get a chat ID

Where do you want pulses to land? Three options:

| Target | How to get the chat_id |
|---|---|
| **A public channel** | Add the bot to the channel as admin (post permission). Use `@channelusername` directly as chat_id. |
| **A private channel / group** | Add the bot, then post any message in the channel; visit `https://api.telegram.org/bot<TOKEN>/getUpdates` and look for `chat.id` (will be a negative number like `-1001234567890`). |
| **Yourself (DM)** | Message the bot once (`/start`). Get your numeric user_id from `getUpdates` or from `@userinfobot`. |

### 3. Import the workflow

In n8n:
- Click **+ Add workflow** → top-right `⋮` → **Import from File** → select `telegram.json`
- Two nodes appear: a Webhook trigger and a Telegram Send Message node

### 4. Wire up credentials

Click the **Send to Telegram** node:
- Under **Credential to connect with**, click **+ Create new credential**
- Paste your bot token, save, name it (e.g. "Equifiz Pulse Bot")
- The node should auto-resolve the credential

### 5. Set the chat ID

Still in the **Send to Telegram** node, replace `REPLACE_ME_WITH_YOUR_CHAT_ID` with your actual chat ID from step 2.

### 6. Activate

Toggle **Active** in the top-right of the workflow editor.

### 7. Copy the webhook URL

Click the **Webhook (pulse)** node. Copy the **Production URL** (looks like `https://your-n8n.example.com/webhook/equifiz-pulse-telegram`).

Drop it into `equifiz-pulse/.env`:
```
N8N_TELEGRAM_WEBHOOK=https://your-n8n.example.com/webhook/equifiz-pulse-telegram
```

### 8. Test

```bash
# First, dry-run — prints the payload, doesn't POST
uv run pulse run --only telegram

# Then actually post
uv run pulse run --only telegram --confirm
```

You should see `OK telegram sent in 200ms (HTTP 200, ~789 chars)` and the message arrives in your Telegram channel within a couple seconds.

If something fails, check `uv run pulse logs --last 5` for the structured run log, then inspect the n8n execution history for the failing run.

## Payload contract

The Webhook node receives this JSON from `pulse run`:

```json
{
  "channel": "telegram",
  "text": "*Equifiz Pulse · 03 May 2026*\n\n\n*Indices*\n• Sensex: ...",
  "format": "markdown",
  "generated_at": "2026-05-03T03:00:00+00:00"
}
```

The current flow uses `{{ $json.body.text }}` to grab the message. If you need to add e.g. a routing key or channel-specific tweaks, branch on `{{ $json.body.format }}`.

## Common gotchas

- **`Bad Request: chat not found`** — chat_id is wrong, or the bot isn't a member/admin.
- **Markdown parse errors** — pulse output uses Telegram **Markdown V1**. If you switch the node to MarkdownV2, you'll need to escape `_*[]()~``>#+-=|{}.!`.
- **Bot token leak** — the token alone gives full bot control. Keep it in n8n credentials, never in the flow JSON.
