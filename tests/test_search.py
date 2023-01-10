import os
import tempfile
from pathlib import Path
from typing import Iterable

from reader import EntrySearchResult, Feed, Reader, make_reader  # type: ignore

from discord_rss_bot.search import create_html_for_search_results


def test_create_html_for_search_results() -> None:
    """Test create_html_for_search_results."""
    # Create a reader.
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory.
        os.makedirs(temp_dir, exist_ok=True)
        assert os.path.exists(temp_dir)

        # Create a temporary reader.
        reader: Reader = make_reader(url=str(Path(temp_dir, "test_db.sqlite")))
        assert reader is not None

        # Add a feed to the reader.
        reader.add_feed("https://www.reddit.com/r/Python/.rss")

        # Update the feed to get the entries.
        reader.update_feeds()

        # Get the feed.
        feed: Feed = reader.get_feed("https://www.reddit.com/r/Python/.rss")
        assert feed is not None

        # Update the search index.
        reader.enable_search()
        reader.update_search()

        # Get the HTML for the search results.
        search_results: Iterable[EntrySearchResult] = reader.search_entries("a", feed=feed)  # type: ignore

        # Create the HTML and check if it is not empty.
        search_html: str = create_html_for_search_results(search_results, reader)
        assert search_html is not None
        assert len(search_html) > 10

        # Close the reader, so we can delete the directory.
        reader.close()
