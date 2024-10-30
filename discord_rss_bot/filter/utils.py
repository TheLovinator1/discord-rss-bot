from __future__ import annotations

import re


def is_word_in_text(word_string: str, text: str) -> bool:
    """Check if any of the words are in the text.

    Args:
        word_string: A comma-separated string of words to search for.
        text: The text to search in.

    Returns:
        bool: True if any word is found in the text, otherwise False.
    """
    word_list: list[str] = word_string.split(",")

    # Compile regex patterns for each word.
    patterns: list[re.Pattern[str]] = [re.compile(rf"(^|[^\w]){word}([^\w]|$)", re.IGNORECASE) for word in word_list]

    # Check if any pattern matches the text.
    return any(pattern.search(text) for pattern in patterns)
