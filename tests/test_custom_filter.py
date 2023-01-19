import os
import pathlib
import tempfile

from reader import Reader

from discord_rss_bot.custom_filters import convert_to_md, encode_url, entry_is_blacklisted, entry_is_whitelisted
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


def test_convert_to_md():
    # Test normal input
    assert (
        convert_to_md("<h1>Headline</h1><h2>Subheadline</h2><h3>subsubheadline</h3>")
        == """Headline
========

Subheadline
-----------

### subsubheadline

"""
    )
    # Test input with tables
    assert (
        convert_to_md(
            "<table><thead><tr><th>Column 1</th><th>Column 2</th><th>Column 3</th></tr></thead><tbody><tr><td>Row 1, Column 1</td><td>Row 1, Column 2</td><td>Row 1, Column 3</td></tr><tr><td>Row 2, Column 1</td><td>Row 2, Column 2</td><td>Row 2, Column 3</td></tr></tbody></table>"  # noqa: E501
        )
        == "Column 1Column 2Column 3Row 1, Column 1Row 1, Column 2Row 1, Column 3Row 2, Column 1Row 2, Column 2Row 2, Column 3"  # noqa: E501
    )
    # Test empty input
    assert convert_to_md("") == ""
    # Test input as None
    assert convert_to_md(None) == ""  # type: ignore
