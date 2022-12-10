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
from reader import Entry
from requests import Response

from discord_rss_bot.settings import reader


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
    if feed is None:
        reader.update_feeds()
        entries: Iterable[Entry] = reader.get_entries(read=False)
    else:
        reader.update_feed(feed)
        entries: Iterable[Entry] = reader.get_entries(feed=feed, read=False)

    for entry in entries:
        reader.set_entry_read(entry, True)
        webhook_url: str = str(reader.get_tag(entry.feed_url, "webhook"))
        webhook_message: str = f":robot: :mega: {entry.title}\n{entry.link}"
        webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, content=webhook_message, rate_limit_retry=True)

        response: Response = webhook.execute()
        if not response.ok:
            reader.set_entry_read(entry, False)

    reader.update_search()
