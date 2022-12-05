import logging
import os
from pathlib import Path

from platformdirs import user_data_dir
from reader import make_reader
from tomlkit import TOMLDocument, comment, document, parse, table

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] [%(funcName)s:%(lineno)d] %(message)s",
)
logger = logging.getLogger(__name__)

# For get_data_dir()
data_directory = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True)


def get_data_dir(data_dir: str = data_directory) -> Path:
    """
    Get the data directory. This is where the database file and config file are stored.

    Args:
        data_dir: The application directory, defaults to user_data_dir().

    Returns:
        Path: The application directory.
    """
    if data_dir != user_data_dir("discord_rss_bot"):
        logger.info(f"Using custom data directory: {data_dir}")

    # Use the environment variable if it exists instead of the default app dir.
    data_dir = os.getenv("DATA_DIR") or data_dir

    logger.debug(f"Data directory: {data_dir}")

    # Create the data directory if it doesn't exist
    os.makedirs(data_dir, exist_ok=True)

    return Path(data_dir)


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
    data_dir = get_data_dir()
    db_location: Path = Path(os.path.join(data_dir, custom_db_name))

    # Use the environment variable if it exists instead of the default db name.
    db_file = os.getenv("DATABASE_LOCATION") or db_location
    logger.debug(f"Database file: {db_file}")

    return Path(db_file)


def _create_settings_file(settings_file) -> None:
    """Create the settings file if it doesn't exist."""
    logger.debug(f"Settings file: {settings_file}")

    # [webhooks]
    # Both options are commented out by default.
    webhooks = table()
    webhooks.add(comment('"First webhook" = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"'))
    webhooks.add(comment('"Second webhook" = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"'))

    # [database]
    # Option is commented out by default.
    database = table()
    database.add(comment('"location" = "/path/to/database/file"'))

    doc = document()
    doc.add("webhooks", webhooks)
    doc.add("database", database)

    logger.debug(f"Settings file: {doc}")
    logger.debug(f"Settings file as TOML: {doc.as_string()}")

    # Write the settings file
    with open(settings_file, "w") as f:
        f.write(doc.as_string())


def read_settings_file(custom_settings_name: str = "settings.toml") -> TOMLDocument:
    """Read the settings file

    Args:
        custom_settings_name: The name of the settings file, defaults to settings.toml.

    Returns:
        dict: The settings file as a dict.
    """
    if custom_settings_name != "settings.toml":
        logger.info(f"Using custom name for settings file: {custom_settings_name}")

    # Store the database file in the data directory
    data_dir = get_data_dir()
    settings_file_location: Path = Path(os.path.join(data_dir, custom_settings_name))

    # Use the environment variable if it exists instead of the default db name.
    settings_file = os.getenv("SETTINGS_FILE_LOCATION") or settings_file_location
    logger.debug(f"Settings file: {settings_file}")

    # Create the settings file if it doesn't exist
    if not os.path.exists(settings_file):
        _create_settings_file(settings_file)

    with open(settings_file, encoding="utf-8") as f:
        data = parse(f.read())
        logger.debug(f"Contents of settings file: {data}")

        return data


reader = make_reader(str(get_db_file()))
