from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import cast

from fastapi.testclient import TestClient

from discord_rss_bot.main import app
from discord_rss_bot.main import create_html_for_feed

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

    monkeypatch.setattr("discord_rss_bot.main.replace_tags_in_text_message", lambda _entry: "Rendered content")
    monkeypatch.setattr("discord_rss_bot.main.entry_is_blacklisted", lambda _entry: False)
    monkeypatch.setattr("discord_rss_bot.main.entry_is_whitelisted", lambda _entry: False)

    html = create_html_for_feed(cast("list[Entry]", [same_feed_entry, other_feed_entry]), selected_feed_url)

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
