from __future__ import annotations

from unittest.mock import Mock

from discord_rss_bot.hoyolab_api import create_hoyolab_webhook, extract_post_id_from_hoyolab_url


class TestExtractPostIdFromHoyolabUrl:
    def test_extract_post_id_from_article_url(self) -> None:
        """Test extracting post ID from a direct article URL."""
        test_cases: list[str] = [
            "https://www.hoyolab.com/article/38588239",
            "http://hoyolab.com/article/12345",
            "https://www.hoyolab.com/article/987654321/comments",
        ]

        expected_ids: list[str] = ["38588239", "12345", "987654321"]

        for url, expected_id in zip(test_cases, expected_ids, strict=False):
            assert extract_post_id_from_hoyolab_url(url) == expected_id

    def test_url_without_post_id(self) -> None:
        """Test with a URL that doesn't have a post ID."""
        test_cases: list[str] = [
            "https://www.hoyolab.com/community",
        ]

        for url in test_cases:
            assert extract_post_id_from_hoyolab_url(url) is None

    def test_edge_cases(self) -> None:
        """Test edge cases like None, empty string, and malformed URLs."""
        test_cases: list[str | None] = [
            None,
            "",
            "not_a_url",
            "http:/",  # Malformed URL
        ]

        for url in test_cases:
            assert extract_post_id_from_hoyolab_url(url) is None  # type: ignore


class TestCreateHoyolabWebhook:
    def test_create_webhook_with_topics(self) -> None:
        """Test creating a webhook with topics/tags."""
        # Mock entry
        entry = Mock()
        entry.link = "https://www.hoyolab.com/article/12345"
        entry.id = "12345"

        # Mock post data with topics
        post_data = {
            "post": {
                "subject": "Test Post",
                "content": "{}",
                "desc": "Test description",
                "created_at": "1234567890",
            },
            "topics": [
                {"id": 25010, "name": "zzzero"},
                {"id": 643504, "name": "Anby"},
                {"id": 1125550, "name": "Soldier 0 - Anby"},
            ],
        }

        webhook_url = "https://discord.com/api/webhooks/123/test"

        webhook = create_hoyolab_webhook(webhook_url, entry, post_data)

        # Check that the webhook was created
        assert webhook is not None
        assert webhook.url == webhook_url

        # Check that topics were added as tags
        embeds = webhook.embeds
        assert len(embeds) == 1

        embed = embeds[0]

        # Find the Tags field in the embed
        tags_field = None
        for field in embed.get("fields", []):
            if field.get("name") == "Tags":
                tags_field = field
                break

        assert tags_field is not None
        assert tags_field["value"] == "zzzero, Anby, Soldier 0 - Anby"

    def test_create_webhook_without_topics(self) -> None:
        """Test creating a webhook without topics."""
        # Mock entry
        entry = Mock()
        entry.link = "https://www.hoyolab.com/article/12345"
        entry.id = "12345"

        # Mock post data without topics
        post_data = {
            "post": {
                "subject": "Test Post",
                "content": "{}",
                "desc": "Test description",
                "created_at": "1234567890",
            },
        }

        webhook_url = "https://discord.com/api/webhooks/123/test"

        webhook = create_hoyolab_webhook(webhook_url, entry, post_data)

        # Check that the webhook was created
        assert webhook is not None
        assert webhook.url == webhook_url

        # Check that no Tags field was added
        embeds = webhook.embeds
        assert len(embeds) == 1

        embed = embeds[0]

        # Find the Tags field in the embed
        tags_field = None
        for field in embed.get("fields", []):
            if field.get("name") == "Tags":
                tags_field = field
                break

        assert tags_field is None

    def test_create_webhook_with_empty_topics(self) -> None:
        """Test creating a webhook with empty topics list."""
        # Mock entry
        entry = Mock()
        entry.link = "https://www.hoyolab.com/article/12345"
        entry.id = "12345"

        # Mock post data with empty topics
        post_data = {
            "post": {
                "subject": "Test Post",
                "content": "{}",
                "desc": "Test description",
                "created_at": "1234567890",
            },
            "topics": [],
        }

        webhook_url = "https://discord.com/api/webhooks/123/test"

        webhook = create_hoyolab_webhook(webhook_url, entry, post_data)

        # Check that the webhook was created
        assert webhook is not None
        assert webhook.url == webhook_url

        # Check that no Tags field was added
        embeds = webhook.embeds
        assert len(embeds) == 1

        embed = embeds[0]

        # Find the Tags field in the embed
        tags_field = None
        for field in embed.get("fields", []):
            if field.get("name") == "Tags":
                tags_field = field
                break

        assert tags_field is None
