import os
import pathlib
import tempfile

from reader import Reader

from discord_rss_bot.custom_filters import encode_url, entry_is_blacklisted, entry_is_whitelisted
from discord_rss_bot.settings import get_reader


def test_encode_url() -> None:
    # Test normal input
    assert encode_url("https://www.example.com") == r"https%3A//www.example.com"
    # Test input with spaces
    assert encode_url("https://www.example.com/my path") == r"https%3A//www.example.com/my%20path"
    # Test input with special characters
    assert (
        encode_url("https://www.example.com/my path?q=abc&b=1")
        == r"https%3A//www.example.com/my%20path%3Fq%3Dabc%26b%3D1"
    )
    # Test empty input
    assert encode_url("") == ""
    # Test input as None
    assert encode_url(None) == ""  # type: ignore


def test_entry_is_whitelisted() -> None:
    # Test with a custom reader.
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory
        os.makedirs(temp_dir, exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "custom_loc_db.sqlite")
        custom_reader: Reader = get_reader(custom_location=str(custom_loc))

        # Add a feed to the database.
        custom_reader.add_feed("https://lovinator.space/rss_test.xml")
        custom_reader.update_feed("https://lovinator.space/rss_test.xml")

        # whitelist_title
        custom_reader.set_tag("https://lovinator.space/rss_test.xml", "whitelist_title", "fvnnnfnfdnfdnfd")  # type: ignore # noqa: E501
        for entry in custom_reader.get_entries():
            if entry_is_whitelisted(entry) is True:
                assert entry.title == "fvnnnfnfdnfdnfd"
                break
        custom_reader.delete_tag("https://lovinator.space/rss_test.xml", "whitelist_title")

        # whitelist_summary
        custom_reader.set_tag("https://lovinator.space/rss_test.xml", "whitelist_summary", "fvnnnfnfdnfdnfd")  # type: ignore # noqa: E501
        for entry in custom_reader.get_entries():
            if entry_is_whitelisted(entry) is True:
                assert entry.summary == "fvnnnfnfdnfdnfd"
                break
        custom_reader.delete_tag("https://lovinator.space/rss_test.xml", "whitelist_summary")

        # whitelist_content
        custom_reader.set_tag("https://lovinator.space/rss_test.xml", "whitelist_content", "fvnnnfnfdnfdnfd")  # type: ignore # noqa: E501
        for entry in custom_reader.get_entries():
            if entry_is_whitelisted(entry) is True:
                assert entry.content[0].value == "<p>ffdnfdnfdnfdnfdndfn</p>"
                break
        custom_reader.delete_tag("https://lovinator.space/rss_test.xml", "whitelist_content")

        # Close the reader, so we can delete the directory.
        custom_reader.close()


def test_entry_is_blacklisted() -> None:
    # Test with a custom reader.
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the temp directory
        os.makedirs(temp_dir, exist_ok=True)

        custom_loc: pathlib.Path = pathlib.Path(temp_dir, "custom_loc_db.sqlite")
        custom_reader: Reader = get_reader(custom_location=str(custom_loc))

        # Add a feed to the database.
        custom_reader.add_feed("https://lovinator.space/rss_test.xml")
        custom_reader.update_feed("https://lovinator.space/rss_test.xml")

        # blacklist_title
        custom_reader.set_tag("https://lovinator.space/rss_test.xml", "blacklist_title", "fvnnnfnfdnfdnfd")  # type: ignore # noqa: E501
        for entry in custom_reader.get_entries():
            if entry_is_blacklisted(entry) is True:
                assert entry.title == "fvnnnfnfdnfdnfd"
                break
        custom_reader.delete_tag("https://lovinator.space/rss_test.xml", "blacklist_title")

        # blacklist_summary
        custom_reader.set_tag("https://lovinator.space/rss_test.xml", "blacklist_summary", "fvnnnfnfdnfdnfd")  # type: ignore # noqa: E501
        for entry in custom_reader.get_entries():
            if entry_is_blacklisted(entry) is True:
                assert entry.summary == "fvnnnfnfdnfdnfd"
                break
        custom_reader.delete_tag("https://lovinator.space/rss_test.xml", "blacklist_summary")

        # blacklist_content
        custom_reader.set_tag("https://lovinator.space/rss_test.xml", "blacklist_content", "fvnnnfnfdnfdnfd")  # type: ignore # noqa: E501
        for entry in custom_reader.get_entries():
            if entry_is_blacklisted(entry) is True:
                assert entry.content[0].value == "<p>ffdnfdnfdnfdnfdndfn</p>"
                break
        custom_reader.delete_tag("https://lovinator.space/rss_test.xml", "blacklist_content")

        # Close the reader, so we can delete the directory.
        custom_reader.close()
