from __future__ import annotations

import pathlib
import tempfile
from pathlib import Path

from reader import Reader

from discord_rss_bot.settings import data_dir
from discord_rss_bot.settings import default_custom_message
from discord_rss_bot.settings import get_reader


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
