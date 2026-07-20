"""Tests for the feed extension system.

Tests cover the ABC base class, plugin discovery, per-feed storage, the
``run_extensions`` integration function, and the built-in example plugin.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from reader import Reader as ReaderType
from reader import make_reader

from discord_rss_bot.custom_message import CustomEmbed
from discord_rss_bot.custom_message import get_embed
from discord_rss_bot.custom_message import replace_tags_in_embed
from discord_rss_bot.custom_message import replace_tags_in_text_message
from discord_rss_bot.custom_message import save_embed
from discord_rss_bot.extensions import FeedExtension
from discord_rss_bot.extensions import auto_enable_extensions_for_feed
from discord_rss_bot.extensions import discover_plugins
from discord_rss_bot.extensions import registry_clear
from discord_rss_bot.extensions import run_extensions
from discord_rss_bot.extensions.base import FeedExtension as FeedExtensionABC
from discord_rss_bot.extensions.hoyolab import HoyolabExtension
from discord_rss_bot.extensions.jwplayer_thumbnail import _SLUG_CACHE
from discord_rss_bot.extensions.jwplayer_thumbnail import JWPlayerThumbnailExtension
from discord_rss_bot.extensions.steam import SteamExtension
from discord_rss_bot.extensions.storage import get_enabled_extensions_for_feed
from discord_rss_bot.extensions.storage import set_enabled_extensions_for_feed
from discord_rss_bot.extensions.wordpress import WordPressExtension
from discord_rss_bot.extensions.youtube import YouTubeExtension

if TYPE_CHECKING:
    from collections.abc import Iterator

    from reader import Entry
    from reader import Reader

    from discord_rss_bot.feeds import JsonValue


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_registry() -> Iterator[None]:
    """Clear the extension registry before and after each test.

    Yields:
        Control back to the test body, then cleans up.
    """
    registry_clear()
    yield
    registry_clear()


@pytest.fixture
def temp_extensions_dir() -> Iterator[str]:
    """Create a temporary directory to act as the extensions directory.

    Yields:
        The path to the temporary extensions directory.
    """
    tmpdir: str = tempfile.mkdtemp(prefix="ext-test-")
    old_env: str | None = os.environ.pop("EXTENSIONS_DIR", None)
    os.environ["EXTENSIONS_DIR"] = tmpdir
    yield tmpdir
    if old_env is not None:
        os.environ["EXTENSIONS_DIR"] = old_env
    else:
        os.environ.pop("EXTENSIONS_DIR", None)


@pytest.fixture
def mock_reader() -> MagicMock:
    """A mock Reader with tag storage support.

    Returns:
        A MagicMock configured with set_tag/get_tag side effects.
    """
    reader: MagicMock = MagicMock()
    reader.tags = {}  # type: ignore[valid-type]

    def _resolve_feed_key(feed_or_url: str | SimpleNamespace) -> str:
        """Extract the feed URL string from either a string or SimpleNamespace.

        Returns:
            The URL as a string.
        """
        if isinstance(feed_or_url, str):
            return feed_or_url
        url = getattr(feed_or_url, "url", None)
        if url is not None:
            return str(url)
        return str(feed_or_url)

    def set_tag(feed_or_url: str | SimpleNamespace, key: str, value: JsonValue) -> None:
        feed_key: str = _resolve_feed_key(feed_or_url)
        if feed_key not in reader.tags:
            reader.tags[feed_key] = {}
        reader.tags[feed_key][key] = value

    def get_tag(feed_or_url: str | SimpleNamespace, key: str, default: JsonValue = None) -> JsonValue:
        feed_key: str = _resolve_feed_key(feed_or_url)
        feed_tags = reader.tags.get(feed_key, {})
        return feed_tags.get(key, default)

    reader.set_tag.side_effect = set_tag
    reader.get_tag.side_effect = get_tag
    return reader


@pytest.fixture
def mock_feed() -> SimpleNamespace:
    """A feed object with all attributes required by tag replacement.

    Returns:
        A SimpleNamespace with feed-like attributes.
    """
    return SimpleNamespace(
        added=None,
        author="Feed Author",
        authors_str="Feed Author",
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


@pytest.fixture
def mock_entry(mock_feed: SimpleNamespace) -> SimpleNamespace:
    """An entry object with all attributes required by tag replacement.

    Returns:
        A SimpleNamespace with entry-like attributes.
    """
    return SimpleNamespace(
        added=None,
        author="Entry Author",
        authors_str="Entry Author",
        content=[SimpleNamespace(value="<p>Hello world</p>")],
        feed=mock_feed,
        feed_url=mock_feed.url,
        id="entry-1",
        important=False,
        link="https://example.com/entry-1",
        published=None,
        read=False,
        read_modified=None,
        summary="",
        title="Test Entry",
        updated=None,
    )


# ---------------------------------------------------------------------------
# Tests: base.py
# ---------------------------------------------------------------------------


def test_feed_extension_abc_cannot_be_instantiated() -> None:
    """FeedExtension should be abstract and not instantiable directly."""
    with pytest.raises(TypeError):
        FeedExtensionABC()  # type: ignore[abstract]


def test_feed_extension_subclass_can_be_instantiated() -> None:
    """A concrete subclass with ``process_entry`` should work."""

    class ConcreteExtension(FeedExtensionABC):
        name = "test_concrete"

        def process_entry(self, entry: Entry, reader: Reader) -> dict[str, str]:  # ruff:ignore[unused-method-argument]
            return {"hello": "world"}

    instance = ConcreteExtension()
    assert instance.name == "test_concrete"


def test_feed_extension_name_defaults_to_empty_string() -> None:
    """The ``name`` class variable defaults to ``""``."""

    class UnnamedExtension(FeedExtensionABC):
        def process_entry(self, entry: Entry, reader: Reader) -> dict[str, str]:  # ruff:ignore[unused-method-argument]
            return {}

    assert not UnnamedExtension.name, "Expected name to be empty"


# ---------------------------------------------------------------------------
# Tests: discovery.py
# ---------------------------------------------------------------------------


BUILT_IN_EXTENSIONS: frozenset[str] = frozenset({"steam", "youtube", "hoyolab", "jwplayer_thumbnail", "wordpress"})


def _assert_only_built_in_extensions(registry: dict[str, type[FeedExtension]]) -> None:
    """Assert that *registry* contains exactly the built-in extensions."""
    registered: set[str] = set(registry.keys())
    unexpected: set[str] = registered - BUILT_IN_EXTENSIONS
    missing: frozenset[str] = BUILT_IN_EXTENSIONS - registered
    assert not unexpected, f"Registry contains unexpected extensions: {unexpected}"
    assert not missing, f"Registry missing built-in extensions: {missing}"


def test_discover_plugins_empty_directory(temp_extensions_dir: str) -> None:
    """An empty external directory still has built-in extensions."""
    registry: dict[str, type[FeedExtension]] = discover_plugins(force=True)
    _assert_only_built_in_extensions(registry)


def test_discover_plugins_missing_directory() -> None:
    """If the external extensions directory doesn't exist, built-ins still load."""
    old_env: str | None = os.environ.pop("EXTENSIONS_DIR", None)
    try:
        os.environ["EXTENSIONS_DIR"] = str(Path(tempfile.gettempdir()) / "nonexistent-extensions-dir-12345")
        registry: dict[str, type[FeedExtension]] = discover_plugins(force=True)
        _assert_only_built_in_extensions(registry)
    finally:
        if old_env is not None:
            os.environ["EXTENSIONS_DIR"] = old_env
        else:
            os.environ.pop("EXTENSIONS_DIR", None)


def test_discover_plugins_imports_plugin(temp_extensions_dir: str) -> None:
    """A valid plugin file should be discovered and registered alongside built-ins."""
    plugin_code: str = """
from discord_rss_bot.extensions.base import FeedExtension

class TestPlugin(FeedExtension):
    name = "test_plugin"
    description = "A test plugin."

    def process_entry(self, entry, reader):
        return {"test_var": "hello"}
"""
    plugin_path: Path = Path(temp_extensions_dir) / "test_plugin.py"
    plugin_path.write_text(plugin_code, encoding="utf-8")

    registry: dict[str, type[FeedExtension]] = discover_plugins(force=True)
    assert "test_plugin" in registry
    assert registry["test_plugin"].name == "test_plugin"
    assert registry["test_plugin"].description == "A test plugin."
    # Built-in extensions should also be present.
    for name in BUILT_IN_EXTENSIONS:
        assert name in registry, f"Missing built-in extension {name}"


def test_discover_plugins_skips_broken_plugin(temp_extensions_dir: str) -> None:
    """A plugin that raises during import should be skipped, not crash."""
    plugin_path: Path = Path(temp_extensions_dir) / "broken.py"
    plugin_path.write_text("raise SyntaxError('bad syntax'", encoding="utf-8")

    # Should not raise.
    registry: dict[str, type[FeedExtension]] = discover_plugins(force=True)
    assert "broken" not in registry
    # Built-in extensions should still load.
    _assert_only_built_in_extensions(registry)


def test_discover_plugins_skips_init_py(temp_extensions_dir: str) -> None:
    """__init__.py files in the extensions directory should be ignored."""
    init_path: Path = Path(temp_extensions_dir) / "__init__.py"
    init_path.write_text("# package init", encoding="utf-8")

    registry: dict[str, type[FeedExtension]] = discover_plugins(force=True)
    _assert_only_built_in_extensions(registry)


def test_discover_plugins_deduplicates_by_name(temp_extensions_dir: str) -> None:
    """If two plugins define the same name, the last one wins."""
    plugin_a: str = """
from discord_rss_bot.extensions.base import FeedExtension

class PluginA(FeedExtension):
    name = "dup_name"
    def process_entry(self, entry, reader):
        return {"from": "a"}
"""
    plugin_b: str = """
from discord_rss_bot.extensions.base import FeedExtension

class PluginB(FeedExtension):
    name = "dup_name"
    def process_entry(self, entry, reader):
        return {"from": "b"}
"""
    (Path(temp_extensions_dir) / "a.py").write_text(plugin_a)
    (Path(temp_extensions_dir) / "b.py").write_text(plugin_b)

    registry: dict[str, type[FeedExtension]] = discover_plugins(force=True)
    assert "dup_name" in registry
    # The last one alphabetically (b.py) should win.
    assert registry["dup_name"].__name__ == "PluginB"


# ---------------------------------------------------------------------------
# Tests: storage.py
# ---------------------------------------------------------------------------


def test_get_enabled_extensions_empty_when_no_tag(mock_reader: MagicMock, mock_feed: SimpleNamespace) -> None:
    """If no extensions tag is set, an empty list is returned."""
    enabled: list[str] = get_enabled_extensions_for_feed(mock_reader, mock_feed.url)
    assert enabled == []


def test_set_and_get_enabled_extensions(mock_reader: MagicMock, mock_feed: SimpleNamespace) -> None:
    """Setting enabled extensions and retrieving them should round-trip."""
    names: list[str] = ["jwplayer_thumbnail", "encode_links"]
    set_enabled_extensions_for_feed(mock_reader, mock_feed.url, names)
    enabled: list[str] = get_enabled_extensions_for_feed(mock_reader, mock_feed.url)
    assert enabled == names


def test_set_enabled_extensions_clears_list(mock_reader: MagicMock, mock_feed: SimpleNamespace) -> None:
    """Setting an empty list should clear the enabled extensions."""
    set_enabled_extensions_for_feed(mock_reader, mock_feed.url, ["some_plugin"])
    set_enabled_extensions_for_feed(mock_reader, mock_feed.url, [])
    enabled: list[str] = get_enabled_extensions_for_feed(mock_reader, mock_feed.url)
    assert enabled == []


def test_get_enabled_extensions_handles_string_tag(mock_reader: MagicMock, mock_feed: SimpleNamespace) -> None:
    """If the tag is stored as a JSON string, it should still be parsed."""

    def json_string_tag(feed_url: str, key: str, default: JsonValue = None) -> str:
        return json.dumps(["plugin_a", "plugin_b"])

    mock_reader.get_tag.side_effect = json_string_tag
    enabled: list[str] = get_enabled_extensions_for_feed(mock_reader, mock_feed.url)
    assert enabled == ["plugin_a", "plugin_b"]


def test_get_enabled_extensions_handles_empty_string_tag(mock_reader: MagicMock, mock_feed: SimpleNamespace) -> None:
    """An empty string tag should return an empty list."""

    def empty_string_tag(feed_url: str, key: str, default: JsonValue = None) -> str:
        return ""

    mock_reader.get_tag.side_effect = empty_string_tag
    enabled: list[str] = get_enabled_extensions_for_feed(mock_reader, mock_feed.url)
    assert enabled == []


# ---------------------------------------------------------------------------
# Tests: run_extensions (integration)
# ---------------------------------------------------------------------------


def test_run_extensions_empty_when_none_enabled(
    mock_reader: MagicMock,
    mock_entry: SimpleNamespace,
    mock_feed: SimpleNamespace,
) -> None:
    """If no extensions are enabled for the feed, the result is empty."""
    set_enabled_extensions_for_feed(mock_reader, mock_feed.url, [])
    result: dict[str, str] = run_extensions(mock_entry, mock_reader)  # type: ignore[arg-type]
    assert result == {}


def test_run_extensions_with_missing_plugin(
    mock_reader: MagicMock,
    mock_entry: SimpleNamespace,
    mock_feed: SimpleNamespace,
) -> None:
    """Enabled extension that doesn't exist in the registry is skipped."""
    set_enabled_extensions_for_feed(mock_reader, mock_feed.url, ["nonexistent_plugin"])
    result: dict[str, str] = run_extensions(mock_entry, mock_reader)  # type: ignore[arg-type]
    assert result == {}


def test_run_extensions_with_registered_plugin(
    mock_reader: MagicMock,
    mock_entry: SimpleNamespace,
    mock_feed: SimpleNamespace,
    temp_extensions_dir: str,
) -> None:
    """A registered and enabled extension should produce variables."""
    # Register a plugin via discovery.
    plugin_code: str = """
from discord_rss_bot.extensions.base import FeedExtension

class TestPlugin(FeedExtension):
    name = "test_plugin"

    def process_entry(self, entry, reader):
        return {"custom_var": "hello_from_plugin"}
"""
    (Path(temp_extensions_dir) / "my_plugin.py").write_text(plugin_code)
    discover_plugins(force=True)

    set_enabled_extensions_for_feed(mock_reader, mock_feed.url, ["test_plugin"])
    result: dict[str, str] = run_extensions(mock_entry, mock_reader)  # type: ignore[arg-type]
    assert result == {"custom_var": "hello_from_plugin"}


def test_run_extensions_continues_after_plugin_error(
    mock_reader: MagicMock,
    mock_entry: SimpleNamespace,
    mock_feed: SimpleNamespace,
    temp_extensions_dir: str,
) -> None:
    """If one plugin raises, others should still run and produce results."""
    # Register two plugins: one that raises and one that works.
    good_code: str = """
from discord_rss_bot.extensions.base import FeedExtension

class GoodPlugin(FeedExtension):
    name = "good_plugin"
    def process_entry(self, entry, reader):
        return {"good_var": "ok"}
"""
    bad_code: str = """
from discord_rss_bot.extensions.base import FeedExtension

class BadPlugin(FeedExtension):
    name = "bad_plugin"
    def process_entry(self, entry, reader):
        raise RuntimeError("This plugin failed!")
"""
    (Path(temp_extensions_dir) / "good.py").write_text(good_code)
    (Path(temp_extensions_dir) / "bad.py").write_text(bad_code)
    discover_plugins(force=True)

    set_enabled_extensions_for_feed(mock_reader, mock_feed.url, ["bad_plugin", "good_plugin"])
    result: dict[str, str] = run_extensions(mock_entry, mock_reader)  # type: ignore[arg-type]
    assert result == {"good_var": "ok"}


# ---------------------------------------------------------------------------
# Tests: tag replacement integration (custom_message.py)
# ---------------------------------------------------------------------------


def test_replace_tags_in_embed_uses_extension_variables(
    mock_reader: MagicMock,
    mock_feed: SimpleNamespace,
    mock_entry: SimpleNamespace,
    temp_extensions_dir: str,
) -> None:
    """Extension variables should be available in embed tag replacement."""
    # Register a test plugin.
    plugin_code: str = """
from discord_rss_bot.extensions.base import FeedExtension

class EmbedVarPlugin(FeedExtension):
    name = "embed_var"
    def process_entry(self, entry, reader):
        return {"custom_thumbnail": "https://example.com/thumb.jpg"}
"""
    (Path(temp_extensions_dir) / "embed_var.py").write_text(plugin_code)
    discover_plugins(force=True)

    # Enable the plugin for this feed.
    set_enabled_extensions_for_feed(mock_reader, mock_feed.url, ["embed_var"])

    # Create an embed that uses the extension variable.
    embed: CustomEmbed = get_embed(mock_reader, mock_feed)  # type: ignore[arg-type]
    embed.image_url = "{{custom_thumbnail}}"
    save_embed(mock_reader, mock_feed, embed)  # type: ignore[arg-type]

    # Run replacement.
    result: CustomEmbed = replace_tags_in_embed(mock_feed, mock_entry, mock_reader)  # type: ignore[arg-type]
    assert "https://example.com/thumb.jpg" in result.image_url


def test_replace_tags_in_text_message_uses_extension_variables(
    mock_reader: MagicMock,
    mock_feed: SimpleNamespace,
    mock_entry: SimpleNamespace,
    temp_extensions_dir: str,
) -> None:
    """Extension variables should be available in text message tag replacement."""
    # Register a test plugin.
    plugin_code: str = """
from discord_rss_bot.extensions.base import FeedExtension

class TextVarPlugin(FeedExtension):
    name = "text_var"
    def process_entry(self, entry, reader):
        return {"custom_text": "hello_from_extension"}
"""
    (Path(temp_extensions_dir) / "text_var.py").write_text(plugin_code)
    discover_plugins(force=True)

    # Enable the plugin for this feed.
    set_enabled_extensions_for_feed(mock_reader, mock_feed.url, ["text_var"])

    # Set a custom message that uses the extension variable.
    mock_reader.set_tag(mock_feed.url, "custom_message", "{{custom_text}}")

    # Run replacement.
    result: str = replace_tags_in_text_message(mock_entry, mock_reader)  # type: ignore[arg-type]
    assert "hello_from_extension" in result


# ---------------------------------------------------------------------------
# Tests: JWPlayer example plugin
# ---------------------------------------------------------------------------


def test_jwplayer_thumbnail_extension_extracts_image() -> None:
    """The JWPlayer thumbnail extension should extract the image URL."""
    ext = JWPlayerThumbnailExtension()
    raw_html: str = """
    <div id="player_01"></div>
    <script type="text/javascript">
    jwplayer("player_01").setup({
        file: "https://example.com/video.mp4",
        image: "https://example.com/thumbnail.jpg",
    });
    </script>
    """
    entry: SimpleNamespace = SimpleNamespace(
        id="test",
        content=[SimpleNamespace(value=raw_html)],
        summary="",
        feed=SimpleNamespace(url="https://example.com/feed.xml"),
    )
    result: dict[str, str] = ext.process_entry(entry, MagicMock())  # type: ignore[arg-type]
    assert result.get("jwplayer_thumbnail") == "https://example.com/thumbnail.jpg"
    assert result.get("jwplayer_file") == "https://example.com/video.mp4"


def test_jwplayer_thumbnail_extension_returns_empty_without_content() -> None:
    """If the entry has no content, the extension should return an empty dict."""
    ext = JWPlayerThumbnailExtension()
    entry: SimpleNamespace = SimpleNamespace(
        id="test",
        content=[],
        summary="",
        link="https://example.com/video",
        feed=SimpleNamespace(url="https://example.com/feed.xml"),
    )
    result: dict[str, str] = ext.process_entry(entry, MagicMock())  # type: ignore[arg-type]
    assert result == {}


def test_jwplayer_thumbnail_extension_returns_empty_without_match() -> None:
    """If the HTML has no JWPlayer pattern, the extension should return empty."""
    ext = JWPlayerThumbnailExtension()
    raw_html: str = "<p>No player here.</p>"
    entry: SimpleNamespace = SimpleNamespace(
        id="test",
        content=[SimpleNamespace(value=raw_html)],
        summary="",
        link="https://example.com/video",
        feed=SimpleNamespace(url="https://example.com/feed.xml"),
    )
    result: dict[str, str] = ext.process_entry(entry, MagicMock())  # type: ignore[arg-type]
    assert result == {}


def test_jwplayer_thumbnail_extension_matches_hentaigasm_format() -> None:
    """The extension should extract URLs from the actual hentaigasm.com feed format."""
    ext = JWPlayerThumbnailExtension()
    # This is the actual HTML structure from the main hentaigasm feed.
    raw_html: str = """
<p style="text-align: center;"><strong>HENTAIGASM EXCLUSIVE!</strong></p>

<div style="width:620px; height:349px">
<script src="https://content.jwplatform.com/libraries/SAHhwvZq.js"></script>
<script>jwplayer.key="zTEbSn/eAplL0RLXT030FzOcek6qXmtrxju6Jg=="</script>

<div id="player_01"></div>
<script type="text/javascript">
.jwplayer("player_01").setup({
    file: "https://hgasm2.com/Test Video 1 Subbed.mp4",
    width: "620",
    height: "349",
    skin: "seven",
    preload: "none",
    autostart: "false",
    image: "https://hgasm1.com/thumbnail/Test Video 1 Subbed.jpg",
    advertising: {}
});
</script>
</div>

<a class="btn btn-pink" href="https://hgasm3.com/Test Video 1 Subbed.mp4" download>DOWNLOAD</a>
"""
    entry: SimpleNamespace = SimpleNamespace(
        id="test-hentai",
        content=[SimpleNamespace(value=raw_html)],
        summary="",
        feed=SimpleNamespace(url="https://hentaigasm.com/feed/"),
    )
    result: dict[str, str] = ext.process_entry(entry, MagicMock())  # type: ignore[arg-type]
    assert result.get("jwplayer_thumbnail") == "https://hgasm1.com/thumbnail/Test%20Video%201%20Subbed.jpg"
    assert result.get("jwplayer_file") == "https://hgasm2.com/Test%20Video%201%20Subbed.mp4"


# ---------------------------------------------------------------------------
# Tests: auto_enable_url_patterns
# ---------------------------------------------------------------------------


def test_auto_enable_by_url_pattern_matches(
    mock_reader: MagicMock,
    temp_extensions_dir: str,
) -> None:
    """An extension with matching auto_enable_url_patterns should be auto-enabled.

    Check that ``auto_enable_extensions_for_feed`` activates the plugin.
    """
    # Register a test plugin with a URL pattern.
    plugin_code: str = """
from discord_rss_bot.extensions.base import FeedExtension

class AutoPlugin(FeedExtension):
    name = "auto_test"
    auto_enable_url_patterns = [r"example\\.com/feeds"]

    def process_entry(self, entry, reader):
        return {"auto_var": "enabled"}
"""
    plugin_path: Path = Path(temp_extensions_dir) / "auto_plugin.py"
    plugin_path.write_text(plugin_code, encoding="utf-8")
    discover_plugins(force=True)

    mock_feed_url: str = "https://example.com/feeds/test.xml"
    result: list[str] = auto_enable_extensions_for_feed(mock_reader, mock_feed_url)

    assert "auto_test" in result


def test_auto_enable_by_url_pattern_does_not_match(
    mock_reader: MagicMock,
    temp_extensions_dir: str,
) -> None:
    """An extension whose pattern does not match should NOT be auto-enabled."""
    # Register the same plugin as the matching test, so this test actually
    # validates that a non-matching URL does not trigger auto-enable.
    plugin_code: str = """
from discord_rss_bot.extensions.base import FeedExtension

class AutoPlugin(FeedExtension):
    name = "auto_test"
    auto_enable_url_patterns = [r"example\\.com/feeds"]

    def process_entry(self, entry, reader):
        return {"auto_var": "enabled"}
"""
    plugin_path: Path = Path(temp_extensions_dir) / "auto_plugin.py"
    plugin_path.write_text(plugin_code, encoding="utf-8")
    discover_plugins(force=True)

    mock_feed_url: str = "https://other-site.com/feed.xml"
    result: list[str] = auto_enable_extensions_for_feed(mock_reader, mock_feed_url)

    assert "auto_test" not in result


def test_auto_enable_does_not_duplicate_explicitly_enabled(
    mock_reader: MagicMock,
) -> None:
    """If an extension is already explicitly enabled, auto-enable should not add it again."""
    mock_feed_url: str = "https://example.com/feeds/test.xml"
    # Explicitly enable the extension first.
    set_enabled_extensions_for_feed(mock_reader, mock_feed_url, ["auto_test"])

    result: list[str] = auto_enable_extensions_for_feed(mock_reader, mock_feed_url)
    # Should contain auto_test only once.
    assert result == ["auto_test"]


def test_matches_feed_url_classmethod() -> None:
    """The ``matches_feed_url`` classmethod should work correctly."""
    assert FeedExtension.matches_feed_url("http://example.com") is False, "Base class has no patterns"


def test_steam_extension_has_auto_enable_patterns() -> None:
    """The built-in Steam extension should declare URL patterns."""
    assert len(SteamExtension.auto_enable_url_patterns) > 0
    assert SteamExtension.matches_feed_url("https://store.steampowered.com/feeds/news/app/570/")
    assert SteamExtension.matches_feed_url("https://steamcommunity.com/games/570/")
    assert not SteamExtension.matches_feed_url("https://example.com/feed.xml")


def test_youtube_extension_has_auto_enable_patterns() -> None:
    """The built-in YouTube extension should declare URL patterns."""
    assert len(YouTubeExtension.auto_enable_url_patterns) > 0
    assert YouTubeExtension.matches_feed_url("https://www.youtube.com/feeds/videos.xml?channel_id=123")
    assert not YouTubeExtension.matches_feed_url("https://example.com/feed.xml")


def test_hoyolab_extension_has_auto_enable_patterns() -> None:
    """The built-in Hoyolab extension should declare URL patterns."""
    assert len(HoyolabExtension.auto_enable_url_patterns) > 0
    assert HoyolabExtension.matches_feed_url("https://feeds.c3kay.de/hoyolab.xml")
    assert not HoyolabExtension.matches_feed_url("https://example.com/feed.xml")


# ---------------------------------------------------------------------------
# Integration test with a real WordPress comment RSS feed (the original issue)
# ---------------------------------------------------------------------------


_COMMENTS_FEED_XML: str = r"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
    xmlns:content="http://purl.org/rss/1.0/modules/content/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:atom="http://www.w3.org/2005/Atom"
    xmlns:sy="http://purl.org/rss/1.0/modules/syndication/">
<channel>
<title>Comments on: Test Article</title>
<link>https://example.com/test-article/</link>
<description></description>
<lastBuildDate>Sat, 18 Jul 2026 05:11:01 +0000</lastBuildDate>
<sy:updatePeriod>hourly</sy:updatePeriod>
<sy:updateFrequency>1</sy:updateFrequency>
<generator>https://wordpress.org/?v=5.8.2</generator>
<item>
    <title>By: Anonymous</title>
    <link>https://example.com/test-article/comment-page-1/#comment-820928</link>
    <dc:creator><![CDATA[Anonymous]]></dc:creator>
    <pubDate>Sat, 18 Jul 2026 05:11:01 +0000</pubDate>
    <guid isPermaLink="false">https://example.com/?p=5633#comment-820928</guid>
    <description><![CDATA[Am I the only one that saw the &quot;Bookmark us&quot; message?]]></description>
    <content:encoded><![CDATA[<p>Am I the only one that saw &#8220;Bookmark us&#8221; message?</p>]]></content:encoded>
</item>
<item>
    <title>By: Unknown</title>
    <link>https://example.com/test-article/comment-page-1/#comment-820900</link>
    <dc:creator><![CDATA[Unknown]]></dc:creator>
    <pubDate>Fri, 17 Jul 2026 14:29:42 +0000</pubDate>
    <guid isPermaLink="false">https://example.com/?p=5633#comment-820900</guid>
    <description><![CDATA[Please uncensor the video]]></description>
    <content:encoded><![CDATA[<p>Please uncensor the video</p>]]></content:encoded>
</item>
<item>
    <title>By: mid</title>
    <link>https://example.com/test-article/comment-page-1/#comment-820887</link>
    <dc:creator><![CDATA[mid]]></dc:creator>
    <pubDate>Fri, 17 Jul 2026 06:20:56 +0000</pubDate>
    <guid isPermaLink="false">https://example.com/?p=5633#comment-820887</guid>
    <description><![CDATA[that&#039;s not uncensored]]></description>
    <content:encoded><![CDATA[<p>that&#8217;s not uncensored</p>]]></content:encoded>
</item>
</channel>
</rss>
"""


class _CommentsFeedHandler(BaseHTTPRequestHandler):
    """Serves the WordPress comment RSS XML on any request."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/xml")
        self.end_headers()
        self.wfile.write(_COMMENTS_FEED_XML.encode("utf-8"))

    def log_message(self, _format: str, *args: str | int) -> None:
        pass


@contextmanager
def _serve_feed() -> Iterator[str]:
    """Start a local HTTP server serving the comments feed XML.

    Yields:
        The URL of the feed.
    """
    with ThreadingHTTPServer(("127.0.0.1", 0), _CommentsFeedHandler) as server:
        server_thread = Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/feed.xml"
        finally:
            server.shutdown()
            server_thread.join()


@pytest.mark.slow
def test_wordpress_comments_feed_pipeline() -> None:
    """End-to-end test using the WordPress comment RSS feed from the original issue.

    Validates that:
    1. The feed XML parses correctly via the reader library
    2. Entry content and summary are populated as expected
    3. The jwplayer_thumbnail extension gracefully returns empty (no script tags)
    4. Tag replacement does not crash with comment feed data
    """
    with (
        tempfile.TemporaryDirectory() as tmpdir,
        _serve_feed() as feed_url,
    ):
        db_path: Path = Path(tmpdir) / "test.sqlite"
        reader: ReaderType = make_reader(url=str(db_path))

        try:
            # Add and update the feed.
            reader.add_feed(feed_url)
            reader.update_feed(feed_url)

            feed = reader.get_feed(feed_url)
            entries: list[Entry] = list(reader.get_entries(feed=feed_url))

            # The comments feed should have 3 entries.
            assert len(entries) == 3, f"Expected 3 comments, got {len(entries)}"

            for entry in entries:
                # Each entry should have a title (comment author).
                assert entry.title is not None
                assert entry.title.startswith("By:")

                # Each entry should have a link back to the comment.
                assert entry.link is not None
                assert "comment-page" in entry.link

                # Summary should be plain text (from <description>),
                # content should be HTML (from <content:encoded>).
                assert entry.summary is not None
                assert "<p>" not in entry.summary
                if entry.content:
                    assert "<p>" in entry.content[0].value

                # The jwplayer_thumbnail extension should return empty
                # because this feed has no JWPlayer script blocks.
                ext = JWPlayerThumbnailExtension()
                result: dict[str, str] = ext.process_entry(entry, reader)  # type: ignore[arg-type]
                assert result == {}, f"JWPlayer extension should return empty for comment feed, got {result}"

                # Tag replacement should not crash.
                replaced_text: str = replace_tags_in_text_message(entry, reader)
                assert isinstance(replaced_text, str)

                # Embed replacement should not crash.
                replaced_embed = replace_tags_in_embed(feed, entry, reader)
                assert replaced_embed is not None

            # Verify content:encoded was parsed into the content field.
            first_entry = entries[0]
            assert first_entry.content is not None
            raw_content: str = first_entry.content[0].value
            assert "Bookmark us" in raw_content or "bookmark" in raw_content.lower()
            assert "<p>" in raw_content

        finally:
            reader.close()


# ---------------------------------------------------------------------------
# Main feed XML (hentaigasm-style, with JWPlayer video entries)
# ---------------------------------------------------------------------------

_MAIN_FEED_XML: str = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
    xmlns:content="http://purl.org/rss/1.0/modules/content/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:atom="http://www.w3.org/2005/Atom"
    xmlns:sy="http://purl.org/rss/1.0/modules/syndication/">
<channel>
<title>Hentaigasm - Test Feed</title>
<link>https://example.com</link>
<description></description>
<lastBuildDate>Sun, 19 Jul 2026 04:20:40 +0000</lastBuildDate>
<item>
    <title>Test Video 1 Subbed</title>
    <link>https://example.com/test-video-1/</link>
    <dc:creator><![CDATA[admin]]></dc:creator>
    <pubDate>Sun, 19 Jul 2026 04:00:49 +0000</pubDate>
    <guid isPermaLink="false">https://example.com/?p=5501</guid>
    <description><![CDATA[]]></description>
    <content:encoded><![CDATA[

<p style="text-align: center;"><strong>HENTAIGASM EXCLUSIVE!</strong></p>

<div style="width:620px; height:349px">
<script src="https://content.jwplatform.com/libraries/SAHhwvZq.js"></script>
<script>jwplayer.key="zTEbSn/eAplL0RLXT030FzOcek6qXmtrxju6Jg=="</script>

<div id="player_01"></div>
<script type="text/javascript">
jwplayer("player_01").setup({
    file: "https://cdn.example.com/Test Video 1 Subbed.mp4",
    width: "620",
    height: "349",
    skin: "seven",
    preload: "none",
    autostart: "false",
    image: "https://cdn.example.com/thumbnail/Test Video 1 Subbed.jpg",
    advertising: {}
});
</script>
</div>

]]></content:encoded>
</item>
</channel>
</rss>
"""


class _MainFeedHandler(BaseHTTPRequestHandler):
    """Serves the main feed XML with JWPlayer video entries."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/xml")
        self.end_headers()
        self.wfile.write(_MAIN_FEED_XML.encode("utf-8"))

    def log_message(self, _format: str, *args: str | int) -> None:
        pass


@contextmanager
def _serve_main_feed() -> Iterator[str]:
    """Start a local HTTP server serving the main feed XML with JWPlayer content.

    Yields:
        The URL of the feed.
    """
    with ThreadingHTTPServer(("127.0.0.1", 0), _MainFeedHandler) as server:
        server_thread = Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/feed.xml"
        finally:
            server.shutdown()
            server_thread.join()


@pytest.mark.slow
def test_hentaigasm_main_feed_jwplayer_extraction() -> None:
    """End-to-end test using a hentaigasm-style main feed with JWPlayer content.

    This test confirms that feedparser strips ``<script>`` tags from
    ``<content:encoded>``, so the JWPlayer ``image:`` and ``file:``
    properties are NOT available in ``entry.content``.

    The extension falls back to fetching the HTML page at ``entry.link``,
    but in the test environment no real server is available, so the
    extension returns empty.  A separate test validates the HTTP fetch
    fallback with a local server.
    """
    with (
        tempfile.TemporaryDirectory() as tmpdir,
        _serve_main_feed() as feed_url,
    ):
        db_path: Path = Path(tmpdir) / "test.sqlite"
        reader: ReaderType = make_reader(url=str(db_path))

        try:
            reader.add_feed(feed_url)
            reader.update_feed(feed_url)

            entries = list(reader.get_entries(feed=feed_url))

            # Should have 1 video entry.
            assert len(entries) == 1, f"Expected 1 entry, got {len(entries)}"

            entry = entries[0]
            assert entry.title is not None

            # CONFIRMATION: feedparser strips <script> tags entirely.
            # The content <p> and <div> survive, but all <script> blocks
            # (including the jwplayer setup with image:/file:) are gone.
            assert entry.content is not None
            assert len(entry.content) > 0
            raw_content: str = entry.content[0].value
            assert "jwplayer" not in raw_content, (
                f"BUG: script content survived parsing! Content: {raw_content[:300]!r}"
            )
            assert "image:" not in raw_content
            assert "file:" not in raw_content
            assert "player_01" in raw_content  # non-script div survives

            # Auto-enable is URL-based — the test feed URL (127.0.0.1) doesn't
            # match "hentaigasm\.com", so we manually enable for this test.
            set_enabled_extensions_for_feed(reader, entry.feed.url, ["jwplayer_thumbnail"])
            enabled: list[str] = get_enabled_extensions_for_feed(reader, entry.feed.url)
            assert "jwplayer_thumbnail" in enabled

        finally:
            reader.close()


@pytest.mark.slow
def test_jwplayer_thumbnail_wordpress_batch_fallback() -> None:
    """Verify the batch WordPress API fallback works.

    Serves a fake WordPress REST API response (a list of posts) so the
    extension extracts JWPlayer URLs from the cached batch data.
    """
    _SLUG_CACHE.clear()

    wp_json: str = json.dumps([
        {
            "slug": "test-slug",
            "content": {
                "rendered": (
                    '<p>Test</p><div id="player_01"></div>'
                    '<script>jwplayer("player_01").setup({'
                    'file: "https://cdn.example.com/video.mp4", '
                    'image: "https://cdn.example.com/thumb.jpg"'
                    "});</script>"
                ),
            },
        },
        {
            "slug": "other-post",
            "content": {"rendered": "<p>No player here.</p>"},
        },
    ])

    class _APIHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(wp_json.encode("utf-8"))

        def log_message(self, _format: str, *args: str | int) -> None:
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), _APIHandler) as server:
        server_thread = Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        port: int = server.server_port

        try:
            entry = SimpleNamespace(
                id="test-wp-batch",
                content=[],
                summary="",
                link=f"http://127.0.0.1:{port}/test-slug/",
                feed=SimpleNamespace(url=f"http://127.0.0.1:{port}/feed/"),
            )

            ext = JWPlayerThumbnailExtension()
            result: dict[str, str] = ext.process_entry(entry, MagicMock())  # type: ignore[arg-type]

            assert result.get("jwplayer_thumbnail") == "https://cdn.example.com/thumb.jpg", (
                f"Batch WP fallback should extract thumbnail, got {result}"
            )
            assert result.get("jwplayer_file") == "https://cdn.example.com/video.mp4", (
                f"Batch WP fallback should extract file, got {result}"
            )

            # Second entry from the same site uses cache — no API call.
            entry2 = SimpleNamespace(
                id="other-post",
                content=[],
                summary="",
                link=f"http://127.0.0.1:{port}/other-post/",
                feed=SimpleNamespace(url=f"http://127.0.0.1:{port}/feed/"),
            )
            result2: dict[str, str] = ext.process_entry(entry2, MagicMock())  # type: ignore[arg-type]
            assert result2 == {}, "Entry without player should return empty"

        finally:
            server.shutdown()
            server_thread.join()
            _SLUG_CACHE.clear()


# ---------------------------------------------------------------------------
# Tests: WordPress extension
# ---------------------------------------------------------------------------


def test_wordpress_extension_uses_shared_batch_cache() -> None:
    """The WordPress extension should use the shared batch cache."""
    _SLUG_CACHE.clear()
    content_html: str = (
        "<p>Test</p>"
        "<script>jwplayer().setup({file: 'https://cdn.example.com/v.mp4', image: 'https://cdn.example.com/thumb.jpg'});</script>"
    )
    # Pre-populate the shared cache with the new richer format.
    _SLUG_CACHE["https://example.com"] = {
        "test-slug": {
            "content": content_html,
            "excerpt": "<p>Test excerpt</p>",
            "title": "Test Post",
        },
    }

    ext = WordPressExtension()
    entry = SimpleNamespace(
        id="test",
        link="https://example.com/test-slug/",
        feed=SimpleNamespace(url="https://example.com/feed/"),
    )
    result = ext.process_entry(entry, MagicMock())  # type: ignore[arg-type]
    assert result.get("wp_jwplayer_thumbnail") == "https://cdn.example.com/thumb.jpg"
    assert result.get("wp_jwplayer_file") == "https://cdn.example.com/v.mp4"
    assert result.get("wp_content_raw") == content_html
    assert result.get("wp_content") is not None
    assert "Test" in result.get("wp_content", "")
    assert result.get("wp_excerpt_raw") == "<p>Test excerpt</p>"
    assert result.get("wp_excerpt") is not None
    assert "Test excerpt" in result.get("wp_excerpt", "")
    # No spaces in URL values.
    for key, val in result.items():
        if key.startswith("wp_jwplayer"):
            assert " " not in val, f"URL should be encoded, got spaces: {val}"
    _SLUG_CACHE.clear()


def test_wordpress_extension_provides_correct_variables() -> None:
    """The WordPress extension should declare the correct variables."""
    expected: set[str] = {
        "wp_content",
        "wp_content_raw",
        "wp_excerpt",
        "wp_excerpt_raw",
        "wp_jwplayer_file",
        "wp_jwplayer_thumbnail",
    }
    assert set(WordPressExtension.provides_variables) == expected
