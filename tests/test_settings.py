import os
import pathlib
import tempfile

from platformdirs import user_data_dir
from reader import Reader

from discord_rss_bot.settings import (
    data_dir,
    default_custom_message,
    get_db_location,
    get_reader,
    get_webhook_for_entry,
)


def test_get_db_location() -> None:
    """Test getting the database location."""
    with tempfile.TemporaryDirectory() as temp_dir:
        custom_loc: str = os.path.join(temp_dir, "test_db.sqlite")

        # File should not exist yet.
        assert not os.path.exists(custom_loc)

        # Create the file and check if it exists.
        assert get_db_location(custom_location=custom_loc) == os.path.join(temp_dir, "test_db.sqlite")

        # Test with the default location
        loc: str = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True)
        assert get_db_location() == os.path.join(loc, "db.sqlite")


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

        for entry in custom_reader.get_entries():
            assert get_webhook_for_entry(custom_reader=custom_reader, entry=entry) == ""

        # Add a webhook to the database.
        custom_reader.set_tag("https://www.reddit.com/r/movies.rss", "webhook", "https://example.com")  # type: ignore
        our_tag: str = custom_reader.get_tag("https://www.reddit.com/r/movies.rss", "webhook")  # type: ignore
        assert our_tag == "https://example.com"

        # Close the reader, so we can delete the directory.
        custom_reader.close()
