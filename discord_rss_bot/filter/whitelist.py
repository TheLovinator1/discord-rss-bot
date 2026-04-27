from __future__ import annotations

from typing import TYPE_CHECKING

from discord_rss_bot.filter.evaluator import find_filter_match
from discord_rss_bot.filter.evaluator import get_filter_values_from_reader
from discord_rss_bot.filter.evaluator import has_filter_values

if TYPE_CHECKING:
    from reader import Entry
    from reader import Feed
    from reader import Reader


def has_white_tags(reader: Reader, feed: Feed) -> bool:
    """Return True if the feed has whitelist tags.

    The following tags are checked:
    - regex_whitelist_author
    - regex_whitelist_content
    - regex_whitelist_summary
    - regex_whitelist_title
    - whitelist_author
    - whitelist_content
    - whitelist_summary
    - whitelist_title

    Args:
        reader: The reader.
        feed: The feed to check.

    Returns:
        bool: If the feed has any of the tags.
    """
    return has_filter_values(get_filter_values_from_reader(reader, feed, "whitelist"))


def should_be_sent(reader: Reader, entry: Entry) -> bool:
    """Return True if the entry is in the whitelist.

    Args:
        reader: The reader.
        entry: The entry to check.

    Returns:
        bool: If the entry is in the whitelist.
    """
    return bool(find_filter_match(entry, get_filter_values_from_reader(reader, entry.feed, "whitelist"), "whitelist"))
