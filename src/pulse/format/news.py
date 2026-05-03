"""Format the news snapshot exactly as requested:

    *News Headlines from Business News Agencies:*

    *Business Standard*

    📝 headline
    📝 headline
    ...

    *Economic Times*
    ...
"""
from __future__ import annotations

from ..data.news import NewsSnapshot

SOURCE_ORDER = ("Business Standard", "Economic Times", "Mint")
HEADLINE_PREFIX = "📝"


def format_news(snap: NewsSnapshot, *, per_source: int = 11) -> str:
    parts: list[str] = ["*News Headlines from Business News Agencies:*", ""]
    for source in SOURCE_ORDER:
        items = snap.by_source.get(source, [])
        if not items:
            continue
        parts.append(f"*{source}*")
        parts.append("")
        for item in items[:per_source]:
            parts.append(f"{HEADLINE_PREFIX} {item.title}")
        parts.append("")
    return "\n".join(parts).rstrip()
