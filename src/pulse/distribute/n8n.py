"""Post the rendered briefing to n8n webhooks.

Each channel maps to its own webhook URL and gets a JSON envelope:

    {
      "channel":      "telegram" | "whatsapp",
      "text":         "<formatted message>",
      "format":       "markdown" | "plain",
      "generated_at": "<iso8601 utc>"
    }

The n8n flow on the receiving end is responsible for actually calling
Telegram / WhatsApp.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Literal, Optional

import httpx
from pydantic import BaseModel, ConfigDict

from ..format import format_telegram, format_whatsapp
from ..models import PulseBriefing

Channel = Literal["telegram", "whatsapp"]
PAYLOAD_FORMAT: dict[Channel, str] = {
    "telegram": "markdown",
    "whatsapp": "plain",
}


class DistributionError(RuntimeError):
    pass


class ChannelPost(BaseModel):
    model_config = ConfigDict(frozen=True)

    channel: Channel
    webhook_url: str
    payload: dict[str, Any]


class PostResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    channel: Channel
    status: Literal["sent", "failed", "skipped", "dry_run"]
    http_status: Optional[int] = None
    duration_ms: int = 0
    error: Optional[str] = None
    payload_chars: int = 0


def build_channel_post(
    channel: Channel,
    briefing: PulseBriefing,
    *,
    webhook_url: str,
) -> ChannelPost:
    if channel == "telegram":
        text = format_telegram(briefing)
    elif channel == "whatsapp":
        text = format_whatsapp(briefing)
    else:
        raise DistributionError(f"unknown channel {channel!r}")

    payload = {
        "channel": channel,
        "text": text,
        "format": PAYLOAD_FORMAT[channel],
        "generated_at": briefing.fetched_at.isoformat(),
    }
    return ChannelPost(channel=channel, webhook_url=webhook_url, payload=payload)


async def post_to_n8n(
    post: ChannelPost,
    *,
    http: Optional[httpx.AsyncClient] = None,
    retries: int = 2,
    timeout: float = 15.0,
) -> PostResult:
    """POST the envelope. Retries on 5xx and network errors only — 4xx fails fast."""
    chars = len(post.payload.get("text") or "")
    owns = http is None
    if http is None:
        http = httpx.AsyncClient(timeout=timeout)
    started = time.perf_counter()
    last_status: Optional[int] = None
    last_error: Optional[str] = None
    try:
        for attempt in range(retries + 1):
            try:
                r = await http.post(post.webhook_url, json=post.payload)
                last_status = r.status_code
                if 200 <= r.status_code < 300:
                    return PostResult(
                        channel=post.channel,
                        status="sent",
                        http_status=r.status_code,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        payload_chars=chars,
                    )
                if 400 <= r.status_code < 500:
                    last_error = f"HTTP {r.status_code}: {r.text[:200]}"
                    break  # 4xx — retrying won't help
                last_error = f"HTTP {r.status_code}: {r.text[:200]}"
            except httpx.HTTPError as e:
                last_error = f"{type(e).__name__}: {e}"
            if attempt < retries:
                await asyncio.sleep(0.5 * (attempt + 1))
    finally:
        if owns:
            await http.aclose()
    return PostResult(
        channel=post.channel,
        status="failed",
        http_status=last_status,
        duration_ms=int((time.perf_counter() - started) * 1000),
        error=last_error,
        payload_chars=chars,
    )
