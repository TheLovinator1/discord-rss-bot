"""WordPress REST API extension: fetch post content with scripts intact.

Shares the batch cache with ``jwplayer_thumbnail`` so only one API call
is made per site regardless of which extension is enabled.

Provides ``{{wp_content}}`` (formatted) / ``{{wp_content_raw}}`` (raw HTML),
``{{wp_excerpt}}`` (formatted) / ``{{wp_excerpt_raw}}`` (raw HTML),
``{{wp_jwplayer_thumbnail}}`` and ``{{wp_jwplayer_file}}``.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from typing import ClassVar
from urllib.parse import quote
from urllib.parse import urlparse

from discord_rss_bot.extensions.base import FeedExtension
from discord_rss_bot.extensions.jwplayer_thumbnail import _extract_slug
from discord_rss_bot.extensions.jwplayer_thumbnail import _get_post_data_for_slug
from discord_rss_bot.html_format import format_entry_html_for_discord

if TYPE_CHECKING:
    from reader import Entry
    from reader import Reader

logger: logging.Logger = logging.getLogger(__name__)

_IMAGE_PATTERN: re.Pattern[str] = re.compile(
    r'image:\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

_FILE_PATTERN: re.Pattern[str] = re.compile(
    r'file:\s*["\']([^"\']+\.\w+)["\']',
    re.IGNORECASE,
)


class WordPressExtension(FeedExtension):
    """Fetch post content from the WordPress REST API.

    Retrieves full post HTML so that ``<script>`` blocks survive.
    Shares the batch cache with ``jwplayer_thumbnail``.
    """

    name = "wordpress"
    description = (
        "Fetches post HTML from the WordPress REST API (batched). "
        "Extracts JWPlayer URLs. "
        "Available as {{wp_content}} (formatted) / {{wp_content_raw}} (raw HTML), "
        "{{wp_excerpt}} (formatted) / {{wp_excerpt_raw}} (raw HTML), "
        "{{wp_jwplayer_thumbnail}} and {{wp_jwplayer_file}}."
    )
    provides_variables: ClassVar[list[str]] = [
        "wp_content",
        "wp_content_raw",
        "wp_excerpt",
        "wp_excerpt_raw",
        "wp_jwplayer_file",
        "wp_jwplayer_thumbnail",
    ]

    def process_entry(self, entry: Entry, _reader: Reader) -> dict[str, str]:
        """Return WordPress post data as template variables.

        Uses the shared batch cache (single API call per site, not per entry).
        Exposes the full post content and excerpt, plus any JWPlayer URLs
        found within the content.

        Args:
            entry: The feed entry to process.

        Returns:
            Dict with ``wp_content`` (formatted) / ``wp_content_raw`` (raw), ``wp_excerpt``
            (formatted) / ``wp_excerpt_raw`` (raw), ``wp_jwplayer_thumbnail``
            and ``wp_jwplayer_file`` if found, otherwise empty dict.
        """
        entry_link: str = entry.link or ""
        slug: str | None = _extract_slug(entry_link)
        if not slug:
            return {}

        try:
            parsed = urlparse(entry.feed.url)
            base_url: str = f"{parsed.scheme}://{parsed.netloc}"
        except ValueError:
            return {}

        post_data: dict[str, str] | None = _get_post_data_for_slug(slug, base_url)
        if not post_data:
            return {}

        result: dict[str, str] = {}

        # Expose full content and excerpt from the WordPress REST API.
        content_html: str = post_data.get("content", "")
        if content_html:
            result["wp_content"] = format_entry_html_for_discord(content_html)
            result["wp_content_raw"] = content_html
        excerpt_html: str = post_data.get("excerpt", "")
        if excerpt_html:
            result["wp_excerpt"] = format_entry_html_for_discord(excerpt_html)
            result["wp_excerpt_raw"] = excerpt_html

        # Extract JWPlayer URLs from the full content HTML.
        image_match = _IMAGE_PATTERN.search(content_html)
        if image_match:
            result["wp_jwplayer_thumbnail"] = quote(image_match.group(1).strip(), safe=":/")
        file_match = _FILE_PATTERN.search(content_html)
        if file_match:
            result["wp_jwplayer_file"] = quote(file_match.group(1).strip(), safe=":/")

        return result
