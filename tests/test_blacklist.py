import tempfile
from pathlib import Path
from typing import Iterable

from reader import Entry, Feed, Reader, make_reader

from discord_rss_bot.filter.blacklist import (
    get_blacklist_content,
    get_blacklist_summary,
    get_blacklist_title,
    has_black_tags,
    should_be_skipped,
)

feed_url = "https://lovinator.space/rss_test.xml"


# Create the database
def get_reader() -> Reader:
    tempdir: Path = Path(tempfile.mkdtemp())

    reader_database: Path = tempdir / "test.sqlite"
    reader: Reader = make_reader(url=str(reader_database))

    return reader


def test_has_black_tags():
    reader: Reader = get_reader()

    # Add feed and update entries
    reader.add_feed(feed_url)
    feed: Feed = reader.get_feed(feed_url)
    reader.update_feeds()

    # Test feed without any blacklist tags
    assert has_black_tags(custom_reader=get_reader(), feed=feed) is False

    check_if_has_tag(reader, feed, "blacklist_title")
    check_if_has_tag(reader, feed, "blacklist_summary")
    check_if_has_tag(reader, feed, "blacklist_content")

    # Clean up
    reader.delete_feed(feed_url)


def check_if_has_tag(reader, feed, blacklist_name):
    reader.set_tag(feed, blacklist_name, "a")
    assert has_black_tags(custom_reader=reader, feed=feed) is True
    reader.delete_tag(feed, blacklist_name)
    assert has_black_tags(custom_reader=reader, feed=feed) is False


def test_should_be_skipped():
    reader: Reader = get_reader()

    # Add feed and update entries
    reader.add_feed(feed_url)
    feed: Feed = reader.get_feed(feed_url)
    reader.update_feeds()

    # Get first entry
    first_entry: list[Entry] = []
    entries: Iterable[Entry] = reader.get_entries(feed=feed)
    assert entries is not None
    for entry in entries:
        first_entry.append(entry)
        break
    assert len(first_entry) == 1

    # Test entry without any blacklists
    assert should_be_skipped(reader, first_entry[0]) is False

    reader.set_tag(feed, "blacklist_title", "fvnnnfnfdnfdnfd")  # type: ignore
    assert should_be_skipped(reader, first_entry[0]) is True
    reader.delete_tag(feed, "blacklist_title")
    assert should_be_skipped(reader, first_entry[0]) is False

    reader.set_tag(feed, "blacklist_summary", "ffdnfdnfdnfdnfdndfn")  # type: ignore
    assert should_be_skipped(reader, first_entry[0]) is True
    reader.delete_tag(feed, "blacklist_summary")
    assert should_be_skipped(reader, first_entry[0]) is False

    reader.set_tag(feed, "blacklist_content", "ffdnfdnfdnfdnfdndfn")  # type: ignore
    # TODO: This is not impelemented yes
    assert should_be_skipped(reader, first_entry[0]) is False
    reader.delete_tag(feed, "blacklist_content")
    assert should_be_skipped(reader, first_entry[0]) is False

    # TODO: Also add support for entry_text


def test_get_blacklist_content():
    reader: Reader = get_reader()

    # Add feed and update entries
    reader.add_feed(feed_url)
    feed: Feed = reader.get_feed(feed_url)
    reader.update_feeds()

    assert get_blacklist_content(reader, feed) == ""  # type: ignore

    reader.set_tag(feed, "blacklist_content", "ffdnfdnfdnfdnfdndfn")  # type: ignore
    assert get_blacklist_content(reader, feed) == "ffdnfdnfdnfdnfdndfn"  # type: ignore

    reader.delete_tag(feed, "blacklist_content")
    assert get_blacklist_content(reader, feed) == ""  # type: ignore


def test_get_blacklist_summary():
    reader: Reader = get_reader()

    # Add feed and update entries
    reader.add_feed(feed_url)
    feed: Feed = reader.get_feed(feed_url)
    reader.update_feeds()

    assert get_blacklist_summary(reader, feed) == ""  # type: ignore

    reader.set_tag(feed, "blacklist_summary", "ffdnfdnfdnfdnfdndfn")  # type: ignore
    assert get_blacklist_summary(reader, feed) == "ffdnfdnfdnfdnfdndfn"  # type: ignore

    reader.delete_tag(feed, "blacklist_summary")
    assert get_blacklist_summary(reader, feed) == ""  # type: ignore


def test_get_blacklist_title():
    reader: Reader = get_reader()

    # Add feed and update entries
    reader.add_feed(feed_url)
    feed: Feed = reader.get_feed(feed_url)
    reader.update_feeds()

    assert get_blacklist_title(reader, feed) == ""  # type: ignore

    reader.set_tag(feed, "blacklist_title", "ffdnfdnfdnfdnfdndfn")  # type: ignore
    assert get_blacklist_title(reader, feed) == "ffdnfdnfdnfdnfdndfn"  # type: ignore

    reader.delete_tag(feed, "blacklist_title")
    assert get_blacklist_title(reader, feed) == ""  # type: ignore
