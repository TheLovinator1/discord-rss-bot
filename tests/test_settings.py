from __future__ import annotations

import pathlib
import tempfile
from contextlib import closing
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from reader import ParseError
from reader import Reader

import discord_rss_bot.settings as settings_module
from discord_rss_bot.settings import data_dir
from discord_rss_bot.settings import default_custom_message
from discord_rss_bot.settings import get_reader
from discord_rss_bot.settings import has_plugin
from discord_rss_bot.settings import make_app_reader

if TYPE_CHECKING:
    from collections.abc import Iterator


class _AutodiscoverHandler(BaseHTTPRequestHandler):
    """Serve an HTML page that advertises an RSS feed."""

    def do_GET(self) -> None:
        """Return HTML instead of a feed so reader attempts autodiscovery."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b'<html><head><link rel="alternate" href="/rss.xml" '
            b'type="application/rss+xml" title="Example"></head></html>'
        )

    def log_message(self, _format: str, *_args: object) -> None:
        """Suppress HTTP request logging during tests."""


@contextmanager
def _serve_autodiscover_html() -> Iterator[str]:
    """Serve an HTML page URL while the context is active.

    Yields:
        The URL of the HTML page.
    """
    with ThreadingHTTPServer(("127.0.0.1", 0), _AutodiscoverHandler) as server:
        server_thread = Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            server_thread.join()


def test_reader() -> None:
    """Test the reader."""
    reader: Reader = get_reader()
    assert isinstance(reader, Reader), f"The reader should be an instance of Reader. But it was '{type(reader)}'."

    # Test the reader with a custom location.
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory
        Path.mkdir(Path(temp_dir), exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "custom_loc_db.sqlite")
        reader: Reader = get_reader(custom_location=str(custom_loc))
        assert_msg = f"The custom reader should be an instance of Reader. But it was '{type(reader)}'."
        assert isinstance(reader, Reader), assert_msg

        # Close the reader, so we can delete the directory.
        reader.close()


def test_data_dir() -> None:
    """Test the data directory."""
    assert Path.exists(Path(data_dir)), f"The data directory '{data_dir}' should exist."


def test_default_custom_message() -> None:
    """Test the default custom message."""
    assert_msg = f"The default custom message should be '{{entry_title}}\n{{entry_link}}'. But it was '{default_custom_message}'."  # noqa: E501
    assert default_custom_message == "{{entry_title}}\n{{entry_link}}", assert_msg


def test_get_webhook_for_entry() -> None:
    """Test getting the webhook for an entry."""
    # Test with a custom reader.
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory
        Path.mkdir(Path(temp_dir), exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "custom_loc_db.sqlite")
        reader: Reader = get_reader(custom_location=str(custom_loc))

        # Add a feed to the database.
        reader.add_feed("https://www.reddit.com/r/movies.rss")

        # Add a webhook to the database.
        reader.set_tag("https://www.reddit.com/r/movies.rss", "webhook", "https://example.com")  # pyright: ignore[reportArgumentType]
        our_tag = reader.get_tag("https://www.reddit.com/r/movies.rss", "webhook")  # pyright: ignore[reportArgumentType]
        assert our_tag == "https://example.com", f"The tag should be 'https://example.com'. But it was '{our_tag}'."

        # Close the reader, so we can delete the directory.
        reader.close()


def test_get_reader_sets_default_global_screenshot_layout() -> None:
    """get_reader should initialize global screenshot layout to desktop when missing."""
    get_reader.cache_clear()

    with tempfile.TemporaryDirectory() as temp_dir:
        Path.mkdir(Path(temp_dir), exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "screenshot_default_db.sqlite")
        reader: Reader = get_reader(custom_location=custom_loc)

        screenshot_layout = reader.get_tag((), "screenshot_layout", None)
        assert screenshot_layout == "desktop", (
            f"Expected default global screenshot layout to be 'desktop', got: {screenshot_layout}"
        )

        reader.close()
        get_reader.cache_clear()


def test_get_reader_preserves_existing_global_screenshot_layout() -> None:
    """get_reader should not overwrite an existing global screenshot layout value."""
    get_reader.cache_clear()

    with tempfile.TemporaryDirectory() as temp_dir:
        Path.mkdir(Path(temp_dir), exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "screenshot_existing_db.sqlite")
        first_reader: Reader = get_reader(custom_location=custom_loc)
        first_reader.set_tag((), "screenshot_layout", "mobile")  # pyright: ignore[reportArgumentType]
        first_reader.close()
        get_reader.cache_clear()

        second_reader: Reader = get_reader(custom_location=custom_loc)
        screenshot_layout = second_reader.get_tag((), "screenshot_layout", None)
        assert screenshot_layout == "mobile", (
            f"Expected existing global screenshot layout to stay 'mobile', got: {screenshot_layout}"
        )

        second_reader.close()
        get_reader.cache_clear()


def test_get_reader_sets_default_global_delivery_mode() -> None:
    """get_reader should initialize global delivery mode to embed when missing."""
    get_reader.cache_clear()

    with tempfile.TemporaryDirectory() as temp_dir:
        Path.mkdir(Path(temp_dir), exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "delivery_mode_default_db.sqlite")
        reader: Reader = get_reader(custom_location=custom_loc)

        delivery_mode = reader.get_tag((), "delivery_mode", None)
        assert delivery_mode == "embed", f"Expected default global delivery mode to be 'embed', got: {delivery_mode}"

        reader.close()
        get_reader.cache_clear()


def test_get_reader_preserves_existing_global_delivery_mode() -> None:
    """get_reader should not overwrite an existing global delivery mode value."""
    get_reader.cache_clear()

    with tempfile.TemporaryDirectory() as temp_dir:
        Path.mkdir(Path(temp_dir), exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "delivery_mode_existing_db.sqlite")
        first_reader: Reader = get_reader(custom_location=custom_loc)
        first_reader.set_tag((), "delivery_mode", "text")  # pyright: ignore[reportArgumentType]
        first_reader.close()
        get_reader.cache_clear()

        second_reader: Reader = get_reader(custom_location=custom_loc)
        delivery_mode = second_reader.get_tag((), "delivery_mode", None)
        assert delivery_mode == "text", f"Expected existing global delivery mode to stay 'text', got: {delivery_mode}"

        second_reader.close()
        get_reader.cache_clear()


def test_get_reader_enables_autodiscover_plugin() -> None:
    """get_reader should store advertised feed links when HTML parsing fails."""
    get_reader.cache_clear()

    try:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            _serve_autodiscover_html() as feed_url,
            closing(get_reader(custom_location=Path(temp_dir, "autodiscover_db.sqlite"))) as reader,
        ):
            reader.add_feed(feed_url)

            with pytest.raises(ParseError):
                reader.update_feed(feed_url)

            assert reader.get_tag(feed_url, ".reader.autodiscover", None) == [
                {
                    "href": f"{feed_url}rss.xml",
                    "type": "application/rss+xml",
                    "title": "Example",
                }
            ]
    finally:
        get_reader.cache_clear()


def test_make_app_reader_enables_supported_builtin_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supported reader versions should load both built-in plugins explicitly."""
    reader = object()
    make_reader = MagicMock(return_value=reader)
    monkeypatch.setattr(settings_module, "has_plugin", lambda _plugin_name: True)
    monkeypatch.setattr(settings_module, "make_reader", make_reader)

    assert make_app_reader(Path("db.sqlite")) is reader
    make_reader.assert_called_once_with(
        url="db.sqlite",
        plugins=[".ua_fallback", ".autodiscover"],
    )


@pytest.mark.parametrize(
    ("available_plugin", "expected_plugin"),
    [
        (".ua_fallback", ".ua_fallback"),
        (".autodiscover", ".autodiscover"),
    ],
)
def test_make_app_reader_loads_only_available_builtin_plugin(
    monkeypatch: pytest.MonkeyPatch,
    available_plugin: str,
    expected_plugin: str,
) -> None:
    """Reader construction should not receive unavailable built-in plugins."""
    reader = object()
    make_reader = MagicMock(return_value=reader)
    monkeypatch.setattr(settings_module, "has_plugin", lambda plugin_name: plugin_name == available_plugin)
    monkeypatch.setattr(settings_module, "make_reader", make_reader)

    assert make_app_reader(Path("db.sqlite")) is reader
    make_reader.assert_called_once_with(url="db.sqlite", plugins=[expected_plugin])


def test_make_app_reader_preserves_defaults_without_builtin_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reader versions without built-in plugins should start with their defaults."""
    reader = object()
    make_reader = MagicMock(return_value=reader)
    monkeypatch.setattr(settings_module, "has_plugin", lambda _plugin_name: False)
    monkeypatch.setattr(settings_module, "make_reader", make_reader)

    assert make_app_reader(Path("db.sqlite")) is reader
    make_reader.assert_called_once_with(url="db.sqlite")


def test_has_plugin_handles_reader_versions_without_plugins_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older reader versions without a plugins package should be supported."""

    def find_spec(_name: str) -> None:
        raise ModuleNotFoundError

    monkeypatch.setattr(settings_module, "find_spec", find_spec)

    assert has_plugin(".autodiscover") is False
