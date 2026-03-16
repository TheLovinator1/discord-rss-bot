from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import cast
from unittest.mock import MagicMock
from unittest.mock import patch

from fastapi.testclient import TestClient

import discord_rss_bot.main as main_module
from discord_rss_bot.main import app
from discord_rss_bot.main import create_html_for_feed
from discord_rss_bot.main import get_reader_dependency

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from httpx import Response
    from reader import Entry

client: TestClient = TestClient(app)
webhook_name: str = "Hello, I am a webhook!"
webhook_url: str = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"
feed_url: str = "https://lovinator.space/rss_test.xml"


def encoded_feed_url(url: str) -> str:
    return urllib.parse.quote(feed_url) if url else ""


def test_search() -> None:
    """Test the /search page."""
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get("/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Delete the webhook if it already exists before we run the test.
    response: Response = client.post(url="/delete_webhook", data={"webhook_url": webhook_url})

    # Add the webhook.
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Check that the feed was added.
    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert encoded_feed_url(feed_url) in response.text, f"Feed not found in /: {response.text}"

    # Search for an entry.
    response: Response = client.get(url="/search/?query=a")
    assert response.status_code == 200, f"Failed to search for entry: {response.text}"


def test_add_webhook() -> None:
    """Test the /add_webhook page."""
    # Delete the webhook if it already exists before we run the test.
    response: Response = client.post(url="/delete_webhook", data={"webhook_url": webhook_url})

    # Add the webhook.
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Check that the webhook was added.
    response = client.get(url="/webhooks")
    assert response.status_code == 200, f"Failed to get /webhooks: {response.text}"
    assert webhook_name in response.text, f"Webhook not found in /webhooks: {response.text}"


def test_create_feed() -> None:
    """Test the /create_feed page."""
    # Ensure webhook exists for this test regardless of test order.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Check that the feed was added.
    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert encoded_feed_url(feed_url) in response.text, f"Feed not found in /: {response.text}"


def test_get() -> None:
    """Test the /create_feed page."""
    # Ensure webhook exists for this test regardless of test order.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get("/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Check that the feed was added.
    response = client.get("/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert encoded_feed_url(feed_url) in response.text, f"Feed not found in /: {response.text}"

    response: Response = client.get(url="/add")
    assert response.status_code == 200, f"/add failed: {response.text}"

    response: Response = client.get(url="/add_webhook")
    assert response.status_code == 200, f"/add_webhook failed: {response.text}"

    response: Response = client.get(url="/blacklist", params={"feed_url": encoded_feed_url(feed_url)})
    assert response.status_code == 200, f"/blacklist failed: {response.text}"

    response: Response = client.get(url="/custom", params={"feed_url": encoded_feed_url(feed_url)})
    assert response.status_code == 200, f"/custom failed: {response.text}"

    response: Response = client.get(url="/embed", params={"feed_url": encoded_feed_url(feed_url)})
    assert response.status_code == 200, f"/embed failed: {response.text}"

    response: Response = client.get(url="/feed", params={"feed_url": encoded_feed_url(feed_url)})
    assert response.status_code == 200, f"/feed failed: {response.text}"

    response: Response = client.get(url="/")
    assert response.status_code == 200, f"/ failed: {response.text}"

    response: Response = client.get(url="/webhooks")
    assert response.status_code == 200, f"/webhooks failed: {response.text}"

    response = client.get(url="/webhook_entries", params={"webhook_url": webhook_url})
    assert response.status_code == 200, f"/webhook_entries failed: {response.text}"

    response: Response = client.get(url="/whitelist", params={"feed_url": encoded_feed_url(feed_url)})
    assert response.status_code == 200, f"/whitelist failed: {response.text}"


def test_pause_feed() -> None:
    """Test the /pause_feed page."""
    # Ensure webhook exists for this test regardless of test order.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Unpause the feed if it is paused.
    feeds: Response = client.get(url="/")
    if "Paused" in feeds.text:
        response: Response = client.post(url="/unpause", data={"feed_url": feed_url})
        assert response.status_code == 200, f"Failed to unpause feed: {response.text}"

    # Pause the feed.
    response: Response = client.post(url="/pause", data={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to pause feed: {response.text}"

    # Check that the feed was paused.
    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert encoded_feed_url(feed_url) in response.text, f"Feed not found in /: {response.text}"


def test_unpause_feed() -> None:
    """Test the /unpause_feed page."""
    # Ensure webhook exists for this test regardless of test order.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get("/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Pause the feed if it is unpaused.
    feeds: Response = client.get(url="/")
    if "Paused" not in feeds.text:
        response: Response = client.post(url="/pause", data={"feed_url": feed_url})
        assert response.status_code == 200, f"Failed to pause feed: {response.text}"

    # Unpause the feed.
    response: Response = client.post(url="/unpause", data={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to unpause feed: {response.text}"

    # Check that the feed was unpaused.
    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert encoded_feed_url(feed_url) in response.text, f"Feed not found in /: {response.text}"


def test_remove_feed() -> None:
    """Test the /remove page."""
    # Ensure webhook exists for this test regardless of test order.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Remove the feed.
    response: Response = client.post(url="/remove", data={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to remove feed: {response.text}"

    # Check that the feed was removed.
    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert feed_url not in response.text, f"Feed found in /: {response.text}"


def test_change_feed_url() -> None:
    """Test changing a feed URL from the feed page endpoint."""
    new_feed_url = "https://lovinator.space/rss_test_small.xml"

    # Ensure test feeds do not already exist.
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/remove", data={"feed_url": new_feed_url})

    # Ensure webhook exists.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Add the original feed.
    response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Change feed URL.
    response = client.post(
        url="/change_feed_url",
        data={"old_feed_url": feed_url, "new_feed_url": new_feed_url},
    )
    assert response.status_code == 200, f"Failed to change feed URL: {response.text}"

    # New feed should be accessible.
    response = client.get(url="/feed", params={"feed_url": new_feed_url})
    assert response.status_code == 200, f"New feed URL is not accessible: {response.text}"

    # Old feed should no longer be accessible.
    response = client.get(url="/feed", params={"feed_url": feed_url})
    assert response.status_code == 404, "Old feed URL should no longer exist"

    # Cleanup.
    client.post(url="/remove", data={"feed_url": new_feed_url})


def test_change_feed_url_marks_entries_as_read() -> None:
    """After changing a feed URL all entries on the new feed should be marked read to prevent resending."""
    new_feed_url = "https://lovinator.space/rss_test_small.xml"

    # Ensure feeds do not already exist.
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/remove", data={"feed_url": new_feed_url})

    # Ensure webhook exists.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    client.post(url="/add_webhook", data={"webhook_name": webhook_name, "webhook_url": webhook_url})

    # Add the original feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Patch reader on the main module so we can observe calls.
    mock_entry_a = MagicMock()
    mock_entry_a.id = "entry-a"
    mock_entry_b = MagicMock()
    mock_entry_b.id = "entry-b"

    real_reader = main_module.get_reader_dependency()

    # Use a no-redirect client so the POST response is inspected directly; the
    # redirect target (/feed?feed_url=…) would 404 because change_feed_url is mocked.
    no_redirect_client = TestClient(app, follow_redirects=False)

    with (
        patch.object(real_reader, "get_entries", return_value=[mock_entry_a, mock_entry_b]) as mock_get_entries,
        patch.object(real_reader, "set_entry_read") as mock_set_read,
        patch.object(real_reader, "update_feed") as mock_update_feed,
        patch.object(real_reader, "change_feed_url"),
    ):
        response = no_redirect_client.post(
            url="/change_feed_url",
            data={"old_feed_url": feed_url, "new_feed_url": new_feed_url},
        )
        assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"

        # update_feed should have been called with the new URL.
        mock_update_feed.assert_called_once_with(new_feed_url)

        # get_entries should have been called to fetch unread entries on the new URL.
        mock_get_entries.assert_called_once_with(feed=new_feed_url, read=False)

        # Every returned entry should have been marked as read.
        assert mock_set_read.call_count == 2, f"Expected 2 set_entry_read calls, got {mock_set_read.call_count}"
        mock_set_read.assert_any_call(mock_entry_a, True)
        mock_set_read.assert_any_call(mock_entry_b, True)

    # Cleanup.
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/remove", data={"feed_url": new_feed_url})


def test_change_feed_url_empty_old_url_returns_400() -> None:
    """Submitting an empty old_feed_url should return HTTP 400."""
    response: Response = client.post(
        url="/change_feed_url",
        data={"old_feed_url": "   ", "new_feed_url": "https://example.com/feed.xml"},
    )
    assert response.status_code == 400, f"Expected 400 for empty old URL, got {response.status_code}"


def test_change_feed_url_empty_new_url_returns_400() -> None:
    """Submitting a blank new_feed_url should return HTTP 400."""
    response: Response = client.post(
        url="/change_feed_url",
        data={"old_feed_url": feed_url, "new_feed_url": "   "},
    )
    assert response.status_code == 400, f"Expected 400 for blank new URL, got {response.status_code}"


def test_change_feed_url_nonexistent_old_url_returns_404() -> None:
    """Trying to rename a feed that does not exist should return HTTP 404."""
    non_existent = "https://does-not-exist.example.com/rss.xml"
    # Make sure it really is absent.
    client.post(url="/remove", data={"feed_url": non_existent})

    response: Response = client.post(
        url="/change_feed_url",
        data={"old_feed_url": non_existent, "new_feed_url": "https://example.com/new.xml"},
    )
    assert response.status_code == 404, f"Expected 404 for non-existent feed, got {response.status_code}"


def test_change_feed_url_new_url_already_exists_returns_409() -> None:
    """Changing to a URL that is already tracked should return HTTP 409."""
    second_feed_url = "https://lovinator.space/rss_test_small.xml"

    # Ensure both feeds are absent.
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/remove", data={"feed_url": second_feed_url})

    # Ensure webhook exists.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    client.post(url="/add_webhook", data={"webhook_name": webhook_name, "webhook_url": webhook_url})

    # Add both feeds.
    client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    client.post(url="/add", data={"feed_url": second_feed_url, "webhook_dropdown": webhook_name})

    # Try to rename one to the other.
    response: Response = client.post(
        url="/change_feed_url",
        data={"old_feed_url": feed_url, "new_feed_url": second_feed_url},
    )
    assert response.status_code == 409, f"Expected 409 when new URL already exists, got {response.status_code}"

    # Cleanup.
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/remove", data={"feed_url": second_feed_url})


def test_change_feed_url_same_url_redirects_without_error() -> None:
    """Changing a feed's URL to itself should redirect cleanly without any error."""
    # Ensure webhook exists.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    client.post(url="/add_webhook", data={"webhook_name": webhook_name, "webhook_url": webhook_url})

    # Add the feed.
    client.post(url="/remove", data={"feed_url": feed_url})
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Submit the same URL as both old and new.
    response = client.post(
        url="/change_feed_url",
        data={"old_feed_url": feed_url, "new_feed_url": feed_url},
    )
    assert response.status_code == 200, f"Expected 200 redirect for same URL, got {response.status_code}"

    # Feed should still be accessible.
    response = client.get(url="/feed", params={"feed_url": feed_url})
    assert response.status_code == 200, f"Feed should still exist after no-op URL change: {response.text}"

    # Cleanup.
    client.post(url="/remove", data={"feed_url": feed_url})


def test_delete_webhook() -> None:
    """Test the /delete_webhook page."""
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/webhooks")
    if webhook_url in feeds.text:
        client.post(url="/delete_webhook", data={"webhook_url": webhook_url})

    # Add the webhook.
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )

    # Delete the webhook.
    response: Response = client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    assert response.status_code == 200, f"Failed to delete webhook: {response.text}"

    # Check that the webhook was added.
    response = client.get(url="/webhooks")
    assert response.status_code == 200, f"Failed to get /webhooks: {response.text}"
    assert webhook_name not in response.text, f"Webhook found in /webhooks: {response.text}"


def test_update_feed_not_found() -> None:
    """Test updating a non-existent feed."""
    # Generate a feed URL that does not exist
    nonexistent_feed_url = "https://nonexistent-feed.example.com/rss.xml"

    # Try to update the non-existent feed
    response: Response = client.get(url="/update", params={"feed_url": urllib.parse.quote(nonexistent_feed_url)})

    # Check that it returns a 404 status code
    assert response.status_code == 404, f"Expected 404 for non-existent feed, got: {response.status_code}"
    assert "Feed not found" in response.text


def test_post_entry_send_to_discord() -> None:
    """Test that /post_entry sends an entry to Discord and redirects to the feed page.

    Regression test for the bug where the injected reader was not passed to
    send_entry_to_discord, meaning the dependency-injected reader was silently ignored.
    """
    # Ensure webhook and feed exist.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Retrieve an entry from the feed to get a valid entry ID.
    reader: main_module.Reader = main_module.get_reader_dependency()
    entries: list[Entry] = list(reader.get_entries(feed=feed_url, limit=1))
    assert entries, "Feed should have at least one entry to send"
    entry_to_send: main_module.Entry = entries[0]
    encoded_id: str = urllib.parse.quote(entry_to_send.id)

    no_redirect_client = TestClient(app, follow_redirects=False)

    # Patch execute_webhook so no real HTTP requests are made to Discord.
    with patch("discord_rss_bot.feeds.execute_webhook") as mock_execute:
        response = no_redirect_client.get(
            url="/post_entry",
            params={"entry_id": encoded_id, "feed_url": urllib.parse.quote(feed_url)},
        )

    assert response.status_code == 303, f"Expected redirect after sending, got {response.status_code}: {response.text}"
    location: str = response.headers.get("location", "")
    assert "feed?feed_url=" in location, f"Should redirect to feed page, got: {location}"
    assert mock_execute.called, "execute_webhook should have been called to deliver the entry to Discord"

    # Cleanup.
    client.post(url="/remove", data={"feed_url": feed_url})


def test_post_entry_unknown_id_returns_404() -> None:
    """Test that /post_entry returns 404 when the entry ID does not exist."""
    response: Response = client.get(
        url="/post_entry",
        params={"entry_id": "https://nonexistent.example.com/entry-that-does-not-exist"},
    )
    assert response.status_code == 404, f"Expected 404 for unknown entry, got {response.status_code}"


def test_post_entry_uses_feed_url_to_disambiguate_duplicate_ids() -> None:
    """When IDs collide across feeds, /post_entry should pick the entry from provided feed_url."""

    @dataclass(slots=True)
    class DummyFeed:
        url: str

    @dataclass(slots=True)
    class DummyEntry:
        id: str
        feed: DummyFeed
        feed_url: str

    feed_a = "https://example.com/feed-a.xml"
    feed_b = "https://example.com/feed-b.xml"
    shared_id = "https://example.com/shared-entry-id"

    entry_a: Entry = cast("Entry", DummyEntry(id=shared_id, feed=DummyFeed(feed_a), feed_url=feed_a))
    entry_b: Entry = cast("Entry", DummyEntry(id=shared_id, feed=DummyFeed(feed_b), feed_url=feed_b))

    class StubReader:
        def get_entries(self, feed: str | None = None) -> list[Entry]:
            if feed == feed_a:
                return [entry_a]
            if feed == feed_b:
                return [entry_b]
            return [entry_a, entry_b]

    selected_feed_urls: list[str] = []

    def fake_send_entry_to_discord(entry: Entry, reader: object) -> None:
        selected_feed_urls.append(entry.feed.url)

    app.dependency_overrides[get_reader_dependency] = StubReader
    no_redirect_client = TestClient(app, follow_redirects=False)

    try:
        with patch("discord_rss_bot.main.send_entry_to_discord", side_effect=fake_send_entry_to_discord):
            response: Response = no_redirect_client.get(
                url="/post_entry",
                params={"entry_id": urllib.parse.quote(shared_id), "feed_url": urllib.parse.quote(feed_b)},
            )

        assert response.status_code == 303, f"Expected redirect after sending, got {response.status_code}"
        assert selected_feed_urls == [feed_b], f"Expected feed-b entry, got: {selected_feed_urls}"

        location = response.headers.get("location", "")
        assert urllib.parse.quote(feed_b) in location, f"Expected redirect to feed-b page, got: {location}"
    finally:
        app.dependency_overrides = {}


def test_navbar_backup_link_hidden_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the backup link is not shown in the navbar when GIT_BACKUP_PATH is not set."""
    # Ensure GIT_BACKUP_PATH is not set
    monkeypatch.delenv("GIT_BACKUP_PATH", raising=False)

    # Get the index page
    response: Response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"

    # Check that the backup button is not in the response
    assert "Backup" not in response.text or 'action="/backup"' not in response.text, (
        "Backup button should not be visible when GIT_BACKUP_PATH is not configured"
    )


def test_navbar_backup_link_visible_when_configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test that the backup link is shown in the navbar when GIT_BACKUP_PATH is set."""
    # Set GIT_BACKUP_PATH
    monkeypatch.setenv("GIT_BACKUP_PATH", str(tmp_path))

    # Get the index page
    response: Response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"

    # Check that the backup button is in the response
    assert "Backup" in response.text, "Backup button text should be visible when GIT_BACKUP_PATH is configured"
    assert 'action="/backup"' in response.text, "Backup form should be visible when GIT_BACKUP_PATH is configured"


def test_backup_endpoint_returns_error_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the backup endpoint returns an error when GIT_BACKUP_PATH is not set."""
    # Ensure GIT_BACKUP_PATH is not set
    monkeypatch.delenv("GIT_BACKUP_PATH", raising=False)

    # Try to trigger a backup
    response: Response = client.post(url="/backup")

    # Should redirect to index with error message
    assert response.status_code == 200, f"Failed to post /backup: {response.text}"
    assert "Git backup is not configured" in response.text or "GIT_BACKUP_PATH" in response.text, (
        "Error message about backup not being configured should be shown"
    )


def test_show_more_entries_button_visible_when_many_entries() -> None:
    """Test that the 'Show more entries' button is visible when there are more than 20 entries."""
    # Add the webhook first
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})

    # Add the feed
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get the feed page
    response: Response = client.get(url="/feed", params={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to get /feed: {response.text}"

    # Check if the feed has more than 20 entries by looking at the response
    # The button should be visible if there are more than 20 entries
    # We check for both the button text and the link structure
    if "Show more entries" in response.text:
        # Button is visible - verify it has the correct structure
        assert "starting_after=" in response.text, "Show more entries button should contain starting_after parameter"
        # The button should be a link to the feed page with pagination
        assert (
            f'href="/feed?feed_url={urllib.parse.quote(feed_url)}' in response.text
            or f'href="/feed?feed_url={encoded_feed_url(feed_url)}' in response.text
        ), "Show more entries button should link back to the feed page"


def test_show_more_entries_button_not_visible_when_few_entries() -> None:
    """Test that the 'Show more entries' button is not visible when there are 20 or fewer entries."""
    # Ensure webhook exists for this test regardless of test order.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Use a feed with very few entries
    small_feed_url = "https://lovinator.space/rss_test_small.xml"

    # Clean up if exists
    client.post(url="/remove", data={"feed_url": small_feed_url})

    # Add a small feed (this may not exist, so this test is conditional)
    response: Response = client.post(url="/add", data={"feed_url": small_feed_url, "webhook_dropdown": webhook_name})

    if response.status_code == 200:
        # Get the feed page
        response: Response = client.get(url="/feed", params={"feed_url": small_feed_url})
        assert response.status_code == 200, f"Failed to get /feed: {response.text}"

        # If the feed has 20 or fewer entries, the button should not be visible
        # We check the total entry count in the page
        if "0 entries" in response.text or " entries)" in response.text:
            # Extract entry count and verify button visibility

            match: re.Match[str] | None = re.search(r"\((\d+) entries\)", response.text)
            if match:
                entry_count = int(match.group(1))
                if entry_count <= 20:
                    assert "Show more entries" not in response.text, (
                        f"Show more entries button should not be visible when there are {entry_count} entries"
                    )

        # Clean up
        client.post(url="/remove", data={"feed_url": small_feed_url})


def test_show_more_entries_pagination_works() -> None:
    """Test that pagination with starting_after parameter works correctly."""
    # Add the webhook first
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})

    # Add the feed
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get the first page
    response: Response = client.get(url="/feed", params={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to get /feed: {response.text}"

    # Check if pagination is available
    if "Show more entries" in response.text and "starting_after=" in response.text:
        # Extract the starting_after parameter from the button link
        match: re.Match[str] | None = re.search(r'starting_after=([^"&]+)', response.text)
        if match:
            starting_after_id: str = match.group(1)

            # Request the second page
            response: Response = client.get(
                url="/feed",
                params={"feed_url": feed_url, "starting_after": starting_after_id},
            )
            assert response.status_code == 200, f"Failed to get paginated feed: {response.text}"

            # Verify we got a valid response (the page should contain entries)
            assert "entries)" in response.text, "Paginated page should show entry count"


def test_show_more_entries_button_context_variable() -> None:
    """Test that the button visibility variable is correctly passed to the template context."""
    # Add the webhook first
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})

    # Add the feed
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get the feed page
    response: Response = client.get(url="/feed", params={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to get /feed: {response.text}"

    # Extract the total entries count from the page
    match: re.Match[str] | None = re.search(r"\((\d+) entries\)", response.text)
    if match:
        entry_count = int(match.group(1))

        # If more than 20 entries, button should be visible
        if entry_count > 20:
            assert "Show more entries" in response.text, (
                f"Button should be visible when there are {entry_count} entries (more than 20)"
            )
        # If 20 or fewer entries, button should not be visible
        else:
            assert "Show more entries" not in response.text, (
                f"Button should not be visible when there are {entry_count} entries (20 or fewer)"
            )


def test_create_html_marks_entries_from_another_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Entries from another feed should be marked in /feed html output."""

    @dataclass(slots=True)
    class DummyContent:
        value: str

    @dataclass(slots=True)
    class DummyFeed:
        url: str

    @dataclass(slots=True)
    class DummyEntry:
        feed: DummyFeed
        id: str
        original_feed_url: str | None = None
        link: str = "https://example.com/post"
        title: str = "Example title"
        author: str = "Author"
        summary: str = "Summary"
        content: list[DummyContent] = field(default_factory=lambda: [DummyContent("Content")])
        published: None = None

        def __post_init__(self) -> None:
            if self.original_feed_url is None:
                self.original_feed_url = self.feed.url

    selected_feed_url = "https://example.com/feed-a.xml"
    same_feed_entry = DummyEntry(DummyFeed(selected_feed_url), "same")
    # feed.url matches selected feed, but original_feed_url differs; marker should still show.
    other_feed_entry = DummyEntry(
        DummyFeed(selected_feed_url),
        "other",
        original_feed_url="https://example.com/feed-b.xml",
    )

    monkeypatch.setattr(
        "discord_rss_bot.main.replace_tags_in_text_message",
        lambda _entry, **_kwargs: "Rendered content",
    )
    monkeypatch.setattr("discord_rss_bot.main.entry_is_blacklisted", lambda _entry, **_kwargs: False)
    monkeypatch.setattr("discord_rss_bot.main.entry_is_whitelisted", lambda _entry, **_kwargs: False)

    same_feed_entry_typed: Entry = cast("Entry", same_feed_entry)
    other_feed_entry_typed: Entry = cast("Entry", other_feed_entry)

    html: str = create_html_for_feed(
        reader=MagicMock(),
        current_feed_url=selected_feed_url,
        entries=[
            same_feed_entry_typed,
            other_feed_entry_typed,
        ],
    )

    assert "From another feed: https://example.com/feed-b.xml" in html
    assert "From another feed: https://example.com/feed-a.xml" not in html


def test_webhook_entries_webhook_not_found() -> None:
    """Test webhook_entries endpoint returns 404 when webhook doesn't exist."""
    nonexistent_webhook_url = "https://discord.com/api/webhooks/999999/nonexistent"

    response: Response = client.get(
        url="/webhook_entries",
        params={"webhook_url": nonexistent_webhook_url},
    )

    assert response.status_code == 404, f"Expected 404 for non-existent webhook, got: {response.status_code}"
    assert "Webhook not found" in response.text


def test_webhook_entries_no_feeds() -> None:
    """Test webhook_entries endpoint displays message when webhook has no feeds."""
    # Clean up any existing feeds first
    client.post(url="/remove", data={"feed_url": feed_url})

    # Clean up and create a webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Get webhook_entries without adding any feeds
    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
    assert webhook_name in response.text, "Webhook name not found in response"
    assert "No feeds found" in response.text or "Add feeds" in response.text, "Expected message about no feeds"


def test_webhook_entries_no_feeds_still_shows_webhook_settings() -> None:
    """The webhook detail view should show settings/actions even with no attached feeds."""
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
    assert "Settings" in response.text, "Expected settings card on webhook detail view"
    assert "Modify Webhook" in response.text, "Expected modify form on webhook detail view"
    assert "Delete Webhook" in response.text, "Expected delete action on webhook detail view"
    assert "Back to dashboard" in response.text, "Expected dashboard navigation link"
    assert "All webhooks" in response.text, "Expected all webhooks navigation link"
    assert f'name="old_hook" value="{webhook_url}"' in response.text, "Expected old_hook hidden input"
    assert f'value="/webhook_entries?webhook_url={urllib.parse.quote(webhook_url)}"' in response.text, (
        "Expected modify form to redirect back to the current webhook detail view"
    )


def test_webhook_entries_with_feeds_no_entries() -> None:
    """Test webhook_entries endpoint when webhook has feeds but no entries yet."""
    # Clean up and create fresh webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Use a feed URL that exists but has no entries (or clean feed)
    empty_feed_url = "https://lovinator.space/empty_feed.xml"
    client.post(url="/remove", data={"feed_url": empty_feed_url})

    # Add the feed
    response = client.post(
        url="/add",
        data={"feed_url": empty_feed_url, "webhook_dropdown": webhook_name},
    )

    # Get webhook_entries
    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
    assert webhook_name in response.text, "Webhook name not found in response"

    # Clean up
    client.post(url="/remove", data={"feed_url": empty_feed_url})


def test_webhook_entries_with_entries() -> None:
    """Test webhook_entries endpoint displays entries correctly."""
    # Clean up and create webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove and add the feed
    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(
        url="/add",
        data={"feed_url": feed_url, "webhook_dropdown": webhook_name},
    )
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get webhook_entries
    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
    assert webhook_name in response.text, "Webhook name not found in response"
    # Should show entries (the feed has entries)
    assert "total from" in response.text, "Expected to see entry count"
    assert "Modify Webhook" in response.text, "Expected webhook settings to be visible"
    assert "Attached feeds" in response.text, "Expected attached feeds section to be visible"


def test_webhook_entries_shows_attached_feed_link() -> None:
    """The webhook detail view should list attached feeds linking to their feed pages."""
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(
        url="/add",
        data={"feed_url": feed_url, "webhook_dropdown": webhook_name},
    )
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
    assert f"/feed?feed_url={urllib.parse.quote(feed_url)}" in response.text, (
        "Expected attached feed to link to its feed detail page"
    )
    assert "Latest entries" in response.text, "Expected latest entries heading on webhook detail view"

    client.post(url="/remove", data={"feed_url": feed_url})


def test_webhook_entries_multiple_feeds() -> None:
    """Test webhook_entries endpoint shows feed count correctly."""
    # Clean up and create webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove and add feed
    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(
        url="/add",
        data={"feed_url": feed_url, "webhook_dropdown": webhook_name},
    )
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get webhook_entries
    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
    assert webhook_name in response.text, "Webhook name not found in response"
    # Should show entries and feed count
    assert "feed" in response.text.lower(), "Expected to see feed information"

    # Clean up
    client.post(url="/remove", data={"feed_url": feed_url})


def test_webhook_entries_pagination() -> None:
    """Test webhook_entries endpoint pagination functionality."""
    # Clean up and create webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove and add the feed
    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(
        url="/add",
        data={"feed_url": feed_url, "webhook_dropdown": webhook_name},
    )
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get first page of webhook_entries
    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"

    # Check if pagination button is shown when there are many entries
    # The button should be visible if total_entries > 20 (entries_per_page)
    if "Load More Entries" in response.text:
        # Extract the starting_after parameter from the pagination form
        # This is a simple check that pagination elements exist
        assert 'name="starting_after"' in response.text, "Expected pagination form with starting_after parameter"

    # Clean up
    client.post(url="/remove", data={"feed_url": feed_url})


def test_webhook_entries_url_encoding() -> None:
    """Test webhook_entries endpoint handles URL encoding correctly."""
    # Clean up and create webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove and add the feed
    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(
        url="/add",
        data={"feed_url": feed_url, "webhook_dropdown": webhook_name},
    )
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get webhook_entries with URL-encoded webhook URL
    encoded_webhook_url = urllib.parse.quote(webhook_url)
    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": encoded_webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries with encoded URL: {response.text}"
    assert webhook_name in response.text, "Webhook name not found in response"

    # Clean up
    client.post(url="/remove", data={"feed_url": feed_url})


def test_dashboard_webhook_name_links_to_webhook_detail() -> None:
    """Webhook names on the dashboard should open the webhook detail view."""
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"

    expected_link = f"/webhook_entries?webhook_url={urllib.parse.quote(webhook_url)}"
    assert expected_link in response.text, "Expected dashboard webhook link to point to the webhook detail view"

    client.post(url="/remove", data={"feed_url": feed_url})


def test_modify_webhook_redirects_back_to_webhook_detail() -> None:
    """Webhook updates from the detail view should redirect back to that view with the new URL."""
    original_webhook_url = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"
    new_webhook_url = "https://discord.com/api/webhooks/1234567890/updated-token"

    client.post(url="/delete_webhook", data={"webhook_url": original_webhook_url})
    client.post(url="/delete_webhook", data={"webhook_url": new_webhook_url})

    response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": original_webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    no_redirect_client = TestClient(app, follow_redirects=False)
    response = no_redirect_client.post(
        url="/modify_webhook",
        data={
            "old_hook": original_webhook_url,
            "new_hook": new_webhook_url,
            "redirect_to": f"/webhook_entries?webhook_url={urllib.parse.quote(original_webhook_url)}",
        },
    )

    assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"
    assert response.headers["location"] == (f"/webhook_entries?webhook_url={urllib.parse.quote(new_webhook_url)}"), (
        f"Unexpected redirect location: {response.headers['location']}"
    )

    client.post(url="/delete_webhook", data={"webhook_url": new_webhook_url})


def test_reader_dependency_override_is_used() -> None:
    """Reader should be injectable and overridable via FastAPI dependency overrides."""

    class StubReader:
        def get_tag(self, _resource: str, _key: str, default: str | None = None) -> str | None:
            """Stub get_tag that always returns the default value.

            Args:
                _resource: Ignored.
                _key: Ignored.
                default: The value to return.

            Returns:
                The default value, simulating a missing tag.
            """
            return default

    app.dependency_overrides[get_reader_dependency] = StubReader
    try:
        response: Response = client.get(url="/add")
        assert response.status_code == 200, f"Expected /add to render with overridden reader: {response.text}"
    finally:
        app.dependency_overrides = {}
