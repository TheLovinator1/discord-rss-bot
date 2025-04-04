from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from reader import Feed, Reader, make_reader

from discord_rss_bot.search import create_html_for_search_results

if TYPE_CHECKING:
    from collections.abc import Iterable


def test_create_html_for_search_results() -> None:
    """Test create_html_for_search_results."""
    # Create a reader.
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory.
        Path.mkdir(Path(temp_dir), exist_ok=True)
        assert Path.exists(Path(temp_dir)), f"The directory '{temp_dir}' should exist."

        # Create a temporary reader.
        reader: Reader = make_reader(url=str(Path(temp_dir, "test_db.sqlite")))
        assert reader is not None, "The reader should not be None."

        # Add a feed to the reader.
        reader.add_feed("https://lovinator.space/rss_test.xml", exist_ok=True)

        # Check that the feed was added.
        feeds: Iterable[Feed] = reader.get_feeds()
        assert feeds is not None, f"The feeds should not be None. Got: {feeds}"
        assert len(list(feeds)) == 1, f"The number of feeds should be 1. Got: {len(list(feeds))}"

        # Update the feed to get the entries.
        reader.update_feeds()

        # Get the feed.
        feed: Feed = reader.get_feed("https://lovinator.space/rss_test.xml")
        assert feed is not None, f"The feed should not be None. Got: {feed}"

        # Update the search index.
        reader.enable_search()
        reader.update_search()

        # Create the HTML and check if it is not empty.
        search_html: str = create_html_for_search_results("a", reader)
        assert search_html is not None, f"The search HTML should not be None. Got: {search_html}"
        assert len(search_html) > 10, f"The search HTML should be longer than 10 characters. Got: {len(search_html)}"

        # Close the reader, so we can delete the directory.
        reader.close()
