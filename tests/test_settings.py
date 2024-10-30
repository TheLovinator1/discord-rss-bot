import pathlib
import tempfile
from pathlib import Path

from reader import Reader

from discord_rss_bot.settings import data_dir, default_custom_message, get_reader


def test_reader() -> None:
    """Test the reader."""
    reader: Reader = get_reader()
    assert isinstance(reader, Reader), f"The reader should be an instance of Reader. But it was '{type(reader)}'."

    # Test the reader with a custom location.
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory
        Path.mkdir(Path(temp_dir), exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "custom_loc_db.sqlite")
        custom_reader: Reader = get_reader(custom_location=str(custom_loc))
        assert_msg = f"The custom reader should be an instance of Reader. But it was '{type(custom_reader)}'."
        assert isinstance(custom_reader, Reader), assert_msg

        # Close the reader, so we can delete the directory.
        custom_reader.close()


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
        custom_reader: Reader = get_reader(custom_location=str(custom_loc))

        # Add a feed to the database.
        custom_reader.add_feed("https://www.reddit.com/r/movies.rss")
        custom_reader.update_feed("https://www.reddit.com/r/movies.rss")

        # Add a webhook to the database.
        custom_reader.set_tag("https://www.reddit.com/r/movies.rss", "webhook", "https://example.com")  # type: ignore
        our_tag: str = custom_reader.get_tag("https://www.reddit.com/r/movies.rss", "webhook")  # type: ignore
        assert our_tag == "https://example.com", f"The tag should be 'https://example.com'. But it was '{our_tag}'."

        # Close the reader, so we can delete the directory.
        custom_reader.close()
