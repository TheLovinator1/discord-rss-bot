from typing import TYPE_CHECKING, Literal

from fastapi.testclient import TestClient

from discord_rss_bot.main import app, encode_url

if TYPE_CHECKING:
    from httpx import Response

client: TestClient = TestClient(app)
webhook_name: str = "Hello, I am a webhook!"
webhook_url: str = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"
feed_url: str = "https://lovinator.space/rss_test.xml"
encoded_feed_url: str = encode_url(feed_url)


def test_search() -> None:
    """Test the /search page."""
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get("/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url})

    # Delete the webhook if it already exists before we run the test.
    response: Response = client.post(url="/delete_webhook", data={"webhook_url": webhook_url})

    # Add the webhook.
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200

    # Check that the feed was added.
    response = client.get(url="/")
    assert response.status_code == 200
    assert feed_url in response.text

    # Search for an entry.
    response: Response = client.get(url="/search/?query=a")
    assert response.status_code == 200


def test_encode_url() -> None:
    """Test the encode_url function."""
    before: Literal["https://www.google.com/"] = "https://www.google.com/"
    after: Literal["https%3A//www.google.com/"] = "https%3A//www.google.com/"
    assert encode_url(url_to_quote=before) == after


def test_add_webhook() -> None:
    """Test the /add_webhook page."""
    # Delete the webhook if it already exists before we run the test.
    response: Response = client.post(url="/delete_webhook", data={"webhook_url": webhook_url})

    # Add the webhook.
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200

    # Check that the webhook was added.
    response = client.get(url="/webhooks")
    assert response.status_code == 200
    assert webhook_name in response.text


def test_create_feed() -> None:
    """Test the /create_feed page."""
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200

    # Check that the feed was added.
    response = client.get(url="/")
    assert response.status_code == 200
    assert feed_url in response.text


def test_get() -> None:
    """Test the /create_feed page."""
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get("/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200

    # Check that the feed was added.
    response = client.get("/")
    assert response.status_code == 200
    assert feed_url in response.text

    response: Response = client.get(url="/add")
    assert response.status_code == 200

    response: Response = client.get(url="/add_webhook")
    assert response.status_code == 200

    response: Response = client.get(url="/blacklist", params={"feed_url": encoded_feed_url})
    assert response.status_code == 200

    response: Response = client.get(url="/custom", params={"feed_url": encoded_feed_url})
    assert response.status_code == 200

    response: Response = client.get(url="/embed", params={"feed_url": encoded_feed_url})
    assert response.status_code == 200

    response: Response = client.get(url="/feed", params={"feed_url": encoded_feed_url})
    assert response.status_code == 200

    response: Response = client.get(url="/feed_more", params={"feed_url": encoded_feed_url})
    assert response.status_code == 200

    response: Response = client.get(url="/")
    assert response.status_code == 200

    response: Response = client.get(url="/webhooks")
    assert response.status_code == 200

    response: Response = client.get(url="/whitelist", params={"feed_url": encoded_feed_url})
    assert response.status_code == 200


def test_pause_feed() -> None:
    """Test the /pause_feed page."""
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})

    # Unpause the feed if it is paused.
    feeds: Response = client.get(url="/")
    if "Paused" in feeds.text:
        response: Response = client.post(url="/unpause", data={"feed_url": feed_url})
        assert response.status_code == 200

    # Pause the feed.
    response: Response = client.post(url="/pause", data={"feed_url": feed_url})
    assert response.status_code == 200

    # Check that the feed was paused.
    response = client.get(url="/")
    assert response.status_code == 200
    assert feed_url in response.text


def test_unpause_feed() -> None:
    """Test the /unpause_feed page."""
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get("/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})

    # Pause the feed if it is unpaused.
    feeds: Response = client.get(url="/")
    if "Paused" not in feeds.text:
        response: Response = client.post(url="/pause", data={"feed_url": feed_url})
        assert response.status_code == 200

    # Unpause the feed.
    response: Response = client.post(url="/unpause", data={"feed_url": feed_url})
    assert response.status_code == 200

    # Check that the feed was unpaused.
    response = client.get(url="/")
    assert response.status_code == 200
    assert feed_url in response.text


def test_remove_feed() -> None:
    """Test the /remove page."""
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})

    # Remove the feed.
    response: Response = client.post(url="/remove", data={"feed_url": feed_url})
    assert response.status_code == 200

    # Check that the feed was removed.
    response = client.get(url="/")
    assert response.status_code == 200
    assert feed_url not in response.text


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
    assert response.status_code == 200

    # Check that the webhook was added.
    response = client.get(url="/webhooks")
    assert response.status_code == 200
    assert webhook_name not in response.text
