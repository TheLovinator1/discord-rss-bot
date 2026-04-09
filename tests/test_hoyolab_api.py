from __future__ import annotations

import json
import typing
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests

from discord_rss_bot.hoyolab_api import create_hoyolab_webhook
from discord_rss_bot.hoyolab_api import extract_post_id_from_hoyolab_url
from discord_rss_bot.hoyolab_api import fetch_hoyolab_post
from discord_rss_bot.hoyolab_api import is_c3kay_feed

if typing.TYPE_CHECKING:
    from reader import Entry


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


def make_entry(link: str | None = "https://www.hoyolab.com/article/38588239") -> SimpleNamespace:
    feed: SimpleNamespace = SimpleNamespace(url="https://feeds.c3kay.de/hoyolab.xml")
    return SimpleNamespace(
        id="entry-123",
        link=link,
        feed=feed,
    )


class TestIsC3KayFeed:
    def test_true_for_c3kay_feed(self) -> None:
        assert is_c3kay_feed("https://feeds.c3kay.de/rss") is True

    def test_false_for_non_c3kay_feed(self) -> None:
        assert is_c3kay_feed("https://example.com/rss") is False


class TestFetchHoyolabPost:
    @patch("discord_rss_bot.hoyolab_api.requests.get")
    def test_returns_none_for_empty_post_id(self, mock_get: MagicMock) -> None:
        assert fetch_hoyolab_post("") is None
        mock_get.assert_not_called()

    @patch("discord_rss_bot.hoyolab_api.requests.get")
    def test_returns_post_data_for_success_response(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "retcode": 0,
            "data": {
                "post": {
                    "post_id": "38588239",
                    "subject": "Event",
                },
            },
        }
        mock_get.return_value = mock_response

        result = fetch_hoyolab_post("38588239")

        assert result == {"post_id": "38588239", "subject": "Event"}
        assert mock_get.call_args.args[0].endswith("post_id=38588239")

    @patch("discord_rss_bot.hoyolab_api.logger")
    @patch("discord_rss_bot.hoyolab_api.requests.get")
    def test_returns_none_and_logs_warning_for_non_success_payload(
        self,
        mock_get: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "bad payload"
        mock_response.json.return_value = {
            "retcode": -1,
            "data": {},
        }
        mock_get.return_value = mock_response

        result = fetch_hoyolab_post("38588239")

        assert result is None
        mock_logger.warning.assert_called_once()

    @patch("discord_rss_bot.hoyolab_api.logger")
    @patch("discord_rss_bot.hoyolab_api.requests.get")
    def test_returns_none_and_logs_exception_on_request_error(
        self,
        mock_get: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_get.side_effect = requests.RequestException("network issue")

        result = fetch_hoyolab_post("38588239")

        assert result is None
        mock_logger.exception.assert_called_once()


class TestCreateHoyolabWebhook:
    @patch("discord_rss_bot.hoyolab_api.requests.get")
    @patch("discord_rss_bot.hoyolab_api.DiscordEmbed")
    @patch("discord_rss_bot.hoyolab_api.DiscordWebhook")
    def test_builds_embed_webhook_with_full_post_data(
        self,
        mock_webhook_cls: MagicMock,
        mock_embed_cls: MagicMock,
        mock_requests_get: MagicMock,
    ) -> None:
        webhook_instance = MagicMock()
        embed_instance = MagicMock()
        mock_webhook_cls.return_value = webhook_instance
        mock_embed_cls.return_value = embed_instance

        video_response = MagicMock()
        video_response.ok = True
        video_response.content = b"video-bytes"
        mock_requests_get.return_value = video_response

        post_data = {
            "post": {
                "subject": "Update 4.0",
                "content": json.dumps({"describe": "Patch notes"}),
                "desc": "fallback description",
                "structured_content": json.dumps(
                    [{"insert": {"video": "https://www.youtube.com/embed/abc123_XY"}}],
                ),
                "event_start_date": "1712000000",
                "event_end_date": "1712600000",
                "created_at": "1711000000",
            },
            "image_list": [{"url": "https://img.example.com/hero.jpg", "height": 1080, "width": 1920}],
            "video": {"url": "https://cdn.example.com/video.mp4"},
            "game": {"color": "#11AAFF"},
            "user": {"nickname": "Paimon", "avatar_url": "https://img.example.com/avatar.jpg"},
            "classification": {"name": "Official"},
        }

        entry = make_entry(link=None)
        entry = typing.cast("Entry", entry)
        webhook = create_hoyolab_webhook("https://discord.test/webhook", entry, post_data)

        assert webhook is webhook_instance
        mock_webhook_cls.assert_called_once_with(url="https://discord.test/webhook", rate_limit_retry=True)

        embed_instance.set_title.assert_called_once_with("Update 4.0")
        embed_instance.set_url.assert_called_once_with("https://feeds.c3kay.de/hoyolab.xml")
        embed_instance.set_image.assert_called_once_with(
            url="https://img.example.com/hero.jpg",
            height=1080,
            width=1920,
        )
        embed_instance.set_color.assert_called_once_with("11AAFF")
        embed_instance.set_footer.assert_called_once_with(text="Official")
        embed_instance.add_embed_field.assert_any_call(name="Start", value="<t:1712000000:R>")
        embed_instance.add_embed_field.assert_any_call(name="End", value="<t:1712600000:R>")
        embed_instance.set_timestamp.assert_called_once_with(timestamp="1711000000")

        webhook_instance.add_file.assert_called_once_with(file=b"video-bytes", filename="entry-123.mp4")
        webhook_instance.add_embed.assert_called_once_with(embed_instance)
        assert webhook_instance.content == "https://www.youtube.com/watch?v=abc123_XY"
        webhook_instance.remove_embeds.assert_called_once()

    @patch("discord_rss_bot.hoyolab_api.requests.get")
    @patch("discord_rss_bot.hoyolab_api.DiscordEmbed")
    @patch("discord_rss_bot.hoyolab_api.DiscordWebhook")
    def test_handles_invalid_structured_content_without_removing_embeds(
        self,
        mock_webhook_cls: MagicMock,
        mock_embed_cls: MagicMock,
        mock_requests_get: MagicMock,
    ) -> None:
        webhook_instance = MagicMock()
        embed_instance = MagicMock()
        mock_webhook_cls.return_value = webhook_instance
        mock_embed_cls.return_value = embed_instance
        mock_requests_get.return_value = MagicMock(ok=False)

        post_data = {
            "post": {
                "subject": "News",
                "content": "{}",
                "structured_content": "not-json",
            },
        }

        entry = make_entry()
        entry = typing.cast("Entry", entry)
        webhook = create_hoyolab_webhook("https://discord.test/webhook", entry, post_data)

        assert webhook is webhook_instance
        webhook_instance.remove_embeds.assert_not_called()


def test_extract_post_id_with_querystring() -> None:
    url = "https://www.hoyolab.com/article/38588239?utm_source=feed"
    assert extract_post_id_from_hoyolab_url(url) == "38588239"


def test_extract_post_id_non_string_input_returns_none() -> None:
    assert extract_post_id_from_hoyolab_url(None) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://feeds.c3kay.de/rss", True),
        ("https://www.hoyolab.com/feed", False),
    ],
)
def test_is_c3kay_feed_parametrized(*, url: str, expected: bool) -> None:
    assert is_c3kay_feed(url) is expected
