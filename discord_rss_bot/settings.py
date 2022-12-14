"""This module contains functions for reading and writing settings and configuration files.

Functions:
    create_settings_file:
        Create the settings file if it doesn't exist.
    get_db_file:
        Where we store the database file.
    read_settings_file:
        Read the settings file and return it as a dict.

Variables:
    data_dir:
        Where we store the database and settings file.
"""
import logging
import os

from platformdirs import user_data_dir
from reader import Reader, make_reader
from tomlkit import comment, document, parse, table
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument

logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] [%(funcName)s:%(lineno)d] %(message)s")
data_dir: str = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True)
os.makedirs(data_dir, exist_ok=True)


def create_settings_file(settings_file_location) -> None:
    """Create the settings file if it doesn't exist.

    Args:
        settings_file_location: The location of the settings file.

    Returns:
        None
    """
    webhooks: Table = table()
    webhooks.add(comment('"First webhook" = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"'))
    webhooks.add(comment('"Second webhook" = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"'))

    database: Table = table()
    database.add(comment('"location" = "/path/to/database/file"'))

    doc: TOMLDocument = document()
    doc.add("webhooks", webhooks)
    doc.add("database", database)

    # Write the settings file
    with open(settings_file_location, "w", encoding="utf-8") as f:
        f.write(doc.as_string())


def get_db_location(custom_location: str = "") -> str:
    """Where we store the database file.

    Args:
        custom_location: Where the database file should be stored. This should be with the file name.

    Returns:
        The database location.
    """
    # Use the custom location if it is provided.
    return custom_location or os.path.join(data_dir, "db.sqlite")


def read_settings_file(custom_location: str = "") -> TOMLDocument:
    """Read the settings file and return the settings as a dict.

    Args:
        custom_location: The name of the settings file, defaults to settings.toml.

    Returns:
        dict: The settings file as a dict.
    """
    # Use the custom location if it is provided.
    settings_location: str = custom_location or os.path.join(data_dir, "settings.toml")

    # Create the settings file if it doesn't exist.
    if not os.path.exists(settings_location):
        create_settings_file(settings_location)

    # Read the settings file and return it as a dict.
    with open(settings_location, encoding="utf-8") as f:
        return parse(f.read())


def get_reader(custom_location: str = "") -> Reader:
    """Get the reader.

    Args:
        custom_location: The location of the database file.

    """
    db_location: str = get_db_location(custom_location)
    return make_reader(url=db_location)
