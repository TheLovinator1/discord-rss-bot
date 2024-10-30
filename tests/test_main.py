import urllib.parse
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from discord_rss_bot.main import app

if TYPE_CHECKING:
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
    assert feed_url in response.text, f"Feed not found in /: {response.text}"

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
    assert feed_url in response.text, f"Feed not found in /: {response.text}"


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
    assert feed_url in response.text, f"Feed not found in /: {response.text}"

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
    assert feed_url in response.text, f"Feed not found in /: {response.text}"


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
    assert feed_url in response.text, f"Feed not found in /: {response.text}"


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
