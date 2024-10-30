from reader import Entry, Feed, Reader

from discord_rss_bot.filter.utils import is_word_in_text


def feed_has_blacklist_tags(custom_reader: Reader, feed: Feed) -> bool:
    """Return True if the feed has blacklist tags.

    The following tags are checked:
    - blacklist_title
    - blacklist_summary
    - blacklist_content.

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


def entry_should_be_skipped(custom_reader: Reader, entry: Entry) -> bool:
    """Return True if the entry is in the blacklist.

    Args:
        custom_reader: The reader.
        entry: The entry to check.

    Returns:
        bool: If the entry is in the blacklist.
    """
    blacklist_title: str = str(custom_reader.get_tag(entry.feed, "blacklist_title", ""))
    blacklist_summary: str = str(custom_reader.get_tag(entry.feed, "blacklist_summary", ""))
    blacklist_content: str = str(custom_reader.get_tag(entry.feed, "blacklist_content", ""))
    blacklist_author: str = str(custom_reader.get_tag(entry.feed, "blacklist_author", ""))
    # TODO(TheLovinator): Also add support for entry_text and more.

    if entry.title and blacklist_title and is_word_in_text(blacklist_title, entry.title):
        return True
    if entry.summary and blacklist_summary and is_word_in_text(blacklist_summary, entry.summary):
        return True
    if entry.author and blacklist_author and is_word_in_text(blacklist_author, entry.author):
        return True
    return bool(
        entry.content
        and entry.content[0].value
        and blacklist_content
        and is_word_in_text(blacklist_content, entry.content[0].value),
    )
