import logging
import os

from platformdirs import user_data_dir
from reader import Entry, Reader, TagNotFoundError, make_reader  # type: ignore

logging_format: str = "[%(asctime)s] [%(funcName)s:%(lineno)d] %(message)s"
logging.basicConfig(level=logging.INFO, format=logging_format)
data_dir: str = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True)
os.makedirs(data_dir, exist_ok=True)

default_custom_message: str = "{{entry_title}}\n{{entry_link}}"


def get_webhook_for_entry(custom_reader: Reader, entry: Entry) -> str:
    """
    Get the webhook from the database.

    Args:
        custom_reader: If we should use a custom reader, or the default one.
        entry: The entry to get the webhook for.

    Returns:
        Webhook URL if it has one, returns None if not or error.
    """
    # Get the default reader if we didn't get a custom one.
    reader: Reader = get_reader() if custom_reader is None else custom_reader

    # Get the webhook from the feed.
    # Is None if not found or error.
    webhook_url: str
    try:
        webhook_url = str(reader.get_tag(entry.feed_url, "webhook"))
    except TagNotFoundError:
        webhook_url = ""

    return webhook_url


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


def list_webhooks(reader: Reader) -> list[dict[str, str]]:
    """
    Get current webhooks from the database if they exist otherwise use an empty list.

    Args:
        reader: The reader to use.

    Returns:
        list[dict[str, str]]: The webhooks.
    """
    webhooks: list[dict[str, str]] = []

    # Get global tags
    if reader.get_tags(()) is not None:
        for tag in reader.get_tag_keys(()):
            # Check if the tag is named webhooks
            if tag == "webhooks":
                webhooks = reader.get_tag((), "webhooks")  # type: ignore
            break
    return webhooks
