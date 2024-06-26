from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from reader import Feed, Reader, make_reader  # type: ignore

from discord_rss_bot.feeds import send_to_discord
from discord_rss_bot.missing_tags import add_missing_tags


def test_send_to_discord() -> None:
    """Test sending to Discord."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory.
        Path.mkdir(Path(temp_dir), exist_ok=True)
        assert Path.exists(Path(temp_dir))

        # Create a temporary reader.
        reader: Reader = make_reader(url=str(Path(temp_dir) / "test_db.sqlite"))
        assert reader is not None

        # Add a feed to the reader.
        reader.add_feed("https://www.reddit.com/r/Python/.rss")

        add_missing_tags(reader)

        # Update the feed to get the entries.
        reader.update_feeds()

        # Get the feed.
        feed: Feed = reader.get_feed("https://www.reddit.com/r/Python/.rss")
        assert feed is not None

        # Get the webhook.
        webhook_url: str | None = os.environ.get("TEST_WEBHOOK_URL")

        if not webhook_url:
            reader.close()
            pytest.skip("No webhook URL provided.")

        assert webhook_url is not None

        # Add tag to the feed and check if it is there.
        reader.set_tag(feed, "webhook", webhook_url)  # type: ignore
        assert reader.get_tag(feed, "webhook") == webhook_url  # type: ignore

        # Send the feed to Discord.
        send_to_discord(custom_reader=reader, feed=feed, do_once=True)

        # Close the reader, so we can delete the directory.
        reader.close()
