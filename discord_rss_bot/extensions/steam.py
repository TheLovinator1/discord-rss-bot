"""Steam feed extension: extracts app metadata and provides thumbnail URLs.

Detects feeds from ``store.steampowered.com`` and ``steamcommunity.com``,
extracts the application ID, and exposes the game's capsule image URL
as ``{{steam_thumbnail_url}}`` and the app ID as ``{{steam_app_id}}``.

Usage:
    1. Enable ``steam`` on the feed's Extensions page.
    2. In embed settings, set Thumbnail URL to ``{{steam_thumbnail_url}}``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from typing import ClassVar
from urllib.parse import parse_qs
from urllib.parse import urlparse

from reader import ReaderError

from discord_rss_bot.extensions.base import FeedExtension
from discord_rss_bot.settings import data_dir
from discord_rss_bot.webhook import DiscordWebhook
from discord_rss_bot.webhook import WebhookFile

if TYPE_CHECKING:
    from reader import Entry
    from reader import Feed
    from reader import Reader

logger: logging.Logger = logging.getLogger(__name__)

_STEAM_NETLOCS: frozenset[str] = frozenset({"store.steampowered.com", "steamcommunity.com"})


def is_steam_url(url: str) -> bool:
    """Return whether *url* belongs to Steam."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.netloc.lower().removeprefix("www.") in _STEAM_NETLOCS


def _extract_store_app_id(segments: list[str]) -> str | None:
    """Extract app ID from ``store.steampowered.com`` path segments.

    Returns:
        The numeric app ID, or ``None`` if no match.
    """
    for prefix in (
        ("feeds", "news", "app"),
        ("news", "app"),
        ("app",),
    ):
        if len(segments) > len(prefix) and tuple(segments[: len(prefix)]) == prefix:
            candidate: str = segments[len(prefix)]
            if candidate.isdigit():
                return candidate
    return None


def _extract_community_app_id(segments: list[str]) -> str | None:
    """Extract app ID from ``steamcommunity.com`` path segments.

    Returns:
        The numeric app ID, or ``None`` if no match.
    """
    if len(segments) > 1 and segments[0] in frozenset({"games", "app"}) and segments[1].isdigit():
        return segments[1]
    return None


def _extract_app_id_from_query(query: str) -> str | None:
    """Extract app ID from query parameters as a fallback.

    Args:
        query: The URL query string.

    Returns:
        The numeric app ID, or ``None`` if no match.
    """
    for key in ("appid", "app_id", "appids"):
        for value in parse_qs(query).get(key, []):
            if value.strip().isdigit():
                return value.strip()
    return None


def extract_app_id(url: str) -> str | None:
    """Extract a Steam application ID from a URL.

    Args:
        url: The URL to inspect.

    Returns:
        The numeric app ID if found, otherwise ``None``.
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    netloc: str = parsed.netloc.lower().removeprefix("www.")
    segments: list[str] = [s for s in parsed.path.split("/") if s]

    if netloc == "store.steampowered.com":
        return _extract_store_app_id(segments) or _extract_app_id_from_query(parsed.query)

    if netloc == "steamcommunity.com":
        return _extract_community_app_id(segments) or _extract_app_id_from_query(parsed.query)

    # Query parameter fallback for any other netloc
    return _extract_app_id_from_query(parsed.query)


def _try_read_icon_file(app_id: str) -> WebhookFile | None:
    """Read a Steam game icon from disk, returning a ``WebhookFile`` or ``None``.

    Does not catch exceptions — the caller handles them.

    Returns:
        A ``WebhookFile`` with the icon content, or ``None`` if no icon
        was found on disk.
    """
    # Check the old project-relative icons/ directory first,
    # then fall back to the data directory.
    old_icon: Path = Path(__file__).resolve().parent.parent.parent / "icons" / f"{app_id}.png"
    icon_path = old_icon if old_icon.is_file() else Path(data_dir) / "steam_icons" / f"{app_id}.png"
    if not icon_path.is_file():
        return None
    icon_bytes: bytes = icon_path.read_bytes()
    if not icon_bytes:
        return None
    content_hash: str = hashlib.sha256(icon_bytes).hexdigest()[:12]
    return WebhookFile(
        filename=f"steam-app-{app_id}-{content_hash}.png",
        content=icon_bytes,
    )


def get_icon_file_for_app(app_id: str) -> WebhookFile | None:
    """Return a local Steam game icon file if one exists on disk."""
    try:
        return _try_read_icon_file(app_id)
    except Exception:
        logger.exception("Failed to read local Steam icon for app %s", app_id)
        return None


def _steam_thumbnail_enabled(reader: Reader, feed: Entry | Feed) -> bool:
    """Return ``True`` if the "use Steam game icon" toggle is on for *feed*.

    Reads the embed tag directly from the reader to avoid importing
    ``custom_message`` (which would create a circular dependency).
    Defaults to ``True`` when the tag is missing or unparseable.
    """
    try:
        embed_tag_raw = reader.get_tag(feed, "embed", None)
    except ReaderError:
        return True

    raw_val = True
    if isinstance(embed_tag_raw, str) and embed_tag_raw.strip():
        try:
            embed_data = json.loads(embed_tag_raw)
        except (json.JSONDecodeError, ValueError):
            return True
        if isinstance(embed_data, dict):
            raw_val = embed_data.get("show_steam_game_icon_in_thumbnail", True)
    elif isinstance(embed_tag_raw, dict):
        raw_val = embed_tag_raw.get("show_steam_game_icon_in_thumbnail", True)

    return raw_val  # pyright: ignore[reportReturnType]


class SteamExtension(FeedExtension):
    """Provide ``{{steam_thumbnail_url}}`` and ``{{steam_app_id}}``.

    Extracts the app ID from Steam store and community feeds and makes
    the game's capsule image URL and app ID available as template variables.
    """

    name = "steam"
    description = (
        "Extracts the Steam app ID from feed URLs and exposes the game's "
        "capsule image as {{steam_thumbnail_url}}. "
        "Available as {{steam_app_id}}."
    )
    provides_variables: ClassVar[list[str]] = ["steam_thumbnail_url", "steam_app_id"]
    auto_enable_url_patterns: ClassVar[list[str]] = [
        r"store\.steampowered\.com",
        r"steamcommunity\.com",
    ]

    def process_entry(self, entry: Entry, reader: Reader) -> dict[str, str]:  # ruff:ignore[unused-method-argument]
        """Extract Steam app metadata from the entry.

        Args:
            entry: The feed entry to process.
            reader: The reader instance.

        Returns:
            Dict with ``steam_thumbnail_url`` and ``steam_app_id`` if
            this is a Steam feed, otherwise empty dict.
        """
        feed_url: str = entry.feed.url or ""
        if not is_steam_url(feed_url):
            return {}

        app_id: str | None = extract_app_id(feed_url) or extract_app_id(str(entry.link or ""))
        if not app_id:
            return {}

        return {
            "steam_app_id": app_id,
            "steam_thumbnail_url": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/capsule_sm_120.jpg",
        }

    def modify_webhook(
        self,
        webhook: DiscordWebhook,
        entry: Entry,
        reader: Reader,
    ) -> DiscordWebhook:
        """Set the embed thumbnail to the Steam game's capsule image.

        Also attaches a locally cached icon file when available.
        Only applies when ``show_steam_game_icon_in_thumbnail`` is enabled
        in the feed's embed settings.

        Args:
            webhook: The fully built webhook payload.
            entry: The feed entry being processed.
            reader: The reader instance.

        Returns:
            The (possibly modified) webhook.
        """
        feed_url: str = entry.feed.url or ""
        if not is_steam_url(feed_url):
            return webhook

        if not _steam_thumbnail_enabled(reader, entry.feed):
            return webhook

        app_id: str | None = extract_app_id(feed_url) or extract_app_id(str(entry.link or ""))
        if not app_id:
            return webhook

        # Only modify embed thumbnail when there IS an embed (not in text mode).
        embeds = webhook.json.get("embeds", [])
        if not isinstance(embeds, list) or not embeds:
            return webhook

        # Use a local icon file if available (better quality), otherwise CDN.
        icon_file: WebhookFile | None = get_icon_file_for_app(app_id)
        if icon_file:
            webhook.add_file(file=icon_file.content, filename=icon_file.filename)
            thumbnail_url: str = f"attachment://{icon_file.filename}"
        else:
            thumbnail_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/capsule_sm_120.jpg"

        embed = embeds[0]
        if isinstance(embed, dict):
            embed["thumbnail"] = {"url": thumbnail_url}

        return webhook
