"""Hoyolab feed extension: fetches full post data from the Hoyolab API.

Detects feeds from ``feeds.c3kay.de`` and replaces the Discord embed
with richer content fetched directly from Hoyolab (Genshin Impact,
Honkai Starrail, Honkai Impact 3rd, Zenless Zone Zero).

Usage:
    1. Enable ``hoyolab`` on the feed's Extensions page.
    2. The extension automatically decorates the embed with the post
       title, author avatar, game color, images, and more.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from typing import TYPE_CHECKING
from typing import ClassVar
from typing import cast

import requests

from discord_rss_bot.extensions.base import FeedExtension
from discord_rss_bot.webhook import DiscordEmbed
from discord_rss_bot.webhook import DiscordWebhook

if TYPE_CHECKING:
    from reader import Entry
    from reader import Reader

logger: logging.Logger = logging.getLogger(__name__)

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]


def is_c3kay_feed_url(feed_url: str) -> bool:
    """Return whether a feed URL is from feeds.c3kay.de."""
    return "feeds.c3kay.de" in (feed_url or "")


def extract_post_id(url: str) -> str | None:
    """Extract the Hoyolab post ID from a URL.

    Args:
        url: The URL to inspect (e.g. ``https://www.hoyolab.com/article/38588239``).

    Returns:
        The numeric post ID if found, otherwise ``None``.
    """
    if not url:
        return None
    try:
        match = re.search(r"/article/(\d+)", url)
        if match:
            return match.group(1)
    except (ValueError, AttributeError, TypeError) as exc:
        logger.warning("Error extracting post ID from URL %s: %s", url, exc)
    return None


def _try_fetch_post(post_id: str) -> JsonObject | None:
    """Attempt to fetch a Hoyolab post, returning the payload or ``None``.

    Does not catch exceptions — the caller handles them.

    Returns:
        The post payload dict, or ``None`` on failure.
    """
    url: str = f"https://bbs-api-os.hoyolab.com/community/post/wapi/getPostFull?post_id={post_id}"
    response: requests.Response = requests.get(url, timeout=10)
    if response.status_code == http_ok:
        data = cast("JsonObject", response.json())
        data_payload: JsonObject = cast("JsonObject", data.get("data", {}))
        post_payload: JsonObject = cast("JsonObject", data_payload.get("post", {}))
        if data.get("retcode") == 0 and post_payload:
            return post_payload
    logger.warning("Failed to fetch Hoyolab post %s: %s", post_id, response.text)
    return None


def fetch_post(post_id: str) -> JsonObject | None:
    """Fetch post data from the Hoyolab API.

    Args:
        post_id: The numeric post ID.

    Returns:
        The post payload dict, or ``None`` on failure.
    """
    if not post_id:
        return None
    try:
        return _try_fetch_post(post_id)
    except (requests.RequestException, ValueError):
        logger.exception("Error fetching Hoyolab post %s", post_id)
    return None


http_ok: int = 200


def _as_json_object(value: JsonValue) -> JsonObject:
    return cast("JsonObject", value) if isinstance(value, dict) else {}


class HoyolabExtension(FeedExtension):
    """Fetches full post data from the Hoyolab API for c3kay.de feeds.

    Replaces the Discord embed with richer content (title, author avatar,
    game color, images, video, and more).
    """

    name = "hoyolab"
    description = (
        "Detects c3kay.de / Hoyolab feeds and replaces the Discord embed "
        "with full post data from the Hoyolab API "
        "(Genshin Impact, Honkai Starrail, Honkai Impact 3rd, ZZZ)."
    )
    provides_variables: ClassVar[list[str]] = [
        "hoyolab_subject",
        "hoyolab_description",
        "hoyolab_image",
        "hoyolab_author",
    ]
    auto_enable_url_patterns: ClassVar[list[str]] = [
        r"feeds\.c3kay\.de",
    ]

    def process_entry(self, entry: Entry, reader: Reader) -> dict[str, str]:  # ruff:ignore[unused-method-argument]
        """Provide Hoyolab post data as template variables.

        Args:
            entry: The feed entry to process.
            reader: The reader instance.

        Returns:
            Dict with ``hoyolab_subject``, ``hoyolab_description``,
            ``hoyolab_image`` and ``hoyolab_author`` if the data was
            fetched successfully, otherwise empty dict.
        """
        if not is_c3kay_feed_url(entry.feed.url):
            return {}

        post_id: str | None = extract_post_id(str(entry.link or ""))
        if not post_id:
            return {}

        post_data: JsonObject | None = fetch_post(post_id)
        if not post_data:
            return {}

        post: JsonObject = _as_json_object(post_data.get("post"))
        subject: str = str(post.get("subject", ""))
        description: str = str(post.get("desc", ""))

        image_url: str = ""
        image_list = post_data.get("image_list", [])
        if isinstance(image_list, list) and image_list:
            first_image = image_list[0]
            if isinstance(first_image, dict):
                image_url = str(first_image.get("url", ""))

        author: str = ""
        user: JsonObject = _as_json_object(post_data.get("user"))
        if user:
            author = str(user.get("nickname", ""))

        return {
            "hoyolab_subject": subject,
            "hoyolab_description": description,
            "hoyolab_image": image_url,
            "hoyolab_author": author,
        }

    def modify_webhook(
        self,
        webhook: DiscordWebhook,
        entry: Entry,
        reader: Reader,  # ruff:ignore[unused-method-argument]
    ) -> DiscordWebhook:
        """Replace the embed with richer Hoyolab content when applicable.

        Args:
            webhook: The fully built webhook payload.
            entry: The feed entry being processed.
            reader: The reader instance.

        Returns:
            The modified webhook with Hoyolab data.
        """
        if not is_c3kay_feed_url(entry.feed.url):
            return webhook

        # Don't interfere with non-embed delivery modes.
        if not webhook.json.get("embeds"):
            return webhook

        post_id: str | None = extract_post_id(str(entry.link or ""))
        if not post_id:
            return webhook

        post_data: JsonObject | None = fetch_post(post_id)
        if not post_data:
            return webhook

        discord_embed = self._build_embed_from_post(post_data, entry.link or entry.feed.url)

        self._attach_video_if_present(webhook, entry, post_data)
        self._apply_author_from_post(webhook, post_data)
        self._apply_structured_content(webhook, post_data)

        webhook.remove_embeds()
        webhook.add_embed(discord_embed)
        return webhook

    def _build_embed_from_post(self, post_data: JsonObject, entry_link: str) -> DiscordEmbed:
        """Build a ``DiscordEmbed`` populated with post data.

        Args:
            post_data: Raw Hoyolab post payload.
            entry_link: Fallback link URL.

        Returns:
            A populated embed.
        """
        post: JsonObject = _as_json_object(post_data.get("post"))
        subject: str = str(post.get("subject", ""))
        content_raw: str = str(post.get("content", "{}"))

        content_data: JsonObject = {}
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            loaded = cast("JsonValue", json.loads(content_raw))
            content_data = _as_json_object(loaded)

        description: str = str(content_data.get("describe", ""))
        if not description:
            description = str(post.get("desc", ""))

        discord_embed = DiscordEmbed()
        discord_embed.set_title(subject)
        discord_embed.set_url(entry_link)

        # Image list
        image_list_value: JsonValue = post_data.get("image_list", [])
        image_list: list[JsonObject] = (
            [cast("JsonObject", item) for item in image_list_value if isinstance(item, dict)]
            if isinstance(image_list_value, list)
            else []
        )
        if image_list:
            discord_embed.set_image(url=str(image_list[0].get("url", "")))

        # Game colour
        game: JsonObject = _as_json_object(post_data.get("game"))
        if game and game.get("color"):
            discord_embed.set_color(str(game.get("color", "")).removeprefix("#"))

        # Footer
        classification: JsonObject = _as_json_object(post_data.get("classification"))
        if classification and classification.get("name"):
            discord_embed.set_footer(text=str(classification.get("name", "")))

        # Event dates
        event_start: str = str(post.get("event_start_date", ""))
        if event_start and event_start != "0":
            discord_embed.add_embed_field(name="Start", value=f"<t:{event_start}:R>")
        event_end: str = str(post.get("event_end_date", ""))
        if event_end and event_end != "0":
            discord_embed.add_embed_field(name="End", value=f"<t:{event_end}:R>")

        created_at: str = str(post.get("created_at", ""))
        if created_at and created_at != "0":
            discord_embed.set_timestamp(timestamp=created_at)

        if description:
            discord_embed.set_description(description)

        return discord_embed

    def _attach_video_if_present(self, webhook: DiscordWebhook, entry: Entry, post_data: JsonObject) -> None:
        """Download and attach a Hoyolab video to the webhook if present."""
        video: JsonObject = _as_json_object(post_data.get("video"))
        if not video or not video.get("url"):
            return
        video_url: str = str(video.get("url", ""))
        with contextlib.suppress(requests.RequestException):
            video_response: requests.Response = requests.get(video_url, stream=True, timeout=10)
            if video_response.ok:
                webhook.add_file(file=video_response.content, filename=f"{entry.id}.mp4")

    def _apply_author_from_post(self, webhook: DiscordWebhook, post_data: JsonObject) -> None:
        """Set webhook author (username and avatar) from post user data."""
        user: JsonObject = _as_json_object(post_data.get("user"))
        author_name: str = str(user.get("nickname", ""))
        avatar_url: str = str(user.get("avatar_url", ""))
        if author_name:
            webhook.avatar_url = avatar_url
            webhook.username = author_name

    def _apply_structured_content(self, webhook: DiscordWebhook, post_data: JsonObject) -> None:
        """Parse structured content for YouTube embeds and add them to the webhook."""
        post: JsonObject = _as_json_object(post_data.get("post"))
        structured_content: str = str(post.get("structured_content", ""))
        if not structured_content:
            return
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            loaded_structured = cast("JsonValue", json.loads(structured_content))
            structured_items: list[JsonObject] = (
                [cast("JsonObject", item) for item in loaded_structured if isinstance(item, dict)]
                if isinstance(loaded_structured, list)
                else []
            )
            for item in structured_items:
                self._apply_structured_item(webhook, item)

    def _apply_structured_item(self, webhook: DiscordWebhook, item: JsonObject) -> None:
        """Apply a single structured content item (e.g. YouTube embed)."""
        insert: JsonObject = _as_json_object(item.get("insert"))
        if not insert:
            return
        video_url_str: str = str(insert.get("video", ""))
        if not video_url_str:
            return
        video_id_match = re.search(r"embed/([a-zA-Z0-9_-]+)", video_url_str)
        if not video_id_match:
            return
        webhook.content = f"https://www.youtube.com/watch?v={video_id_match.group(1)}"
        webhook.remove_embeds()
