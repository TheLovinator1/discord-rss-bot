from __future__ import annotations

from discord_rss_bot.filter.utils import is_word_in_text


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
