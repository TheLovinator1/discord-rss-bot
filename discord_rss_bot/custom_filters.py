import urllib.parse
from functools import lru_cache

from reader import Entry, Reader

from discord_rss_bot.filter.blacklist import entry_should_be_skipped, feed_has_blacklist_tags
from discord_rss_bot.filter.whitelist import has_white_tags, should_be_sent
from discord_rss_bot.settings import get_reader

# Our reader
reader: Reader = get_reader()


@lru_cache
def encode_url(url_to_quote: str) -> str:
    """%-escape the URL so it can be used in a URL.

    If we didn't do this, we couldn't go to feeds with a ? in the URL.
    You can use this in templates with {{ url | encode_url }}.

    Args:
        url_to_quote: The url to encode.

    Returns:
        The encoded url.
    """
    return urllib.parse.quote(string=url_to_quote) if url_to_quote else ""


def entry_is_whitelisted(entry_to_check: Entry) -> bool:
    """Check if the entry is whitelisted.

    Args:
        entry_to_check: The feed to check.

    Returns:
        bool: True if the feed is whitelisted, False otherwise.

    """
    return bool(has_white_tags(reader, entry_to_check.feed) and should_be_sent(reader, entry_to_check))


def entry_is_blacklisted(entry_to_check: Entry) -> bool:
    """Check if the entry is blacklisted.

    Args:
        entry_to_check: The feed to check.

    Returns:
        bool: True if the feed is blacklisted, False otherwise.

    """
    return bool(
        feed_has_blacklist_tags(reader, entry_to_check.feed) and entry_should_be_skipped(reader, entry_to_check),
    )
