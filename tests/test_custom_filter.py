import pathlib
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from discord_rss_bot.custom_filters import encode_url, entry_is_blacklisted, entry_is_whitelisted
from discord_rss_bot.settings import get_reader

if TYPE_CHECKING:
    from reader import Reader


def test_encode_url() -> None:
    # Test normal input
    assert_msg: str = "Got: {encode_url('https://www.example.com')}, Expected: https%3A//www.example.com"
    assert encode_url("https://www.example.com") == r"https%3A//www.example.com", assert_msg

    # Test input with spaces
    assert_msg: str = (
        "Got: {encode_url('https://www.example.com/my path')}, Expected: https%3A//www.example.com/my%20path"
    )
    assert encode_url("https://www.example.com/my path") == r"https%3A//www.example.com/my%20path", assert_msg

    # Test input with special characters
    assert_msg: str = f"Got: {encode_url('https://www.example.com/my path?q=abc&b=1')}, Expected: https%3A//www.example.com/my%20path%3Fq%3Dabc%26b%3D1"  # noqa: E501
    assert (
        encode_url("https://www.example.com/my path?q=abc&b=1")
        == r"https%3A//www.example.com/my%20path%3Fq%3Dabc%26b%3D1"
    ), assert_msg

    # Test empty input
    assert not encode_url(""), "Got: True, Expected: False"
    # Test input as None
    assert not encode_url(None), "Got: True, Expected: False"


def test_entry_is_whitelisted() -> None:
    # Test with a custom reader.
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory
        Path.mkdir(Path(temp_dir), exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "custom_loc_db.sqlite")
        custom_reader: Reader = get_reader(custom_location=str(custom_loc))

        # Add a feed to the database.
        custom_reader.add_feed("https://lovinator.space/rss_test.xml")
        custom_reader.update_feed("https://lovinator.space/rss_test.xml")

        # whitelist_title
        custom_reader.set_tag("https://lovinator.space/rss_test.xml", "whitelist_title", "fvnnnfnfdnfdnfd")  # type: ignore
        for entry in custom_reader.get_entries():
            if entry_is_whitelisted(entry) is True:
                assert entry.title == "fvnnnfnfdnfdnfd", f"Expected: fvnnnfnfdnfdnfd, Got: {entry.title}"
                break
        custom_reader.delete_tag("https://lovinator.space/rss_test.xml", "whitelist_title")

        # whitelist_summary
        custom_reader.set_tag("https://lovinator.space/rss_test.xml", "whitelist_summary", "fvnnnfnfdnfdnfd")  # type: ignore
        for entry in custom_reader.get_entries():
            if entry_is_whitelisted(entry) is True:
                assert entry.summary == "fvnnnfnfdnfdnfd", f"Expected: fvnnnfnfdnfdnfd, Got: {entry.summary}"
                break
        custom_reader.delete_tag("https://lovinator.space/rss_test.xml", "whitelist_summary")

        # whitelist_content
        custom_reader.set_tag("https://lovinator.space/rss_test.xml", "whitelist_content", "fvnnnfnfdnfdnfd")  # type: ignore
        for entry in custom_reader.get_entries():
            if entry_is_whitelisted(entry) is True:
                assert_msg = f"Expected: <p>ffdnfdnfdnfdnfdndfn</p>, Got: {entry.content[0].value}"
                assert entry.content[0].value == "<p>ffdnfdnfdnfdnfdndfn</p>", assert_msg
                break
        custom_reader.delete_tag("https://lovinator.space/rss_test.xml", "whitelist_content")

        # Close the reader, so we can delete the directory.
        custom_reader.close()


def test_entry_is_blacklisted() -> None:
    # Test with a custom reader.
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory
        Path.mkdir(Path(temp_dir), exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "custom_loc_db.sqlite")
        custom_reader: Reader = get_reader(custom_location=str(custom_loc))

        # Add a feed to the database.
        custom_reader.add_feed("https://lovinator.space/rss_test.xml")
        custom_reader.update_feed("https://lovinator.space/rss_test.xml")

        # blacklist_title
        custom_reader.set_tag("https://lovinator.space/rss_test.xml", "blacklist_title", "fvnnnfnfdnfdnfd")  # type: ignore
        for entry in custom_reader.get_entries():
            if entry_is_blacklisted(entry) is True:
                assert entry.title == "fvnnnfnfdnfdnfd", f"Expected: fvnnnfnfdnfdnfd, Got: {entry.title}"
                break
        custom_reader.delete_tag("https://lovinator.space/rss_test.xml", "blacklist_title")

        # blacklist_summary
        custom_reader.set_tag("https://lovinator.space/rss_test.xml", "blacklist_summary", "fvnnnfnfdnfdnfd")  # type: ignore
        for entry in custom_reader.get_entries():
            if entry_is_blacklisted(entry) is True:
                assert entry.summary == "fvnnnfnfdnfdnfd", f"Expected: fvnnnfnfdnfdnfd, Got: {entry.summary}"
                break
        custom_reader.delete_tag("https://lovinator.space/rss_test.xml", "blacklist_summary")

        # blacklist_content
        custom_reader.set_tag("https://lovinator.space/rss_test.xml", "blacklist_content", "fvnnnfnfdnfdnfd")  # type: ignore
        for entry in custom_reader.get_entries():
            if entry_is_blacklisted(entry) is True:
                assert_msg = f"Expected: <p>ffdnfdnfdnfdnfdndfn</p>, Got: {entry.content[0].value}"
                assert entry.content[0].value == "<p>ffdnfdnfdnfdnfdndfn</p>", assert_msg
                break
        custom_reader.delete_tag("https://lovinator.space/rss_test.xml", "blacklist_content")

        # Close the reader, so we can delete the directory.
        custom_reader.close()
