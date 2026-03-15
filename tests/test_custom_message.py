from __future__ import annotations

import typing
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from discord_rss_bot.custom_message import CustomEmbed
from discord_rss_bot.custom_message import format_entry_html_for_discord
from discord_rss_bot.custom_message import replace_tags_in_embed
from discord_rss_bot.custom_message import replace_tags_in_text_message

if typing.TYPE_CHECKING:
    from reader import Entry

# https://docs.discord.com/developers/reference#message-formatting
TIMESTAMP_FORMATS: tuple[str, ...] = (
    "<t:1773461490>",
    "<t:1773461490:F>",
    "<t:1773461490:f>",
    "<t:1773461490:D>",
    "<t:1773461490:d>",
    "<t:1773461490:t>",
    "<t:1773461490:T>",
    "<t:1773461490:R>",
    "<t:1773461490:s>",
    "<t:1773461490:S>",
)


def make_feed() -> SimpleNamespace:
    return SimpleNamespace(
        added=None,
        author="Feed Author",
        last_exception=None,
        last_updated=None,
        link="https://example.com/feed",
        subtitle="",
        title="Example Feed",
        updated=None,
        updates_enabled=True,
        url="https://example.com/feed.xml",
        user_title="",
        version="atom10",
    )


def make_entry(summary: str) -> SimpleNamespace:
    feed: SimpleNamespace = make_feed()
    return SimpleNamespace(
        added=None,
        author="Entry Author",
        content=[],
        feed=feed,
        feed_url=feed.url,
        id="entry-1",
        important=False,
        link="https://example.com/entry-1",
        published=None,
        read=False,
        read_modified=None,
        summary=summary,
        title="Entry Title",
        updated=None,
    )


@pytest.mark.parametrize("timestamp_tag", TIMESTAMP_FORMATS)
def test_format_entry_html_for_discord_preserves_timestamp_tags(timestamp_tag: str) -> None:
    escaped_timestamp_tag: str = timestamp_tag.replace("<", "&lt;").replace(">", "&gt;")
    html_summary: str = f"<p>Starts: 2026-03-13 23:30 UTC ({escaped_timestamp_tag})</p>"

    rendered: str = format_entry_html_for_discord(html_summary)

    assert timestamp_tag in rendered
    assert "DISCORDTIMESTAMPPLACEHOLDER" not in rendered


def test_format_entry_html_for_discord_empty_text_returns_empty_string() -> None:
    rendered: str = format_entry_html_for_discord("")
    assert not rendered


def test_format_entry_html_for_discord_cleans_markdownified_https_link_text() -> None:
    html_summary: str = "[https://example.com](https://example.com)"

    rendered: str = format_entry_html_for_discord(html_summary)

    assert "[example.com](https://example.com)" in rendered
    assert "[https://example.com]" not in rendered


def test_format_entry_html_for_discord_does_not_preserve_invalid_timestamp_style() -> None:
    invalid_timestamp: str = "<t:1773461490:Z>"
    html_summary: str = f"<p>Invalid style ({invalid_timestamp.replace('<', '&lt;').replace('>', '&gt;')})</p>"

    rendered: str = format_entry_html_for_discord(html_summary)

    assert invalid_timestamp not in rendered


@patch("discord_rss_bot.custom_message.get_custom_message")
def test_replace_tags_in_text_message_preserves_timestamp_tags(
    mock_get_custom_message: MagicMock,
) -> None:
    mock_reader = MagicMock()
    mock_get_custom_message.return_value = "{{entry_summary}}"
    summary_parts: list[str] = [
        f"<p>Format {index}: ({timestamp_tag.replace('<', '&lt;').replace('>', '&gt;')})</p>"
        for index, timestamp_tag in enumerate(TIMESTAMP_FORMATS, start=1)
    ]
    entry_ns: SimpleNamespace = make_entry("".join(summary_parts))

    entry: Entry = typing.cast("Entry", entry_ns)
    rendered: str = replace_tags_in_text_message(entry, reader=mock_reader)

    for timestamp_tag in TIMESTAMP_FORMATS:
        assert timestamp_tag in rendered


@patch("discord_rss_bot.custom_message.get_embed")
def test_replace_tags_in_embed_preserves_timestamp_tags(
    mock_get_embed: MagicMock,
) -> None:
    mock_reader = MagicMock()
    mock_get_embed.return_value = CustomEmbed(description="{{entry_summary}}")
    summary_parts: list[str] = [
        f"<p>Format {index}: ({timestamp_tag.replace('<', '&lt;').replace('>', '&gt;')})</p>"
        for index, timestamp_tag in enumerate(TIMESTAMP_FORMATS, start=1)
    ]
    entry_ns: SimpleNamespace = make_entry("".join(summary_parts))

    entry: Entry = typing.cast("Entry", entry_ns)

    embed: CustomEmbed = replace_tags_in_embed(entry_ns.feed, entry, reader=mock_reader)

    for timestamp_tag in TIMESTAMP_FORMATS:
        assert timestamp_tag in embed.description
