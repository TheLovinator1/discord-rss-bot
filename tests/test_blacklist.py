from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from reader import Entry, Feed, Reader, make_reader

from discord_rss_bot.filter.blacklist import entry_should_be_skipped, feed_has_blacklist_tags

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
    assert feed_has_blacklist_tags(custom_reader=get_reader(), feed=feed) is False, assert_msg

    check_if_has_tag(reader, feed, "blacklist_title")
    check_if_has_tag(reader, feed, "blacklist_summary")
    check_if_has_tag(reader, feed, "blacklist_content")

    # Clean up
    reader.delete_feed(feed_url)


def check_if_has_tag(reader: Reader, feed: Feed, blacklist_name: str) -> None:
    reader.set_tag(feed, blacklist_name, "a")  # type: ignore
    assert_msg: str = f"Feed should have blacklist tags: {blacklist_name}"
    assert feed_has_blacklist_tags(custom_reader=reader, feed=feed) is True, assert_msg

    asset_msg: str = f"Feed should not have any blacklist tags: {blacklist_name}"
    reader.delete_tag(feed, blacklist_name)
    assert feed_has_blacklist_tags(custom_reader=reader, feed=feed) is False, asset_msg


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

    reader.set_tag(feed, "blacklist_title", "fvnnnfnfdnfdnfd")  # type: ignore
    assert entry_should_be_skipped(reader, first_entry[0]) is True, f"Entry should be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_title")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_title", "åäö")  # type: ignore
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_title")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_summary", "ffdnfdnfdnfdnfdndfn")  # type: ignore
    assert entry_should_be_skipped(reader, first_entry[0]) is True, f"Entry should be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_summary")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_summary", "åäö")  # type: ignore
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_summary")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_content", "ffdnfdnfdnfdnfdndfn")  # type: ignore
    assert entry_should_be_skipped(reader, first_entry[0]) is True, f"Entry should be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_content")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_content", "åäö")  # type: ignore
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_content")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_author", "TheLovinator")  # type: ignore
    assert entry_should_be_skipped(reader, first_entry[0]) is True, f"Entry should be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_author")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"

    reader.set_tag(feed, "blacklist_author", "åäö")  # type: ignore
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"
    reader.delete_tag(feed, "blacklist_author")
    assert entry_should_be_skipped(reader, first_entry[0]) is False, f"Entry should not be skipped: {first_entry[0]}"
