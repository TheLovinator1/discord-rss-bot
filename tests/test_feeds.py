from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import LiteralString

import pytest
from reader import Feed, Reader, make_reader

from discord_rss_bot.feeds import send_to_discord, truncate_webhook_message
from discord_rss_bot.missing_tags import add_missing_tags


def test_send_to_discord() -> None:
    """Test sending to Discord."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory.
        Path.mkdir(Path(temp_dir), exist_ok=True)
        assert Path.exists(Path(temp_dir)), f"The directory '{temp_dir}' should exist."

        # Create a temporary reader.
        reader: Reader = make_reader(url=str(Path(temp_dir) / "test_db.sqlite"))
        assert reader is not None, "The reader should not be None."

        # Add a feed to the reader.
        reader.add_feed("https://www.reddit.com/r/Python/.rss")

        add_missing_tags(reader)

        # Update the feed to get the entries.
        reader.update_feeds()

        # Get the feed.
        feed: Feed = reader.get_feed("https://www.reddit.com/r/Python/.rss")
        assert feed is not None, f"The feed should not be None. Got: {feed}"

        # Get the webhook.
        webhook_url: str | None = os.environ.get("TEST_WEBHOOK_URL")

        if not webhook_url:
            reader.close()
            pytest.skip("No webhook URL provided.")

        assert webhook_url is not None, f"The webhook URL should not be None. Got: {webhook_url}"

        # Add tag to the feed and check if it is there.
        reader.set_tag(feed, "webhook", webhook_url)  # pyright: ignore[reportArgumentType]
        assert reader.get_tag(feed, "webhook") == webhook_url, f"The webhook URL should be '{webhook_url}'."

        # Send the feed to Discord.
        send_to_discord(custom_reader=reader, feed=feed, do_once=True)

        # Close the reader, so we can delete the directory.
        reader.close()


def test_truncate_webhook_message_short_message():
    message = "This is a short message."
    assert_msg = "The message should remain unchanged if it's less than 4000 characters."
    assert truncate_webhook_message(message) == message, assert_msg


def test_truncate_webhook_message_exact_length():
    message: LiteralString = "A" * 4000  # Exact length of max_content_length
    assert_msg: str = f"The message should remain unchanged if it's exactly {4000} characters."
    assert truncate_webhook_message(message) == message, assert_msg


def test_truncate_webhook_message_long_message():
    message: str = "A" * 4100  # Exceeds max_content_length
    truncated_message: str = truncate_webhook_message(message)

    # Ensure the truncated message length is correct
    assert_msg = "The length of the truncated message should be between 3999 and 4000."
    assert 3999 <= len(truncated_message) <= 4000, assert_msg

    # Calculate half length for the truncated parts
    half_length = (4000 - 3) // 2

    # Test the beginning of the message
    assert_msg = "The beginning of the truncated message should match the original message."
    assert truncated_message[:half_length] == "A" * half_length, assert_msg

    # Test the end of the message
    assert_msg = "The end of the truncated message should be '...' to indicate truncation."
    assert truncated_message[-half_length:] == "A" * half_length, assert_msg
