from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from discord_rss_bot.settings import get_reader

if TYPE_CHECKING:
    from collections.abc import Iterable

    from reader import EntrySearchResult, Feed, HighlightedString, Reader


def create_search_context(query: str, custom_reader: Reader | None = None) -> dict:
    """Build context for search.html template.

    If custom_reader is None, use the default reader from settings.

    Args:
        query (str): The search query.
        custom_reader (Reader | None): Optional custom Reader instance.

    Returns:
        dict: Context dictionary for rendering the search results.
    """
    reader: Reader = get_reader() if custom_reader is None else custom_reader
    search_results: Iterable[EntrySearchResult] = reader.search_entries(query)

    results: list[dict] = []
    for result in search_results:
        feed: Feed = reader.get_feed(result.feed_url)
        feed_url: str = urllib.parse.quote(feed.url)

        # Prefer summary, fall back to content
        if ".summary" in result.content:
            highlighted = result.content[".summary"]
        else:
            content_keys = [k for k in result.content if k.startswith(".content")]
            highlighted = result.content[content_keys[0]] if content_keys else None

        summary: str = add_spans(highlighted) if highlighted else "(no preview available)"

        results.append({
            "title": add_spans(result.metadata.get(".title")),
            "summary": summary,
            "feed_url": feed_url,
        })

    return {
        "query": query,
        "search_amount": {"total": len(results)},
        "results": results,
    }


def add_spans(highlighted_string: HighlightedString | None) -> str:
    """Wrap all highlighted parts with <span> tags.

    Args:
        highlighted_string (HighlightedString | None): The highlighted string to process.

    Returns:
        str: The processed string with <span> tags around highlighted parts.
    """
    if highlighted_string is None:
        return ""

    value: str = highlighted_string.value
    parts: list[str] = []
    last_index = 0

    for txt_slice in highlighted_string.highlights:
        parts.extend((
            value[last_index : txt_slice.start],
            f"<span class='bg-warning'>{value[txt_slice.start : txt_slice.stop]}</span>",
        ))
        last_index = txt_slice.stop

    # add any trailing text
    parts.append(value[last_index:])

    return "".join(parts)
