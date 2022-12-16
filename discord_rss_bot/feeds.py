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

from typing import Iterable

from discord_webhook import DiscordWebhook
from reader import Entry, Reader
from requests import Response

from discord_rss_bot.settings import get_reader


def send_to_discord(custom_reader: Reader | None = None, feed=None, do_once=False) -> None:
    """
    Send entries to Discord.

    If response was not ok, we will log the error and mark the entry as unread, so it will be sent again next time.

    Args:
        custom_reader: If we should use a custom reader instead of the default one.
        feed: The entry to send.
        do_once: If we should only send one entry. This is used in the test.

    Returns:
        Response: The response from the webhook.
    """
    # Get the default reader if we didn't get a custom one.
    reader: Reader = get_reader() if custom_reader is None else custom_reader

    # If we should get all entries, or just the entries from a specific feed.
    if feed is None:
        reader.update_feeds()
        entries: Iterable[Entry] = reader.get_entries(read=False)
    else:
        reader.update_feed(feed)
        entries: Iterable[Entry] = reader.get_entries(feed=feed, read=False)

    for entry in entries:
        # Set the webhook to read, so we don't send it again.
        reader.set_entry_read(entry, True)

        # Get the webhook from the feed.
        webhook_url: str = str(reader.get_tag(entry.feed_url, "webhook"))
        webhook_message: str = f":robot: :mega: {entry.title}\n{entry.link}"
        webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, content=webhook_message, rate_limit_retry=True)

        # Send the webhook.
        response: Response = webhook.execute()
        if not response.ok:
            reader.set_entry_read(entry, False)

        # If we only want to send one entry, we will break the loop. This is used when testing this function.
        if do_once:
            break

    reader.update_search()
