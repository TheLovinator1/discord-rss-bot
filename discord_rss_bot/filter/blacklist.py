from __future__ import annotations

from typing import TYPE_CHECKING

from discord_rss_bot.filter.utils import is_regex_match, is_word_in_text

if TYPE_CHECKING:
    from reader import Entry, Feed, Reader


def feed_has_blacklist_tags(custom_reader: Reader, feed: Feed) -> bool:
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
        custom_reader: The reader.
        feed: The feed to check.

    Returns:
        bool: If the feed has any of the tags.
    """
    blacklist_author: str = str(custom_reader.get_tag(feed, "blacklist_author", "")).strip()
    blacklist_content: str = str(custom_reader.get_tag(feed, "blacklist_content", "")).strip()
    blacklist_summary: str = str(custom_reader.get_tag(feed, "blacklist_summary", "")).strip()
    blacklist_title: str = str(custom_reader.get_tag(feed, "blacklist_title", "")).strip()

    regex_blacklist_author: str = str(custom_reader.get_tag(feed, "regex_blacklist_author", "")).strip()
    regex_blacklist_content: str = str(custom_reader.get_tag(feed, "regex_blacklist_content", "")).strip()
    regex_blacklist_summary: str = str(custom_reader.get_tag(feed, "regex_blacklist_summary", "")).strip()
    regex_blacklist_title: str = str(custom_reader.get_tag(feed, "regex_blacklist_title", "")).strip()

    return bool(
        blacklist_title
        or blacklist_author
        or blacklist_content
        or blacklist_summary
        or regex_blacklist_author
        or regex_blacklist_content
        or regex_blacklist_summary
        or regex_blacklist_title,
    )


def entry_should_be_skipped(custom_reader: Reader, entry: Entry) -> bool:  # noqa: PLR0911
    """Return True if the entry is in the blacklist.

    Args:
        custom_reader: The reader.
        entry: The entry to check.

    Returns:
        bool: If the entry is in the blacklist.
    """
    feed = entry.feed

    blacklist_title: str = str(custom_reader.get_tag(feed, "blacklist_title", "")).strip()
    blacklist_summary: str = str(custom_reader.get_tag(feed, "blacklist_summary", "")).strip()
    blacklist_content: str = str(custom_reader.get_tag(feed, "blacklist_content", "")).strip()
    blacklist_author: str = str(custom_reader.get_tag(feed, "blacklist_author", "")).strip()

    regex_blacklist_title: str = str(custom_reader.get_tag(feed, "regex_blacklist_title", "")).strip()
    regex_blacklist_summary: str = str(custom_reader.get_tag(feed, "regex_blacklist_summary", "")).strip()
    regex_blacklist_content: str = str(custom_reader.get_tag(feed, "regex_blacklist_content", "")).strip()
    regex_blacklist_author: str = str(custom_reader.get_tag(feed, "regex_blacklist_author", "")).strip()
    # TODO(TheLovinator): Also add support for entry_text and more.

    # Check regular blacklist
    if entry.title and blacklist_title and is_word_in_text(blacklist_title, entry.title):
        return True
    if entry.summary and blacklist_summary and is_word_in_text(blacklist_summary, entry.summary):
        return True
    if (
        entry.content
        and entry.content[0].value
        and blacklist_content
        and is_word_in_text(blacklist_content, entry.content[0].value)
    ):
        return True
    if entry.author and blacklist_author and is_word_in_text(blacklist_author, entry.author):
        return True
    if (
        entry.content
        and entry.content[0].value
        and blacklist_content
        and is_word_in_text(blacklist_content, entry.content[0].value)
    ):
        return True

    # Check regex blacklist
    if entry.title and regex_blacklist_title and is_regex_match(regex_blacklist_title, entry.title):
        return True
    if entry.summary and regex_blacklist_summary and is_regex_match(regex_blacklist_summary, entry.summary):
        return True
    if (
        entry.content
        and entry.content[0].value
        and regex_blacklist_content
        and is_regex_match(regex_blacklist_content, entry.content[0].value)
    ):
        return True
    if entry.author and regex_blacklist_author and is_regex_match(regex_blacklist_author, entry.author):
        return True
    return bool(
        entry.content
        and entry.content[0].value
        and regex_blacklist_content
        and is_regex_match(regex_blacklist_content, entry.content[0].value),
    )
