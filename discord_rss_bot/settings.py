"""This module contains functions for reading and writing settings and configuration files.

Functions:
    create_settings_file:
        Create the settings file if it doesn't exist.
    get_data_dir:
        Path to the data directory. This is where the database file and config file are stored.
    get_db_file:
        Where we store the database file.
    read_settings_file:
        Read the settings file and return it as a dict.

Variables:
    data_directory:
        The application directory, defaults to user_data_dir().
    logger:
        The logger for this program.
"""
import logging
import os
from pathlib import Path

from platformdirs import user_data_dir
from reader import Reader, make_reader
from tomlkit import comment, document, parse, table
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument

logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] [%(funcName)s:%(lineno)d] %(message)s")
logger: logging.Logger = logging.getLogger(__name__)

# For get_data_dir()
data_directory: str = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True)


def create_settings_file(settings_file) -> None:
    """Create the settings file if it doesn't exist."""
    logger.debug(f"Settings file: {settings_file}")

    # [webhooks]
    # Both options are commented out by default.
    webhooks: Table = table()
    webhooks.add(comment('"First webhook" = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"'))
    webhooks.add(comment('"Second webhook" = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"'))

    # [database]
    # Option is commented out by default.
    database: Table = table()
    database.add(comment('"location" = "/path/to/database/file"'))

    doc: TOMLDocument = document()
    doc.add("webhooks", webhooks)
    doc.add("database", database)

    logger.debug(f"Settings file: {doc}")
    logger.debug(f"Settings file as TOML: {doc.as_string()}")

    # Write the settings file
    with open(settings_file, "w") as f:
        f.write(doc.as_string())


def get_db_file(custom_db_name: str = "db.sqlite") -> Path:
    """Where we store the database file

    Args:
        custom_db_name: The name of the database file, defaults to db.sqlite.

    Returns:
        Path: The database file.
    """
    if custom_db_name != "db.sqlite":
        logger.info(f"Using custom database file: {custom_db_name}")

    # Store the database file in the data directory
    data_dir = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True)
    os.makedirs(data_dir, exist_ok=True)

    db_location: Path = Path(os.path.join(data_dir, custom_db_name))

    logger.debug(f"Database file: {db_location}")

    return Path(db_location)


def read_settings_file(custom_settings_name: str = "settings.toml") -> TOMLDocument:
    """Read the settings file

    Args:
        custom_settings_name: The name of the settings file, defaults to settings.toml.

    Returns:
        dict: The settings file as a dict.
    """
    if custom_settings_name != "settings.toml":
        logger.info(f"Using custom name for settings file: {custom_settings_name}")

    # Store the database file in the data directory.
    data_dir = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True)
    os.makedirs(data_dir, exist_ok=True)

    settings_file_location: Path = Path(os.path.join(data_dir, custom_settings_name))

    # Create the settings file if it doesn't exist
    if not os.path.exists(settings_file_location):
        create_settings_file(settings_file_location)

    with open(settings_file_location, encoding="utf-8") as f:
        data: TOMLDocument = parse(f.read())
        logger.debug(f"Contents of settings file: {data}")

        return data


reader: Reader = make_reader(str(get_db_file()))
