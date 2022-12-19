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

logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] [%(funcName)s:%(lineno)d] %(message)s")
data_dir: str = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True)
os.makedirs(data_dir, exist_ok=True)


def get_db_location(custom_location: str = "") -> str:
    """Where we store the database file.

    Args:
        custom_location: Where the database file should be stored. This should be with the file name.

    Returns:
        The database location.
    """
    # Use the custom location if it is provided.
    return custom_location or os.path.join(data_dir, "db.sqlite")


def get_reader(custom_location: str = "") -> Reader:
    """Get the reader.

    Args:
        custom_location: The location of the database file.

    """
    db_location: str = get_db_location(custom_location)
    return make_reader(url=db_location)


def get_webhooks(reader: Reader) -> list[dict[str, str]]:
    """
    Get current webhooks from the database if they exist otherwise use an empty list.

    Args:
        reader: The reader to use.

    Returns:
        list[dict[str, str]]: The webhooks.
    """
    webhooks: list[dict[str, str]] = []
    if reader.get_tags(()) is not None:
        for tag in reader.get_tag_keys(()):
            if tag == "webhooks":
                webhooks = reader.get_tag((), "webhooks")
            break
    return webhooks
