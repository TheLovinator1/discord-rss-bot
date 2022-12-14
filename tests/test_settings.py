import os
import pathlib
import tempfile

from platformdirs import user_data_dir
from reader import Reader
from tomlkit import TOMLDocument

from discord_rss_bot.settings import (
    create_settings_file,
    data_dir,
    get_db_location,
    get_reader,
    read_settings_file,
)


def test_read_settings_file() -> None:
    """Test reading the settings file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        custom_loc: str = os.path.join(temp_dir, "test_settings.toml")

        # File should not exist yet should this should fail.
        assert not os.path.exists(custom_loc)

        # Create the file.
        settings: TOMLDocument = read_settings_file(custom_location=custom_loc)

        # Check if the settings file is a toml document.
        assert isinstance(settings, TOMLDocument)

        # Check if file exists
        assert os.path.exists(os.path.join(temp_dir, "test_settings.toml"))

        # Check if the file has the correct contents
        assert settings["webhooks"] == {}
        assert settings["database"] == {}


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


def test_create_settings_file() -> None:
    """Test creating the settings file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        settings_file_location: str = os.path.join(temp_dir, "settings.toml")

        # File should not exist yet.
        assert not os.path.exists(settings_file_location)

        # Create the file and check if it exists.
        create_settings_file(settings_file_location)
        assert os.path.exists(settings_file_location)


def test_data_dir() -> None:
    """Test the data directory."""
    assert os.path.exists(data_dir)
