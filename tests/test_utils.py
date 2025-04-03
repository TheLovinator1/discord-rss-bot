from __future__ import annotations

from discord_rss_bot.filter.utils import is_regex_match, is_word_in_text


def test_is_word_in_text() -> None:
    msg_true = "Should return True"
    msg_false = "Should return False"

    assert is_word_in_text("word1,word2", "This is a sample text containing word1 and word2.") is True, msg_true
    assert is_word_in_text("word1,word2", "This is a sample text containing word1.") is True, msg_true
    assert is_word_in_text("word1,word2", "This is a sample text containing word2.") is True, msg_true
    assert is_word_in_text("word1,word2", "This is a sample text containing WORD1 and WORD2.") is True, msg_true
    assert is_word_in_text("Alert,Forma", "Outbreak - Mutagen Mass - Rhea (Saturn)") is False, msg_false
    assert is_word_in_text("Alert,Forma", "Outbreak - Mutagen Mass - Rhea (Saturn)") is False, msg_false
    assert is_word_in_text("word1,word2", "This is a sample text containing none of the words.") is False, msg_false


def test_is_regex_match() -> None:
    msg_true = "Should return True"
    msg_false = "Should return False"

    # Test basic regex patterns
    assert is_regex_match(r"word\d+", "This text contains word123") is True, msg_true
    assert is_regex_match(r"^Hello", "Hello world") is True, msg_true
    assert is_regex_match(r"world$", "Hello world") is True, msg_true

    # Test case insensitivity
    assert is_regex_match(r"hello", "This text contains HELLO") is True, msg_true

    # Test comma-separated patterns
    assert is_regex_match(r"pattern1,pattern2", "This contains pattern2") is True, msg_true
    assert is_regex_match(r"pattern1, pattern2", "This contains pattern1") is True, msg_true

    # Test regex that shouldn't match
    assert is_regex_match(r"^start", "This doesn't start with the pattern") is False, msg_false
    assert is_regex_match(r"end$", "This doesn't end with the pattern") is False, msg_false

    # Test with empty input
    assert is_regex_match("", "Some text") is False, msg_false
    assert is_regex_match("pattern", "") is False, msg_false

    # Test with invalid regex (should not raise an exception and return False)
    assert is_regex_match(r"[incomplete", "Some text") is False, msg_false

    # Test with multiple patterns where one is invalid
    assert is_regex_match(r"valid, [invalid, \w+", "Contains word") is True, msg_true

    # Test newline-separated patterns
    newline_patterns = "pattern1\n^start\ncontains\\d+"
    assert is_regex_match(newline_patterns, "This contains123 text") is True, msg_true
    assert is_regex_match(newline_patterns, "start of line") is True, msg_true
    assert is_regex_match(newline_patterns, "pattern1 is here") is True, msg_true
    assert is_regex_match(newline_patterns, "None of these match") is False, msg_false

    # Test mixed newline and comma patterns (for backward compatibility)
    mixed_patterns = "pattern1\npattern2,pattern3\npattern4"
    assert is_regex_match(mixed_patterns, "Contains pattern3") is True, msg_true
    assert is_regex_match(mixed_patterns, "Contains pattern4") is True, msg_true

    # Test with empty lines and spaces
    whitespace_patterns = "\\s+\n \n\npattern\n\n"
    assert is_regex_match(whitespace_patterns, "text with    spaces") is True, msg_true
    assert is_regex_match(whitespace_patterns, "text with pattern") is True, msg_true
