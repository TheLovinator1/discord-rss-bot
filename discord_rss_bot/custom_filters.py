import urllib.parse

from loguru import logger
from markdownify import markdownify
from reader import Entry, Reader

from discord_rss_bot.filter.blacklist import has_black_tags, should_be_skipped
from discord_rss_bot.filter.whitelist import has_white_tags, should_be_sent
from discord_rss_bot.settings import get_reader

# Our reader
reader: Reader = get_reader()


def encode_url(url_to_quote: str) -> str:
    """%-escape the URL so it can be used in a URL.

    If we didn't do this, we couldn't go to feeds with a ? in the URL.
    You can use this in templates with {{ url | encode_url }}.

    Args:
        url_to_quote: The url to encode.

    Returns:
        The encoded url.
    """
    if url_to_quote:
        return urllib.parse.quote(url_to_quote)

    logger.error("URL to quote is None.")
    return ""


def entry_is_whitelisted(entry_to_check: Entry) -> bool:
    """
    Check if the entry is whitelisted.

    Args:
        entry_to_check: The feed to check.

    Returns:
        bool: True if the feed is whitelisted, False otherwise.

    """
    logger.debug(f"Checking if {entry_to_check.title} is whitelisted.")
    return bool(has_white_tags(reader, entry_to_check.feed) and should_be_sent(reader, entry_to_check))


def entry_is_blacklisted(entry_to_check: Entry) -> bool:
    """
    Check if the entry is blacklisted.

    Args:
        entry_to_check: The feed to check.

    Returns:
        bool: True if the feed is blacklisted, False otherwise.

    """
    logger.debug(f"Checking if {entry_to_check.title} is blacklisted.")
    return bool(has_black_tags(reader, entry_to_check.feed) and should_be_skipped(reader, entry_to_check))


def convert_to_md(thing: str) -> str:
    """Discord does not support tables so we need to remove them from the markdown."""
    logger.debug(f"Converting {thing} to markdown.")
    # TODO: Should we remove thead, tbody, tr, th, and td instead?
    return markdownify(thing, strip=["table", "thead", "tbody", "tr", "th", "td"]) if thing else ""
