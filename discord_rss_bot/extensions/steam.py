"""Steam feed extension: extracts app metadata and provides thumbnail URLs.

Detects feeds from ``store.steampowered.com`` and ``steamcommunity.com``,
extracts the application ID, and exposes the game's capsule image URL
as ``{{steam_thumbnail_url}}`` and the app ID as ``{{steam_app_id}}``.

It also rewrites broken Steam CDN image URLs: some news feeds reference
localized image names such as ``.../english.png`` that return a 404, and
the working URL omits the language segment (``.../<hash>.png``).

Steam feeds' ``{{feed_title}}`` (and web UI display names) use the game
name (e.g. "Dota") instead of the raw feed title (e.g. "570 RSS Feed").
The name is fetched once from the Steam Store API and cached in the reader
DB per feed, so no repeated network requests are needed.

Usage:
    1. Enable ``steam`` on the feed's Extensions page.
    2. In embed settings, set Thumbnail URL to ``{{steam_thumbnail_url}}``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING
from typing import ClassVar
from typing import cast
from urllib.parse import ParseResult
from urllib.parse import parse_qs
from urllib.parse import urlparse
from urllib.parse import urlunsplit

import httpx2
from httpx2 import HTTPError
from httpx2 import Response
from reader import ReaderError

from discord_rss_bot.extensions.base import FeedExtension
from discord_rss_bot.settings import data_dir
from discord_rss_bot.webhook import DiscordWebhook
from discord_rss_bot.webhook import JsonValue
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


#: Steam language codes that appear as image filename suffixes
#: (e.g. ``.../aa83bcaaafe7cd4d11a841ec381ec28ccb039d41/english.png``).
#: These localized URLs 404; the working URL omits the language segment.
_STEAM_IMAGE_LOCALES: tuple[str, ...] = (
    "arabic",
    "brazilian",
    "bulgarian",
    "czech",
    "danish",
    "dutch",
    "english",
    "finnish",
    "french",
    "german",
    "greek",
    "hungarian",
    "indonesian",
    "italian",
    "japanese",
    "koreana",
    "latam",
    "norwegian",
    "polish",
    "portuguese",
    "romanian",
    "russian",
    "schinese",
    "spanish",
    "swedish",
    "tchinese",
    "thai",
    "turkish",
    "ukrainian",
    "vietnamese",
)

#: Image file extensions that may carry a Steam locale suffix.
_STEAM_IMAGE_EXTENSIONS: tuple[str, ...] = ("png", "jpg", "jpeg", "gif", "webp")

_STEAM_IMAGE_PATH_RE: re.Pattern[str] = re.compile(
    rf"^(.+)/({'|'.join(_STEAM_IMAGE_LOCALES)})\.({'|'.join(_STEAM_IMAGE_EXTENSIONS)})$",
    re.IGNORECASE,
)


def fix_steam_image_url(url: str) -> str:
    """Return *url* with Steam's broken localized image suffix removed.

    Some Steam news feeds reference localized images such as
    ``.../<hash>/english.png``, which return a 404.  The working URL omits
    the language segment: ``.../<hash>.png``.

    Args:
        url: The image URL to inspect.

    Returns:
        The fixed URL, or *url* unchanged when no fix applies.
    """
    if not url:
        return url
    stripped_url: str = url.strip()
    parsed: ParseResult = urlparse(stripped_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc.lower().endswith(".steamstatic.com"):
        return url
    match: re.Match[str] | None = _STEAM_IMAGE_PATH_RE.match(parsed.path)
    if not match:
        return url
    fixed_path: str = f"{match.group(1)}.{match.group(3)}"
    return urlunsplit((parsed.scheme, parsed.netloc, fixed_path, parsed.query, parsed.fragment))


#: Matches http(s) URLs within larger text so they can be rewritten in place.
_STEAM_URL_IN_TEXT_RE: re.Pattern[str] = re.compile(r"""https?://[^\s<>"']+""", re.IGNORECASE)

#: Punctuation that may trail a URL inside prose or a markdown link.
_STEAM_URL_TRAILING_CHARS: frozenset[str] = frozenset(")]},.;!?")


def _fix_steam_image_urls_in_text(text: str) -> str:
    """Rewrite broken Steam image URLs that appear inside *text*.

    Handles both standalone URLs and URLs embedded in markdown or prose
    (e.g. ``[image](https://.../english.png)``).

    Args:
        text: The text to rewrite.

    Returns:
        The text with matching Steam image URLs fixed.
    """

    def _replace(match: re.Match[str]) -> str:
        raw_url: str = match.group(0)
        trimmed_url: str = raw_url
        while trimmed_url and trimmed_url[-1] in _STEAM_URL_TRAILING_CHARS:
            trimmed_url = trimmed_url[:-1]
        trailing: str = raw_url[len(trimmed_url) :]
        fixed_url: str = fix_steam_image_url(trimmed_url)
        if fixed_url == trimmed_url:
            return raw_url
        return f"{fixed_url}{trailing}"

    return _STEAM_URL_IN_TEXT_RE.sub(_replace, text)


def fix_steam_image_urls_in_payload(value: JsonValue) -> JsonValue:
    """Recursively rewrite Steam image URLs throughout a webhook payload.

    Walks every string in a JSON-compatible payload (embeds, media gallery
    components, description text, avatar URL, etc.) and applies
    :func:`fix_steam_image_url` to each.

    Args:
        value: A JSON-compatible webhook payload value.

    Returns:
        A new payload with all matching Steam image URLs fixed.
    """
    if isinstance(value, str):
        return _fix_steam_image_urls_in_text(value)
    if isinstance(value, list):
        return [fix_steam_image_urls_in_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: fix_steam_image_urls_in_payload(item) for key, item in value.items()}
    return value


#: Reader tag under which the Steam game name is cached per feed.  Populated
#: once per feed so title rendering never needs a second network request.
STEAM_GAME_NAME_TAG: str = "steam_game_name"

#: Steam Store API endpoint used to resolve app IDs to game names.
_STEAM_APPDETAILS_URL: str = "https://store.steampowered.com/api/appdetails"

#: How long to wait before retrying a failed game-name lookup for the same app.
_STEAM_GAME_NAME_RETRY_COOLDOWN: float = 60.0 * 60.0

#: Last lookup attempt time per app ID.  Used so a repeatedly failing feed
#: does not trigger a network request on every single message.
_steam_game_name_attempts: dict[str, float] = {}


def get_steam_game_name(app_id: str) -> str | None:  # ruff:ignore[too-many-return-statements]
    """Fetch the game name for *app_id* from the Steam Store API.

    Args:
        app_id: The Steam application ID.

    Returns:
        The game name, or ``None`` if it could not be determined.
    """
    try:
        response: Response = httpx2.get(
            _STEAM_APPDETAILS_URL,
            params={"appids": app_id, "l": "english"},
            timeout=10.0,
        )
        response.raise_for_status()
    except (HTTPError, OSError) as exc:
        logger.warning("Failed to fetch Steam game name for app %s: %s", app_id, exc)
        return None

    try:
        data: object = response.json()
    except ValueError as exc:
        logger.warning("Invalid JSON from Steam Store API for app %s: %s", app_id, exc)
        return None

    if not isinstance(data, dict):
        return None
    details: object = data.get(app_id)
    if not isinstance(details, dict) or not details.get("success"):
        logger.warning("Steam Store API returned no details for app %s", app_id)
        return None
    app_data: object = details.get("data")
    if not isinstance(app_data, dict):
        return None
    name: object = app_data.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def get_cached_steam_game_name(reader: Reader, feed: Feed | str) -> str | None:
    """Return the Steam game name cached in the reader DB for *feed*, if any.

    Args:
        reader: The reader instance.
        feed: The feed (or feed URL) to look up.

    Returns:
        The cached game name, or ``None`` when nothing is cached.
    """
    try:
        cached = reader.get_tag(feed, STEAM_GAME_NAME_TAG, None)
    except ReaderError:
        logger.exception("Failed to read Steam game name tag for %s", feed)
        return None
    if isinstance(cached, str) and cached.strip():
        return cached.strip()
    return None


def set_steam_game_name(reader: Reader, feed: Feed | str, game_name: str) -> None:
    """Cache *game_name* for *feed* in the reader DB.

    Args:
        reader: The reader instance.
        feed: The feed (or feed URL) to store the name for.
        game_name: The game name to cache.
    """
    try:
        reader.set_tag(feed, STEAM_GAME_NAME_TAG, game_name)  # pyright: ignore[reportArgumentType]
    except ReaderError:
        logger.exception("Failed to cache Steam game name for %s", feed)


def get_feed_display_title(feed: Feed, reader: Reader) -> str:
    """Return the display title for a feed.

    For Steam feeds, uses the game name (e.g. "Dota") instead of the raw feed
    title (e.g. "570 RSS Feed").  The name is read from the reader DB cache;
    when the cache is empty it is fetched from the Steam Store API once and
    then cached, so title rendering never makes "unnecessary network requests"
    for feeds that have already been resolved.  Falls back to the feed's own
    title when the game name cannot be determined.  Non-Steam feeds are
    returned with their title unchanged.

    Args:
        feed: The feed to render a title for.
        reader: The reader instance.

    Returns:
        The display title for *feed*.
    """
    feed_url: str = getattr(feed, "url", "") or ""
    fallback_title: str = getattr(feed, "title", "") or ""
    if not is_steam_url(feed_url):
        return fallback_title

    app_id: str | None = extract_app_id(feed_url)
    if not app_id:
        return fallback_title

    cached: str | None = get_cached_steam_game_name(reader, feed)
    if cached:
        return cached

    # Don't hammer the API for app IDs whose lookup recently failed.
    now: float = time.monotonic()
    last_attempt: float = _steam_game_name_attempts.get(app_id, 0.0)
    if now - last_attempt < _STEAM_GAME_NAME_RETRY_COOLDOWN:
        return fallback_title

    _steam_game_name_attempts[app_id] = now
    game_name: str | None = get_steam_game_name(app_id)
    if game_name:
        set_steam_game_name(reader, feed, game_name)
        return game_name
    return fallback_title


def get_cached_feed_display_title(feed: Feed, reader: Reader) -> str:
    """Return the display title for a feed using only cached data.

    For Steam feeds, uses the cached game name when available, otherwise the
    feed's own title.  Unlike :func:`get_feed_display_title`, this never
    performs network requests or writes to the reader — it only reads the
    cache.  Meant for read-only render paths (e.g. web UI pages) that must not
    block on the Steam Store API.

    Args:
        feed: The feed to render a title for.
        reader: The reader instance.

    Returns:
        The display title for *feed* using only cached data.
    """
    feed_url: str = getattr(feed, "url", "") or ""
    fallback_title: str = getattr(feed, "title", "") or ""
    if not is_steam_url(feed_url):
        return fallback_title

    app_id: str | None = extract_app_id(feed_url)
    if not app_id:
        return fallback_title

    cached: str | None = get_cached_steam_game_name(reader, feed)
    if cached:
        return cached
    return fallback_title


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

        Also rewrites broken Steam CDN image URLs (localized image names
        like ``.../english.png``) anywhere in the payload, and attaches a
        locally cached icon file when available.
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

        # Steam news feeds occasionally emit localized image names
        # (e.g. ".../english.png") that 404.  Rewrite them throughout the
        # payload so embeds, media galleries, and text links resolve.
        fixed_payload = cast("dict[str, JsonValue]", fix_steam_image_urls_in_payload(webhook.json))
        webhook.json.clear()
        webhook.json.update(fixed_payload)

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
