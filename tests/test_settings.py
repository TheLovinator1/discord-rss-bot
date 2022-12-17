import os
import pathlib
import tempfile

from platformdirs import user_data_dir
from reader import Reader

from discord_rss_bot.settings import (
    data_dir,
    get_db_location,
    get_reader,
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
