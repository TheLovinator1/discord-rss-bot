"""YouTube feed extension: extracts video IDs from YouTube video URLs.

Detects feeds from ``youtube.com/feeds/videos.xml`` and exposes the
video ID as ``{{youtube_video_id}}`` and the full embeddable URL as
``{{youtube_embed_url}}``.

Usage:
    1. Enable ``youtube`` on the feed's Extensions page.
    2. Use ``{{youtube_video_id}}`` or ``{{youtube_embed_url}}`` in
       your message template or embed.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from typing import ClassVar
from urllib.parse import parse_qs
from urllib.parse import urlparse

from discord_rss_bot.extensions.base import FeedExtension

if TYPE_CHECKING:
    from reader import Entry
    from reader import Reader

logger: logging.Logger = logging.getLogger(__name__)

# Various YouTube URL formats for video ID extraction.
_VIDEO_ID_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:v|vi|video)=([\w-]+)"),
    re.compile(r"(?:youtu\.be|youtube\.com/embed)/([\w-]+)"),
    re.compile(r"^([\w-]{11})$"),
)


def extract_youtube_video_id(url: str) -> str | None:
    """Extract a YouTube video ID from a URL.

    Args:
        url: The YouTube video URL.

    Returns:
        The video ID if found, otherwise ``None``.
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    # Try query parameter first
    for value in parse_qs(parsed.query).get("v", []):
        if value.strip():
            return value.strip()

    # Try path-based patterns
    for pattern in _VIDEO_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)

    return None


def is_youtube_feed_url(feed_url: str) -> bool:
    """Return whether a feed URL is a YouTube video feed."""
    return "youtube.com/feeds/videos.xml" in (feed_url or "")


class YouTubeExtension(FeedExtension):
    """Extract YouTube video IDs from entry links.

    Makes ``{{youtube_video_id}}`` and ``{{youtube_embed_url}}``
    available for YouTube channel feeds.
    """

    name = "youtube"
    description = (
        "Extracts the YouTube video ID from entry links. Available as {{youtube_video_id}} and {{youtube_embed_url}}."
    )
    provides_variables: ClassVar[list[str]] = ["youtube_video_id", "youtube_embed_url"]
    auto_enable_url_patterns: ClassVar[list[str]] = [
        r"youtube\.com/feeds/videos\.xml",
    ]

    def process_entry(self, entry: Entry, _reader: Reader) -> dict[str, str]:
        """Extract the video ID from the entry link.

        Args:
            entry: The feed entry to process.

        Returns:
            Dict with ``youtube_video_id`` and ``youtube_embed_url`` if
            this is a YouTube feed, otherwise empty dict.
        """
        if not is_youtube_feed_url(entry.feed.url):
            return {}

        entry_link: str = entry.link or ""
        video_id: str | None = extract_youtube_video_id(entry_link)
        if not video_id:
            return {}

        return {
            "youtube_video_id": video_id,
            "youtube_embed_url": f"https://www.youtube.com/watch?v={video_id}",
        }
