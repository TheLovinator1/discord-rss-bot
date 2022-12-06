"""
Functions:
    add_feed()
        Add a feed to the reader. This also updates the feed.
    check_feed()
        Check a single feed.
    check_feeds()
        Check all feeds.
    send_to_discord()
        Send entries to Discord.
    update_feed()
        Update a feed.

Classes:
    IfFeedError
        Used in add_feed() and update_feed(). If an error, it will return IfFeedError with error=True.
        If no error, it will return IfFeedError with error=False.

Exceptions:
    NoWebhookFoundError
        Used in send_to_discord(). If no webhook found, it will raise NoWebhookFoundError.
"""

from typing import Any, Iterable

from discord_webhook import DiscordWebhook
from pydantic import BaseModel
from reader import (
    Entry,
    EntryNotFoundError,
    FeedExistsError,
    FeedNotFoundError,
    InvalidFeedURLError,
    ParseError,
    StorageError,
    TagNotFoundError,
)
from requests import Response

from discord_rss_bot.settings import logger, reader


class IfFeedError(BaseModel):
    """Update a feed.

    Attributes:
        feed_url: The feed to update.
        webhook: The webhook to use.
        error: True if error, False if no error.
        err_msg: The error message, if any.
        exception: The exception, if any.
    """

    feed_url: str
    webhook: str
    error: bool
    err_msg: str = ""
    exception: str = ""


class NoWebhookFoundError(Exception):
    """Raises an exception if no webhook is found.

    Used in send_to_discord()."""

    def __init__(self, message) -> None:
        self.message = message

    def __str__(self) -> Any:
        return self.message


def add_feed(feed_url: str, webhook: str, exist_ok=False, allow_invalid_url=False) -> IfFeedError:
    """
    Add a feed to reader. If error occurs, it will return IfFeedError with error=True.

    Args:
        feed_url: The feed to add.
        webhook:  The webhook to use.
        exist_ok:  If the feed already exists, do nothing.
        allow_invalid_url:  If the feed url is invalid, add it anyway.

    Returns:
        IfFeedError: Error or not.
    """
    try:
        reader.add_feed(feed_url, exist_ok=exist_ok, allow_invalid_url=allow_invalid_url)
    except FeedExistsError as error:
        error_msg = "Feed already exists"
        logger.error(error_msg, exc_info=True)
        return IfFeedError(
            error=True,
            err_msg=error_msg,
            feed_url=feed_url,
            webhook=webhook,
            exception=error.message,
        )

    except InvalidFeedURLError as error:
        error_msg = "Invalid feed URL"
        logger.error(error_msg, exc_info=True)
        return IfFeedError(
            error=True,
            err_msg=error_msg,
            feed_url=feed_url,
            webhook=webhook,
            exception=error.message,
        )

    return IfFeedError(error=False, feed_url=feed_url, webhook=webhook)


def check_feed(feed_url: str) -> None:
    """Update a single feed and send its unread entries to Discord.

    We don't need to mark entries as read here, because send_to_discord() does that when sending entries to Discord
    if it was successful.

    Args:
        feed_url: The feed to check.
    """
    if feed_url is None:
        logger.error("No feed URL given")
        send_to_discord(feed_url)
        return
    send_to_discord(feed_url)


def send_to_discord(feed=None) -> None:
    """
    Send entries to Discord.

    If response was not ok, we will log the error and mark the entry as unread, so it will be sent again next time.

    Args:
        feed: The entry to send.

    Raises:
        NoWebhookFoundError: If no webhook is found.

    Returns:
        Response: The response from the webhook.
    """
    reader.update_feeds()

    if feed is None:
        entries: Iterable[Entry] = reader.get_entries(read=False)
    else:
        entries: Iterable[Entry] = reader.get_entries(feed=feed, read=False)

    if not entries:
        logger.info("No entries to send")
        return

    for entry in entries:
        logger.debug(f"Sending entry {entry} to Discord")
        try:
            reader.set_entry_read(entry, True)
            logger.debug(f"New entry: {entry.title}")
        except EntryNotFoundError:
            logger.error("Entry not found", exc_info=True)
            raise
        except StorageError:
            logger.error("Storage error", exc_info=True)
            raise

        try:
            webhook_url: str = str(reader.get_tag(entry.feed.url, "webhook"))
        except TagNotFoundError:
            logger.error("Tag not found", exc_info=True)
            raise
        except StorageError:
            logger.error("Storage error", exc_info=True)
            raise

        if not webhook_url:
            logger.error(f"No webhook found for feed: {entry.feed.url}")
            raise NoWebhookFoundError(f"No webhook found for feed: {entry.feed.url}")

        logger.debug(f"Sending to webhook: {webhook_url}")
        webhook_message: str = f":robot: :mega: {entry.title}\n{entry.link}"
        webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, content=webhook_message, rate_limit_retry=True)
        response: Response = webhook.execute()
        if not response.ok:
            logger.error(f"Error: {response.status_code} {response.reason}")
            reader.set_entry_read(entry, False)


def update_feed(feed_url: str, webhook: str) -> IfFeedError:
    """
    Update a feed.

    Args:
        feed_url: The feed to update.
        webhook: The webhook to use.

    Returns:
        IfFeedError: Error or not.
    """
    try:
        reader.update_feed(feed_url)

    except FeedNotFoundError as error:
        error_msg = "Feed not found"
        logger.error(error_msg, exc_info=True)
        return IfFeedError(
            error=True,
            err_msg=error_msg,
            feed_url=feed_url,
            webhook=webhook,
            exception=error.message,
        )

    except ParseError as error:
        error_msg = "An error occurred while getting/parsing feed"
        logger.error(error_msg, exc_info=True)
        return IfFeedError(
            error=True,
            err_msg=error_msg,
            feed_url=feed_url,
            webhook=webhook,
            exception=error.message,
        )

    except StorageError as error:
        error_msg = "An exception was raised by the underlying storage"
        logger.error(error_msg, exc_info=True)
        return IfFeedError(
            error=True,
            err_msg=error_msg,
            feed_url=feed_url,
            webhook=webhook,
            exception=error.message,
        )

    return IfFeedError(error=False, feed_url=feed_url, webhook=webhook)
