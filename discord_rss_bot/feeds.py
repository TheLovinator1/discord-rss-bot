from __future__ import annotations

import datetime
import logging
import pprint
from typing import TYPE_CHECKING

from discord_webhook import DiscordEmbed, DiscordWebhook
from fastapi import HTTPException
from reader import Entry, EntryNotFoundError, Feed, FeedExistsError, Reader, ReaderError, StorageError, TagNotFoundError

from discord_rss_bot.custom_message import (
    CustomEmbed,
    get_custom_message,
    replace_tags_in_embed,
    replace_tags_in_text_message,
)
from discord_rss_bot.filter.blacklist import entry_should_be_skipped
from discord_rss_bot.filter.whitelist import has_white_tags, should_be_sent
from discord_rss_bot.is_url_valid import is_url_valid
from discord_rss_bot.missing_tags import add_missing_tags
from discord_rss_bot.settings import default_custom_message, get_reader

if TYPE_CHECKING:
    from collections.abc import Iterable

    from requests import Response

logger: logging.Logger = logging.getLogger(__name__)


def send_entry_to_discord(entry: Entry, custom_reader: Reader | None = None) -> str | None:
    """Send a single entry to Discord.

    Args:
        entry: The entry to send to Discord.
        custom_reader: The reader to use. If None, the default reader will be used.

    Returns:
        str | None: The error message if there was an error, otherwise None.
    """
    # Get the default reader if we didn't get a custom one.
    reader: Reader = get_reader() if custom_reader is None else custom_reader

    # Get the webhook URL for the entry.
    webhook_url: str = str(reader.get_tag(entry.feed_url, "webhook", ""))
    if not webhook_url:
        return "No webhook URL found."

    webhook_message: str = ""

    # Try to get the custom message for the feed. If the user has none, we will use the default message.
    # This has to be a string for some reason so don't change it to "not custom_message.get_custom_message()"
    if get_custom_message(reader, entry.feed) != "":  # noqa: PLC1901
        webhook_message: str = replace_tags_in_text_message(entry=entry)

    if not webhook_message:
        webhook_message = "No message found."

    # Create the webhook.
    try:
        should_send_embed = bool(reader.get_tag(entry.feed, "should_send_embed"))
    except TagNotFoundError:
        logger.exception("No should_send_embed tag found for feed: %s", entry.feed.url)
        should_send_embed = True
    except StorageError:
        logger.exception("Error getting should_send_embed tag for feed: %s", entry.feed.url)
        should_send_embed = True

    # YouTube feeds should never use embeds
    if is_youtube_feed(entry.feed.url):
        should_send_embed = False

    if should_send_embed:
        webhook = create_embed_webhook(webhook_url, entry)
    else:
        webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, content=webhook_message, rate_limit_retry=True)

    execute_webhook(webhook, entry)
    return None


def set_description(custom_embed: CustomEmbed, discord_embed: DiscordEmbed) -> None:
    """Set the description of the embed.

    Args:
        custom_embed (custom_message.CustomEmbed): The custom embed to get the description from.
        discord_embed (DiscordEmbed): The Discord embed to set the description on.
    """
    # Its actually 2048, but we will use 2000 to be safe.
    max_description_length: int = 2000
    embed_description: str = custom_embed.description
    embed_description = (
        f"{embed_description[:max_description_length]}..."
        if len(embed_description) > max_description_length
        else embed_description
    )
    discord_embed.set_description(embed_description) if embed_description else None


def set_title(custom_embed: CustomEmbed, discord_embed: DiscordEmbed) -> None:
    """Set the title of the embed.

    Args:
        custom_embed: The custom embed to get the title from.
        discord_embed: The Discord embed to set the title on.
    """
    # Its actually 256, but we will use 200 to be safe.
    max_title_length: int = 200
    embed_title: str = custom_embed.title
    embed_title = f"{embed_title[:max_title_length]}..." if len(embed_title) > max_title_length else embed_title
    discord_embed.set_title(embed_title) if embed_title else None


def create_embed_webhook(webhook_url: str, entry: Entry) -> DiscordWebhook:
    """Create a webhook with an embed.

    Args:
        webhook_url (str): The webhook URL.
        entry (Entry): The entry to send to Discord.

    Returns:
        DiscordWebhook: The webhook with the embed.
    """
    webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, rate_limit_retry=True)
    feed: Feed = entry.feed

    # Get the embed data from the database.
    custom_embed: CustomEmbed = replace_tags_in_embed(feed=feed, entry=entry)

    discord_embed: DiscordEmbed = DiscordEmbed()

    set_description(custom_embed=custom_embed, discord_embed=discord_embed)
    set_title(custom_embed=custom_embed, discord_embed=discord_embed)

    custom_embed_author_url: str | None = custom_embed.author_url
    if not is_url_valid(custom_embed_author_url):
        custom_embed_author_url = None

    custom_embed_color: str | None = custom_embed.color or None
    if custom_embed_color and custom_embed_color.startswith("#"):
        custom_embed_color = custom_embed_color[1:]
        discord_embed.set_color(int(custom_embed_color, 16))

    if custom_embed.author_name and not custom_embed_author_url and not custom_embed.author_icon_url:
        discord_embed.set_author(name=custom_embed.author_name)

    if custom_embed.author_name and custom_embed_author_url and not custom_embed.author_icon_url:
        discord_embed.set_author(name=custom_embed.author_name, url=custom_embed_author_url)

    if custom_embed.author_name and not custom_embed_author_url and custom_embed.author_icon_url:
        discord_embed.set_author(name=custom_embed.author_name, icon_url=custom_embed.author_icon_url)

    if custom_embed.author_name and custom_embed_author_url and custom_embed.author_icon_url:
        discord_embed.set_author(
            name=custom_embed.author_name,
            url=custom_embed_author_url,
            icon_url=custom_embed.author_icon_url,
        )

    if custom_embed.thumbnail_url:
        discord_embed.set_thumbnail(url=custom_embed.thumbnail_url)

    if custom_embed.image_url:
        discord_embed.set_image(url=custom_embed.image_url)

    if custom_embed.footer_text:
        discord_embed.set_footer(text=custom_embed.footer_text)

    if custom_embed.footer_icon_url and custom_embed.footer_text:
        discord_embed.set_footer(text=custom_embed.footer_text, icon_url=custom_embed.footer_icon_url)

    if custom_embed.footer_icon_url and not custom_embed.footer_text:
        discord_embed.set_footer(text="-", icon_url=custom_embed.footer_icon_url)

    webhook.add_embed(discord_embed)
    return webhook


def get_webhook_url(reader: Reader, entry: Entry) -> str:
    """Get the webhook URL for the entry.

    Args:
        reader: The reader to use.
        entry: The entry to get the webhook URL for.

    Returns:
        str: The webhook URL.
    """
    try:
        webhook_url: str = str(reader.get_tag(entry.feed_url, "webhook"))
    except TagNotFoundError:
        logger.exception("No webhook URL found for feed: %s", entry.feed.url)
        return ""
    except StorageError:
        logger.exception("Storage error getting webhook URL for feed: %s", entry.feed.url)
        return ""
    return webhook_url


def set_entry_as_read(reader: Reader, entry: Entry) -> None:
    """Set the webhook to read, so we don't send it again.

    Args:
        reader: The reader to use.
        entry: The entry to set as read.
    """
    try:
        reader.set_entry_read(entry, True)
    except EntryNotFoundError:
        logger.exception("Error setting entry to read: %s", entry.id)
    except StorageError:
        logger.exception("Error setting entry to read: %s", entry.id)


def send_to_discord(custom_reader: Reader | None = None, feed: Feed | None = None, *, do_once: bool = False) -> None:
    """Send entries to Discord.

    If response was not ok, we will log the error and mark the entry as unread, so it will be sent again next time.

    Args:
        custom_reader: If we should use a custom reader instead of the default one.
        feed: The feed to send to Discord.
        do_once: If we should only send one entry. This is used in the test.
    """
    # Get the default reader if we didn't get a custom one.
    reader: Reader = get_reader() if custom_reader is None else custom_reader

    # Check for new entries for every feed.
    reader.update_feeds()

    # Loop through the unread entries.
    entries: Iterable[Entry] = reader.get_entries(feed=feed, read=False)
    for entry in entries:
        set_entry_as_read(reader, entry)

        if entry.added < datetime.datetime.now(tz=entry.added.tzinfo) - datetime.timedelta(days=1):
            logger.info("Entry is older than 24 hours: %s from %s", entry.id, entry.feed.url)
            continue

        webhook_url: str = get_webhook_url(reader, entry)
        if not webhook_url:
            logger.info("No webhook URL found for feed: %s", entry.feed.url)
            continue

        should_send_embed: bool = should_send_embed_check(reader, entry)
        if should_send_embed:
            webhook = create_embed_webhook(webhook_url, entry)
        else:
            # If the user has set the custom message to an empty string, we will use the default message, otherwise we
            # will use the custom message.
            if get_custom_message(reader, entry.feed) != "":  # noqa: PLC1901
                webhook_message = replace_tags_in_text_message(entry)
            else:
                webhook_message: str = str(default_custom_message)

            webhook_message = truncate_webhook_message(webhook_message)

            # Create the webhook.
            webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, content=webhook_message, rate_limit_retry=True)

        # Check if the entry is blacklisted, and if it is, we will skip it.
        if entry_should_be_skipped(reader, entry):
            logger.info("Entry was blacklisted: %s", entry.id)
            continue

        # Check if the feed has a whitelist, and if it does, check if the entry is whitelisted.
        if has_white_tags(reader, entry.feed):
            if should_be_sent(reader, entry):
                execute_webhook(webhook, entry)
                return
            continue

        # Send the entry to Discord as it is not blacklisted or feed has a whitelist.
        execute_webhook(webhook, entry)

        # If we only want to send one entry, we will break the loop. This is used when testing this function.
        if do_once:
            logger.info("Sent one entry to Discord. Breaking the loop.")
            break


def execute_webhook(webhook: DiscordWebhook, entry: Entry) -> None:
    """Execute the webhook.

    Args:
        webhook (DiscordWebhook): The webhook to execute.
        entry (Entry): The entry to send to Discord.

    """
    response: Response = webhook.execute()
    if response.status_code not in {200, 204}:
        msg: str = f"Error sending entry to Discord: {response.text}\n{pprint.pformat(webhook.json)}"
        if entry:
            msg += f"\n{entry}"

        logger.error(msg)
    else:
        logger.info("Sent entry to Discord: %s", entry.id)


def is_youtube_feed(feed_url: str) -> bool:
    """Check if the feed is a YouTube feed.

    Args:
        feed_url: The feed URL to check.

    Returns:
        bool: True if the feed is a YouTube feed, False otherwise.
    """
    return "youtube.com/feeds/videos.xml" in feed_url


def should_send_embed_check(reader: Reader, entry: Entry) -> bool:
    """Check if we should send an embed to Discord.

    Args:
        reader (Reader): The reader to use.
        entry (Entry): The entry to check.

    Returns:
        bool: True if we should send an embed, False otherwise.
    """
    # YouTube feeds should never use embeds - only links
    if is_youtube_feed(entry.feed.url):
        return False

    try:
        should_send_embed = bool(reader.get_tag(entry.feed, "should_send_embed"))
    except TagNotFoundError:
        logger.exception("No should_send_embed tag found for feed: %s", entry.feed.url)
        should_send_embed = True
    except ReaderError:
        logger.exception("Error getting should_send_embed tag for feed: %s", entry.feed.url)
        should_send_embed = True

    return should_send_embed


def truncate_webhook_message(webhook_message: str) -> str:
    """Truncate the webhook message if it is too long.

    Args:
        webhook_message (str): The webhook message to truncate.

    Returns:
        str: The truncated webhook message.
    """
    max_content_length: int = 4000
    if len(webhook_message) > max_content_length:
        half_length = (max_content_length - 3) // 2  # Subtracting 3 for the "..." in the middle
        webhook_message = f"{webhook_message[:half_length]}...{webhook_message[-half_length:]}"
    return webhook_message


def create_feed(reader: Reader, feed_url: str, webhook_dropdown: str) -> None:
    """Add a new feed, update it and mark every entry as read.

    Args:
        reader: The reader to use.
        feed_url: The feed to add.
        webhook_dropdown: The webhook we should send entries to.

    Raises:
        HTTPException: If webhook_dropdown does not equal a webhook or default_custom_message not found.
    """
    clean_feed_url: str = feed_url.strip()
    webhook_url: str = ""
    if hooks := reader.get_tag((), "webhooks", []):
        # Get the webhook URL from the dropdown.
        for hook in hooks:
            if not isinstance(hook, dict):
                logger.error("Webhook is not a dict: %s", hook)
                continue

            if hook["name"] == webhook_dropdown:  # pyright: ignore[reportArgumentType]
                webhook_url = hook["url"]
                break

    if not webhook_url:
        raise HTTPException(status_code=404, detail="Webhook not found")

    try:
        reader.add_feed(clean_feed_url)
    except FeedExistsError:
        # Add the webhook to an already added feed if it doesn't have a webhook instead of trying to create a new.
        try:
            reader.get_tag(clean_feed_url, "webhook")
        except TagNotFoundError:
            reader.set_tag(clean_feed_url, "webhook", webhook_url)  # pyright: ignore[reportArgumentType]
    except ReaderError as e:
        raise HTTPException(status_code=404, detail=f"Error adding feed: {e}") from e

    try:
        reader.update_feed(clean_feed_url)
    except ReaderError as e:
        raise HTTPException(status_code=404, detail=f"Error updating feed: {e}") from e

    # Mark every entry as read, so we don't send all the old entries to Discord.
    entries: Iterable[Entry] = reader.get_entries(feed=clean_feed_url, read=False)
    for entry in entries:
        reader.set_entry_read(entry, True)

    if not default_custom_message:
        # TODO(TheLovinator): Show this error on the page.
        raise HTTPException(status_code=404, detail="Default custom message couldn't be found.")

    # This is the webhook that will be used to send the feed to Discord.
    reader.set_tag(clean_feed_url, "webhook", webhook_url)  # pyright: ignore[reportArgumentType]

    # This is the default message that will be sent to Discord.
    reader.set_tag(clean_feed_url, "custom_message", default_custom_message)  # pyright: ignore[reportArgumentType]

    # Update the full-text search index so our new feed is searchable.
    reader.update_search()

    add_missing_tags(reader)
