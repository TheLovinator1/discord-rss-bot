import tempfile
from pathlib import Path
from typing import Iterable

from reader import Entry, Feed, Reader, make_reader

from discord_rss_bot.filter.whitelist import has_white_tags, should_be_sent

feed_url: str = "https://lovinator.space/rss_test.xml"


# Create the database
def get_reader() -> Reader:
    tempdir: Path = Path(tempfile.mkdtemp())

    reader_database: Path = tempdir / "test.sqlite"
    reader: Reader = make_reader(url=str(reader_database))

    return reader


def test_has_white_tags() -> None:
    reader: Reader = get_reader()

    # Add feed and update entries
    reader.add_feed(feed_url)
    feed: Feed = reader.get_feed(feed_url)
    reader.update_feeds()

    # Test feed without any whitelist tags
    assert has_white_tags(custom_reader=get_reader(), feed=feed) is False

    check_if_has_tag(reader, feed, "whitelist_title")
    check_if_has_tag(reader, feed, "whitelist_summary")
    check_if_has_tag(reader, feed, "whitelist_content")

    # Clean up
    reader.delete_feed(feed_url)


def check_if_has_tag(reader: Reader, feed: Feed, whitelist_name: str) -> None:
    reader.set_tag(feed, whitelist_name, "a")  # type: ignore
    assert has_white_tags(custom_reader=reader, feed=feed) is True
    reader.delete_tag(feed, whitelist_name)
    assert has_white_tags(custom_reader=reader, feed=feed) is False


def test_should_be_sent() -> None:
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

    # Test entry without any whitelists
    assert should_be_sent(reader, first_entry[0]) is False

    reader.set_tag(feed, "whitelist_title", "fvnnnfnfdnfdnfd")  # type: ignore
    assert should_be_sent(reader, first_entry[0]) is True
    reader.delete_tag(feed, "whitelist_title")
    assert should_be_sent(reader, first_entry[0]) is False

    reader.set_tag(feed, "whitelist_title", "åäö")  # type: ignore
    assert should_be_sent(reader, first_entry[0]) is False
    reader.delete_tag(feed, "whitelist_title")
    assert should_be_sent(reader, first_entry[0]) is False

    reader.set_tag(feed, "whitelist_summary", "ffdnfdnfdnfdnfdndfn")  # type: ignore
    assert should_be_sent(reader, first_entry[0]) is True
    reader.delete_tag(feed, "whitelist_summary")
    assert should_be_sent(reader, first_entry[0]) is False

    reader.set_tag(feed, "whitelist_summary", "åäö")  # type: ignore
    assert should_be_sent(reader, first_entry[0]) is False
    reader.delete_tag(feed, "whitelist_summary")
    assert should_be_sent(reader, first_entry[0]) is False

    reader.set_tag(feed, "whitelist_content", "ffdnfdnfdnfdnfdndfn")  # type: ignore
    # TODO: This is not impelemented yet
    assert should_be_sent(reader, first_entry[0]) is False
    reader.delete_tag(feed, "whitelist_content")
    assert should_be_sent(reader, first_entry[0]) is False

    # TODO: Also add support for entry_text
