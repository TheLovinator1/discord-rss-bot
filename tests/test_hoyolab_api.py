from __future__ import annotations

from discord_rss_bot.hoyolab_api import extract_post_id_from_hoyolab_url


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
