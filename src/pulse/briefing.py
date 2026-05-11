"""Top-level orchestrator: fetch all data in parallel, assemble a PulseBriefing."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .data.flows import fetch_flows
from .data.indices import fetch_indices
from .data.macro import fetch_macro
from .data.movers import fetch_movers
from .data.nse_client import NSEClient, default_cache
from .models import PulseBriefing


async def build_briefing() -> PulseBriefing:
    cache = default_cache()
    async with NSEClient(cache=cache, cache_ttl=120.0) as nse:
        # First call seeds the NSE session (cookies). Run sequentially.
        indices = await fetch_indices(nse)
        movers_task = asyncio.create_task(fetch_movers(nse))
        flows_task = asyncio.create_task(fetch_flows(nse))
        macro_task = asyncio.create_task(fetch_macro())

        movers, flows, macro = await asyncio.gather(
            movers_task, flows_task, macro_task
        )

    return PulseBriefing(
        fetched_at=datetime.now(timezone.utc),
        indices=indices,
        movers=movers,
        flows=flows,
        macro=macro,
    )
