import os
import pathlib
import tempfile

from reader import Reader

from discord_rss_bot.settings import data_dir, default_custom_message, get_reader


def test_reader() -> None:
    """Test the reader."""
    reader: Reader = get_reader()
    assert isinstance(reader, Reader)

    # Test the reader with a custom location.
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory
        os.makedirs(temp_dir, exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "custom_loc_db.sqlite")
        custom_reader: Reader = get_reader(custom_location=str(custom_loc))
        assert isinstance(custom_reader, Reader)

        # Close the reader, so we can delete the directory.
        custom_reader.close()


def test_data_dir() -> None:
    """Test the data directory."""
    assert os.path.exists(data_dir)


def test_default_custom_message() -> None:
    """Test the default custom message."""
    assert "{{entry_title}}\n{{entry_link}}" == default_custom_message


def test_get_webhook_for_entry() -> None:
    """Test getting the webhook for an entry."""
    # Test with a custom reader.
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory
        os.makedirs(temp_dir, exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "custom_loc_db.sqlite")
        custom_reader: Reader = get_reader(custom_location=str(custom_loc))

        # Add a feed to the database.
        custom_reader.add_feed("https://www.reddit.com/r/movies.rss")
        custom_reader.update_feed("https://www.reddit.com/r/movies.rss")

        # Add a webhook to the database.
        custom_reader.set_tag("https://www.reddit.com/r/movies.rss", "webhook", "https://example.com")  # type: ignore
        our_tag: str = custom_reader.get_tag("https://www.reddit.com/r/movies.rss", "webhook")  # type: ignore
        assert our_tag == "https://example.com"

        # Close the reader, so we can delete the directory.
        custom_reader.close()
