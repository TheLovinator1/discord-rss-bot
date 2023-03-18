import re


def is_word_in_text(words: str, text: str) -> bool:
    """Check if the word is in the text.

    Args:
        words: The words to search for.
        text: The text to search in.

    Returns:
        bool: If the word is in the text.
    """
    # Split the word list into a list of words.
    word_list: list[str] = words.split(",")

    # Check if each word is in the text.
    for word in word_list:
        look_for: str = rf"(^|[^\w]){word}([^\w]|$)"
        pattern: re.Pattern[str] = re.compile(look_for, re.IGNORECASE)
        if re.search(pattern, text):
            return True
    return False
