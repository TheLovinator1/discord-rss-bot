from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from discord_rss_bot.settings import get_reader

if TYPE_CHECKING:
    from collections.abc import Iterable

    from reader import EntrySearchResult, Feed, HighlightedString, Reader


def create_html_for_search_results(query: str, custom_reader: Reader | None = None) -> str:
    """Create HTML for the search results.

    Args:
        query: Our search query
        custom_reader: The reader. If None, we will get the reader from the settings.

    Returns:
        str: The HTML.
    """
    # TODO(TheLovinator): There is a .content that also contains text, we should use that if .summary is not available.
    # TODO(TheLovinator): We should also add <span> tags to the title.

    # Get the default reader if we didn't get a custom one.
    reader: Reader = get_reader() if custom_reader is None else custom_reader

    search_results: Iterable[EntrySearchResult] = reader.search_entries(query)

    html: str = ""
    for result in search_results:
        if ".summary" in result.content:
            result_summary: str = add_span_with_slice(result.content[".summary"])
            feed: Feed = reader.get_feed(result.feed_url)
            feed_url: str = urllib.parse.quote(feed.url)

            html += f"""
            <div class="p-2 mb-2 border border-dark">
                <a class="text-muted text-decoration-none" href="/feed?feed_url={feed_url}">
                    <h2>{result.metadata[".title"]}</h2>
                </a>
                {result_summary}
            </div>
            """

    return html


def add_span_with_slice(highlighted_string: HighlightedString) -> str:
    """Add span tags to the string to highlight the search results.

    Args:
        highlighted_string: The highlighted string.

    Returns:
        str: The string with added <span> tags.
    """
    # TODO(TheLovinator): We are looping through the highlights and only using the last one. We should use all of them.
    before_span, span_part, after_span = "", "", ""

    for txt_slice in highlighted_string.highlights:
        before_span: str = f"{highlighted_string.value[: txt_slice.start]}"
        span_part: str = f"<span class='bg-warning'>{highlighted_string.value[txt_slice.start : txt_slice.stop]}</span>"
        after_span: str = f"{highlighted_string.value[txt_slice.stop :]}"

    return f"{before_span}{span_part}{after_span}"
