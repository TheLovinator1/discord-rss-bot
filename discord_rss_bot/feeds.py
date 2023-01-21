from typing import Iterable

from discord_webhook import DiscordWebhook
from reader import Entry, Feed, Reader
from requests import Response

from discord_rss_bot import custom_message, settings
from discord_rss_bot.filter.blacklist import should_be_skipped
from discord_rss_bot.filter.whitelist import has_white_tags, should_be_sent
from discord_rss_bot.settings import default_custom_message, get_reader


def get_entry_from_id(entry_id: str, custom_reader: Reader | None = None) -> Entry | None:
    """
    Get an entry from an ID.

    Args:
        entry_id: The ID of the entry.
        custom_reader: If we should use a custom reader instead of the default one.

    Returns:
        Entry: The entry with the ID. None if it doesn't exist.
    """
    # Get the default reader if we didn't get a custom one.
    reader: Reader = get_reader() if custom_reader is None else custom_reader

    # Get the entry from the ID, or return None if it doesn't exist.
    return next((entry for entry in reader.get_entries() if entry.id == entry_id), None)


def send_entry_to_discord(entry: Entry, custom_reader: Reader | None = None):
    """
    Send a single entry to Discord.

    Args:
        entry: The entry to send to Discord.
    """
    # Get the default reader if we didn't get a custom one.
    reader: Reader = get_reader() if custom_reader is None else custom_reader

    # Get the webhook URL for the entry.
    webhook_url: str = settings.get_webhook_for_entry(reader, entry)
    if not webhook_url:
        return "No webhook URL found."

    # Try to get the custom message for the feed. If the user has none, we will use the default message.
    if custom_message.get_custom_message(reader, entry.feed) != "":
        webhook_message = custom_message.replace_tags(entry=entry, feed=entry.feed)  # type: ignore
    else:
        webhook_message: str = default_custom_message

    # Create the webhook.
    webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, content=webhook_message, rate_limit_retry=True)

    response: Response = webhook.execute()
    if not response.ok:
        return f"Error sending entry to Discord: {response.text}"


def send_to_discord(custom_reader: Reader | None = None, feed: Feed | None = None, do_once: bool = False) -> None:
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
        entries = reader.get_entries(feed=feed, read=False)

    # Loop through the unread entries.
    for entry in entries:
        # Set the webhook to read, so we don't send it again.
        reader.set_entry_read(entry, True)

        # Get the webhook URL for the entry. If it is None, we will continue to the next entry.
        webhook_url: str = settings.get_webhook_for_entry(reader, entry)
        if not webhook_url:
            continue

        # If the user has set the custom message to an empty string, we will use the default message, otherwise we will
        # use the custom message.
        if custom_message.get_custom_message(reader, entry.feed) != "":
            webhook_message = custom_message.replace_tags(entry=entry, feed=entry.feed)  # type: ignore
        else:
            webhook_message: str = default_custom_message

        # Create the webhook.
        webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, content=webhook_message, rate_limit_retry=True)

        # Check if the feed has a whitelist, and if it does, check if the entry is whitelisted.
        if feed is not None and has_white_tags(reader, feed):
            if should_be_sent(reader, entry):
                response: Response = webhook.execute()
                reader.set_entry_read(entry, True)
                if not response.ok:
                    reader.set_entry_read(entry, False)
            else:
                reader.set_entry_read(entry, True)
                continue

        # Check if the entry is blacklisted, if it is, mark it as read and continue.
        if should_be_skipped(reader, entry):
            reader.set_entry_read(entry, True)
            continue

        # It was not blacklisted, and not forced through whitelist, so we will send it to Discord.
        response: Response = webhook.execute()
        if not response.ok:
            reader.set_entry_read(entry, False)

        # If we only want to send one entry, we will break the loop. This is used when testing this function.
        if do_once:
            break

    # Update the search index.
    reader.update_search()
