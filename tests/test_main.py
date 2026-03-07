from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from discord_rss_bot.main import app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from httpx import Response

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
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})

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
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get("/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})

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
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})

    # Remove the feed.
    response: Response = client.post(url="/remove", data={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to remove feed: {response.text}"

    # Check that the feed was removed.
    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert feed_url not in response.text, f"Feed found in /: {response.text}"


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
