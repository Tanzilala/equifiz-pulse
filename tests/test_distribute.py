from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest
import respx

from pulse.distribute import (
    ChannelPost,
    PostResult,
    build_channel_post,
    post_to_n8n,
)
from pulse.models import (
    FIIDIICash,
    FlowsSnapshot,
    IndexQuote,
    IndicesSnapshot,
    MacroQuote,
    MacroSnapshot,
    MoversSnapshot,
    PulseBriefing,
    StockMover,
)


def _q(symbol, name, last, prev, pct) -> IndexQuote:
    return IndexQuote(
        symbol=symbol, name=name, last=last,
        change=last - prev, change_pct=pct, prev_close=prev,
        timestamp=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )


def _macro_q(s, n, l, p) -> MacroQuote:
    return MacroQuote(symbol=s, name=n, last=l, prev_close=p,
                       change=l - p, change_pct=(l - p) / p * 100,
                       as_of=datetime(2026, 5, 3, tzinfo=timezone.utc))


@pytest.fixture
def briefing() -> PulseBriefing:
    fa = datetime(2026, 5, 3, 3, 0, tzinfo=timezone.utc)
    return PulseBriefing(
        fetched_at=fa,
        indices=IndicesSnapshot(
            fetched_at=fa,
            sensex=_q("^BSESN", "Sensex", 80000, 80200, -0.25),
            nifty_50=_q("NIFTY 50", "Nifty 50", 24000, 24100, -0.41),
            bank_nifty=_q("NIFTY BANK", "Bank Nifty", 55000, 55400, -0.72),
            india_vix=_q("INDIA VIX", "India VIX", 18.0, 17.5, 2.86),
        ),
        movers=MoversSnapshot(
            fetched_at=fa,
            gainers=[StockMover(symbol="A", name="A Co", last=100, change_pct=10, volume=1_000_000)],
            losers=[StockMover(symbol="Z", name="Z Co", last=50, change_pct=-10, volume=2_000_000)],
        ),
        flows=FlowsSnapshot(
            fetched_at=fa,
            cash=FIIDIICash(date=date(2026, 4, 30), fii_buy=10000, fii_sell=12000,
                            fii_net=-2000, dii_buy=8000, dii_sell=7000, dii_net=1000),
        ),
        macro=MacroSnapshot(
            fetched_at=fa,
            usdinr=_macro_q("INR=X", "USDINR", 84.5, 84.4),
            dxy=_macro_q("DX-Y.NYB", "Dollar Index", 98.5, 98.3),
            brent=_macro_q("BZ=F", "Brent", 80.0, 79.5),
            gold=_macro_q("GC=F", "Gold (USD/oz)", 2700, 2690),
            india_gsec_10y=_macro_q("IN10Y", "India G-Sec 10Y (%)", 7.02, 7.05),
        ),
    )


# ---------- build_channel_post ----------

def test_build_channel_post_telegram_envelope(briefing):
    p = build_channel_post("telegram", briefing, webhook_url="https://hook/x")
    assert p.channel == "telegram"
    assert p.webhook_url == "https://hook/x"
    assert p.payload["channel"] == "telegram"
    assert p.payload["format"] == "markdown"
    assert "Equifiz Pulse" in p.payload["text"]
    assert p.payload["generated_at"].startswith("2026-05-03")


def test_build_channel_post_whatsapp_is_plain(briefing):
    p = build_channel_post("whatsapp", briefing, webhook_url="https://hook/w")
    assert p.payload["format"] == "plain"
    assert "*" not in p.payload["text"]


# ---------- post_to_n8n ----------

@pytest.mark.asyncio
async def test_post_success(briefing):
    post = build_channel_post("telegram", briefing, webhook_url="https://hook.example/abc")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("https://hook.example/abc").respond(200, json={"ok": True})
        async with httpx.AsyncClient() as http:
            res = await post_to_n8n(post, http=http)
    assert res.status == "sent"
    assert res.http_status == 200
    assert res.channel == "telegram"
    assert res.payload_chars > 0
    # And the JSON body matches our envelope
    body = route.calls.last.request.content
    assert b'"channel": "telegram"' in body or b'"channel":"telegram"' in body


@pytest.mark.asyncio
async def test_post_4xx_no_retry(briefing):
    post = build_channel_post("telegram", briefing, webhook_url="https://hook.example/abc")
    with respx.mock() as mock:
        route = mock.post("https://hook.example/abc").respond(404, text="not found")
        async with httpx.AsyncClient() as http:
            res = await post_to_n8n(post, http=http, retries=2)
    assert res.status == "failed"
    assert res.http_status == 404
    assert "404" in (res.error or "")
    assert route.call_count == 1, "4xx should not be retried"


@pytest.mark.asyncio
async def test_post_5xx_retried_then_succeeds(briefing):
    post = build_channel_post("telegram", briefing, webhook_url="https://hook.example/abc")
    with respx.mock() as mock:
        route = mock.post("https://hook.example/abc")
        route.side_effect = [
            httpx.Response(500, text="boom"),
            httpx.Response(503, text="boom"),
            httpx.Response(200, json={"ok": True}),
        ]
        async with httpx.AsyncClient() as http:
            res = await post_to_n8n(post, http=http, retries=2)
    assert res.status == "sent"
    assert res.http_status == 200
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_post_5xx_all_attempts_fail(briefing):
    post = build_channel_post("telegram", briefing, webhook_url="https://hook.example/abc")
    with respx.mock() as mock:
        route = mock.post("https://hook.example/abc").respond(500, text="boom")
        async with httpx.AsyncClient() as http:
            res = await post_to_n8n(post, http=http, retries=2)
    assert res.status == "failed"
    assert res.http_status == 500
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_post_network_error_retries(briefing):
    post = build_channel_post("telegram", briefing, webhook_url="https://hook.example/abc")
    with respx.mock() as mock:
        route = mock.post("https://hook.example/abc")
        route.side_effect = [httpx.ConnectError("boom"), httpx.Response(200, json={"ok": True})]
        async with httpx.AsyncClient() as http:
            res = await post_to_n8n(post, http=http, retries=2)
    assert res.status == "sent"
    assert route.call_count == 2
