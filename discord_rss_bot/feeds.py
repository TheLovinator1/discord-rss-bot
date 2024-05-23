from __future__ import annotations

import datetime
import pprint
from typing import TYPE_CHECKING

from discord_webhook import DiscordEmbed, DiscordWebhook
from fastapi import HTTPException
from reader import Entry, EntryNotFoundError, Feed, FeedExistsError, Reader, StorageError, TagNotFoundError

from discord_rss_bot import custom_message
from discord_rss_bot.filter.blacklist import should_be_skipped
from discord_rss_bot.filter.whitelist import has_white_tags, should_be_sent
from discord_rss_bot.is_url_valid import is_url_valid
from discord_rss_bot.settings import default_custom_message, get_reader, logger

if TYPE_CHECKING:
    from collections.abc import Iterable

    from requests import Response


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

    # Try to get the custom message for the feed. If the user has none, we will use the default message.
    # This has to be a string for some reason so don't change it to "not custom_message.get_custom_message()"
    if custom_message.get_custom_message(reader, entry.feed) != "":  # noqa: PLC1901
        webhook_message = custom_message.replace_tags_in_text_message(entry=entry)

    if not webhook_message:
        webhook_message = "No message found."

    # Create the webhook.
    if bool(reader.get_tag(entry.feed, "should_send_embed")):
        webhook = create_embed_webhook(webhook_url, entry)
    else:
        webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, content=webhook_message, rate_limit_retry=True)

    response: Response = webhook.execute()
    if response.status_code not in {200, 204}:
        logger.error("Error sending entry to Discord: %s\n%s", response.text, pprint.pformat(webhook.json))
        return f"Error sending entry to Discord: {response.text}"
    return None


def set_description(custom_embed: custom_message.CustomEmbed, discord_embed: DiscordEmbed) -> None:
    """Set the description of the embed.

    Args:
        custom_embed (custom_message.CustomEmbed): The custom embed to get the description from.
        discord_embed (DiscordEmbed): The Discord embed to set the description on.
    """
    # Its actually 2048, but we will use 2000 to be safe.
    max_description_length: int = 2000
    embed_description: str = custom_embed.description
    embed_description = (
        embed_description[:max_description_length] + "..."
        if len(embed_description) > max_description_length
        else embed_description
    )
    discord_embed.set_description(embed_description) if embed_description else None


def set_title(custom_embed: custom_message.CustomEmbed, discord_embed: DiscordEmbed) -> None:
    """Set the title of the embed.

    Args:
        custom_embed: The custom embed to get the title from.
        discord_embed: The Discord embed to set the title on.
    """
    # Its actually 256, but we will use 200 to be safe.
    max_title_length: int = 200
    embed_title: str = custom_embed.title
    embed_title = embed_title[:max_title_length] + "..." if len(embed_title) > max_title_length else embed_title
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
    custom_embed: custom_message.CustomEmbed = custom_message.replace_tags_in_embed(feed=feed, entry=entry)

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


def send_to_discord(custom_reader: Reader | None = None, feed: Feed | None = None, *, do_once: bool = False) -> None:  # noqa: PLR0912
    """Send entries to Discord.

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

    # Loop through the unread entries.
    entries: Iterable[Entry] = reader.get_entries(feed=feed, read=False)
    for entry in entries:
        if entry.added < datetime.datetime.now(tz=entry.added.tzinfo) - datetime.timedelta(days=1):
            logger.info("Entry is older than 24 hours: %s from %s", entry.id, entry.feed.url)
            reader.set_entry_read(entry, True)
            continue

        # Set the webhook to read, so we don't send it again.
        try:
            reader.set_entry_read(entry, True)
        except EntryNotFoundError as e:
            logger.error("Error setting entry to read: %s", e)
            continue
        except StorageError as e:
            logger.error("Error setting entry to read: %s", e)
            continue

        # Get the webhook URL for the entry. If it is None, we will continue to the next entry.
        webhook_url: str = str(reader.get_tag(entry.feed_url, "webhook", ""))
        if not webhook_url:
            continue

        if bool(reader.get_tag(entry.feed, "should_send_embed")):
            webhook = create_embed_webhook(webhook_url, entry)
        else:
            # If the user has set the custom message to an empty string, we will use the default message, otherwise we
            # will use the custom message.
            if custom_message.get_custom_message(reader, entry.feed) != "":  # noqa: PLC1901
                webhook_message = custom_message.replace_tags_in_text_message(entry)
            else:
                webhook_message: str = str(default_custom_message)

            # Its actually 4096, but we will use 4000 to be safe.
            max_content_length: int = 4000
            webhook_message = (
                webhook_message[:max_content_length] + "..."
                if len(webhook_message) > max_content_length
                else webhook_message
            )

            # Create the webhook.
            webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, content=webhook_message, rate_limit_retry=True)

        # Check if the feed has a whitelist, and if it does, check if the entry is whitelisted.
        if has_white_tags(reader, entry.feed):
            if should_be_sent(reader, entry):
                response: Response = webhook.execute()
                if response.status_code not in {200, 204}:
                    logger.error("Error sending entry to Discord: %s\n%s", response.text, pprint.pformat(webhook.json))

                reader.set_entry_read(entry, True)
                return
            reader.set_entry_read(entry, True)
            continue

        # Check if the entry is blacklisted, if it is, mark it as read and continue.
        if should_be_skipped(reader, entry):
            logger.info("Entry was blacklisted: %s", entry.id)
            reader.set_entry_read(entry, True)
            continue

        # It was not blacklisted, and not forced through whitelist, so we will send it to Discord.
        response: Response = webhook.execute()
        if response.status_code not in {200, 204}:
            logger.error("Error sending entry to Discord: %s\n%s", response.text, pprint.pformat(webhook.json))
            reader.set_entry_read(entry, True)
            return

        # If we only want to send one entry, we will break the loop. This is used when testing this function.
        if do_once:
            logger.info("Sent one entry to Discord.")
            break

    # Update the search index.
    reader.update_search()


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
            if hook["name"] == webhook_dropdown:  # type: ignore
                webhook_url = hook["url"]  # type: ignore
                break

    if not webhook_url:
        raise HTTPException(status_code=404, detail="Webhook not found")

    try:
        # TODO(TheLovinator): Check if the feed is valid
        reader.add_feed(clean_feed_url)
    except FeedExistsError:
        # Add the webhook to an already added feed if it doesn't have a webhook instead of trying to create a new.
        try:
            reader.get_tag(clean_feed_url, "webhook")
        except TagNotFoundError:
            reader.set_tag(clean_feed_url, "webhook", webhook_url)  # type: ignore

    reader.update_feed(clean_feed_url)

    # Mark every entry as read, so we don't send all the old entries to Discord.
    entries: Iterable[Entry] = reader.get_entries(feed=clean_feed_url, read=False)
    for entry in entries:
        reader.set_entry_read(entry, True)

    if not default_custom_message:
        # TODO(TheLovinator): Show this error on the page.
        raise HTTPException(status_code=404, detail="Default custom message couldn't be found.")

    # This is the webhook that will be used to send the feed to Discord.
    reader.set_tag(clean_feed_url, "webhook", webhook_url)  # type: ignore

    # This is the default message that will be sent to Discord.
    reader.set_tag(clean_feed_url, "custom_message", default_custom_message)  # type: ignore

    # Update the full-text search index so our new feed is searchable.
    reader.update_search()
