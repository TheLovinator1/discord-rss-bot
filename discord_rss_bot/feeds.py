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

from discord_webhook import DiscordWebhook
from pydantic import BaseModel
from reader import FeedExistsError, FeedNotFoundError, InvalidFeedURLError, ParseError, StorageError
from requests import Response

from discord_rss_bot.settings import logger, reader


def check_feeds() -> None:
    """Check all feeds"""
    reader.update_feeds()
    entries = reader.get_entries(read=False)
    send_to_discord(entries)


def check_feed(feed_url: str) -> None:
    """Check a single feed"""
    reader.update_feeds()
    entry = reader.get_entries(feed=feed_url, read=False)
    send_to_discord(entry)


class NoWebhookFoundError(Exception):
    """No webhook found error."""

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message


def send_to_discord(entry) -> Response:
    """
    Send entries to Discord.

    Args:
        entry: The entry to send.

    Returns:
        Response: The response from the webhook.
    """

    reader.mark_entry_as_read(entry)
    logger.debug(f"New entry: {entry.title}")

    webhook_url = reader.get_tag(entry.feed.url, "webhook")
    if not webhook_url:
        logger.error(f"No webhook found for feed: {entry.feed.url}")
        raise NoWebhookFoundError(f"No webhook found for feed: {entry.feed.url}")

    logger.debug(f"Sending to webhook: {webhook_url}")
    webhook = DiscordWebhook(url=str(webhook_url), content=f":robot: :mega: New entry: {entry.title}\n"
                                                           f"{entry.link}", rate_limit_retry=True)
    response = webhook.execute()
    if not response.ok:
        # TODO: Send error to discord
        logger.error(f"Error: {response.status_code} {response.reason}")
        reader.mark_entry_as_unread(entry)
    return response


class IfFeedError(BaseModel):
    """Update a feed."""
    feed_url: str
    webhook: str
    error: bool
    err_msg: str = ""
    exception: str = ""


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
        return IfFeedError(error=True, err_msg=error_msg, feed_url=feed_url, webhook=webhook, exception=error.message)

    except ParseError as error:
        error_msg = "An error occurred while getting/parsing feed"
        logger.error(error_msg, exc_info=True)
        return IfFeedError(error=True, err_msg=error_msg, feed_url=feed_url, webhook=webhook, exception=error.message)

    except StorageError as error:
        error_msg = "An exception was raised by the underlying storage"
        logger.error(error_msg, exc_info=True)
        return IfFeedError(error=True, err_msg=error_msg, feed_url=feed_url, webhook=webhook, exception=error.message)

    return IfFeedError(error=False, feed_url=feed_url, webhook=webhook)


def add_feed(feed_url: str, webhook: str, exist_ok=False, allow_invalid_url=False) -> IfFeedError:
    """
    Add a feed.

    Args:
        feed_url: The feed to add.
        webhook:  The webhook to use.
        exist_ok:  If the feed already exists, do nothing.
        allow_invalid_url:  If the feed url is invalid, add it anyway.

    Returns:
        IfFeedError: Error or not.
    """
    try:
        reader.add_feed(feed=feed_url, exist_ok=exist_ok, allow_invalid_url=allow_invalid_url)
    except FeedExistsError as error:
        error_msg = "Feed already exists"
        logger.error(f"{error_msg}: {error}")
        return IfFeedError(error=True, err_msg=error_msg, feed_url=feed_url, webhook=webhook, exception=error.message)

    except InvalidFeedURLError as error:
        error_msg = "Invalid feed URL"
        logger.error(f"{error_msg}: {error}")
        return IfFeedError(error=True, err_msg=error_msg, feed_url=feed_url, webhook=webhook, exception=error.message)
