from __future__ import annotations

import contextlib
import json
import logging
import re
from typing import TYPE_CHECKING, Any

import requests
from discord_webhook import DiscordEmbed, DiscordWebhook

if TYPE_CHECKING:
    from reader import Entry


logger: logging.Logger = logging.getLogger(__name__)


def is_c3kay_feed(feed_url: str) -> bool:
    """Check if the feed is from c3kay.de.

    Args:
        feed_url: The feed URL to check.

    Returns:
        bool: True if the feed is from c3kay.de, False otherwise.
    """
    return "feeds.c3kay.de" in feed_url


def extract_post_id_from_hoyolab_url(url: str) -> str | None:
    """Extract the post ID from a Hoyolab URL.

    Args:
        url: The Hoyolab URL to extract the post ID from.
            For example: https://www.hoyolab.com/article/38588239

    Returns:
        str | None: The post ID if found, None otherwise.
    """
    try:
        match: re.Match[str] | None = re.search(r"/article/(\d+)", url)
        if match:
            return match.group(1)
    except (ValueError, AttributeError, TypeError) as e:
        logger.warning("Error extracting post ID from Hoyolab URL %s: %s", url, e)

    return None


def fetch_hoyolab_post(post_id: str) -> dict[str, Any] | None:
    """Fetch post data from the Hoyolab API.

    Args:
        post_id: The post ID to fetch.

    Returns:
        dict[str, Any] | None: The post data if successful, None otherwise.
    """
    if not post_id:
        return None

    http_ok = 200
    try:
        url: str = f"https://bbs-api-os.hoyolab.com/community/post/wapi/getPostFull?post_id={post_id}"
        response: requests.Response = requests.get(url, timeout=10)

        if response.status_code == http_ok:
            data: dict[str, Any] = response.json()
            if data.get("retcode") == 0 and "data" in data and "post" in data["data"]:
                return data["data"]["post"]

        logger.warning("Failed to fetch Hoyolab post %s: %s", post_id, response.text)
    except (requests.RequestException, ValueError):
        logger.exception("Error fetching Hoyolab post %s", post_id)

    return None


def create_hoyolab_webhook(webhook_url: str, entry: Entry, post_data: dict[str, Any]) -> DiscordWebhook:  # noqa: C901, PLR0912, PLR0914, PLR0915
    """Create a webhook with data from the Hoyolab API.

    Args:
        webhook_url: The webhook URL.
        entry: The entry to send to Discord.
        post_data: The post data from the Hoyolab API.

    Returns:
        DiscordWebhook: The webhook with the embed.
    """
    entry_link: str = entry.link or entry.feed.url
    webhook = DiscordWebhook(url=webhook_url, rate_limit_retry=True)

    # Extract relevant data from the post
    post: dict[str, Any] = post_data.get("post", {})
    subject: str = post.get("subject", "")
    content: str = post.get("content", "{}")

    logger.debug("Post subject: %s", subject)
    logger.debug("Post content: %s", content)

    content_data: dict[str, str] = {}
    with contextlib.suppress(json.JSONDecodeError, ValueError):
        content_data = json.loads(content)

    logger.debug("Content data: %s", content_data)

    description: str = content_data.get("describe", "")
    if not description:
        description = post.get("desc", "")

    # Create the embed
    discord_embed = DiscordEmbed()

    # Set title and description
    discord_embed.set_title(subject)
    discord_embed.set_url(entry_link)

    # Set description if available and short enough
    if description:
        # Use the same length limit as other parts of the codebase
        max_description_length: int = 2000
        if len(description) > max_description_length:
            description = f"{description[:max_description_length]}..."
        discord_embed.set_description(description)

    # Get post.image_list
    image_list: list[dict[str, Any]] = post_data.get("image_list", [])
    if image_list:
        image_url: str = str(image_list[0].get("url", ""))
        image_height: int = int(image_list[0].get("height", 1080))
        image_width: int = int(image_list[0].get("width", 1920))

        logger.debug("Image URL: %s, Height: %s, Width: %s", image_url, image_height, image_width)
        discord_embed.set_image(url=image_url, height=image_height, width=image_width)

    video: dict[str, str | int | bool] = post_data.get("video", {})
    if video and video.get("url"):
        video_url: str = str(video.get("url", ""))
        logger.debug("Video URL: %s", video_url)
        with contextlib.suppress(requests.RequestException):
            video_response: requests.Response = requests.get(video_url, stream=True, timeout=10)
            if video_response.ok:
                webhook.add_file(
                    file=video_response.content,
                    filename=f"{entry.id}.mp4",
                )

    game = post_data.get("game", {})

    if game and game.get("color"):
        game_color = str(game.get("color", ""))
        discord_embed.set_color(game_color.removeprefix("#"))

    user: dict[str, str | int | bool] = post_data.get("user", {})
    author_name: str = str(user.get("nickname", ""))
    avatar_url: str = str(user.get("avatar_url", ""))
    if author_name:
        webhook.avatar_url = avatar_url
        webhook.username = author_name

    classification = post_data.get("classification", {})

    if classification and classification.get("name"):
        footer = str(classification.get("name", ""))
        discord_embed.set_footer(text=footer)

    webhook.add_embed(discord_embed)

    # Only show Youtube URL if available
    structured_content: str = post.get("structured_content", "")
    if structured_content:  # noqa: PLR1702
        try:
            structured_content_data: list[dict[str, Any]] = json.loads(structured_content)
            for item in structured_content_data:
                if item.get("insert") and isinstance(item["insert"], dict):
                    video_url: str = str(item["insert"].get("video", ""))
                    if video_url:
                        video_id_match: re.Match[str] | None = re.search(r"embed/([a-zA-Z0-9_-]+)", video_url)
                        if video_id_match:
                            video_id: str = video_id_match.group(1)
                            logger.debug("Video ID: %s", video_id)
                            webhook.content = f"https://www.youtube.com/watch?v={video_id}"
                            webhook.remove_embeds()

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Error parsing structured content: %s", e)

    event_start_date: str = post.get("event_start_date", "")
    if event_start_date and event_start_date != "0":
        discord_embed.add_embed_field(name="Start", value=f"<t:{event_start_date}:R>")

    event_end_date: str = post.get("event_end_date", "")
    if event_end_date and event_end_date != "0":
        discord_embed.add_embed_field(name="End", value=f"<t:{event_end_date}:R>")

    created_at: str = post.get("created_at", "")
    if created_at and created_at != "0":
        discord_embed.set_timestamp(timestamp=created_at)

    return webhook
