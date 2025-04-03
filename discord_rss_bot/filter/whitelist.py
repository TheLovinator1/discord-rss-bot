from __future__ import annotations

from typing import TYPE_CHECKING

from discord_rss_bot.filter.utils import is_regex_match, is_word_in_text

if TYPE_CHECKING:
    from reader import Entry, Feed, Reader


def has_white_tags(custom_reader: Reader, feed: Feed) -> bool:
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
        custom_reader: The reader.
        feed: The feed to check.

    Returns:
        bool: If the feed has any of the tags.
    """
    whitelist_title: str = str(custom_reader.get_tag(feed, "whitelist_title", "")).strip()
    whitelist_summary: str = str(custom_reader.get_tag(feed, "whitelist_summary", "")).strip()
    whitelist_content: str = str(custom_reader.get_tag(feed, "whitelist_content", "")).strip()
    whitelist_author: str = str(custom_reader.get_tag(feed, "whitelist_author", "")).strip()

    regex_whitelist_title: str = str(custom_reader.get_tag(feed, "regex_whitelist_title", "")).strip()
    regex_whitelist_summary: str = str(custom_reader.get_tag(feed, "regex_whitelist_summary", "")).strip()
    regex_whitelist_content: str = str(custom_reader.get_tag(feed, "regex_whitelist_content", "")).strip()
    regex_whitelist_author: str = str(custom_reader.get_tag(feed, "regex_whitelist_author", "")).strip()

    return bool(
        whitelist_title
        or whitelist_author
        or whitelist_content
        or whitelist_summary
        or regex_whitelist_author
        or regex_whitelist_content
        or regex_whitelist_summary
        or regex_whitelist_title,
    )


def should_be_sent(custom_reader: Reader, entry: Entry) -> bool:  # noqa: PLR0911
    """Return True if the entry is in the whitelist.

    Args:
        custom_reader: The reader.
        entry: The entry to check.

    Returns:
        bool: If the entry is in the whitelist.
    """
    feed: Feed = entry.feed
    # Regular whitelist tags
    whitelist_title: str = str(custom_reader.get_tag(feed, "whitelist_title", "")).strip()
    whitelist_summary: str = str(custom_reader.get_tag(feed, "whitelist_summary", "")).strip()
    whitelist_content: str = str(custom_reader.get_tag(feed, "whitelist_content", "")).strip()
    whitelist_author: str = str(custom_reader.get_tag(feed, "whitelist_author", "")).strip()

    # Regex whitelist tags
    regex_whitelist_title: str = str(custom_reader.get_tag(feed, "regex_whitelist_title", "")).strip()
    regex_whitelist_summary: str = str(custom_reader.get_tag(feed, "regex_whitelist_summary", "")).strip()
    regex_whitelist_content: str = str(custom_reader.get_tag(feed, "regex_whitelist_content", "")).strip()
    regex_whitelist_author: str = str(custom_reader.get_tag(feed, "regex_whitelist_author", "")).strip()

    # Check regular whitelist
    if entry.title and whitelist_title and is_word_in_text(whitelist_title, entry.title):
        return True
    if entry.summary and whitelist_summary and is_word_in_text(whitelist_summary, entry.summary):
        return True
    if entry.author and whitelist_author and is_word_in_text(whitelist_author, entry.author):
        return True
    if (
        entry.content
        and entry.content[0].value
        and whitelist_content
        and is_word_in_text(whitelist_content, entry.content[0].value)
    ):
        return True

    # Check regex whitelist
    if entry.title and regex_whitelist_title and is_regex_match(regex_whitelist_title, entry.title):
        return True
    if entry.summary and regex_whitelist_summary and is_regex_match(regex_whitelist_summary, entry.summary):
        return True
    if entry.author and regex_whitelist_author and is_regex_match(regex_whitelist_author, entry.author):
        return True
    return bool(
        entry.content
        and entry.content[0].value
        and regex_whitelist_content
        and is_regex_match(regex_whitelist_content, entry.content[0].value),
    )
