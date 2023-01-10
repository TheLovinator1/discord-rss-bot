from reader import Entry, Feed, Reader, TagNotFoundError

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
    whitelist_title: str = get_whitelist_title(custom_reader, feed)
    whitelist_summary: str = get_whitelist_summary(custom_reader, feed)
    whitelist_content: str = get_whitelist_content(custom_reader, feed)

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
    whitelist_title: str = get_whitelist_title(custom_reader, feed)
    whitelist_summary: str = get_whitelist_summary(custom_reader, feed)
    # whitelist_content: str = get_whitelist_content(custom_reader, feed)
    # TODO: Fix content
    # TODO: Check author

    if entry.title and whitelist_title and is_word_in_text(whitelist_title, entry.title):
        return True
    elif entry.summary and whitelist_summary and is_word_in_text(whitelist_summary, entry.summary):
        return True
    return False


def get_whitelist_content(custom_reader: Reader, feed: Feed) -> str:
    """
    Get the whitelist_content tag from the feed.

    Args:
        custom_reader: The reader.
        feed: The feed to get the tag from.

    Returns:
        str: The whitelist_content tag.
    """
    try:
        whitelist_content: str = custom_reader.get_tag(feed, "whitelist_content")  # type: ignore
    except TagNotFoundError:
        whitelist_content: str = ""
    except ValueError:
        whitelist_content: str = ""
    return whitelist_content


def get_whitelist_summary(custom_reader: Reader, feed: Feed) -> str:
    """
    Get the whitelist_summary tag from the feed.

    Args:
        custom_reader: The reader.
        feed: The feed to get the tag from.

    Returns:
        str: The whitelist_summary tag.
    """
    try:
        whitelist_summary: str = custom_reader.get_tag(feed, "whitelist_summary")  # type: ignore
    except TagNotFoundError:
        whitelist_summary: str = ""
    except ValueError:
        whitelist_summary: str = ""
    return whitelist_summary


def get_whitelist_title(custom_reader: Reader, feed: Feed) -> str:
    """
    Get the whitelist_title tag from the feed.

    Args:
        custom_reader: The reader.
        feed: The feed to get the tag from.

    Returns:
        str: The whitelist_title tag.
    """
    try:
        whitelist_title: str = custom_reader.get_tag(feed, "whitelist_title")  # type: ignore
    except TagNotFoundError:
        whitelist_title: str = ""
    except ValueError:
        whitelist_title: str = ""
    return whitelist_title
