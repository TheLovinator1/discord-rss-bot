from __future__ import annotations

import logging
import re

logger: logging.Logger = logging.getLogger(__name__)


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


def is_regex_match(regex_string: str, text: str) -> bool:
    """Check if any of the regex patterns match the text.

    Args:
        regex_string: A string containing regex patterns, separated by newlines or commas.
        text: The text to search in.

    Returns:
        bool: True if any regex pattern matches the text, otherwise False.
    """
    if not regex_string or not text:
        return False

    # Split by newlines first, then by commas (for backward compatibility)
    regex_list: list[str] = []

    # First split by newlines
    lines: list[str] = regex_string.split("\n")
    for line in lines:
        stripped_line: str = line.strip()
        if stripped_line:
            # For backward compatibility, also split by commas if there are any
            if "," in stripped_line:
                regex_list.extend([part.strip() for part in stripped_line.split(",") if part.strip()])
            else:
                regex_list.append(stripped_line)

    # Attempt to compile and apply each regex pattern
    for pattern_str in regex_list:
        if not pattern_str:
            logger.warning("Empty regex pattern found in the list.")
            continue

        try:
            pattern: re.Pattern[str] = re.compile(pattern_str, re.IGNORECASE)
            if pattern.search(text):
                logger.info("Regex pattern matched: %s", pattern_str)
                return True
        except re.error:
            logger.warning("Invalid regex pattern: %s", pattern_str)
            continue

    logger.info("No regex patterns matched.")

    return False
