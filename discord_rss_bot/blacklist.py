import re

from reader import Entry, Feed, Reader, TagNotFoundError


def is_word_in_text(words: str, text: str) -> bool:
    """
    Args:
        words: The words to search for.
        text: The text to search in.

    Returns:
        bool: If the word is in the text.
    """
    # Split the word list into a list of words.
    word_list: list[str] = words.split(",")

    # Check if each word is in the text.
    for word in word_list:
        look_for: str = rf"(^|[^\w]){word}([^\w]|$)"
        pattern: re.Pattern[str] = re.compile(look_for, re.IGNORECASE)
        if re.search(pattern, text):
            return True
    return False


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
    blacklist_title: str = get_blacklist_title(custom_reader, feed)
    blacklist_summary: str = get_blacklist_summary(custom_reader, feed)
    blacklist_content: str = get_blacklist_content(custom_reader, feed)

    if blacklist_title or blacklist_summary or blacklist_content:
        return True
    return False


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
    blacklist_title: str = get_blacklist_title(custom_reader, feed)
    blacklist_summary: str = get_blacklist_summary(custom_reader, feed)
    blacklist_content: str = get_blacklist_content(custom_reader, feed)
    # TODO: Fix content
    # TODO: Check author

    if blacklist_title:
        if is_word_in_text(blacklist_title, entry.title):
            return True

    if blacklist_summary:
        if is_word_in_text(blacklist_summary, entry.summary):
            return True

    return False

    # if blacklist_content.lower() in entry.content.lower():


def get_blacklist_content(custom_reader: Reader, feed: Feed) -> str:
    """
    Get the blacklist_content tag from the feed.

    Args:
        custom_reader: The reader.
        feed: The feed to get the tag from.

    Returns:
        str: The blacklist_content tag.
    """
    try:
        blacklist_content: str = custom_reader.get_tag(feed, "blacklist_content")  # type: ignore
    except TagNotFoundError:
        blacklist_content: str = ""
    except ValueError:
        blacklist_content: str = ""
    return blacklist_content


def get_blacklist_summary(custom_reader: Reader, feed: Feed) -> str:
    """
    Get the blacklist_summary tag from the feed.

    Args:
        custom_reader: The reader.
        feed: The feed to get the tag from.

    Returns:
        str: The blacklist_summary tag.
    """
    try:
        blacklist_summary: str = custom_reader.get_tag(feed, "blacklist_summary")  # type: ignore
    except TagNotFoundError:
        blacklist_summary: str = ""
    except ValueError:
        blacklist_summary: str = ""
    return blacklist_summary


def get_blacklist_title(custom_reader: Reader, feed: Feed) -> str:
    """
    Get the blacklist_title tag from the feed.

    Args:
        custom_reader: The reader.
        feed: The feed to get the tag from.

    Returns:
        str: The blacklist_title tag.
    """
    try:
        blacklist_title: str = custom_reader.get_tag(feed, "blacklist_title")  # type: ignore
    except TagNotFoundError:
        blacklist_title: str = ""
    except ValueError:
        blacklist_title: str = ""
    return blacklist_title
