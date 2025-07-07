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
    def test_sets_description_from_post_desc(self) -> None:
        """Test that description is set from post.desc when available."""
        # Mock entry
        mock_entry = Mock()
        mock_entry.link = "https://www.hoyolab.com/article/123"
        mock_entry.feed.url = "https://feeds.c3kay.de/test"
        mock_entry.id = "test-123"
        
        # Test data with description
        post_data = {
            "post": {
                "subject": "Test Subject",
                "content": "{}",
                "desc": "Test description from post.desc"
            }
        }
        
        webhook = create_hoyolab_webhook("https://discord.com/api/webhooks/test", mock_entry, post_data)
        
        # Check that webhook has an embed with the description
        assert len(webhook.embeds) == 1
        embed = webhook.embeds[0]
        assert embed["description"] == "Test description from post.desc"
        assert embed["title"] == "Test Subject"
        assert embed["url"] == "https://www.hoyolab.com/article/123"
    
    def test_truncates_long_description(self) -> None:
        """Test that long descriptions are truncated to 2000 characters."""
        # Mock entry
        mock_entry = Mock()
        mock_entry.link = "https://www.hoyolab.com/article/123"
        mock_entry.feed.url = "https://feeds.c3kay.de/test"
        mock_entry.id = "test-123"
        
        # Test data with very long description
        long_desc = "a" * 2500  # 2500 characters
        post_data = {
            "post": {
                "subject": "Test Subject",
                "content": "{}",
                "desc": long_desc
            }
        }
        
        webhook = create_hoyolab_webhook("https://discord.com/api/webhooks/test", mock_entry, post_data)
        
        # Check that description is truncated
        assert len(webhook.embeds) == 1
        embed = webhook.embeds[0]
        assert embed["description"] == "a" * 2000 + "..."
        assert len(embed["description"]) == 2003  # 2000 + "..."
    
    def test_no_description_when_empty(self) -> None:
        """Test that no description is set when desc is empty."""
        # Mock entry
        mock_entry = Mock()
        mock_entry.link = "https://www.hoyolab.com/article/123"
        mock_entry.feed.url = "https://feeds.c3kay.de/test"
        mock_entry.id = "test-123"
        
        # Test data without description
        post_data = {
            "post": {
                "subject": "Test Subject",
                "content": "{}",
                "desc": ""
            }
        }
        
        webhook = create_hoyolab_webhook("https://discord.com/api/webhooks/test", mock_entry, post_data)
        
        # Check that no description is set
        assert len(webhook.embeds) == 1
        embed = webhook.embeds[0]
        assert embed["description"] is None
        assert embed["title"] == "Test Subject"
    
    def test_prefers_content_describe_over_post_desc(self) -> None:
        """Test that content.describe is preferred over post.desc."""
        # Mock entry
        mock_entry = Mock()
        mock_entry.link = "https://www.hoyolab.com/article/123"
        mock_entry.feed.url = "https://feeds.c3kay.de/test"
        mock_entry.id = "test-123"
        
        # Test data with both describe and desc
        post_data = {
            "post": {
                "subject": "Test Subject",
                "content": '{"describe": "Priority description from content"}',
                "desc": "Fallback description from post.desc"
            }
        }
        
        webhook = create_hoyolab_webhook("https://discord.com/api/webhooks/test", mock_entry, post_data)
        
        # Check that content.describe is used
        assert len(webhook.embeds) == 1
        embed = webhook.embeds[0]
        assert embed["description"] == "Priority description from content"
