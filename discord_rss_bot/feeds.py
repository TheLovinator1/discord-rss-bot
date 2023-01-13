from typing import Iterable

from discord_webhook import DiscordWebhook
from reader import Entry, Feed, Reader
from requests import Response

from discord_rss_bot import custom_message, settings
from discord_rss_bot.filter.blacklist import should_be_skipped
from discord_rss_bot.filter.whitelist import has_white_tags, should_be_sent
from discord_rss_bot.settings import get_reader


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
        entries: Iterable[Entry] = reader.get_entries(feed=feed, read=False)

    for entry in entries:
        # Set the webhook to read, so we don't send it again.
        reader.set_entry_read(entry, True)

        webhook_url: str | None = settings.get_webhook_for_entry(reader, entry)

        webhook_message: str = f":robot: :mega: {entry.title}\n{entry.link}"

        if webhook_url is None:
            print(f"Error: No webhook found for feed: {entry.feed.title}")
            continue

        webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, content=webhook_message, rate_limit_retry=True)

        if custom_message.get_custom_message(reader, entry.feed) != "":
            print("Custom message found, replacing tags.")
            webhook.content = custom_message.replace_tags(entry=entry, feed=entry.feed)

        print(f"Webhook content: {webhook.content}")
        if feed is not None and has_white_tags(reader, feed):
            # Only send the entry if it is whitelisted, otherwise, mark it as read and continue.
            if should_be_sent(reader, entry):
                response: Response = webhook.execute()
                reader.set_entry_read(entry, True)
                if not response.ok:
                    print(f"Error sending to Discord: {response.text}")
                    reader.set_entry_read(entry, False)
            else:
                reader.set_entry_read(entry, True)
                continue

        # Check if the entry is blacklisted, if it is, mark it as read and continue.
        if should_be_skipped(reader, entry):
            print(f"Blacklisted entry: {entry.title}, not sending to Discord.")
            reader.set_entry_read(entry, True)
            continue

        # It was not blacklisted, and not forced through whitelist, so we will send it to Discord.
        response: Response = webhook.execute()
        if not response.ok:
            print(f"Error sending to Discord: {response.text}")
            reader.set_entry_read(entry, False)

        # If we only want to send one entry, we will break the loop. This is used when testing this function.
        if do_once:
            break

    # Update the search index.
    reader.update_search()
