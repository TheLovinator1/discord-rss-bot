from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from discord_rss_bot.main import app

if TYPE_CHECKING:
    from httpx import Response

client: TestClient = TestClient(app)
webhook_name: str = "Test Webhook for Update Interval"
webhook_url: str = "https://discord.com/api/webhooks/1234567890/test_update_interval"
feed_url: str = "https://lovinator.space/rss_test.xml"


def test_global_update_interval() -> None:
    """Test setting the global update interval."""
    # Set global update interval to 30 minutes
    response: Response = client.post("/set_global_update_interval", data={"interval_minutes": "30"})
    assert response.status_code == 200, f"Failed to set global interval: {response.text}"

    # Check that the settings page shows the new interval
    response = client.get("/settings")
    assert response.status_code == 200, f"Failed to get settings page: {response.text}"
    assert "30" in response.text, "Global interval not updated on settings page"


def test_per_feed_update_interval() -> None:
    """Test setting per-feed update interval."""
    # Clean up any existing feed/webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    client.post(url="/remove", data={"feed_url": feed_url})

    # Add webhook and feed
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Set feed-specific update interval to 15 minutes
    response = client.post("/set_update_interval", data={"feed_url": feed_url, "interval_minutes": "15"})
    assert response.status_code == 200, f"Failed to set feed interval: {response.text}"

    # Check that the feed page shows the custom interval
    encoded_url = urllib.parse.quote(feed_url)
    response = client.get(f"/feed?feed_url={encoded_url}")
    assert response.status_code == 200, f"Failed to get feed page: {response.text}"
    assert "15" in response.text, "Feed interval not displayed on feed page"
    assert "Custom" in response.text, "Custom badge not shown for feed-specific interval"


def test_reset_feed_update_interval() -> None:
    """Test resetting feed update interval to global default."""
    # Ensure feed/webhook setup exists regardless of test order
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    client.post(url="/remove", data={"feed_url": feed_url})

    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # First set a custom interval
    response = client.post("/set_update_interval", data={"feed_url": feed_url, "interval_minutes": "15"})
    assert response.status_code == 200, f"Failed to set feed interval: {response.text}"

    # Reset to global default
    response = client.post("/reset_update_interval", data={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to reset feed interval: {response.text}"

    # Check that the feed page shows global default
    encoded_url = urllib.parse.quote(feed_url)
    response = client.get(f"/feed?feed_url={encoded_url}")
    assert response.status_code == 200, f"Failed to get feed page: {response.text}"
    assert "Using global default" in response.text, "Global default badge not shown after reset"


def test_update_interval_validation() -> None:
    """Test that update interval validation works."""
    # Try to set an interval below minimum (should be clamped to 1)
    response: Response = client.post("/set_global_update_interval", data={"interval_minutes": "0"})
    assert response.status_code == 200, f"Failed to handle minimum interval: {response.text}"

    # Try to set an interval above maximum (should be clamped to 10080)
    response = client.post("/set_global_update_interval", data={"interval_minutes": "20000"})
    assert response.status_code == 200, f"Failed to handle maximum interval: {response.text}"

    # Clean up
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
