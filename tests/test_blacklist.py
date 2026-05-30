from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from typing import cast

from reader import Entry
from reader import Feed
from reader import Reader
from reader import make_reader

from discord_rss_bot.filter.blacklist import entry_should_be_skipped
from discord_rss_bot.filter.blacklist import feed_has_blacklist_tags
from discord_rss_bot.filter.evaluator import evaluate_entry_filters
from discord_rss_bot.filter.evaluator import get_entry_fields
from discord_rss_bot.filter.evaluator import get_filter_values_from_reader

if TYPE_CHECKING:
    from collections.abc import Iterable

feed_url: str = "https://lovinator.space/rss_test.xml"


# Create the database
def get_reader() -> Reader:
    tempdir: Path = Path(tempfile.mkdtemp())

    reader_database: Path = tempdir / "test.sqlite"
    reader: Reader = make_reader(url=str(reader_database))

    return reader


def test_has_black_tags() -> None:
    reader: Reader = get_reader()

    # Add feed and update entries
    reader.add_feed(feed_url)
    feed: Feed = reader.get_feed(feed_url)
    reader.update_feeds()

    # Test feed without any blacklist tags
    assert_msg: str = "Feed should not have any blacklist tags"
    assert feed_has_blacklist_tags(reader=get_reader(), feed=feed) is False, assert_msg

    check_if_has_tag(reader, feed, "blacklist_title")
    check_if_has_tag(reader, feed, "blacklist_summary")
    check_if_has_tag(reader, feed, "blacklist_content")
    check_if_has_tag(reader, feed, "blacklist_author")

    # Test regex blacklist tags
    check_if_has_tag(reader, feed, "regex_blacklist_title")
    check_if_has_tag(reader, feed, "regex_blacklist_summary")
    check_if_has_tag(reader, feed, "regex_blacklist_content")
    check_if_has_tag(reader, feed, "regex_blacklist_author")

    # Clean up
    reader.delete_feed(feed_url)


def check_if_has_tag(reader: Reader, feed: Feed, blacklist_name: str) -> None:
    reader.set_tag(feed, blacklist_name, "a")  # pyright: ignore[reportArgumentType]
    assert_msg: str = f"Feed should have blacklist tags: {blacklist_name}"
    assert feed_has_blacklist_tags(reader=reader, feed=feed) is True, assert_msg

    asset_msg: str = f"Feed should not have any blacklist tags: {blacklist_name}"
    reader.delete_tag(feed, blacklist_name)
    assert feed_has_blacklist_tags(reader=reader, feed=feed) is False, asset_msg


def test_get_entry_fields_uses_authors_str() -> None:
    entry = cast(
        "Entry",
        SimpleNamespace(
            title="Title",
            summary="Summary",
            content=[],
            author="Legacy Author",
            authors_str="Author One, Author Two",
        ),
    )

    fields: dict[str, str] = get_entry_fields(entry)

    assert fields["author"] == "Author One, Author Two"


def test_should_be_skipped() -> None:
    reader: Reader = get_reader()

    # Add feed and update entries
    reader.add_feed(feed_url)
    feed: Feed = reader.get_feed(feed_url)
    reader.update_feeds()

    # Get first entry
    first_entry: list[Entry] = []
    entries: Iterable[Entry] = reader.get_entries(feed=feed)
    assert entries is not None, f"Entries should not be None: {entries}"
    for entry in entries:
        first_entry.append(entry)
        break
    assert len(first_entry) == 1, f"First entry should be added: {first_entry}"

    # Test entry without any blacklists
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    # Test standard blacklist functionality
    reader.set_tag(feed, "blacklist_title", "fvnnnfnfdnfdnfd")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is True, f"Entry should be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_title")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_title", "åäö")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_title")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_summary", "ffdnfdnfdnfdnfdndfn")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is True, f"Entry should be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_summary")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_summary", "åäö")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_summary")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_content", "ffdnfdnfdnfdnfdndfn")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is True, f"Entry should be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_content")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_content", "åäö")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_content")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_author", "TheLovinator")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is True, f"Entry should be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_author")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_author", "åäö")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_author")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"


def test_regex_should_be_skipped() -> None:
    """Test the regex filtering functionality for blacklist."""
    reader: Reader = get_reader()

    # Add feed and update entries
    reader.add_feed(feed_url)
    feed: Feed = reader.get_feed(feed_url)
    reader.update_feeds()

    # Get first entry
    first_entry: list[Entry] = []
    entries: Iterable[Entry] = reader.get_entries(feed=feed)
    assert entries is not None, f"Entries should not be None: {entries}"
    for entry in entries:
        first_entry.append(entry)
        break
    assert len(first_entry) == 1, f"First entry should be added: {first_entry}"

    # Test entry without any regex blacklists
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    # Test regex blacklist for title
    reader.set_tag(feed, "regex_blacklist_title", r"fvnnn\w+")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is True, (
        f"Entry should be skipped with regex title match: {first_entry[0]}"
    )
    reader.delete_tag(feed, "regex_blacklist_title")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    # Test regex blacklist for summary
    reader.set_tag(feed, "regex_blacklist_summary", r"ffdnfdn\w+")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is True, (
        f"Entry should be skipped with regex summary match: {first_entry[0]}"
    )
    reader.delete_tag(feed, "regex_blacklist_summary")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    # Test regex blacklist for content
    reader.set_tag(feed, "regex_blacklist_content", r"ffdnfdnfdn\w+")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is True, (
        f"Entry should be skipped with regex content match: {first_entry[0]}"
    )
    reader.delete_tag(feed, "regex_blacklist_content")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    # Test regex blacklist for author
    reader.set_tag(feed, "regex_blacklist_author", r"TheLovinator\d*")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is True, (
        f"Entry should be skipped with regex author match: {first_entry[0]}"
    )
    reader.delete_tag(feed, "regex_blacklist_author")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    # Test invalid regex pattern (should not raise an exception)
    reader.set_tag(feed, "regex_blacklist_title", r"[incomplete")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is False, (
        f"Entry should not be skipped with invalid regex: {first_entry[0]}"
    )
    reader.delete_tag(feed, "regex_blacklist_title")

    # Test multiple regex patterns separated by commas
    reader.set_tag(feed, "regex_blacklist_author", r"pattern1,TheLovinator\d*,pattern3")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is True, (
        f"Entry should be skipped with one matching pattern in list: {first_entry[0]}"
    )
    reader.delete_tag(feed, "regex_blacklist_author")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    # Test newline-separated regex patterns
    newline_patterns = "pattern1\nTheLovinator\\d*\npattern3"
    reader.set_tag(feed, "regex_blacklist_author", newline_patterns)  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is True, (
        f"Entry should be skipped with newline-separated patterns: {first_entry[0]}"
    )
    reader.delete_tag(feed, "regex_blacklist_author")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"


def test_blacklist_match_overrides_whitelist_match() -> None:
    """A blacklist hit should beat a whitelist hit in the final decision."""
    reader: Reader = get_reader()

    reader.add_feed(feed_url)
    feed: Feed = reader.get_feed(feed_url)
    reader.update_feeds()

    first_entry: list[Entry] = []
    entries: Iterable[Entry] = reader.get_entries(feed=feed)
    for entry in entries:
        first_entry.append(entry)
        break

    assert len(first_entry) == 1, f"First entry should be added: {first_entry}"

    reader.set_tag(feed, "blacklist_title", "fvnnnfnfdnfdnfd")  # pyright: ignore[reportArgumentType]
    reader.set_tag(feed, "whitelist_title", "fvnnnfnfdnfdnfd")  # pyright: ignore[reportArgumentType]

    decision = evaluate_entry_filters(
        first_entry[0],
        blacklist_values=get_filter_values_from_reader(reader, feed, "blacklist"),
        whitelist_values=get_filter_values_from_reader(reader, feed, "whitelist"),
    )

    assert decision.should_send is False, "Blacklist match should override whitelist match"
    assert decision.blacklist_match is not None, "Expected a blacklist match"
    assert decision.whitelist_match is not None, "Expected a whitelist match"
    assert "blacklist overrides whitelist" in decision.reason


def test_blacklist_substring_match_on_title() -> None:
    """Blacklist plain-text rules should match title substrings."""
    reader: Reader = get_reader()

    reader.add_feed(feed_url)
    feed: Feed = reader.get_feed(feed_url)
    reader.update_feeds()

    first_entry: list[Entry] = []
    entries: Iterable[Entry] = reader.get_entries(feed=feed)
    for entry in entries:
        first_entry.append(entry)
        break

    assert len(first_entry) == 1, f"First entry should be added: {first_entry}"

    reader.set_tag(feed, "blacklist_title", "vnnnfn")  # pyright: ignore[reportArgumentType]
    assert entry_should_be_skipped(reader, first_entry[0]) is True, "Substring title match should blacklist the entry"
