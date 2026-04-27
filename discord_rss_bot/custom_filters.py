from __future__ import annotations

import urllib.parse
from functools import lru_cache
from typing import TYPE_CHECKING

from discord_rss_bot.filter.evaluator import get_entry_filter_decision_from_reader

if TYPE_CHECKING:
    from reader import Entry
    from reader import Reader


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


def entry_is_whitelisted(entry_to_check: Entry, reader: Reader) -> bool:
    """Check if the entry is whitelisted.

    Args:
        entry_to_check: The feed to check.
        reader: Custom Reader instance.

    Returns:
        bool: True if the feed is whitelisted, False otherwise.

    """
    return get_entry_filter_decision_from_reader(reader, entry_to_check).whitelist_match is not None


def entry_is_blacklisted(entry_to_check: Entry, reader: Reader) -> bool:
    """Check if the entry is blacklisted.

    Args:
        entry_to_check: The feed to check.
        reader: Custom Reader instance.

    Returns:
        bool: True if the feed is blacklisted, False otherwise.

    """
    return get_entry_filter_decision_from_reader(reader, entry_to_check).blacklist_match is not None
