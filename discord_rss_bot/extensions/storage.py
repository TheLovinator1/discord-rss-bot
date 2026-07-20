"""Per-feed storage of enabled extension lists.

Enabled extensions for a feed are stored as a JSON list in the reader
tag ``"extensions"``.  An empty list or missing tag means no extensions
are active for that feed.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from typing import cast

if TYPE_CHECKING:
    from reader import Reader
    from reader.types import JSONType

logger: logging.Logger = logging.getLogger(__name__)

EXTENSIONS_TAG: str = "extensions"


def get_enabled_extensions_for_feed(reader: Reader, feed_url: str) -> list[str]:
    """Return the list of enabled extension names for the given feed.

    Args:
        reader: The reader instance.
        feed_url: The feed URL.

    Returns:
        List of extension names enabled for this feed.  Never ``None``.
    """
    raw = reader.get_tag(feed_url, EXTENSIONS_TAG, None)
    if raw is None:
        return []

    if isinstance(raw, list):
        return [str(name) for name in raw]

    if isinstance(raw, str):
        if not raw.strip():
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(name) for name in parsed]
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse extensions tag for feed %r: %r", feed_url, raw)
            return []

    logger.warning("Unexpected type for extensions tag on feed %r: %s (%s)", feed_url, type(raw).__name__, raw)
    return []


def set_enabled_extensions_for_feed(
    reader: Reader,
    feed_url: str,
    extension_names: list[str],
) -> None:
    """Persist a list of enabled extension names for a feed.

    Args:
        reader: The reader instance.
        feed_url: The feed URL.
        extension_names: Extension names to enable (empty = disable all).
    """
    reader.set_tag(feed_url, EXTENSIONS_TAG, cast("JSONType", extension_names))
