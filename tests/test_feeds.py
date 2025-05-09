from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import LiteralString
from unittest.mock import MagicMock, patch

import pytest
from reader import Feed, Reader, make_reader

from discord_rss_bot.feeds import (
    extract_domain,
    is_youtube_feed,
    send_entry_to_discord,
    send_to_discord,
    should_send_embed_check,
    truncate_webhook_message,
)
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


def test_is_youtube_feed():
    """Test the is_youtube_feed function."""
    # YouTube feed URLs
    assert is_youtube_feed("https://www.youtube.com/feeds/videos.xml?channel_id=123456") is True
    assert is_youtube_feed("https://www.youtube.com/feeds/videos.xml?user=username") is True

    # Non-YouTube feed URLs
    assert is_youtube_feed("https://www.example.com/feed.xml") is False
    assert is_youtube_feed("https://www.youtube.com/watch?v=123456") is False
    assert is_youtube_feed("https://www.reddit.com/r/Python/.rss") is False


@patch("discord_rss_bot.feeds.logger")
def test_should_send_embed_check_youtube_feeds(mock_logger: MagicMock) -> None:
    """Test should_send_embed_check returns False for YouTube feeds regardless of settings."""
    # Create mocks
    mock_reader = MagicMock()
    mock_entry = MagicMock()

    # Configure a YouTube feed
    mock_entry.feed.url = "https://www.youtube.com/feeds/videos.xml?channel_id=123456"

    # Set reader to return True for should_send_embed (would normally create an embed)
    mock_reader.get_tag.return_value = True

    # Result should be False, overriding the feed settings
    result = should_send_embed_check(mock_reader, mock_entry)
    assert result is False, "YouTube feeds should never use embeds"

    # Function should not even call get_tag for YouTube feeds
    mock_reader.get_tag.assert_not_called()


@patch("discord_rss_bot.feeds.logger")
def test_should_send_embed_check_normal_feeds(mock_logger: MagicMock) -> None:
    """Test should_send_embed_check returns feed settings for non-YouTube feeds."""
    # Create mocks
    mock_reader = MagicMock()
    mock_entry = MagicMock()

    # Configure a normal feed
    mock_entry.feed.url = "https://www.example.com/feed.xml"

    # Test with should_send_embed set to True
    mock_reader.get_tag.return_value = True
    result = should_send_embed_check(mock_reader, mock_entry)
    assert result is True, "Normal feeds should use embeds when enabled"

    # Test with should_send_embed set to False
    mock_reader.get_tag.return_value = False
    result = should_send_embed_check(mock_reader, mock_entry)
    assert result is False, "Normal feeds should not use embeds when disabled"


@patch("discord_rss_bot.feeds.get_reader")
@patch("discord_rss_bot.feeds.get_custom_message")
@patch("discord_rss_bot.feeds.replace_tags_in_text_message")
@patch("discord_rss_bot.feeds.create_embed_webhook")
@patch("discord_rss_bot.feeds.DiscordWebhook")
@patch("discord_rss_bot.feeds.execute_webhook")
def test_send_entry_to_discord_youtube_feed(
    mock_execute_webhook: MagicMock,
    mock_discord_webhook: MagicMock,
    mock_create_embed: MagicMock,
    mock_replace_tags: MagicMock,
    mock_get_custom_message: MagicMock,
    mock_get_reader: MagicMock,
):
    """Test send_entry_to_discord function with YouTube feeds."""
    # Set up mocks
    mock_reader = MagicMock()
    mock_get_reader.return_value = mock_reader
    mock_entry = MagicMock()
    mock_feed = MagicMock()

    # Configure a YouTube feed
    mock_entry.feed = mock_feed
    mock_entry.feed.url = "https://www.youtube.com/feeds/videos.xml?channel_id=123456"
    mock_entry.feed_url = "https://www.youtube.com/feeds/videos.xml?channel_id=123456"

    # Mock the tags
    mock_reader.get_tag.side_effect = lambda feed, tag, default=None: {  # noqa: ARG005
        "webhook": "https://discord.com/api/webhooks/123/abc",
        "should_send_embed": True,  # This should be ignored for YouTube feeds
    }.get(tag, default)

    # Mock custom message
    mock_get_custom_message.return_value = "Custom message"
    mock_replace_tags.return_value = "Formatted message with {{entry_link}}"

    # Mock webhook
    mock_webhook = MagicMock()
    mock_discord_webhook.return_value = mock_webhook

    # Call the function
    send_entry_to_discord(mock_entry)

    # Assertions
    mock_create_embed.assert_not_called()
    mock_discord_webhook.assert_called_once()

    # Check webhook was created with the right message
    webhook_call_kwargs = mock_discord_webhook.call_args[1]
    assert "content" in webhook_call_kwargs, "Webhook should have content"
    assert webhook_call_kwargs["url"] == "https://discord.com/api/webhooks/123/abc"

    # Verify execute_webhook was called
    mock_execute_webhook.assert_called_once_with(mock_webhook, mock_entry)


def test_extract_domain_youtube_feed() -> None:
    """Test extract_domain for YouTube feeds."""
    url: str = "https://www.youtube.com/feeds/videos.xml?channel_id=123456"
    assert extract_domain(url) == "YouTube", "YouTube feeds should return 'YouTube' as the domain."


def test_extract_domain_reddit_feed() -> None:
    """Test extract_domain for Reddit feeds."""
    url: str = "https://www.reddit.com/r/Python/.rss"
    assert extract_domain(url) == "Reddit", "Reddit feeds should return 'Reddit' as the domain."


def test_extract_domain_github_feed() -> None:
    """Test extract_domain for GitHub feeds."""
    url: str = "https://www.github.com/user/repo"
    assert extract_domain(url) == "GitHub", "GitHub feeds should return 'GitHub' as the domain."


def test_extract_domain_custom_domain() -> None:
    """Test extract_domain for custom domains."""
    url: str = "https://www.example.com/feed"
    assert extract_domain(url) == "Example", "Custom domains should return the capitalized first part of the domain."


def test_extract_domain_no_www_prefix() -> None:
    """Test extract_domain removes 'www.' prefix."""
    url: str = "https://www.example.com/feed"
    assert extract_domain(url) == "Example", "The 'www.' prefix should be removed from the domain."


def test_extract_domain_no_tld() -> None:
    """Test extract_domain for domains without a TLD."""
    url: str = "https://localhost/feed"
    assert extract_domain(url) == "Localhost", "Domains without a TLD should return the capitalized domain."


def test_extract_domain_invalid_url() -> None:
    """Test extract_domain for invalid URLs."""
    url: str = "not-a-valid-url"
    assert extract_domain(url) == "Other", "Invalid URLs should return 'Other' as the domain."


def test_extract_domain_empty_url() -> None:
    """Test extract_domain for empty URLs."""
    url: str = ""
    assert extract_domain(url) == "Other", "Empty URLs should return 'Other' as the domain."


def test_extract_domain_special_characters() -> None:
    """Test extract_domain for URLs with special characters."""
    url: str = "https://www.ex-ample.com/feed"
    assert extract_domain(url) == "Ex-ample", "Domains with special characters should return the capitalized domain."


@pytest.mark.parametrize(
    argnames=("url", "expected"),
    argvalues=[
        ("https://blog.something.com", "Something"),
        ("https://www.something.com", "Something"),
        ("https://subdomain.example.co.uk", "Example"),
        ("https://github.com/user/repo", "GitHub"),
        ("https://youtube.com/feeds/videos.xml?channel_id=abc", "YouTube"),
        ("https://reddit.com/r/python/.rss", "Reddit"),
        ("", "Other"),
        ("not a url", "Other"),
        ("https://www.example.com", "Example"),
        ("https://foo.bar.baz.com", "Baz"),
    ],
)
def test_extract_domain(url: str, expected: str) -> None:
    assert extract_domain(url) == expected
