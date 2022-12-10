import urllib.parse
from typing import Iterable

from reader import EntrySearchResult, HighlightedString

from discord_rss_bot.settings import reader


def create_html_for_search_results(search_results: Iterable[EntrySearchResult]) -> str:
    """Create HTML for the search results.

    Args:
        search_results: The search results.

    Returns:
        str: The HTML.
    """
    html = ""
    for result in search_results:
        if ".summary" in result.content:
            result_summary = add_span_with_slice(result.content[".summary"])
            feed = reader.get_feed(result.feed_url)
            feed_url = urllib.parse.quote(feed.url)

            html += f"""
            <a class="text-muted text-decoration-none" href="/feed?feed_url={feed_url}">
                <h2>{result.metadata[".title"]}</h2>
            </a>
            {result_summary}
            <hr>
            """
    return html


def add_span_with_slice(highlighted_string: HighlightedString) -> str:
    """Add span tags to the string to highlight the search results.

    Args:
        highlighted_string: The highlighted string.

    Returns:
        str: The string with added <span> tags.
    """

    for txt_slice in highlighted_string.highlights:
        before_span = f"{highlighted_string.value[: txt_slice.start]}"
        span_part = f"<span class='bg-warning'>{highlighted_string.value[txt_slice.start: txt_slice.stop]}</span>"
        after_span = f"{highlighted_string.value[txt_slice.stop:]}"
        return f"{before_span}{span_part}{after_span}"
