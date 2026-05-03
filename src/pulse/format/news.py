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

from ..data.news import NewsItem, NewsSnapshot

SOURCE_ORDER = ("Business Standard", "Economic Times", "Mint")
HEADLINE_PREFIX = "📝"


def _safe_link_text(s: str) -> str:
    """Telegram Markdown V1 closes the link-text bracket on `]`. Replace
    bracket chars in titles to avoid broken renders."""
    return s.replace("[", "(").replace("]", ")")


def _headline_line(item: NewsItem) -> str:
    """Markdown link: `📝 [title](url)` — taps open in Telegram."""
    return f"{HEADLINE_PREFIX} [{_safe_link_text(item.title)}]({item.url})"


def format_news(snap: NewsSnapshot, *, per_source: int = 11) -> str:
    parts: list[str] = ["*News Headlines from Business News Agencies:*", ""]
    for source in SOURCE_ORDER:
        items = snap.by_source.get(source, [])
        if not items:
            continue
        parts.append(f"*{source}*")
        parts.append("")
        for item in items[:per_source]:
            parts.append(_headline_line(item))
        parts.append("")
    return "\n".join(parts).rstrip()
