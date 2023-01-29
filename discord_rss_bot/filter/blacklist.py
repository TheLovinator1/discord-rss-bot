from reader import Entry, Feed, Reader

from discord_rss_bot.filter.utils import is_word_in_text


def has_black_tags(custom_reader: Reader, feed: Feed) -> bool:
    """
    Return True if the feed has any of the following tags:
    - blacklist_title
    - blacklist_summary
    - blacklist_content

    Args:
        custom_reader: The reader.
        feed: The feed to check.

    Returns:
        bool: If the feed has any of the tags.
    """
    blacklist_title: str = str(custom_reader.get_tag(feed, "blacklist_title", ""))
    blacklist_summary: str = str(custom_reader.get_tag(feed, "blacklist_summary", ""))
    blacklist_content: str = str(custom_reader.get_tag(feed, "blacklist_content", ""))

    return bool(blacklist_title or blacklist_summary or blacklist_content)


def should_be_skipped(custom_reader: Reader, entry: Entry) -> bool:
    """
    Return True if the entry is in the blacklist.

    Args:
        custom_reader: The reader.
        entry: The entry to check.

    Returns:
        bool: If the entry is in the blacklist.
    """
    feed: Feed = entry.feed
    blacklist_title: str = str(custom_reader.get_tag(feed, "blacklist_title", ""))
    blacklist_summary: str = str(custom_reader.get_tag(feed, "blacklist_summary", ""))
    # blacklist_content: str = str(custom_reader.get_tag(feed, "blacklist_content", ""))
    # TODO: Fix content
    # TODO: Check author
    # TODO: Also add support for entry_text

    if entry.title and blacklist_title and is_word_in_text(blacklist_title, entry.title):
        return True
    elif entry.summary and blacklist_summary and is_word_in_text(blacklist_summary, entry.summary):
        return True
    return False
