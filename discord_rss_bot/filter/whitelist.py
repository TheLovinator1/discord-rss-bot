from reader import Entry, Feed, Reader

from discord_rss_bot.filter.utils import is_word_in_text


def has_white_tags(custom_reader: Reader, feed: Feed) -> bool:
    """
    Return True if the feed has any of the following tags:
    - whitelist_title
    - whitelist_summary
    - whitelist_content

    Args:
        custom_reader: The reader.
        feed: The feed to check.

    Returns:
        bool: If the feed has any of the tags.
    """
    whitelist_title: str = str(custom_reader.get_tag(feed, "whitelist_title", ""))
    whitelist_summary: str = str(custom_reader.get_tag(feed, "whitelist_summary", ""))
    whitelist_content: str = str(custom_reader.get_tag(feed, "whitelist_content", ""))

    return bool(whitelist_title or whitelist_summary or whitelist_content)


def should_be_sent(custom_reader: Reader, entry: Entry) -> bool:
    """
    Return True if the entry is in the whitelist.

    Args:
        custom_reader: The reader.
        entry: The entry to check.

    Returns:
        bool: If the entry is in the whitelist.
    """
    feed: Feed = entry.feed
    whitelist_title: str = str(custom_reader.get_tag(feed, "whitelist_title", ""))
    whitelist_summary: str = str(custom_reader.get_tag(feed, "whitelist_summary", ""))
    whitelist_content: str = str(custom_reader.get_tag(feed, "whitelist_content", ""))
    whitelist_author: str = str(custom_reader.get_tag(feed, "whitelist_author", ""))

    if entry.title and whitelist_title and is_word_in_text(whitelist_title, entry.title):
        return True
    elif entry.summary and whitelist_summary and is_word_in_text(whitelist_summary, entry.summary):
        return True
    elif entry.author and whitelist_author and is_word_in_text(whitelist_author, entry.author):
        return True
    elif entry.content:
        if entry.content[0].value and whitelist_content and is_word_in_text(whitelist_content, entry.content[0].value):
            return True
    return False
