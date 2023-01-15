import urllib.parse

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
    # TODO: Send error to Discord.
    return urllib.parse.quote(url_to_quote) if url_to_quote else "None"


def entry_is_whitelisted(entry_to_check: Entry) -> bool:
    """
    Check if the entry is whitelisted.

    Args:
        entry_to_check: The feed to check.

    Returns:
        bool: True if the feed is whitelisted, False otherwise.

    """
    return bool(has_white_tags(reader, entry_to_check.feed) and should_be_sent(reader, entry_to_check))


def entry_is_blacklisted(entry_to_check: Entry) -> bool:
    """
    Check if the entry is blacklisted.

    Args:
        entry_to_check: The feed to check.

    Returns:
        bool: True if the feed is blacklisted, False otherwise.

    """
    return bool(has_black_tags(reader, entry_to_check.feed) and should_be_skipped(reader, entry_to_check))


def convert_to_md(thing: str) -> str:
    """Discord does not support tables so we need to remove them from the markdown."""
    return markdownify(thing, strip=["table", "thead", "tbody", "tr", "th", "td"])
