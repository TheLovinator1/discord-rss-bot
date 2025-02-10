from __future__ import annotations

from urllib.parse import ParseResult, urlparse


def is_url_valid(url: str) -> bool:
    """Check if a URL is valid.

    Args:
        url: The URL to check.

    Returns:
        bool: True if the URL is valid, False otherwise.
    """
    try:
        result: ParseResult = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False
