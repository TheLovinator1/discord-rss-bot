import re

from reader import Entry, Feed, Reader, TagNotFoundError


def is_word_in_text(word: str, text: str) -> bool:
    """
    Args:
        word: The word to search for.
        text: The text to search in.

    Returns:
        bool: If the word is in the text.
    """
    pattern = rf"(^|[^\w]){word}([^\w]|$)"
    pattern = re.compile(pattern, re.IGNORECASE)
    matches = re.search(pattern, text)
    return bool(matches)


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
    blacklist_title = get_blacklist_title(custom_reader, feed)
    blacklist_summary = get_blacklist_summary(custom_reader, feed)
    blacklist_content = get_blacklist_content(custom_reader, feed)

    if blacklist_title or blacklist_summary or blacklist_content:
        return True


def if_in_blacklist(custom_reader: Reader, entry: Entry) -> bool:
    """
    Return True if the entry is in the blacklist.

    Args:
        custom_reader: The reader.
        entry: The entry to check.

    Returns:
        bool: If the entry is in the blacklist.
    """
    feed: Feed = entry.feed
    blacklist_title = get_blacklist_title(custom_reader, feed)
    blacklist_summary = get_blacklist_summary(custom_reader, feed)
    blacklist_content = get_blacklist_content(custom_reader, feed)
    # TODO: Fix content
    # TODO: Check author

    if blacklist_title:
        if is_word_in_text(blacklist_title, entry.title):
            return True

    if blacklist_summary:
        if is_word_in_text(blacklist_summary, entry.summary):
            return True

    # if blacklist_content.lower() in entry.content.lower():


def get_blacklist_content(custom_reader, feed) -> str:
    """
    Get the blacklist_content tag from the feed.

    Args:
        custom_reader: The reader.
        feed: The feed to get the tag from.

    Returns:
        str: The blacklist_content tag.
    """
    try:
        blacklist_content = custom_reader.get_tag(feed, "blacklist_content")
    except TagNotFoundError:
        blacklist_content = ""
    except ValueError:
        blacklist_content = ""
    return blacklist_content


def get_blacklist_summary(custom_reader, feed) -> str:
    """
    Get the blacklist_summary tag from the feed.

    Args:
        custom_reader: The reader.
        feed: The feed to get the tag from.

    Returns:
        str: The blacklist_summary tag.
    """
    try:
        blacklist_summary = custom_reader.get_tag(feed, "blacklist_summary")
    except TagNotFoundError:
        blacklist_summary = ""
    except ValueError:
        blacklist_summary = ""
    return blacklist_summary


def get_blacklist_title(custom_reader, feed) -> str:
    """
    Get the blacklist_title tag from the feed.

    Args:
        custom_reader: The reader.
        feed: The feed to get the tag from.

    Returns:
        str: The blacklist_title tag.
    """
    try:
        blacklist_title = custom_reader.get_tag(feed, "blacklist_title")
    except TagNotFoundError:
        blacklist_title = ""
    except ValueError:
        blacklist_title = ""
    return blacklist_title
