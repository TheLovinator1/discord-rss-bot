"""Extension: extract JWPlayer thumbnail/video URLs from WordPress sites.

`JWPlayer <https://www.jwplayer.com/>`_ is a commercial video player
used by many sites to serve self-hosted or CDN-hosted video. The player
is embedded via a ``<script>`` block with a ``jwplayer()`` setup call
that contains ``image:`` (thumbnail) and ``file:`` (video URL) properties.

Feedparser strips ``<script>`` tags, so these URLs are invisible in the
parsed feed content. This extension recovers them by either scanning the
raw feed content directly or, for WordPress sites, fetching post HTML
from the REST API in a single batched request (cached by slug).

Created in response to `issue #432
<https://github.com/TheLovinator1/discord-rss-bot/issues/432>`_.

Currently auto-enabled for sites matching ``hentaigasm.com`` and
``hgasm[0-9]*.com``.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from typing import ClassVar
from urllib.parse import quote
from urllib.parse import urlparse

import httpx2

from discord_rss_bot.extensions.base import FeedExtension

if TYPE_CHECKING:
    from reader import Entry
    from reader import Reader

    from discord_rss_bot.feeds import JsonValue

logger: logging.Logger = logging.getLogger(__name__)

_IMAGE_PATTERN: re.Pattern[str] = re.compile(
    r'image:\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

_FILE_PATTERN: re.Pattern[str] = re.compile(
    r'file:\s*["\']([^"\']+\.\w+)["\']',
    re.IGNORECASE,
)

#: Shared HTTP client — pooled connections, no TLS handshake per call.
_HTTP_CLIENT: httpx2.Client | None = None

#: Cache of ``{slug: post_data}`` — populated by the first entry
#: that needs it, then reused for all subsequent entries from the same site.
#: Each post_data dict contains ``content``, ``excerpt``, and ``title`` keys.
_SLUG_CACHE: dict[str, dict[str, dict[str, str]]] = {}

_HTTP_OK: int = 200


def _get_http() -> httpx2.Client:
    """Return the shared ``httpx2.Client``, creating it on first call.

    Returns:
        The shared ``httpx2.Client`` instance.
    """
    global _HTTP_CLIENT  # ruff:ignore[global-statement]
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx2.Client(timeout=10)
    return _HTTP_CLIENT


def _extract_slug(url: str) -> str | None:
    """Extract the last non-numeric path segment as a potential post slug.

    Args:
        url: The URL to extract the slug from.

    Returns:
        The extracted slug, or ``None`` if no slug could be extracted.
    """
    if not url:
        return None
    try:
        path: str = urlparse(url).path.rstrip("/")
        segments: list[str] = [s for s in path.split("/") if s]
        if not segments or segments[-1].isdigit():
            return None
        return segments[-1]
    except ValueError:
        return None


def _build_slug_cache(base_url: str) -> dict[str, dict[str, str]]:
    """Fetch all recent posts from the WordPress API and build the slug cache.

    Fetches ``content``, ``excerpt``, and ``title`` for each post so that
    callers can access full post data without additional API requests.

    Args:
        base_url: The site base URL (scheme + netloc).

    Returns:
        A dict mapping slugs to ``{content: ..., excerpt: ..., title: ...}``.
    """
    client: httpx2.Client = _get_http()
    fields: str = "slug,content,excerpt,title"
    api_url: str = f"{base_url}/wp-json/wp/v2/posts?per_page=100&orderby=date&order=desc&_fields={fields}"
    resp = client.get(api_url)
    if resp.status_code != _HTTP_OK:
        logger.warning("WordPress API returned %s for batch slug lookup", resp.status_code)
        return {}

    data = resp.json()
    if not isinstance(data, list):
        return {}

    fresh: dict[str, dict[str, str]] = {}
    for post in data:
        if not isinstance(post, dict):
            continue
        ps = post.get("slug")
        if not isinstance(ps, str):
            continue
        content_rendered: str = _extract_rendered(post.get("content"))
        excerpt_rendered: str = _extract_rendered(post.get("excerpt"))
        title_rendered: str = _extract_rendered(post.get("title"))
        fresh[ps] = {
            "content": content_rendered,
            "excerpt": excerpt_rendered,
            "title": title_rendered,
        }

    logger.info("Batch-fetched %d posts from %s", len(fresh), base_url)
    return fresh


def _extract_rendered(obj: JsonValue) -> str:
    """Extract the ``rendered`` string from a WordPress API object.

    Args:
        obj: A WordPress API object (typically a dict with a ``rendered`` key).

    Returns:
        The rendered string, or ``""`` if the object is not a dict or
        has no ``rendered`` key.
    """
    if isinstance(obj, dict):
        rendered = obj.get("rendered")
        if isinstance(rendered, str):
            return rendered
    return ""


def _get_rendered_for_slug(slug: str, base_url: str) -> str | None:
    """Return the content.rendered HTML for *slug*, fetching on first miss.

    The first call for a given *base_url* triggers a **single** batch
    request (``?per_page=100``) that caches all recent posts. Every
    subsequent call for the same site is a dict lookup — zero network.

    Args:
        slug: The post slug to look up.
        base_url: The site base URL (scheme + netloc).

    Returns:
        The rendered content HTML for the post, or ``None`` if not found.
    """
    post_data: dict[str, str] | None = _get_post_data_for_slug(slug, base_url)
    if post_data is None:
        return None
    return post_data.get("content") or None


def _get_post_data_for_slug(slug: str, base_url: str) -> dict[str, str] | None:
    """Return the full post data dict for *slug*, fetching on first miss.

    The returned dict contains ``content``, ``excerpt``, and ``title`` keys.

    The first call for a given *base_url* triggers a **single** batch
    request (``?per_page=100``) that caches all recent posts. Every
    subsequent call for the same site is a dict lookup — zero network.

    Args:
        slug: The post slug to look up.
        base_url: The site base URL (scheme + netloc).

    Returns:
        A dict with ``content``, ``excerpt``, ``title`` keys, or ``None``.
    """
    site_cache: dict[str, dict[str, str]] | None = _SLUG_CACHE.get(base_url)
    if site_cache is not None:
        return site_cache.get(slug)

    try:
        fresh: dict[str, dict[str, str]] = _build_slug_cache(base_url)
    except Exception:
        logger.exception("Failed to batch-fetch WordPress posts from %s", base_url)
        fresh = {}

    _SLUG_CACHE[base_url] = fresh
    return fresh.get(slug)


class JWPlayerThumbnailExtension(FeedExtension):
    """Extract the ``image`` URL from a JWPlayer ``setup()`` call.

    Uses a single batch WordPress API request per site to fetch all
    recent post content, then looks up entries by slug — zero API
    calls per entry.
    """

    name = "jwplayer_thumbnail"
    description = (
        "Extracts JWPlayer thumbnail and video URLs from entry content "
        "or the WordPress REST API (batched). "
        "Available as {{jwplayer_thumbnail}} and {{jwplayer_file}}."
    )
    provides_variables: ClassVar[list[str]] = ["jwplayer_thumbnail", "jwplayer_file"]
    auto_enable_url_patterns: ClassVar[list[str]] = [
        r"hentaigasm\.com",
        r"hgasm[0-9]*\.com",
    ]

    def process_entry(self, entry: Entry, _reader: Reader) -> dict[str, str]:
        """Extract JWPlayer URLs from feed content or WordPress API.

        Args:
            entry: The feed entry to process.

        Returns:
            Dict with ``jwplayer_thumbnail`` and ``jwplayer_file``
            if found, otherwise empty dict.
        """
        result: dict[str, str] = {}

        # Phase 1: search feed content (fast).
        sources: list[str] = []
        if entry.content:
            sources.extend(item.value for item in entry.content if hasattr(item, "value") and item.value)
        entry_summary: str | None = getattr(entry, "summary", None)
        if entry_summary:
            sources.append(entry_summary)

        for source in sources:
            self._search(source, result)
            if "jwplayer_thumbnail" in result and "jwplayer_file" in result:
                return result

        # Phase 2: batch WordPress API lookup (one request per site).
        if not result:
            entry_link: str | None = getattr(entry, "link", None)
            if entry_link:
                slug: str | None = _extract_slug(entry_link)
                if slug:
                    base_url: str | None = None
                    try:
                        parsed = urlparse(entry.feed.url)
                        base_url = f"{parsed.scheme}://{parsed.netloc}"
                    except ValueError:
                        return result

                    html: str | None = _get_rendered_for_slug(slug, base_url)
                    if html:
                        self._search(html, result)

        return result

    @staticmethod
    def _search(html: str, result: dict[str, str]) -> None:
        """Search a single HTML source for JWPlayer patterns.

        Args:
            html: The HTML content to search.
            result: The result dict to populate.
        """
        if "jwplayer_thumbnail" not in result:
            match = _IMAGE_PATTERN.search(html)
            if match:
                result["jwplayer_thumbnail"] = quote(match.group(1).strip(), safe=":/")
        if "jwplayer_file" not in result:
            match = _FILE_PATTERN.search(html)
            if match:
                result["jwplayer_file"] = quote(match.group(1).strip(), safe=":/")
