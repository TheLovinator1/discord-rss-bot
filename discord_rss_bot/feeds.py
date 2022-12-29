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

from discord_rss_bot import settings
from discord_rss_bot.blacklist import should_be_skipped
from discord_rss_bot.settings import get_reader
from discord_rss_bot.whitelist import has_white_tags, should_be_sent


def send_to_discord(custom_reader: Reader | None = None, feed=None, do_once=False) -> None:
    """
    Send entries to Discord.

    If response was not ok, we will log the error and mark the entry as unread, so it will be sent again next time.

    Args:
        custom_reader: If we should use a custom reader instead of the default one.
        feed: The feed to send to Discord.
        do_once: If we should only send one entry. This is used in the test.

    Returns:
        Response: The response from the webhook.
    """
    # Get the default reader if we didn't get a custom one.
    reader: Reader = get_reader() if custom_reader is None else custom_reader

    # Check for new entries for every feed.
    reader.update_feeds()

    # If feed is not None we will only get the entries for that feed.
    if feed is None:
        entries: Iterable[Entry] = reader.get_entries(read=False)
    else:
        entries: Iterable[Entry] = reader.get_entries(feed=feed, read=False)

    for entry in entries:
        # Set the webhook to read, so we don't send it again.
        reader.set_entry_read(entry, True)  # type: ignore

        webhook_url = settings.get_webhook_for_entry(reader, entry)

        webhook_message: str = f":robot: :mega: {entry.title}\n{entry.link}"
        webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, content=webhook_message, rate_limit_retry=True)

        # Check if the entry has a whitelist
        if has_white_tags(reader, feed):
            # Only send the entry if it is whitelisted, otherwise, mark it as read and continue.
            if should_be_sent(reader, entry):
                response: Response = webhook.execute()
                reader.set_entry_read(entry, True)  # type: ignore
                if not response.ok:
                    print(f"Error sending to Discord: {response.text}")
                    reader.set_entry_read(entry, False)  # type: ignore
            else:
                reader.set_entry_read(entry, True)  # type: ignore
                continue

        # Check if the entry is blacklisted, if it is, mark it as read and continue.
        if should_be_skipped(reader, entry):
            print(f"Blacklisted entry: {entry.title}, not sending to Discord.")
            reader.set_entry_read(entry, True)  # type: ignore
            continue

        # It was not blacklisted, and not forced through whitelist, so we will send it to Discord.
        response: Response = webhook.execute()
        if not response.ok:
            print(f"Error sending to Discord: {response.text}")
            reader.set_entry_read(entry, False)  # type: ignore

        # If we only want to send one entry, we will break the loop. This is used when testing this function.
        if do_once:
            break

    # Update the search index.
    reader.update_search()
