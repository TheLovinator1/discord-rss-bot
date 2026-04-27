from __future__ import annotations

from typing import TYPE_CHECKING

from discord_rss_bot.filter.evaluator import find_filter_match
from discord_rss_bot.filter.evaluator import get_filter_values_from_reader
from discord_rss_bot.filter.evaluator import has_filter_values

if TYPE_CHECKING:
    from reader import Entry
    from reader import Feed
    from reader import Reader


def feed_has_blacklist_tags(reader: Reader, feed: Feed) -> bool:
    """Return True if the feed has blacklist tags.

    The following tags are checked:
    - blacklist_author
    - blacklist_content
    - blacklist_summary
    - blacklist_title
    - regex_blacklist_author
    - regex_blacklist_content
    - regex_blacklist_summary
    - regex_blacklist_title

    Args:
        reader: The reader.
        feed: The feed to check.

    Returns:
        bool: If the feed has any of the tags.
    """
    return has_filter_values(get_filter_values_from_reader(reader, feed, "blacklist"))


def entry_should_be_skipped(reader: Reader, entry: Entry) -> bool:
    """Return True if the entry is in the blacklist.

    Args:
        reader: The reader.
        entry: The entry to check.

    Returns:
        bool: If the entry is in the blacklist.
    """
    return bool(find_filter_match(entry, get_filter_values_from_reader(reader, entry.feed, "blacklist"), "blacklist"))
