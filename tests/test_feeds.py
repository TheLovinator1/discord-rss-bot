from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import LiteralString
from typing import cast
from unittest.mock import MagicMock
from unittest.mock import call
from unittest.mock import patch

import pytest
from reader import EntryNotFoundError
from reader import Feed
from reader import FeedExistsError
from reader import FeedNotFoundError
from reader import Reader
from reader import StorageError
from reader import make_reader

from discord_rss_bot import feeds
from discord_rss_bot.feeds import JsonObject
from discord_rss_bot.feeds import capture_full_page_screenshot
from discord_rss_bot.feeds import create_feed
from discord_rss_bot.feeds import create_screenshot_webhook
from discord_rss_bot.feeds import execute_webhook
from discord_rss_bot.feeds import extract_domain
from discord_rss_bot.feeds import get_entry_delivery_mode
from discord_rss_bot.feeds import get_screenshot_layout
from discord_rss_bot.feeds import get_webhook_url
from discord_rss_bot.feeds import is_youtube_feed
from discord_rss_bot.feeds import screenshot_filename_for_entry
from discord_rss_bot.feeds import send_discord_quest_notification
from discord_rss_bot.feeds import send_entry_to_discord
from discord_rss_bot.feeds import send_to_discord
from discord_rss_bot.feeds import set_entry_as_read
from discord_rss_bot.feeds import should_send_embed_check
from discord_rss_bot.feeds import truncate_webhook_message


def get_test_webhook_components(webhook: feeds.DiscordWebhook) -> list[feeds.JsonValue]:
    components = webhook.json.get("components")
    assert isinstance(components, list)
    return components


def test_send_to_discord() -> None:
    """Test sending to Discord."""
    # Skip early if no webhook URL is configured to avoid a real network request.
    webhook_url: str | None = os.environ.get("TEST_WEBHOOK_URL")
    if not webhook_url:
        pytest.skip("No webhook URL provided.")

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory.
        Path.mkdir(Path(temp_dir), exist_ok=True)
        assert Path.exists(Path(temp_dir)), f"The directory '{temp_dir}' should exist."

        # Create a temporary reader.
        reader: Reader = make_reader(url=str(Path(temp_dir) / "test_db.sqlite"))
        assert reader is not None, "The reader should not be None."

        # Add a feed to the reader.
        reader.add_feed("https://www.reddit.com/r/Python/.rss")

        # Update the feed to get the entries.
        reader.update_feeds()

        # Get the feed.
        feed: Feed = reader.get_feed("https://www.reddit.com/r/Python/.rss")
        assert feed is not None, f"The feed should not be None. Got: {feed}"

        assert webhook_url is not None, f"The webhook URL should not be None. Got: {webhook_url}"

        # Add tag to the feed and check if it is there.
        reader.set_tag(feed, "webhook", webhook_url)  # pyright: ignore[reportArgumentType]
        assert reader.get_tag(feed, "webhook") == webhook_url, f"The webhook URL should be '{webhook_url}'."

        # Send the feed to Discord.
        send_to_discord(reader=reader, feed=feed, do_once=True)

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


def test_get_entry_delivery_mode_prefers_delivery_mode_tag() -> None:
    reader = MagicMock()
    entry = MagicMock()
    entry.feed.url = "https://example.com/feed.xml"

    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "delivery_mode": "screenshot",
        "should_send_embed": True,
    }.get(key, default)

    result = get_entry_delivery_mode(reader, entry)

    assert result == "screenshot"


def test_get_entry_delivery_mode_falls_back_to_legacy_embed_flag() -> None:
    reader = MagicMock()
    entry = MagicMock()
    entry.feed.url = "https://example.com/feed.xml"

    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "delivery_mode": "",
        "should_send_embed": False,
    }.get(key, default)

    result = get_entry_delivery_mode(reader, entry)

    assert result == "text"


@patch("discord_rss_bot.feeds.execute_webhook")
@patch("discord_rss_bot.feeds.create_text_webhook")
@patch("discord_rss_bot.feeds.create_hoyolab_webhook")
@patch("discord_rss_bot.feeds.fetch_hoyolab_post")
def test_send_entry_to_discord_hoyolab_text_mode_uses_text_webhook(
    mock_fetch_hoyolab_post: MagicMock,
    mock_create_hoyolab_webhook: MagicMock,
    mock_create_text_webhook: MagicMock,
    mock_execute_webhook: MagicMock,
) -> None:
    entry = MagicMock()
    entry.id = "entry-1"
    entry.feed.url = "https://feeds.c3kay.de/hoyolab.xml"
    entry.feed_url = "https://feeds.c3kay.de/hoyolab.xml"
    entry.link = "https://www.hoyolab.com/article/38588239"

    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhook": "https://discord.test/webhook",
        "delivery_mode": "text",
    }.get(key, default)

    text_webhook = MagicMock()
    mock_create_text_webhook.return_value = text_webhook

    result = send_entry_to_discord(entry, reader)

    assert result is None
    mock_fetch_hoyolab_post.assert_not_called()
    mock_create_hoyolab_webhook.assert_not_called()
    mock_create_text_webhook.assert_called_once_with(
        "https://discord.test/webhook",
        entry,
        reader=reader,
        use_default_message_on_empty=False,
    )
    mock_execute_webhook.assert_called_once_with(text_webhook, entry, reader=reader)


@patch("discord_rss_bot.feeds.execute_webhook")
@patch("discord_rss_bot.feeds.create_screenshot_webhook")
@patch("discord_rss_bot.feeds.create_hoyolab_webhook")
@patch("discord_rss_bot.feeds.fetch_hoyolab_post")
def test_send_entry_to_discord_hoyolab_screenshot_mode_uses_screenshot_webhook(
    mock_fetch_hoyolab_post: MagicMock,
    mock_create_hoyolab_webhook: MagicMock,
    mock_create_screenshot_webhook: MagicMock,
    mock_execute_webhook: MagicMock,
) -> None:
    entry = MagicMock()
    entry.id = "entry-2"
    entry.feed.url = "https://feeds.c3kay.de/hoyolab.xml"
    entry.feed_url = "https://feeds.c3kay.de/hoyolab.xml"
    entry.link = "https://www.hoyolab.com/article/38588239"

    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhook": "https://discord.test/webhook",
        "delivery_mode": "screenshot",
    }.get(key, default)

    screenshot_webhook = MagicMock()
    mock_create_screenshot_webhook.return_value = screenshot_webhook

    result = send_entry_to_discord(entry, reader)

    assert result is None
    mock_fetch_hoyolab_post.assert_not_called()
    mock_create_hoyolab_webhook.assert_not_called()
    mock_create_screenshot_webhook.assert_called_once_with(
        "https://discord.test/webhook",
        entry,
        reader=reader,
    )
    mock_execute_webhook.assert_called_once_with(screenshot_webhook, entry, reader=reader)


@patch("discord_rss_bot.feeds.execute_webhook")
@patch("discord_rss_bot.feeds.create_embed_webhook")
@patch("discord_rss_bot.feeds.create_hoyolab_webhook")
@patch("discord_rss_bot.feeds.fetch_hoyolab_post")
def test_send_entry_to_discord_hoyolab_embed_mode_uses_hoyolab_webhook(
    mock_fetch_hoyolab_post: MagicMock,
    mock_create_hoyolab_webhook: MagicMock,
    mock_create_embed_webhook: MagicMock,
    mock_execute_webhook: MagicMock,
) -> None:
    entry = MagicMock()
    entry.id = "entry-3"
    entry.feed.url = "https://feeds.c3kay.de/hoyolab.xml"
    entry.feed_url = "https://feeds.c3kay.de/hoyolab.xml"
    entry.link = "https://www.hoyolab.com/article/38588239"

    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhook": "https://discord.test/webhook",
        "delivery_mode": "embed",
    }.get(key, default)

    mock_fetch_hoyolab_post.return_value = {"post": {"subject": "News"}}
    hoyolab_webhook = MagicMock()
    mock_create_hoyolab_webhook.return_value = hoyolab_webhook

    result = send_entry_to_discord(entry, reader)

    assert result is None
    mock_fetch_hoyolab_post.assert_called_once_with("38588239")
    mock_create_hoyolab_webhook.assert_called_once_with(
        "https://discord.test/webhook",
        entry,
        {"post": {"subject": "News"}},
    )
    mock_create_embed_webhook.assert_not_called()
    mock_execute_webhook.assert_called_once_with(hoyolab_webhook, entry, reader=reader)


def test_get_screenshot_layout_prefers_mobile_tag() -> None:
    reader = MagicMock()
    feed = MagicMock()
    feed.url = "https://example.com/feed.xml"
    reader.get_tag.return_value = "mobile"

    result = get_screenshot_layout(reader, feed)

    assert result == "mobile"


def test_get_screenshot_layout_defaults_to_desktop() -> None:
    reader = MagicMock()
    feed = MagicMock()
    feed.url = "https://example.com/feed.xml"
    reader.get_tag.return_value = "unknown"

    result = get_screenshot_layout(reader, feed)

    assert result == "desktop"


@pytest.mark.parametrize(
    ("tag_value", "expected_limit"),
    [
        (0, 0),
        (1, 1),
        (7, 7),
        (-1, 0),
        (99, 10),
        ("first", 1),
        ("off", 0),
        ("8", 8),
        ("unknown", 1),
    ],
)
def test_get_feed_media_gallery_image_limit_normalizes_stored_tag(
    tag_value: feeds.JsonValue,
    expected_limit: int,
) -> None:
    reader = MagicMock()
    feed = MagicMock()
    feed.url = "https://example.com/feed.xml"
    reader.get_tag.return_value = tag_value

    result = feeds.get_feed_media_gallery_image_limit(reader, feed)

    assert result == expected_limit


def test_get_feed_media_gallery_image_limit_defaults_to_first_image() -> None:
    reader = MagicMock()
    feed = MagicMock()
    feed.url = "https://example.com/feed.xml"
    reader.get_tag.side_effect = lambda resource, key, default=None: default  # noqa: ARG005

    result = feeds.get_feed_media_gallery_image_limit(reader, feed)

    assert result == 1


@pytest.mark.parametrize(
    ("url", "expected_app_id"),
    [
        ("https://store.steampowered.com/feeds/news/app/570/?cc=us&l=english", "570"),
        ("https://store.steampowered.com/news/app/440/view/1234567890", "440"),
        ("https://store.steampowered.com/app/730/CounterStrike_2/", "730"),
        ("https://steamcommunity.com/games/570/rss/", "570"),
        ("https://steamcommunity.com/app/730/announcements/detail/1234567890", "730"),
        ("https://example.com/feed.xml", None),
    ],
)
def test_extract_steam_app_id_from_url(url: str, expected_app_id: str | None) -> None:
    assert feeds.extract_steam_app_id_from_url(url) == expected_app_id


@pytest.mark.parametrize(
    ("tag_value", "expected_limit"),
    [
        (1, 1),
        (25, 25),
        (-1, 1),
        (99_999, 4000),
        ("200", 200),
        ("0", 1),
        ("unknown", 4000),
    ],
)
def test_get_feed_webhook_text_length_limit_normalizes_stored_tag(
    tag_value: feeds.JsonValue,
    expected_limit: int,
) -> None:
    reader = MagicMock()
    feed = MagicMock()
    feed.url = "https://example.com/feed.xml"
    reader.get_tag.return_value = tag_value

    result = feeds.get_feed_webhook_text_length_limit(reader, feed)

    assert result == expected_limit


def test_get_feed_webhook_text_length_limit_defaults_to_discord_limit() -> None:
    reader = MagicMock()
    feed = MagicMock()
    feed.url = "https://example.com/feed.xml"
    reader.get_tag.side_effect = lambda resource, key, default=None: default  # noqa: ARG005

    result = feeds.get_feed_webhook_text_length_limit(reader, feed)

    assert result == 4000


def test_create_feed_inherits_global_screenshot_layout() -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhooks": [{"name": "Main", "url": "https://discord.com/api/webhooks/123/abc"}],
        "screenshot_layout": "mobile",
    }.get(key, default)

    create_feed(reader, "https://example.com/feed.xml", "Main")

    reader.set_tag.assert_any_call("https://example.com/feed.xml", "screenshot_layout", "mobile")


def test_create_feed_inherits_global_text_delivery_mode() -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhooks": [{"name": "Main", "url": "https://discord.com/api/webhooks/123/abc"}],
        "screenshot_layout": "desktop",
        "delivery_mode": "text",
    }.get(key, default)

    create_feed(reader, "https://example.com/feed.xml", "Main")

    reader.set_tag.assert_any_call("https://example.com/feed.xml", "delivery_mode", "text")
    reader.set_tag.assert_any_call("https://example.com/feed.xml", "should_send_embed", False)


def test_create_feed_enables_sent_webhook_tracking_by_default() -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhooks": [{"name": "Main", "url": "https://discord.com/api/webhooks/123/abc"}],
        "screenshot_layout": "desktop",
        "delivery_mode": "embed",
    }.get(key, default)

    create_feed(reader, "https://example.com/feed.xml", "Main")

    reader.set_tag.assert_any_call("https://example.com/feed.xml", "save_sent_webhooks", True)


def test_create_feed_sets_default_media_gallery_image_limit() -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhooks": [{"name": "Main", "url": "https://discord.com/api/webhooks/123/abc"}],
        "screenshot_layout": "desktop",
        "delivery_mode": "embed",
    }.get(key, default)

    create_feed(reader, "https://example.com/feed.xml", "Main")

    reader.set_tag.assert_any_call(
        "https://example.com/feed.xml",
        "media_gallery_image_limit",
        1,
    )


def test_create_feed_sets_default_webhook_text_length_limit() -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhooks": [{"name": "Main", "url": "https://discord.com/api/webhooks/123/abc"}],
        "screenshot_layout": "desktop",
        "delivery_mode": "embed",
    }.get(key, default)

    create_feed(reader, "https://example.com/feed.xml", "Main")

    reader.set_tag.assert_any_call(
        "https://example.com/feed.xml",
        "webhook_text_length_limit",
        4000,
    )


def test_create_feed_inherits_global_webhook_text_length_limit() -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhooks": [{"name": "Main", "url": "https://discord.com/api/webhooks/123/abc"}],
        "screenshot_layout": "desktop",
        "delivery_mode": "embed",
        "webhook_text_length_limit": 2500,
    }.get(key, default)

    create_feed(reader, "https://example.com/feed.xml", "Main")

    reader.set_tag.assert_any_call(
        "https://example.com/feed.xml",
        "webhook_text_length_limit",
        2500,
    )


def test_create_feed_falls_back_to_embed_when_global_delivery_mode_is_invalid() -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhooks": [{"name": "Main", "url": "https://discord.com/api/webhooks/123/abc"}],
        "screenshot_layout": "desktop",
        "delivery_mode": "invalid",
    }.get(key, default)

    create_feed(reader, "https://example.com/feed.xml", "Main")

    reader.set_tag.assert_any_call("https://example.com/feed.xml", "delivery_mode", "embed")
    reader.set_tag.assert_any_call("https://example.com/feed.xml", "should_send_embed", True)


def test_create_feed_removes_new_feed_when_initial_update_fails() -> None:
    feed_url = "https://example.com/not-a-feed"
    autodiscover_links = [{"href": "https://example.com/feed.xml", "type": "application/rss+xml"}]
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhooks": [{"name": "Main", "url": "https://discord.com/api/webhooks/123/abc"}],
        ".reader.autodiscover": autodiscover_links,
    }.get(key, default)
    reader.update_feed.side_effect = StorageError("invalid feed")

    with pytest.raises(feeds.FeedUpdateError) as exc_info:
        create_feed(reader, feed_url, "Main")

    reader.delete_feed.assert_called_once_with(feed_url)
    assert exc_info.value.autodiscover_links == autodiscover_links


def test_create_feed_does_not_remove_existing_feed_when_update_fails() -> None:
    feed_url = "https://example.com/existing-feed.xml"
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhooks": [{"name": "Main", "url": "https://discord.com/api/webhooks/123/abc"}],
    }.get(key, default)
    reader.add_feed.side_effect = FeedExistsError(feed_url)
    reader.update_feed.side_effect = StorageError("temporary failure")

    with pytest.raises(feeds.FeedUpdateError):
        create_feed(reader, feed_url, "Main")

    reader.delete_feed.assert_not_called()


@patch("discord_rss_bot.feeds.capture_full_page_screenshot")
@patch("discord_rss_bot.feeds.DiscordWebhook")
def test_create_screenshot_webhook_adds_image_file(
    mock_discord_webhook: MagicMock,
    mock_capture: MagicMock,
) -> None:
    mock_capture.return_value = b"png-bytes"
    webhook = MagicMock()
    mock_discord_webhook.return_value = webhook

    entry = MagicMock()
    entry.id = "entry-abc"
    entry.link = "https://example.com/article"
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "screenshot_layout": "mobile",
    }.get(key, default)

    result = create_screenshot_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    assert result == webhook
    mock_discord_webhook.assert_called_once_with(
        url="https://discord.com/api/webhooks/123/abc",
        content="<https://example.com/article>",
        rate_limit_retry=True,
    )
    mock_capture.assert_called_once_with(
        "https://example.com/article",
        screenshot_layout="mobile",
        screenshot_type="png",
    )
    webhook.add_file.assert_called_once()


@patch("discord_rss_bot.feeds.capture_full_page_screenshot")
@patch("discord_rss_bot.feeds.DiscordWebhook")
def test_create_screenshot_webhook_retries_jpeg_when_png_too_large(
    mock_discord_webhook: MagicMock,
    mock_capture: MagicMock,
) -> None:
    oversized_png = b"x" * (8 * 1024 * 1024 + 1024)
    compressed_jpeg = b"y" * (7 * 1024 * 1024)
    mock_capture.side_effect = [oversized_png, compressed_jpeg]

    webhook = MagicMock()
    mock_discord_webhook.return_value = webhook

    entry = MagicMock()
    entry.id = "entry-large"
    entry.link = "https://example.com/large-article"
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "screenshot_layout": "desktop",
    }.get(key, default)

    result = create_screenshot_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    assert result == webhook
    assert mock_capture.call_count == 2
    assert mock_capture.call_args_list[0].kwargs == {
        "screenshot_layout": "desktop",
        "screenshot_type": "png",
    }
    assert mock_capture.call_args_list[1].kwargs == {
        "screenshot_layout": "desktop",
        "screenshot_type": "jpeg",
        "jpeg_quality": 85,
    }
    webhook.add_file.assert_called_once()


@patch("discord_rss_bot.feeds.create_text_webhook")
@patch("discord_rss_bot.feeds.capture_full_page_screenshot")
def test_create_screenshot_webhook_falls_back_when_all_formats_too_large(
    mock_capture: MagicMock,
    mock_create_text_webhook: MagicMock,
) -> None:
    oversized_bytes = b"z" * (9 * 1024 * 1024)
    # 1 PNG attempt + 4 JPEG quality attempts
    mock_capture.side_effect = [oversized_bytes, oversized_bytes, oversized_bytes, oversized_bytes, oversized_bytes]
    fallback_webhook = MagicMock()
    mock_create_text_webhook.return_value = fallback_webhook

    entry = MagicMock()
    entry.id = "entry-too-large"
    entry.link = "https://example.com/very-large"
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "screenshot_layout": "desktop",
    }.get(key, default)

    result = create_screenshot_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    assert result == fallback_webhook
    assert mock_capture.call_count == 5
    mock_create_text_webhook.assert_called_once_with(
        "https://discord.com/api/webhooks/123/abc",
        entry,
        reader=reader,
        use_default_message_on_empty=True,
    )


@patch("discord_rss_bot.feeds.capture_full_page_screenshot")
@patch("discord_rss_bot.feeds.create_text_webhook")
def test_create_screenshot_webhook_falls_back_when_entry_has_no_link(
    mock_create_text_webhook: MagicMock,
    mock_capture: MagicMock,
) -> None:
    entry = MagicMock()
    entry.id = "entry-no-link"
    entry.link = None
    reader = MagicMock()
    fallback_webhook = MagicMock()
    mock_create_text_webhook.return_value = fallback_webhook

    result = create_screenshot_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    assert result == fallback_webhook
    mock_capture.assert_not_called()
    mock_create_text_webhook.assert_called_once_with(
        "https://discord.com/api/webhooks/123/abc",
        entry,
        reader=reader,
        use_default_message_on_empty=True,
    )


def test_screenshot_filename_for_entry_custom_extension() -> None:
    entry = MagicMock()
    entry.id = "hello/world?id=123"

    filename = screenshot_filename_for_entry(entry, extension="JPG")

    assert filename.endswith(".jpg")
    assert "/" not in filename
    assert "?" not in filename


@patch("discord_rss_bot.feeds._capture_full_page_screenshot_sync", return_value=b"jpeg-bytes")
def test_capture_full_page_screenshot_forwards_jpeg_options(mock_capture_sync: MagicMock) -> None:
    result = capture_full_page_screenshot(
        "https://example.com/article",
        screenshot_layout="mobile",
        screenshot_type="jpeg",
        jpeg_quality=55,
    )

    assert result == b"jpeg-bytes"
    mock_capture_sync.assert_called_once_with(
        "https://example.com/article",
        screenshot_layout="mobile",
        screenshot_type="jpeg",
        jpeg_quality=55,
    )


@patch("discord_rss_bot.feeds.create_text_webhook")
@patch("discord_rss_bot.feeds.capture_full_page_screenshot")
def test_create_screenshot_webhook_falls_back_to_text_on_failure(
    mock_capture: MagicMock,
    mock_create_text_webhook: MagicMock,
) -> None:
    mock_capture.return_value = None
    fallback_webhook = MagicMock()
    mock_create_text_webhook.return_value = fallback_webhook

    entry = MagicMock()
    entry.id = "entry-def"
    entry.link = "https://example.com/article"
    reader = MagicMock()

    result = create_screenshot_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    assert result == fallback_webhook
    mock_create_text_webhook.assert_called_once_with(
        "https://discord.com/api/webhooks/123/abc",
        entry,
        reader=reader,
        use_default_message_on_empty=True,
    )


@patch("discord_rss_bot.feeds.replace_tags_in_text_message")
def test_create_text_webhook_uses_feed_text_length_limit(mock_replace_tags_in_text_message: MagicMock) -> None:
    mock_replace_tags_in_text_message.return_value = "start-" + ("x" * 40) + "-end"

    entry = MagicMock()
    entry.feed.url = "https://example.com/feed.xml"
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "custom_message": "{{entry_title}}",
        "webhook_text_length_limit": 20,
    }.get(key, default)

    webhook = feeds.create_text_webhook(
        "https://discord.com/api/webhooks/123/abc",
        entry,
        reader,
        use_default_message_on_empty=False,
    )

    assert webhook.content is not None
    assert len(webhook.content) == 20
    assert webhook.content.startswith("start-")
    assert webhook.content.endswith("-end")
    assert "..." in webhook.content


@patch("discord_rss_bot.feeds.fetch_ttvdrops_campaign_media_items", return_value=[])
@patch("discord_rss_bot.feeds.replace_tags_in_embed")
def test_create_embed_webhook_uses_media_gallery_for_entry_images(
    mock_replace_tags_in_embed: MagicMock,
    mock_fetch_ttvdrops_campaign_media_items: MagicMock,
) -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "media_gallery_image_limit": 10,
        "webhook_text_length_limit": 4000,
    }.get(key, default)
    entry = MagicMock()
    entry.id = "entry-1"
    entry.title = "Entry title"
    entry.link = "https://example.com/entry"
    entry.summary = '<img src="https://example.com/summary.jpg" />'
    entry.content = [
        MagicMock(value='<img src="https://example.com/content-1.jpg" />'),
        MagicMock(value='<img src="https://example.com/content-2.jpg" />'),
    ]
    entry.feed.url = "https://example.com/feed.xml"
    mock_replace_tags_in_embed.return_value = feeds.CustomEmbed(
        description="Entry body",
        author_name="Entry title",
        author_url="https://example.com/entry",
    )

    webhook = feeds.create_embed_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    assert webhook.flags == 1 << 15
    components = get_test_webhook_components(webhook)
    assert components[0] == {
        "type": 10,
        "content": "## [Entry title](https://example.com/entry)\n\nEntry body",
    }
    gallery = components[1]
    assert isinstance(gallery, dict)
    assert gallery["type"] == 12
    mock_fetch_ttvdrops_campaign_media_items.assert_called_once_with(entry)
    assert gallery["items"] == [
        {"media": {"url": "https://example.com/content-1.jpg"}, "description": "Entry title"},
        {"media": {"url": "https://example.com/content-2.jpg"}, "description": "Entry title"},
        {"media": {"url": "https://example.com/summary.jpg"}, "description": "Entry title"},
    ]


@patch("discord_rss_bot.feeds.fetch_ttvdrops_campaign_media_items", return_value=[])
@patch("discord_rss_bot.feeds.replace_tags_in_embed")
def test_create_embed_webhook_uses_feed_text_length_limit_for_media_gallery(
    mock_replace_tags_in_embed: MagicMock,
    mock_fetch_ttvdrops_campaign_media_items: MagicMock,
) -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "media_gallery_image_limit": 10,
        "webhook_text_length_limit": 20,
    }.get(key, default)
    entry = MagicMock()
    entry.id = "entry-1"
    entry.title = "Entry title"
    entry.link = "https://example.com/entry"
    entry.summary = '<img src="https://example.com/summary.jpg" />'
    entry.content = [MagicMock(value='<img src="https://example.com/content-1.jpg" />')]
    entry.feed.url = "https://example.com/feed.xml"
    mock_replace_tags_in_embed.return_value = feeds.CustomEmbed(description="x" * 100)

    webhook = feeds.create_embed_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    assert webhook.flags == 1 << 15
    components = get_test_webhook_components(webhook)
    text_component = components[0]
    assert isinstance(text_component, dict)
    assert isinstance(text_component["content"], str)
    assert len(text_component["content"]) == 20
    assert text_component["content"].endswith("...")
    mock_fetch_ttvdrops_campaign_media_items.assert_called_once_with(entry)


@patch("discord_rss_bot.feeds.fetch_ttvdrops_campaign_media_items", return_value=[])
@patch("discord_rss_bot.feeds.replace_tags_in_embed")
def test_create_embed_webhook_can_limit_media_gallery_to_first_image(
    mock_replace_tags_in_embed: MagicMock,
    mock_fetch_ttvdrops_campaign_media_items: MagicMock,
) -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "media_gallery_image_limit": 1,
        "webhook_text_length_limit": 4000,
    }.get(key, default)
    entry = MagicMock()
    entry.id = "entry-1"
    entry.title = "Entry title"
    entry.link = "https://example.com/entry"
    entry.summary = '<img src="https://example.com/summary.jpg" />'
    entry.content = [
        MagicMock(value='<img src="https://example.com/content-1.jpg" />'),
        MagicMock(value='<img src="https://example.com/content-2.jpg" />'),
    ]
    entry.feed.url = "https://example.com/feed.xml"
    mock_replace_tags_in_embed.return_value = feeds.CustomEmbed(description="Entry body")

    webhook = feeds.create_embed_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    gallery = get_test_webhook_components(webhook)[1]
    assert isinstance(gallery, dict)
    mock_fetch_ttvdrops_campaign_media_items.assert_called_once_with(entry)
    assert gallery["items"] == [
        {"media": {"url": "https://example.com/content-1.jpg"}, "description": "Entry title"},
    ]


@patch("discord_rss_bot.feeds.fetch_ttvdrops_campaign_media_items", return_value=[])
@patch("discord_rss_bot.feeds.replace_tags_in_embed")
def test_create_embed_webhook_can_disable_media_images(
    mock_replace_tags_in_embed: MagicMock,
    mock_fetch_ttvdrops_campaign_media_items: MagicMock,
) -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "media_gallery_image_limit": 0,
        "webhook_text_length_limit": 4000,
    }.get(key, default)
    entry = MagicMock()
    entry.id = "entry-1"
    entry.title = "Entry title"
    entry.link = "https://example.com/entry"
    entry.summary = '<img src="https://example.com/summary.jpg" />'
    entry.content = [MagicMock(value='<img src="https://example.com/content-1.jpg" />')]
    entry.feed.url = "https://example.com/feed.xml"
    mock_replace_tags_in_embed.return_value = feeds.CustomEmbed(
        description="Entry body",
        image_url="https://example.com/custom-image.jpg",
        thumbnail_url="https://example.com/custom-thumbnail.jpg",
    )

    webhook = feeds.create_embed_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    assert "components" not in webhook.json
    assert "embeds" in webhook.json
    embeds = webhook.json["embeds"]
    assert isinstance(embeds, list)
    assert isinstance(embeds[0], dict)
    assert "image" not in embeds[0]
    assert "thumbnail" not in embeds[0]
    mock_fetch_ttvdrops_campaign_media_items.assert_not_called()


@patch("discord_rss_bot.feeds.fetch_ttvdrops_campaign_media_items", return_value=[])
@patch("discord_rss_bot.feeds.replace_tags_in_embed")
def test_create_embed_webhook_can_use_steam_game_icon_thumbnail(
    mock_replace_tags_in_embed: MagicMock,
    mock_fetch_ttvdrops_campaign_media_items: MagicMock,
) -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "media_gallery_image_limit": 0,
        "webhook_text_length_limit": 4000,
    }.get(key, default)
    entry = MagicMock()
    entry.id = "entry-steam-1"
    entry.title = "Dota 2 patch notes"
    entry.link = "https://steamcommunity.com/games/570/announcements/detail/1234567890"
    entry.summary = ""
    entry.content = []
    entry.feed.url = "https://store.steampowered.com/feeds/news/app/570/?cc=us&l=english"
    mock_replace_tags_in_embed.return_value = feeds.CustomEmbed(
        description="Steam news",
        thumbnail_url="https://example.com/custom-thumb.jpg",
        show_steam_game_icon_in_thumbnail=True,
    )

    with patch("discord_rss_bot.feeds.Path.is_file", return_value=False):
        webhook = feeds.create_embed_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    assert "components" not in webhook.json
    embeds = webhook.json.get("embeds")
    assert isinstance(embeds, list)
    assert isinstance(embeds[0], dict)
    assert embeds[0]["thumbnail"] == {
        "url": "https://cdn.cloudflare.steamstatic.com/steam/apps/570/capsule_sm_120.jpg",
    }
    assert webhook.files == []
    mock_fetch_ttvdrops_campaign_media_items.assert_not_called()


@patch("discord_rss_bot.feeds.fetch_ttvdrops_campaign_media_items", return_value=[])
@patch("discord_rss_bot.feeds.replace_tags_in_embed")
def test_create_embed_webhook_prefers_local_steam_game_icon_thumbnail(
    mock_replace_tags_in_embed: MagicMock,
    mock_fetch_ttvdrops_campaign_media_items: MagicMock,
) -> None:
    local_icon_bytes = b"local-steam-icon"

    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "media_gallery_image_limit": 0,
        "webhook_text_length_limit": 4000,
    }.get(key, default)
    entry = MagicMock()
    entry.id = "entry-steam-local-1"
    entry.title = "Dota 2 patch notes"
    entry.link = "https://steamcommunity.com/games/570/announcements/detail/1234567890"
    entry.summary = ""
    entry.content = []
    entry.feed.url = "https://store.steampowered.com/feeds/news/app/570/?cc=us&l=english"
    mock_replace_tags_in_embed.return_value = feeds.CustomEmbed(
        description="Steam news",
        thumbnail_url="https://example.com/custom-thumb.jpg",
        show_steam_game_icon_in_thumbnail=True,
    )

    with (
        patch("discord_rss_bot.feeds.Path.is_file", return_value=True),
        patch("discord_rss_bot.feeds.Path.read_bytes", return_value=local_icon_bytes),
    ):
        webhook = feeds.create_embed_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    embeds = webhook.json.get("embeds")
    assert isinstance(embeds, list)
    assert isinstance(embeds[0], dict)
    assert len(webhook.files) == 1
    uploaded_icon = webhook.files[0]
    assert uploaded_icon.content == local_icon_bytes
    assert uploaded_icon.filename.startswith("steam-app-570-")
    assert uploaded_icon.filename.endswith(".png")
    assert embeds[0]["thumbnail"] == {"url": f"attachment://{uploaded_icon.filename}"}
    mock_fetch_ttvdrops_campaign_media_items.assert_not_called()


@patch("discord_rss_bot.feeds.fetch_ttvdrops_campaign_media_items", return_value=[])
@patch("discord_rss_bot.feeds.replace_tags_in_embed")
def test_create_embed_webhook_does_not_inject_steam_thumbnail_when_app_id_is_missing(
    mock_replace_tags_in_embed: MagicMock,
    mock_fetch_ttvdrops_campaign_media_items: MagicMock,
) -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "media_gallery_image_limit": 0,
        "webhook_text_length_limit": 4000,
    }.get(key, default)
    entry = MagicMock()
    entry.id = "entry-steam-2"
    entry.title = "Steam group post"
    entry.link = "https://steamcommunity.com/groups/example/announcements/detail/1234567890"
    entry.summary = ""
    entry.content = []
    entry.feed.url = "https://steamcommunity.com/groups/example/rss/"
    mock_replace_tags_in_embed.return_value = feeds.CustomEmbed(
        description="Steam group news",
        thumbnail_url="https://example.com/custom-thumb.jpg",
        show_steam_game_icon_in_thumbnail=True,
    )

    webhook = feeds.create_embed_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    assert "components" not in webhook.json
    embeds = webhook.json.get("embeds")
    assert isinstance(embeds, list)
    assert isinstance(embeds[0], dict)
    assert "thumbnail" not in embeds[0]
    mock_fetch_ttvdrops_campaign_media_items.assert_not_called()


@patch("discord_rss_bot.feeds.fetch_ttvdrops_campaign_media_items", return_value=[])
@patch("discord_rss_bot.feeds.replace_tags_in_embed")
def test_create_embed_webhook_uses_feed_text_length_limit_for_regular_embed_description(
    mock_replace_tags_in_embed: MagicMock,
    mock_fetch_ttvdrops_campaign_media_items: MagicMock,
) -> None:
    reader = MagicMock()
    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "media_gallery_image_limit": 0,
        "webhook_text_length_limit": 20,
    }.get(key, default)
    entry = MagicMock()
    entry.id = "entry-1"
    entry.title = "Entry title"
    entry.link = "https://example.com/entry"
    entry.summary = ""
    entry.content = []
    entry.feed.url = "https://example.com/feed.xml"
    mock_replace_tags_in_embed.return_value = feeds.CustomEmbed(description="x" * 100)

    webhook = feeds.create_embed_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    assert "components" not in webhook.json
    embeds = webhook.json.get("embeds")
    assert isinstance(embeds, list)
    assert isinstance(embeds[0], dict)
    assert isinstance(embeds[0].get("description"), str)
    assert len(embeds[0]["description"]) == 20  # pyright: ignore[reportArgumentType]
    assert embeds[0]["description"].endswith("...")  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]
    mock_fetch_ttvdrops_campaign_media_items.assert_not_called()


@patch("discord_rss_bot.feeds.fetch_ttvdrops_campaign_media_items")
@patch("discord_rss_bot.feeds.replace_tags_in_embed")
def test_create_embed_webhook_prefers_ttvdrops_reward_images_and_alt_text(
    mock_replace_tags_in_embed: MagicMock,
    mock_fetch_ttvdrops_campaign_media_items: MagicMock,
) -> None:
    reader = MagicMock()
    entry = MagicMock()
    entry.id = "entry-2"
    entry.title = "Drop campaign"
    entry.link = "https://ttvdrops.lovinator.space/twitch/campaigns/93ba35ae-5bfc-43fe-88ac-49a0aabb2fe2/"
    entry.summary = '<img src="https://example.com/feed-image.jpg" />'
    entry.content = []
    entry.feed.url = "https://ttvdrops.lovinator.space/feed.xml"
    mock_replace_tags_in_embed.return_value = feeds.CustomEmbed(description="Campaign body")
    mock_fetch_ttvdrops_campaign_media_items.return_value = [
        {
            "url": "https://ttvdrops.lovinator.space/media/benefits/images/reward.png",
            "description": "120 minutes watched: Skulbladi",
        },
    ]

    webhook = feeds.create_embed_webhook("https://discord.com/api/webhooks/123/abc", entry, reader)

    gallery = get_test_webhook_components(webhook)[1]
    assert isinstance(gallery, dict)
    assert gallery["items"] == [
        {
            "media": {"url": "https://ttvdrops.lovinator.space/media/benefits/images/reward.png"},
            "description": "120 minutes watched: Skulbladi",
        },
    ]


def test_get_ttvdrops_campaign_api_url_from_campaign_page() -> None:
    entry = MagicMock()
    entry.link = "https://ttvdrops.lovinator.space/twitch/campaigns/93ba35ae-5bfc-43fe-88ac-49a0aabb2fe2/"
    entry.id = "entry-3"
    entry.feed.url = "https://example.com/feed.xml"

    api_url = feeds.get_ttvdrops_campaign_api_url(entry)

    assert api_url == "https://ttvdrops.lovinator.space/twitch/api/v1/campaigns/93ba35ae-5bfc-43fe-88ac-49a0aabb2fe2/"


@pytest.mark.parametrize(
    ("feed_url", "include_paid_reward"),
    [
        ("https://ttvdrops.lovinator.space/twitch/feed.xml", True),
        ("https://ttvdrops.lovinator.space/twitch/feed.xml?hide_paid=0", True),
        ("https://ttvdrops.lovinator.space/twitch/feed.xml?hide_paid=true", True),
        ("https://ttvdrops.lovinator.space/twitch/feed.xml?hide_paid=1", False),
        ("https://ttvdrops.lovinator.space/twitch/feed.xml?lang=en&hide_paid=1", False),
        ("https://ttvdrops.lovinator.space/twitch/feed.xml?hide_paid=0&hide_paid=1", False),
    ],
)
@patch("discord_rss_bot.feeds.httpx2.get")
def test_fetch_ttvdrops_campaign_media_items_extracts_reward_alt_text(
    mock_get: MagicMock,
    feed_url: str,
    *,
    include_paid_reward: bool,
) -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "image_url": "/media/campaigns/images/campaign.png",
        "drops": [
            {
                "name": "Drop",
                "required_minutes_watched": 120,
                "benefits": [
                    {"name": "Skulbladi", "image_url": "/media/benefits/images/reward.png"},
                    {"image_url": "javascript:alert(1)"},
                ],
            },
            {
                "name": "Paid drop",
                "required_minutes_watched": 0,
                "required_subs": 2,
                "benefits": [
                    {"name": "Pay2win reward", "image_url": "/media/benefits/images/paid-reward.png"},
                ],
            },
        ],
    }
    mock_get.return_value = response
    entry = MagicMock()
    entry.link = "https://ttvdrops.lovinator.space/twitch/campaigns/93ba35ae-5bfc-43fe-88ac-49a0aabb2fe2/"
    entry.id = "entry-4"
    entry.feed.url = feed_url

    media_items = feeds.fetch_ttvdrops_campaign_media_items(entry)

    expected_media_items: list[JsonObject] = [
        {
            "url": "https://ttvdrops.lovinator.space/media/benefits/images/reward.png",
            "description": "120 minutes watched: Skulbladi",
        },
    ]
    if include_paid_reward:
        expected_media_items.append(
            {
                "url": "https://ttvdrops.lovinator.space/media/benefits/images/paid-reward.png",
                "description": "2 subscriptions: Pay2win reward",
            },
        )
    assert media_items == expected_media_items
    mock_get.assert_called_once_with(
        "https://ttvdrops.lovinator.space/twitch/api/v1/campaigns/93ba35ae-5bfc-43fe-88ac-49a0aabb2fe2/",
        follow_redirects=True,
        timeout=10.0,
    )


def test_extract_ttvdrops_media_gallery_items_includes_paid_rewards_by_default() -> None:
    media_items = feeds.extract_ttvdrops_media_gallery_items(
        {
            "drops": [
                {
                    "required_subs": 1,
                    "benefits": [{"name": "Paid reward", "image_url": "/media/paid.png"}],
                },
            ],
        },
    )

    assert media_items == [
        {
            "url": "https://ttvdrops.lovinator.space/media/paid.png",
            "description": "1 subscriptions: Paid reward",
        },
    ]


def test_extract_ttvdrops_media_gallery_items_hide_paid_omits_non_watch_rewards() -> None:
    media_items = feeds.extract_ttvdrops_media_gallery_items(
        {
            "drops": [
                {
                    "required_minutes_watched": 30,
                    "benefits": [{"name": "Watch reward", "image_url": "/media/watch.png"}],
                },
                {
                    "required_minutes_watched": 0,
                    "required_subs": 1,
                    "benefits": [{"name": "Paid reward", "image_url": "/media/paid.png"}],
                },
                {
                    "benefits": [{"name": "Unknown reward", "image_url": "/media/unknown.png"}],
                },
            ],
        },
        hide_paid=True,
    )

    assert media_items == [
        {
            "url": "https://ttvdrops.lovinator.space/media/watch.png",
            "description": "30 minutes watched: Watch reward",
        },
    ]


def test_extract_ttvdrops_media_gallery_items_extracts_nested_watch_rewards() -> None:
    media_items = feeds.extract_ttvdrops_media_gallery_items(
        {
            "campaign": {
                "drops": [
                    {
                        "required_minutes_watched": 45,
                        "rewards": [{"name": "Nested reward", "image_url": "/media/nested.png"}],
                    },
                ],
            },
        },
        hide_paid=True,
    )

    assert media_items == [
        {
            "url": "https://ttvdrops.lovinator.space/media/nested.png",
            "description": "45 minutes watched: Nested reward",
        },
    ]


def test_capture_full_page_screenshot_uses_thread_when_loop_running() -> None:
    """Capture should offload sync Playwright work when called from an active event loop."""
    with patch("discord_rss_bot.feeds._capture_full_page_screenshot_sync", return_value=b"png") as mock_capture_sync:

        async def run_capture() -> bytes | None:
            return feeds.capture_full_page_screenshot(
                "https://example.com/article",
                screenshot_layout="desktop",
                screenshot_type="png",
            )

        result = asyncio.run(run_capture())

    assert result == b"png"
    mock_capture_sync.assert_called_once_with(
        "https://example.com/article",
        screenshot_layout="desktop",
        screenshot_type="png",
        jpeg_quality=85,
    )


@patch("discord_rss_bot.feeds.get_entry_delivery_mode")
@patch("discord_rss_bot.feeds.create_screenshot_webhook")
@patch("discord_rss_bot.feeds.execute_webhook")
def test_send_entry_to_discord_uses_screenshot_mode(
    mock_execute_webhook: MagicMock,
    mock_create_screenshot_webhook: MagicMock,
    mock_get_entry_delivery_mode: MagicMock,
) -> None:
    reader = MagicMock()
    entry = MagicMock()
    entry.feed.url = "https://example.com/feed.xml"
    entry.feed_url = "https://example.com/feed.xml"

    reader.get_tag.side_effect = lambda resource, key, default=None: {  # noqa: ARG005
        "webhook": "https://discord.com/api/webhooks/123/abc",
    }.get(key, default)

    mock_get_entry_delivery_mode.return_value = "screenshot"
    screenshot_webhook = MagicMock()
    mock_create_screenshot_webhook.return_value = screenshot_webhook

    send_entry_to_discord(entry, reader)

    mock_create_screenshot_webhook.assert_called_once_with(
        "https://discord.com/api/webhooks/123/abc",
        entry,
        reader=reader,
    )
    mock_execute_webhook.assert_called_once_with(screenshot_webhook, entry, reader=reader)


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
    send_entry_to_discord(mock_entry, mock_reader)

    # Assertions
    mock_create_embed.assert_not_called()
    mock_discord_webhook.assert_called_once()

    # Check webhook was created with the right message
    webhook_call_kwargs = mock_discord_webhook.call_args[1]
    assert "content" in webhook_call_kwargs, "Webhook should have content"
    assert webhook_call_kwargs["url"] == "https://discord.com/api/webhooks/123/abc"

    # Verify execute_webhook was called
    mock_execute_webhook.assert_called_once_with(mock_webhook, mock_entry, reader=mock_reader)


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


@patch("discord_rss_bot.feeds.execute_webhook")
def test_send_discord_quest_notification_text_match(mock_execute_webhook: MagicMock) -> None:
    """Send a quest link as a separate notification when plain text content contains one."""
    entry = MagicMock()
    entry.id = "entry-1"
    entry.content = [MagicMock(type="text", value="Check this https://discord.com/quests/12345 now")]
    reader = MagicMock()

    send_discord_quest_notification(entry, "https://discord.com/api/webhooks/123/abc", reader)

    mock_execute_webhook.assert_called_once()
    webhook_sent = mock_execute_webhook.call_args[0][0]
    assert webhook_sent.content == "https://discord.com/quests/12345"


@patch("discord_rss_bot.feeds.execute_webhook")
def test_send_discord_quest_notification_html_match(mock_execute_webhook: MagicMock) -> None:
    """Send a quest link when it is found inside HTML content."""
    entry = MagicMock()
    entry.id = "entry-2"
    entry.content = [
        MagicMock(
            type="text/html",
            value='<p>Click <a href="https://discord.com/quests/777">here</a></p>',
        ),
    ]
    reader = MagicMock()

    send_discord_quest_notification(entry, "https://discord.com/api/webhooks/123/abc", reader)

    mock_execute_webhook.assert_called_once()
    webhook_sent = mock_execute_webhook.call_args[0][0]
    assert webhook_sent.content == "https://discord.com/quests/777"


@patch("discord_rss_bot.feeds.execute_webhook")
def test_send_discord_quest_notification_no_match(mock_execute_webhook: MagicMock) -> None:
    """Do nothing when no quest URL exists in entry content."""
    entry = MagicMock()
    entry.id = "entry-3"
    entry.content = [MagicMock(type="text", value="No quest link here")]
    reader = MagicMock()

    send_discord_quest_notification(entry, "https://discord.com/api/webhooks/123/abc", reader)

    mock_execute_webhook.assert_not_called()


def test_get_webhook_url_returns_value() -> None:
    reader = MagicMock()
    entry = MagicMock()
    entry.feed_url = "https://example.com/feed.xml"
    entry.feed.url = "https://example.com/feed.xml"
    reader.get_tag.return_value = "https://discord.com/api/webhooks/123/abc"

    result = get_webhook_url(reader, entry)

    assert result == "https://discord.com/api/webhooks/123/abc"


def test_get_webhook_url_returns_empty_on_storage_error() -> None:
    reader = MagicMock()
    entry = MagicMock()
    entry.feed_url = "https://example.com/feed.xml"
    entry.feed.url = "https://example.com/feed.xml"
    reader.get_tag.side_effect = StorageError("db error")

    result = get_webhook_url(reader, entry)

    assert not result


def test_set_entry_as_read_handles_entry_not_found_error() -> None:
    reader = MagicMock()
    entry = MagicMock(id="entry-4")
    reader.set_entry_read.side_effect = EntryNotFoundError("https://example.com/feed.xml", "entry-4")

    set_entry_as_read(reader, entry)

    reader.set_entry_read.assert_called_once_with(entry, True)


def test_set_entry_as_read_handles_storage_error() -> None:
    reader = MagicMock()
    entry = MagicMock(id="entry-5")
    reader.set_entry_read.side_effect = StorageError("db error")

    set_entry_as_read(reader, entry)

    reader.set_entry_read.assert_called_once_with(entry, True)


def test_execute_webhook_skips_when_feed_paused() -> None:
    webhook = MagicMock()
    reader = MagicMock()
    entry = MagicMock()
    entry.id = "entry-6"
    entry.feed.url = "https://example.com/feed.xml"
    entry.feed.updates_enabled = False

    execute_webhook(webhook, entry, reader)

    reader.get_feed.assert_not_called()
    webhook.execute.assert_not_called()


def test_execute_webhook_skips_when_feed_missing() -> None:
    webhook = MagicMock()
    reader = MagicMock()
    reader.get_feed.side_effect = FeedNotFoundError("missing")
    entry = MagicMock()
    entry.id = "entry-7"
    entry.feed.url = "https://example.com/feed.xml"
    entry.feed.updates_enabled = True

    execute_webhook(webhook, entry, reader)

    webhook.execute.assert_not_called()


@patch.object(feeds, "logger")
@patch("discord_rss_bot.feeds.send_webhook_message")
def test_execute_webhook_logs_error_on_bad_status(
    mock_send_webhook_message: MagicMock,
    mock_logger: MagicMock,
) -> None:
    webhook = MagicMock()
    webhook.json = {"content": "test"}
    mock_send_webhook_message.return_value = MagicMock(status_code=500, text="fail")
    reader = MagicMock()
    entry = MagicMock()
    entry.id = "entry-8"
    entry.feed.url = "https://example.com/feed.xml"
    entry.feed.updates_enabled = True

    execute_webhook(webhook, entry, reader)

    mock_logger.error.assert_called_once()


@patch.object(feeds, "logger")
@patch("discord_rss_bot.feeds.send_webhook_message")
def test_execute_webhook_logs_info_on_success(
    mock_send_webhook_message: MagicMock,
    mock_logger: MagicMock,
) -> None:
    webhook = MagicMock()
    mock_send_webhook_message.return_value = MagicMock(status_code=204, text="")
    reader = MagicMock()
    entry = MagicMock()
    entry.id = "entry-9"
    entry.feed.url = "https://example.com/feed.xml"
    entry.feed.updates_enabled = True

    execute_webhook(webhook, entry, reader)

    mock_logger.info.assert_called_once_with("Sent entry to Discord: %s", "entry-9")


@patch("discord_rss_bot.feeds.send_webhook_message")
def test_execute_webhook_records_sent_webhook_message(mock_send_webhook_message: MagicMock) -> None:
    webhook_url = "https://discord.com/api/webhooks/123/abc"
    state: dict[str, feeds.JsonValue] = {}

    def get_tag(_resource: str | tuple[()], key: str, default: feeds.JsonValue = None) -> feeds.JsonValue:
        if key == "sent_webhooks":
            return state.get("sent_webhooks", default)
        if key == "save_sent_webhooks":
            return True
        if key == "webhook":
            return webhook_url
        if key == "delivery_mode":
            return "text"
        return default

    def set_tag(_resource: str | tuple[()], key: str, value: feeds.JsonValue) -> None:
        state[key] = value

    reader = MagicMock()
    reader.get_tag.side_effect = get_tag
    reader.set_tag.side_effect = set_tag

    entry = MagicMock()
    entry.id = "entry-1"
    entry.title = "Entry title"
    entry.link = "https://example.com/entry-1"
    entry.updated = datetime(2026, 5, 8, tzinfo=UTC)
    entry.feed_url = "https://example.com/feed.xml"
    entry.feed.url = "https://example.com/feed.xml"
    entry.feed.title = "Example feed"
    entry.feed.updates_enabled = True

    webhook = MagicMock()
    webhook.json = {"content": "Entry title", "embeds": [], "attachments": []}
    response = MagicMock()
    response.status_code = 200
    response.text = '{"id": "message-1"}'
    response.json.return_value = {"id": "message-1"}
    mock_send_webhook_message.return_value = response

    execute_webhook(webhook, entry, reader)

    records = state["sent_webhooks"]
    assert isinstance(records, list)
    assert len(records) == 1
    assert isinstance(records[0], dict)
    assert records[0]["feed_url"] == "https://example.com/feed.xml"
    assert records[0]["entry_id"] == "entry-1"
    assert records[0]["webhook_url"] == webhook_url
    assert records[0]["message_id"] == "message-1"
    assert records[0]["last_status_code"] == 200
    assert records[0]["discord_response"] == {"id": "message-1"}
    assert records[0]["response_text"] == '{"id": "message-1"}'

    assert isinstance(records[0]["payload"], dict)
    assert records[0]["payload"]["content"] == "Entry title"


@patch("discord_rss_bot.feeds.send_webhook_message")
def test_execute_webhook_does_not_record_when_feed_tracking_disabled(mock_send_webhook_message: MagicMock) -> None:
    webhook_url = "https://discord.com/api/webhooks/123/abc"
    reader = MagicMock()
    reader.get_tag.side_effect = lambda _resource, key, default=None: {
        "save_sent_webhooks": False,
        "webhook": webhook_url,
    }.get(key, default)

    entry = MagicMock()
    entry.id = "entry-2"
    entry.feed_url = "https://example.com/feed.xml"
    entry.feed.url = "https://example.com/feed.xml"
    entry.feed.updates_enabled = True

    webhook = MagicMock()
    webhook.json = {"content": "Entry title", "embeds": [], "attachments": []}
    response = MagicMock()
    response.status_code = 200
    response.text = '{"id": "message-2"}'
    response.json.return_value = {"id": "message-2"}
    mock_send_webhook_message.return_value = response

    execute_webhook(webhook, entry, reader)

    reader.set_tag.assert_not_called()


@patch("discord_rss_bot.feeds.httpx2.request")
def test_send_webhook_message_posts_components_with_httpx2(mock_request: MagicMock) -> None:
    response = MagicMock(status_code=200, text='{"id": "message-1"}')
    mock_request.return_value = response
    components: list[feeds.JsonValue] = [
        {
            "type": 10,
            "content": "# Component update",
        },
    ]
    webhook = feeds.DiscordWebhook(
        url="https://discord.com/api/webhooks/123/abc?thread_id=456",
        flags=1 << 15,
        components=components,
    )

    result = feeds.send_webhook_message(webhook, feeds.get_webhook_request_payload(webhook))

    assert result is response
    mock_request.assert_called_once()
    assert mock_request.call_args.args == ("POST", "https://discord.com/api/webhooks/123/abc")
    assert mock_request.call_args.kwargs["json"] == {
        "components": components,
        "flags": 1 << 15,
    }
    assert mock_request.call_args.kwargs["params"] == {
        "thread_id": "456",
        "wait": "true",
        "with_components": "true",
    }


@patch("discord_rss_bot.feeds.httpx2.request")
def test_send_webhook_message_uploads_files_as_multipart(mock_request: MagicMock) -> None:
    response = MagicMock(status_code=200, text='{"id": "message-2"}')
    mock_request.return_value = response
    webhook = feeds.DiscordWebhook(url="https://discord.com/api/webhooks/123/abc", content="Entry link")
    webhook.add_file(file=b"image-bytes", filename="entry.png")

    result = feeds.send_webhook_message(webhook, feeds.get_webhook_request_payload(webhook))

    assert result is response
    mock_request.assert_called_once()
    assert mock_request.call_args.args == ("POST", "https://discord.com/api/webhooks/123/abc")
    assert mock_request.call_args.kwargs["data"] == {"payload_json": '{"content": "Entry link"}'}
    assert mock_request.call_args.kwargs["files"] == [("files[0]", ("entry.png", b"image-bytes"))]
    assert "json" not in mock_request.call_args.kwargs


@patch("discord_rss_bot.feeds.time.sleep")
@patch("discord_rss_bot.feeds.httpx2.request")
def test_request_discord_webhook_retries_rate_limit_with_httpx2(
    mock_request: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    rate_limited_response = MagicMock(status_code=429, headers={})
    rate_limited_response.json.return_value = {"retry_after": 0.25}
    success_response = MagicMock(status_code=200)
    mock_request.side_effect = [rate_limited_response, success_response]
    payload: JsonObject = {"content": "Retry entry"}
    request_call = call(
        "POST",
        "https://discord.com/api/webhooks/123/abc",
        params={"wait": "true"},
        timeout=30.0,
        json=payload,
    )

    result = feeds.request_discord_webhook(
        "POST",
        "https://discord.com/api/webhooks/123/abc",
        payload=payload,
        params={"wait": "true"},
        files=None,
        timeout=30.0,
        rate_limit_retry=True,
    )

    assert result is success_response
    assert mock_request.call_args_list == [request_call, request_call]
    mock_sleep.assert_called_once_with(0.25)


@patch("discord_rss_bot.feeds.httpx2.request")
def test_edit_sent_webhook_message_patches_message_with_httpx2(mock_request: MagicMock) -> None:
    response = MagicMock(status_code=200, text='{"id": "message-3"}')
    mock_request.return_value = response
    payload: JsonObject = {"content": "Updated entry"}
    webhook = feeds.DiscordWebhook(url="https://discord.com/api/webhooks/123/abc")

    result = feeds.edit_sent_webhook_message(
        "https://discord.com/api/webhooks/123/abc?thread_id=456",
        "message-3",
        webhook,
        payload,
    )

    assert result is response
    mock_request.assert_called_once_with(
        "PATCH",
        "https://discord.com/api/webhooks/123/abc/messages/message-3",
        params={"thread_id": "456", "wait": "true"},
        timeout=30.0,
        json=payload,
    )


@patch("discord_rss_bot.feeds.edit_sent_webhook_message")
@patch("discord_rss_bot.feeds.create_webhook_for_entry")
def test_update_sent_webhooks_for_modified_entries_edits_changed_payload(
    mock_create_webhook_for_entry: MagicMock,
    mock_edit_sent_webhook_message: MagicMock,
) -> None:
    webhook_url = "https://discord.com/api/webhooks/123/abc"
    old_payload: JsonObject = {"content": "Old title", "embeds": [], "attachments": []}
    state: dict[str, feeds.JsonValue] = {
        "sent_webhooks": [
            {
                "feed_url": "https://example.com/feed.xml",
                "entry_id": "entry-3",
                "webhook_url": webhook_url,
                "message_id": "message-3",
                "payload": old_payload,
                "payload_hash": feeds.hash_webhook_payload(old_payload),
                "update_count": 0,
            },  # pyright: ignore[reportAssignmentType, reportArgumentType]
        ],
    }

    def get_tag(_resource: str | tuple[()], key: str, default: feeds.JsonValue = None) -> feeds.JsonValue:
        if key == "sent_webhooks":
            return state["sent_webhooks"]
        if key == "save_sent_webhooks":
            return True
        return default

    def set_tag(_resource: str | tuple[()], key: str, value: feeds.JsonValue) -> None:
        state[key] = value

    entry = MagicMock()
    entry.id = "entry-3"
    entry.title = "New title"
    entry.link = "https://example.com/entry-3"
    entry.updated = datetime(2026, 5, 8, tzinfo=UTC)
    entry.feed.url = "https://example.com/feed.xml"
    entry.feed.title = "Example feed"

    reader = MagicMock()
    reader.get_tag.side_effect = get_tag
    reader.set_tag.side_effect = set_tag
    reader.get_entry.return_value = entry

    webhook = MagicMock()
    webhook.json = {"content": "New title", "embeds": [], "attachments": []}
    mock_create_webhook_for_entry.return_value = (webhook, "text")

    response = MagicMock()
    response.status_code = 200
    response.text = '{"id": "message-3"}'
    response.json.return_value = {"id": "message-3"}
    mock_edit_sent_webhook_message.return_value = response

    updated_count: int = feeds.update_sent_webhooks_for_modified_entries(
        reader,
        [("https://example.com/feed.xml", "entry-3")],
    )

    assert updated_count == 1
    mock_edit_sent_webhook_message.assert_called_once()
    edit_payload = mock_edit_sent_webhook_message.call_args.kwargs["payload"]
    assert edit_payload == {"content": "New title"}
    records = state["sent_webhooks"]
    assert isinstance(records, list)
    assert isinstance(records[0], dict)
    assert isinstance(records[0]["payload"], dict)
    assert records[0]["payload"]["content"] == "New title"
    assert records[0]["discord_response"] == {"id": "message-3"}
    assert records[0]["response_text"] == '{"id": "message-3"}'
    assert records[0]["update_count"] == 1
    assert not records[0]["last_error"]


@patch("discord_rss_bot.feeds.edit_sent_webhook_message")
@patch("discord_rss_bot.feeds.create_webhook_for_entry")
def test_update_sent_webhook_record_preserves_existing_embed_image_when_updated_entry_has_no_image(
    mock_create_webhook_for_entry: MagicMock,
    mock_edit_sent_webhook_message: MagicMock,
) -> None:
    previous_image: JsonObject = {
        "url": "https://example.com/original-image.jpg",
        "proxy_url": None,
        "height": None,
        "width": None,
    }
    old_payload: JsonObject = {
        "content": "",
        "embeds": [{"description": "Old summary", "image": previous_image, "thumbnail": None}],
        "attachments": [],
    }
    record: feeds.SentWebhookRecord = {
        "feed_url": "https://example.com/feed.xml",
        "entry_id": "entry-4",
        "webhook_url": "https://discord.com/api/webhooks/123/abc",
        "message_id": "message-4",
        "payload": old_payload,
        "payload_hash": feeds.hash_webhook_payload(old_payload),
        "update_count": 0,
    }

    entry = MagicMock()
    entry.id = "entry-4"
    entry.title = "New title"
    entry.link = "https://example.com/entry-4"
    entry.updated = datetime(2026, 5, 8, tzinfo=UTC)
    entry.feed.url = "https://example.com/feed.xml"
    entry.feed.title = "Example feed"

    reader = MagicMock()
    webhook = MagicMock()
    webhook.json = {
        "content": "",
        "embeds": [{"description": "New summary", "image": None, "thumbnail": None}],
        "attachments": [],
    }
    mock_create_webhook_for_entry.return_value = (webhook, "embed")

    response = MagicMock()
    response.status_code = 200
    response.text = '{"id": "message-4"}'
    response.json.return_value = {"id": "message-4"}
    mock_edit_sent_webhook_message.return_value = response

    updated_record, record_changed, message_was_edited = feeds.update_sent_webhook_record_for_entry(
        reader,
        entry,
        record,
    )

    assert record_changed is True
    assert message_was_edited is True
    edit_payload = mock_edit_sent_webhook_message.call_args.kwargs["payload"]
    assert isinstance(edit_payload["embeds"], list)
    assert edit_payload["embeds"][0]["image"] == previous_image
    assert isinstance(updated_record["payload"], dict)
    updated_payload = cast("JsonObject", updated_record["payload"])
    updated_embeds = cast("list[JsonObject]", updated_payload["embeds"])
    assert updated_embeds[0]["image"] == previous_image
    assert updated_record["payload_hash"] == feeds.hash_webhook_payload(updated_payload)


@patch("discord_rss_bot.feeds.edit_sent_webhook_message")
@patch("discord_rss_bot.feeds.create_webhook_for_entry")
def test_update_sent_webhook_record_skips_edit_when_preserved_image_keeps_payload_unchanged(
    mock_create_webhook_for_entry: MagicMock,
    mock_edit_sent_webhook_message: MagicMock,
) -> None:
    previous_image: JsonObject = {
        "url": "https://example.com/original-image.jpg",
        "proxy_url": None,
        "height": None,
        "width": None,
    }
    old_payload: JsonObject = {
        "content": "",
        "embeds": [{"description": "Same summary", "image": previous_image, "thumbnail": None}],
        "attachments": [],
    }
    record: feeds.SentWebhookRecord = {
        "feed_url": "https://example.com/feed.xml",
        "entry_id": "entry-5",
        "webhook_url": "https://discord.com/api/webhooks/123/abc",
        "message_id": "message-5",
        "payload": old_payload,
        "payload_hash": feeds.hash_webhook_payload(old_payload),
        "update_count": 0,
    }

    entry = MagicMock()
    entry.id = "entry-5"

    reader = MagicMock()
    webhook = MagicMock()
    webhook.json = {
        "content": "",
        "embeds": [{"description": "Same summary", "image": None, "thumbnail": None}],
        "attachments": [],
    }
    mock_create_webhook_for_entry.return_value = (webhook, "embed")

    updated_record, record_changed, message_was_edited = feeds.update_sent_webhook_record_for_entry(
        reader,
        entry,
        record,
    )

    assert updated_record == record
    assert record_changed is False
    assert message_was_edited is False
    mock_edit_sent_webhook_message.assert_not_called()


@patch("discord_rss_bot.feeds.edit_sent_webhook_message")
@patch("discord_rss_bot.feeds.create_webhook_for_entry")
def test_update_sent_webhook_record_backfills_missing_payload_hash_without_editing_discord(
    mock_create_webhook_for_entry: MagicMock,
    mock_edit_sent_webhook_message: MagicMock,
) -> None:
    old_payload: JsonObject = {
        "content": "",
        "embeds": [{"description": "Same summary", "image": None, "thumbnail": None}],
        "attachments": [],
    }
    record: feeds.SentWebhookRecord = {
        "feed_url": "https://example.com/feed.xml",
        "entry_id": "entry-6",
        "webhook_url": "https://discord.com/api/webhooks/123/abc",
        "message_id": "message-6",
        "payload": old_payload,
        "update_count": 0,
    }

    entry = MagicMock()
    entry.id = "entry-6"

    reader = MagicMock()
    webhook = MagicMock()
    webhook.json = old_payload
    mock_create_webhook_for_entry.return_value = (webhook, "embed")

    updated_record, record_changed, message_was_edited = feeds.update_sent_webhook_record_for_entry(
        reader,
        entry,
        record,
    )

    assert record_changed is True
    assert message_was_edited is False
    assert updated_record["payload_hash"] == feeds.hash_webhook_payload(old_payload)
    mock_edit_sent_webhook_message.assert_not_called()


def test_update_feeds_and_collect_modified_entries_only_returns_modified_entries() -> None:
    class StubReader:
        def __init__(self) -> None:
            self.after_entry_update_hooks = []

        def update_feeds(self, *, scheduled: bool, workers: int) -> None:
            assert scheduled is True
            assert workers == 1
            new_entry = MagicMock()
            new_entry.feed_url = "https://example.com/feed.xml"
            new_entry.id = "new"
            modified_entry = MagicMock()
            modified_entry.feed_url = "https://example.com/feed.xml"
            modified_entry.id = "modified"
            for hook in list(self.after_entry_update_hooks):
                hook(self, new_entry, feeds.EntryUpdateStatus.NEW)
                hook(self, modified_entry, feeds.EntryUpdateStatus.MODIFIED)

    reader = StubReader()

    modified_entries: list[tuple[str, str]] = feeds.update_feeds_and_collect_modified_entries(
        reader,  # pyright: ignore[reportArgumentType]
        scheduled=True,
        workers=1,
    )

    assert modified_entries == [("https://example.com/feed.xml", "modified")]
    assert reader.after_entry_update_hooks == []
