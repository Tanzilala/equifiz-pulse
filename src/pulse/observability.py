"""Run logging — one JSONL line per `pulse run` invocation.

Each line includes which data sources succeeded, the narrative source,
post results per channel, total duration, and the resulting exit code.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .distribute import PostResult
from .models import PulseBriefing


def derive_source_statuses(b: PulseBriefing) -> dict[str, Any]:
    """Translate a successful PulseBriefing into per-source status flags."""
    flows: dict[str, Any] = {"cash": "ok"}
    if b.flows.fno is not None:
        flows["fno"] = "ok"
    elif b.flows.fno_unavailable_reason:
        flows["fno"] = f"unavailable: {b.flows.fno_unavailable_reason}"
    else:
        flows["fno"] = "absent"

    enriched = sum(1 for m in (*b.movers.gainers, *b.movers.losers) if m.avg_volume_20d)
    total = len(b.movers.gainers) + len(b.movers.losers)

    return {
        "indices": "ok",
        "movers": {
            "ok": True,
            "volume_enriched": f"{enriched}/{total}",
        },
        "flows": flows,
        "regulatory": {
            "items": len(b.regulatory.items),
            "unavailable_sources": list(b.regulatory.unavailable_sources),
        },
        "macro": "ok",
    }


class RunLogger:
    """Append-only JSONL logger, one file per (UTC) month."""

    def __init__(self, root: Path | str = "logs") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, when: datetime) -> Path:
        return self.root / f"pulse-{when.strftime('%Y-%m')}.jsonl"

    def write(self, entry: dict[str, Any]) -> Path:
        when = datetime.now(timezone.utc)
        entry.setdefault("logged_at", when.isoformat())
        path = self._path(when)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return path

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        when = datetime.now(timezone.utc)
        path = self._path(when)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        out: list[dict[str, Any]] = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out


def build_run_entry(
    *,
    started_at: datetime,
    finished_at: datetime,
    confirm: bool,
    only: str | None,
    narrative_source: str,
    briefing: PulseBriefing | None,
    posts: list[PostResult],
    error: str | None,
    exit_code: int,
) -> dict[str, Any]:
    return {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
        "command": "run",
        "args": {"only": only, "confirm": confirm},
        "narrative": narrative_source,
        "sources": derive_source_statuses(briefing) if briefing else None,
        "posts": [p.model_dump() for p in posts],
        "error": error,
        "exit_code": exit_code,
    }
