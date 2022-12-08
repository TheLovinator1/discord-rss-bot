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
    logger:
        The logger for this program.
"""
import logging
import os

from platformdirs import user_data_dir
from reader import Reader, make_reader
from tomlkit import comment, document, parse, table
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument

logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] [%(funcName)s:%(lineno)d] %(message)s")
logger: logging.Logger = logging.getLogger(__name__)

data_dir: str = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True)
os.makedirs(data_dir, exist_ok=True)


def create_settings_file(settings_file_location) -> None:
    """Create the settings file if it doesn't exist.

    Args:
        settings_file_location: The location of the settings file.

    Returns:
        None
    """
    logger.debug(f"{settings_file_location=}")

    webhooks: Table = table()
    webhooks.add(comment('"First webhook" = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"'))
    webhooks.add(comment('"Second webhook" = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"'))

    database: Table = table()
    database.add(comment('"location" = "/path/to/database/file"'))

    doc: TOMLDocument = document()
    doc.add("webhooks", webhooks)
    doc.add("database", database)

    # Write the settings file
    with open(settings_file_location, "w") as f:
        f.write(doc.as_string())


def get_db_location(custom_name: str = "db.sqlite") -> str:
    """Where we store the database file.

    Args:
        custom_name: The name of the database file, defaults to db.sqlite.

    Returns:
        The database location.
    """
    db_name = os.path.join(data_dir, custom_name)
    logger.debug(f"{db_name=}{f', with custom db name {custom_name!r}' if custom_name != 'db.sqlite' else ''}")

    return db_name


def read_settings_file(custom_name: str = "settings.toml") -> TOMLDocument:
    """Read the settings file and return the settings as a dict.

    Args:
        custom_name: The name of the settings file, defaults to settings.toml.

    Returns:
        dict: The settings file as a dict.
    """

    settings_file = os.path.join(data_dir, custom_name)
    logger.debug(f"{settings_file=}{f', with custom db name {custom_name!r}' if custom_name != 'db.sqlite' else ''}")

    with open(settings_file, encoding="utf-8") as f:
        contents: TOMLDocument = parse(f.read())
        logger.debug(f"{contents=}")

        return contents


db_location: str = get_db_location()
reader: Reader = make_reader(db_location)
