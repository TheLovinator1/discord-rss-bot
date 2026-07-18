from __future__ import annotations

import typing
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from discord_rss_bot.custom_message import CustomEmbed
from discord_rss_bot.custom_message import format_entry_html_for_discord
from discord_rss_bot.custom_message import get_custom_message
from discord_rss_bot.custom_message import get_embed
from discord_rss_bot.custom_message import get_embed_data
from discord_rss_bot.custom_message import get_first_image
from discord_rss_bot.custom_message import get_image_urls
from discord_rss_bot.custom_message import normalize_message_avatar_url
from discord_rss_bot.custom_message import normalize_message_username
from discord_rss_bot.custom_message import replace_tags_in_embed
from discord_rss_bot.custom_message import replace_tags_in_text_message
from discord_rss_bot.custom_message import save_embed
from discord_rss_bot.custom_message import try_to_replace

if typing.TYPE_CHECKING:
    from reader import Entry
    from reader.types import Feed

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
        authors_str="Entry Author",
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
        authors_str="Entry Author",
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


def test_try_to_replace_returns_original_message_when_replace_fails() -> None:
    rendered = try_to_replace(typing.cast("str", None), "{{tag}}", "value")
    assert rendered is None


@patch("discord_rss_bot.custom_message.get_custom_message")
def test_replace_tags_in_text_message_uses_last_content_item_and_unescapes_newline(
    mock_get_custom_message: MagicMock,
) -> None:
    mock_reader = MagicMock()
    mock_get_custom_message.return_value = "{{entry_content}}\\n{{entry_content_raw}}"
    entry_ns: SimpleNamespace = make_entry("<p>Summary</p>")
    entry_ns.content = [SimpleNamespace(value="<p>First content</p>"), SimpleNamespace(value="<p>Last content</p>")]

    entry: Entry = typing.cast("Entry", entry_ns)
    rendered: str = replace_tags_in_text_message(entry, reader=mock_reader)

    assert "Last content" in rendered
    assert "<p>First content</p>" in rendered
    assert "\\n" not in rendered
    assert "\n" in rendered


@patch("discord_rss_bot.custom_message.get_custom_message")
def test_replace_tags_in_text_message_skips_non_string_replacement_values(
    mock_get_custom_message: MagicMock,
) -> None:
    mock_reader = MagicMock()
    mock_get_custom_message.return_value = "{{entry_id}}"
    entry_ns: SimpleNamespace = make_entry("<p>Summary</p>")
    entry_ns.id = 123

    entry: Entry = typing.cast("Entry", entry_ns)
    rendered: str = replace_tags_in_text_message(entry, reader=mock_reader)

    assert rendered == "{{entry_id}}"


@patch("discord_rss_bot.custom_message.get_custom_message")
def test_replace_tags_in_text_message_uses_authors_str(mock_get_custom_message: MagicMock) -> None:
    mock_get_custom_message.return_value = "{{feed_author}} | {{entry_author}}"
    entry_ns: SimpleNamespace = make_entry("<p>Summary</p>")
    entry_ns.feed.author = "Legacy Feed Author"
    entry_ns.feed.authors_str = "Feed Author One, Feed Author Two"
    entry_ns.author = "Legacy Entry Author"
    entry_ns.authors_str = "Entry Author One, Entry Author Two"

    rendered: str = replace_tags_in_text_message(
        typing.cast("Entry", entry_ns),
        reader=MagicMock(),
    )

    assert rendered == "Feed Author One, Feed Author Two | Entry Author One, Entry Author Two"


@patch("discord_rss_bot.custom_message.get_embed")
def test_replace_tags_in_embed_uses_authors_str(mock_get_embed: MagicMock) -> None:
    mock_get_embed.return_value = CustomEmbed(description="{{feed_author}} | {{entry_author}}")
    entry_ns: SimpleNamespace = make_entry("<p>Summary</p>")
    entry_ns.feed.author = "Legacy Feed Author"
    entry_ns.feed.authors_str = "Feed Author One, Feed Author Two"
    entry_ns.author = "Legacy Entry Author"
    entry_ns.authors_str = "Entry Author One, Entry Author Two"

    embed: CustomEmbed = replace_tags_in_embed(
        entry_ns.feed,
        typing.cast("Entry", entry_ns),
        reader=MagicMock(),
    )

    assert embed.description == "Feed Author One, Feed Author Two | Entry Author One, Entry Author Two"


def test_get_first_image_prefers_content_image_over_summary_image() -> None:
    summary = '<p><img src="https://example.com/from-summary.jpg" /></p>'
    content = '<p><img src="https://example.com/from-content.jpg" /></p>'

    image = get_first_image(summary, content)

    assert image == "https://example.com/from-content.jpg"


def test_get_first_image_uses_summary_when_content_image_is_invalid() -> None:
    summary = '<p><img src="https://example.com/from-summary.jpg" /></p>'
    content = '<p><img src="javascript:alert(1)" /></p>'

    image = get_first_image(summary, content)

    assert image == "https://example.com/from-summary.jpg"


def test_get_image_urls_returns_all_valid_images_in_order_without_duplicates() -> None:
    summary = (
        '<p><img src="https://example.com/from-summary.jpg" /><img src="https://example.com/from-content-1.jpg" /></p>'
    )
    content = (
        '<p><img src="https://example.com/from-content-1.jpg" />'
        '<img src="javascript:alert(1)" />'
        '<img src="https://example.com/from-content-2.jpg" /></p>'
    )

    images = get_image_urls(summary, content)

    assert images == [
        "https://example.com/from-content-1.jpg",
        "https://example.com/from-content-2.jpg",
        "https://example.com/from-summary.jpg",
    ]


def test_get_image_urls_respects_limit() -> None:
    summary = '<img src="https://example.com/summary.jpg" />'
    content = '<img src="https://example.com/one.jpg" /><img src="https://example.com/two.jpg" />'

    images = get_image_urls(summary, content, limit=2)

    assert images == ["https://example.com/one.jpg", "https://example.com/two.jpg"]


def test_get_first_image_returns_empty_when_images_have_no_src() -> None:
    summary = "<p></p>"
    content = '<p><img alt="missing source" /></p>'

    image = get_first_image(summary, content)

    assert not image


def test_get_first_image_returns_empty_when_summary_image_url_is_invalid() -> None:
    summary = '<p><img src="javascript:alert(1)" /></p>'

    image = get_first_image(summary, content=None)

    assert not image


def test_get_first_image_returns_empty_when_summary_image_has_no_src() -> None:
    summary = '<p><img alt="missing source" /></p>'

    image = get_first_image(summary, content=None)

    assert not image


@patch("discord_rss_bot.custom_message.get_embed")
def test_replace_tags_in_embed_moves_title_to_author_name_when_required(
    mock_get_embed: MagicMock,
) -> None:
    mock_reader = MagicMock()
    mock_get_embed.return_value = CustomEmbed(
        title="{{entry_title}}",
        author_name="",
        author_url="https://example.com/author",
    )
    entry_ns: SimpleNamespace = make_entry("<p>Summary</p>")

    entry: Entry = typing.cast("Entry", entry_ns)
    embed: CustomEmbed = replace_tags_in_embed(entry_ns.feed, entry, reader=mock_reader)

    assert not embed.title
    assert embed.author_name == "Entry Title"


@patch("discord_rss_bot.custom_message.get_embed")
def test_replace_tags_in_embed_uses_last_content_item(
    mock_get_embed: MagicMock,
) -> None:
    mock_reader = MagicMock()
    mock_get_embed.return_value = CustomEmbed(description="{{entry_content}}")
    entry_ns: SimpleNamespace = make_entry("<p>Summary</p>")
    entry_ns.content = [SimpleNamespace(value="<p>Old content</p>"), SimpleNamespace(value="<p>New content</p>")]

    entry: Entry = typing.cast("Entry", entry_ns)
    embed: CustomEmbed = replace_tags_in_embed(entry_ns.feed, entry, reader=mock_reader)

    assert "New content" in embed.description


@patch("discord_rss_bot.custom_message.get_embed")
def test_replace_tags_in_embed_converts_escaped_newlines(
    mock_get_embed: MagicMock,
) -> None:
    r"""Verify \\n in embed fields becomes actual newlines, and fields without \\n are unchanged."""
    mock_reader = MagicMock()
    mock_get_embed.return_value = CustomEmbed(
        title="Line 1\\nLine 2",
        description="{{entry_text}}\\ntest\\test2",
        author_name="Author\\nSubtitle",
        footer_text="Footer\\n\\nMore",
    )
    entry_ns: SimpleNamespace = make_entry("<p>Summary</p>")

    entry: Entry = typing.cast("Entry", entry_ns)
    embed: CustomEmbed = replace_tags_in_embed(entry_ns.feed, entry, reader=mock_reader)

    # Fields with \\n should have actual newlines
    assert "\n" in embed.title
    assert embed.title == "Line 1\nLine 2"
    assert "\n" in embed.author_name
    assert embed.author_name == "Author\nSubtitle"
    assert "\n" in embed.footer_text
    assert embed.footer_text == "Footer\n\nMore"

    # Description combines tag replacement with \\n conversion.
    # "{{entry_text}}\\ntest\\\\test2" becomes "Summary text\ntest\\test2".
    assert "\n" in embed.description
    assert embed.description == "Summary\ntest\\test2"

    # Fields without \\n should be unchanged (backward compat) - none here but
    # cover other fields that had no \\n originally
    assert "\\n" not in embed.title
    assert "\\n" not in embed.author_name
    assert "\\n" not in embed.footer_text


def test_get_custom_message_returns_empty_string_on_value_error() -> None:
    reader = MagicMock()
    feed = make_feed()
    reader.get_tag.side_effect = ValueError

    feed = typing.cast("Feed", feed)

    custom_message = get_custom_message(reader=reader, feed=feed)

    assert not custom_message


def test_save_embed_serializes_embed_and_writes_feed_tag() -> None:
    reader = MagicMock()
    feed = make_feed()
    feed = typing.cast("Feed", feed)
    embed = CustomEmbed(
        title="Title",
        description="Description",
        color="#123456",
        author_name="Author",
        author_url="https://example.com/author",
        author_icon_url="https://example.com/author.png",
        image_url="https://example.com/image.png",
        thumbnail_url="https://example.com/thumb.png",
        footer_text="Footer",
        footer_icon_url="https://example.com/footer.png",
        show_steam_game_icon_in_thumbnail=True,
    )

    save_embed(reader=reader, feed=feed, embed=embed)

    reader.set_tag.assert_called_once()
    call_args = reader.set_tag.call_args.args
    assert call_args[1] == "embed"
    parsed = typing.cast("dict[str, str]", __import__("json").loads(call_args[2]))
    assert parsed["title"] == "Title"
    assert parsed["footer_icon_url"] == "https://example.com/footer.png"
    assert parsed["show_steam_game_icon_in_thumbnail"] is True


def test_get_embed_returns_default_embed_when_tag_is_empty() -> None:
    reader = MagicMock()
    feed = make_feed()
    feed = typing.cast("Feed", feed)
    reader.get_tag.return_value = ""

    embed = get_embed(reader=reader, feed=feed)

    assert embed.color == "#469ad9"


def test_get_embed_reads_embed_from_dict_tag() -> None:
    reader = MagicMock()
    feed = make_feed()
    feed = typing.cast("Feed", feed)
    reader.get_tag.return_value = {
        "title": "Dict title",
        "description": "Dict description",
        "color": 123,
    }

    embed = get_embed(reader=reader, feed=feed)

    assert embed.title == "Dict title"
    assert embed.description == "Dict description"
    assert embed.color == "123"


def test_get_embed_reads_embed_from_json_string() -> None:
    reader = MagicMock()
    feed = make_feed()
    feed = typing.cast("Feed", feed)
    reader.get_tag.return_value = '{"title": "Json title", "footer_text": "Json footer"}'

    embed = get_embed(reader=reader, feed=feed)

    assert embed.title == "Json title"
    assert embed.footer_text == "Json footer"


def test_get_embed_data_coerces_values_to_strings() -> None:
    embed = get_embed_data(
        {
            "title": 1,
            "description": 2,
            "color": 3,
            "author_name": 4,
            "author_url": 5,
            "author_icon_url": 6,
            "image_url": 7,
            "thumbnail_url": 8,
            "footer_text": 9,
            "footer_icon_url": 10,
            "show_steam_game_icon_in_thumbnail": "true",
        },
    )

    assert embed.title == "1"
    assert embed.footer_icon_url == "10"
    assert embed.show_steam_game_icon_in_thumbnail is True


class TestNormalizeMessageUsername:
    """Tests for normalize_message_username."""

    def test_empty_returns_empty(self) -> None:
        assert not normalize_message_username(None)
        assert not normalize_message_username("")

    def test_whitespace_only_returns_empty(self) -> None:
        assert not normalize_message_username("   ")
        assert not normalize_message_username("\t\n")

    def test_valid_username_returns_stripped(self) -> None:
        assert normalize_message_username("  Power Of The Shell  ") == "Power Of The Shell"

    def test_too_long_returns_empty(self) -> None:
        long_name: str = "a" * 81
        assert not normalize_message_username(long_name)

    def test_max_length_allowed(self) -> None:
        name: str = "a" * 80
        assert normalize_message_username(name) == name

    @pytest.mark.parametrize("char", ["@", "#", ":", "`"])
    def test_forbidden_characters_returns_empty(self, char: str) -> None:
        assert not normalize_message_username(f"valid{char}name")

    @pytest.mark.parametrize("substring", ["clyde", "Clyde", "CLYDE", "discord", "Discord", "DISCOrd"])
    def test_forbidden_substrings_returns_empty(self, substring: str) -> None:
        assert not normalize_message_username(f"my_{substring}_name")


class TestNormalizeMessageAvatarUrl:
    """Tests for normalize_message_avatar_url."""

    def test_empty_returns_empty(self) -> None:
        assert not normalize_message_avatar_url(None)
        assert not normalize_message_avatar_url("")

    def test_whitespace_only_returns_empty(self) -> None:
        assert not normalize_message_avatar_url("   ")

    def test_valid_http_url_returns_stripped(self) -> None:
        url: str = "http://example.com/icon.png"
        assert normalize_message_avatar_url(url) == url

    def test_valid_https_url_returns_stripped(self) -> None:
        url: str = "https://cdn.example.com/images/avatar.jpg"
        assert normalize_message_avatar_url(url) == url

    def test_whitespace_around_url_is_stripped(self) -> None:
        url: str = "https://example.com/icon.png"
        assert normalize_message_avatar_url(f"  {url}  ") == url

    def test_ftp_scheme_returns_empty(self) -> None:
        assert not normalize_message_avatar_url("ftp://example.com/icon.png")

    def test_no_scheme_returns_empty(self) -> None:
        assert not normalize_message_avatar_url("example.com/icon.png")

    def test_javascript_url_returns_empty(self) -> None:
        assert not normalize_message_avatar_url("javascript:alert(1)")

    def test_invalid_url_returns_empty(self) -> None:
        assert not normalize_message_avatar_url("not-a-url")
