from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
from bs4 import Tag

from discord_rss_bot.extensions import run_extensions
from discord_rss_bot.html_format import format_entry_html_for_discord
from discord_rss_bot.is_url_valid import is_url_valid

if TYPE_CHECKING:
    from collections.abc import Sequence

    from reader import Content
    from reader import Entry
    from reader import Feed
    from reader import Reader

logger: logging.Logger = logging.getLogger(__name__)

# Discord webhook username: nickname rules, max 80 chars; no "clyde"/"discord" substrings.
DISCORD_WEBHOOK_USERNAME_MAX_LENGTH: int = 80
DISCORD_WEBHOOK_USERNAME_FORBIDDEN_CHARS: frozenset[str] = frozenset("@#:`")
DISCORD_WEBHOOK_USERNAME_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = ("clyde", "discord")


@dataclass(slots=True)
class CustomEmbed:
    title: str = ""
    description: str = ""
    color: str = ""
    author_name: str = ""
    author_url: str = ""
    author_icon_url: str = ""
    image_url: str = ""
    thumbnail_url: str = ""
    footer_text: str = ""
    footer_icon_url: str = ""
    show_steam_game_icon_in_thumbnail: bool = True
    avatar_url: str = ""
    username: str = ""


def try_to_replace(custom_message: str, template: str, replace_with: str) -> str:
    """Try to replace a tag in custom_message.

    Args:
        custom_message: The custom_message to replace tags in.
        template: The tag to replace.
        replace_with: What to replace the tag with.

    Returns:
        Returns the custom_message with the tag replaced.
    """
    try:
        return custom_message.replace(template, replace_with)
    except (TypeError, AttributeError, ValueError):
        logger.exception("Failed to replace %s with %s in %s", template, replace_with, custom_message)
        return custom_message


def replace_tags_in_text_message(entry: Entry, reader: Reader) -> str:
    """Replace tags in custom_message.

    Args:
        entry: The entry to get the tags from.
        reader: Custom Reader instance.

    Returns:
        Returns the custom_message with the tags replaced.
    """
    feed: Feed = entry.feed
    custom_message: str = get_custom_message(feed=feed, reader=reader)

    content = ""
    if entry.content:
        for content_item in entry.content:
            content: str = content_item.value

    summary: str = entry.summary or ""

    first_image: str = get_first_image(summary, content)

    summary = format_entry_html_for_discord(summary)
    content = format_entry_html_for_discord(content)

    feed_added: str = feed.added.strftime("%Y-%m-%d %H:%M:%S") if feed.added else "Never"
    feed_last_exception: str = feed.last_exception.value_str if feed.last_exception else ""
    feed_last_updated: str = feed.last_updated.strftime("%Y-%m-%d %H:%M:%S") if feed.last_updated else "Never"
    feed_updated: str = feed.updated.strftime("%Y-%m-%d %H:%M:%S") if feed.updated else "Never"
    entry_added: str = entry.added.strftime("%Y-%m-%d %H:%M:%S") if entry.added else "Never"
    entry_published: str = entry.published.strftime("%Y-%m-%d %H:%M:%S") if entry.published else "Never"
    entry_read_modified: str = entry.read_modified.strftime("%Y-%m-%d %H:%M:%S") if entry.read_modified else "Never"
    entry_updated: str = entry.updated.strftime("%Y-%m-%d %H:%M:%S") if entry.updated else "Never"

    list_of_replacements: list[dict[str, str]] = [
        {"{{feed_author}}": feed.authors_str or ""},
        {"{{feed_added}}": feed_added},
        {"{{feed_last_exception}}": feed_last_exception},
        {"{{feed_last_updated}}": feed_last_updated},
        {"{{feed_link}}": feed.link or ""},
        {"{{feed_subtitle}}": feed.subtitle or ""},
        {"{{feed_title}}": feed.title or ""},
        {"{{feed_updated}}": feed_updated},
        {"{{feed_updates_enabled}}": str(feed.updates_enabled) or ""},
        {"{{feed_url}}": feed.url or ""},
        {"{{feed_user_title}}": feed.user_title or ""},
        {"{{feed_version}}": feed.version or ""},
        {"{{entry_added}}": entry_added},
        {"{{entry_author}}": entry.authors_str or ""},
        {"{{entry_content}}": content},
        {"{{entry_content_raw}}": entry.content[0].value if entry.content else ""},
        {"{{entry_id}}": entry.id or ""},
        {"{{entry_important}}": str(entry.important) or ""},
        {"{{entry_link}}": entry.link or ""},
        {"{{entry_published}}": entry_published},
        {"{{entry_read}}": str(entry.read) or ""},
        {"{{entry_read_modified}}": entry_read_modified},
        {"{{entry_summary}}": summary},
        {"{{entry_summary_raw}}": entry.summary or ""},
        {"{{entry_text}}": summary or content},
        {"{{entry_title}}": entry.title or ""},
        {"{{entry_updated}}": entry_updated},
        {"{{image_1}}": first_image},
    ]

    # Compute extension variables (handled separately so they can use
    # the already-computed values above without ordering issues).
    extension_vars: dict[str, str] = run_extensions(entry, reader)
    for var_name, var_value in extension_vars.items():
        list_of_replacements.append({f"{{{{{var_name}}}}}": var_value})

    for replacement in list_of_replacements:
        for template, replace_with in replacement.items():
            if not isinstance(replace_with, str):
                logger.error("replace_with is not a string: %s, it is a %s", replace_with, type(replace_with))
                continue

            custom_message = try_to_replace(custom_message, template, replace_with)

    return custom_message.replace("\\n", "\n")


def _extract_entry_text(data: str | list | tuple | Sequence[Content] | None) -> str | None:
    """Extract text from a reader summary/content value.

    Returns:
        Extracted text, or None when the input is empty.
    """
    if not data:
        return None
    if isinstance(data, str):
        return data
    if isinstance(data, (list, tuple)):
        extracted: list[str] = []
        for item in data:
            if hasattr(item, "value"):
                extracted.append(item.value)
            elif isinstance(item, dict) and "value" in item:
                extracted.append(item.get("value", ""))
            else:
                extracted.append(str(item))
        return "".join(extracted)
    return str(data)


def get_image_urls(
    summary: str | None,
    content: str | Sequence[Content] | None,
    *,
    limit: int | None = None,
) -> list[str]:
    """Get valid image URLs from content, then summary.

    Args:
        summary: The summary from the entry (string, or tuple/list of objects)
        content: The content from the entry (string, or tuple/list of objects)
        limit: Optional maximum number of URLs to return.

    Returns:
        Valid, de-duplicated image URLs.
    """
    image_urls: list[str] = []
    seen_urls: set[str] = set()

    def add_images_from_text(text: str | None) -> None:
        if not text:
            return
        images = BeautifulSoup(text, features="lxml").find_all("img")
        for image in images:
            if not isinstance(image, Tag) or "src" not in image.attrs:
                logger.error("Image is not a Tag or does not have a src attribute.")
                continue

            src = str(image.attrs["src"])
            if not is_url_valid(src):
                logger.warning("Invalid URL: %s", src)
                continue

            if src in seen_urls:
                continue

            image_urls.append(src)
            seen_urls.add(src)
            if limit is not None and len(image_urls) >= limit:
                return

    add_images_from_text(_extract_entry_text(content))
    if limit is None or len(image_urls) < limit:
        add_images_from_text(_extract_entry_text(summary))

    return image_urls


def get_first_image(summary: str | None, content: str | Sequence[Content] | None) -> str:
    """Get the first image from summary or content.

    Returns:
        First valid image URL, or an empty string.
    """
    image_urls: list[str] = get_image_urls(summary, content, limit=1)
    return image_urls[0] if image_urls else ""


def replace_tags_in_embed(feed: Feed, entry: Entry, reader: Reader) -> CustomEmbed:
    """Replace tags in embed.

    Args:
        feed: The feed to get the tags from.
        entry: The entry to get the tags from.
        reader: Custom Reader instance.

    Returns:
        Returns the embed with the tags replaced.
    """
    embed: CustomEmbed = get_embed(feed=feed, reader=reader)

    content = ""
    if entry.content:
        for content_item in entry.content:
            content: str = content_item.value

    summary: str = entry.summary or ""

    first_image: str = get_first_image(summary, content)

    summary = format_entry_html_for_discord(summary)
    content = format_entry_html_for_discord(content)

    feed_added: str = feed.added.strftime("%Y-%m-%d %H:%M:%S") if feed.added else "Never"
    feed_last_exception: str = feed.last_exception.value_str if feed.last_exception else ""
    feed_last_updated: str = feed.last_updated.strftime("%Y-%m-%d %H:%M:%S") if feed.last_updated else "Never"
    feed_updated: str = feed.updated.strftime("%Y-%m-%d %H:%M:%S") if feed.updated else "Never"
    entry_added: str = entry.added.strftime("%Y-%m-%d %H:%M:%S") if entry.added else "Never"
    entry_published: str = entry.published.strftime("%Y-%m-%d %H:%M:%S") if entry.published else "Never"
    entry_read_modified: str = entry.read_modified.strftime("%Y-%m-%d %H:%M:%S") if entry.read_modified else "Never"
    entry_updated: str = entry.updated.strftime("%Y-%m-%d %H:%M:%S") if entry.updated else "Never"

    if embed.title and not embed.author_name and embed.author_url:
        msg = "You are using author_url without author_name, but has title set. We will use author_name instead of title when sending the embed to Discord."  # ruff:ignore[line-too-long]
        logger.info(msg)
        embed.author_name = embed.title
        embed.title = ""

    list_of_replacements: list[dict[str, str]] = [
        {"{{feed_author}}": feed.authors_str or ""},
        {"{{feed_added}}": feed_added or ""},
        {"{{feed_last_exception}}": feed_last_exception},
        {"{{feed_last_updated}}": feed_last_updated or ""},
        {"{{feed_link}}": feed.link or ""},
        {"{{feed_subtitle}}": feed.subtitle or ""},
        {"{{feed_title}}": feed.title or ""},
        {"{{feed_updated}}": feed_updated or ""},
        {"{{feed_updates_enabled}}": "True" if feed.updates_enabled else "False"},
        {"{{feed_url}}": feed.url or ""},
        {"{{feed_user_title}}": feed.user_title or ""},
        {"{{feed_version}}": feed.version or ""},
        {"{{entry_added}}": entry_added or ""},
        {"{{entry_author}}": entry.authors_str or ""},
        {"{{entry_content}}": content or ""},
        {"{{entry_content_raw}}": entry.content[0].value if entry.content else ""},
        {"{{entry_id}}": entry.id},
        {"{{entry_important}}": "True" if entry.important else "False"},
        {"{{entry_link}}": entry.link or ""},
        {"{{entry_published}}": entry_published},
        {"{{entry_read}}": "True" if entry.read else "False"},
        {"{{entry_read_modified}}": entry_read_modified or ""},
        {"{{entry_summary}}": summary or ""},
        {"{{entry_summary_raw}}": entry.summary or ""},
        {"{{entry_text}}": summary or content or ""},
        {"{{entry_title}}": entry.title or ""},
        {"{{entry_updated}}": entry_updated or ""},
        {"{{image_1}}": first_image or ""},
    ]
    # Compute extension variables (handled separately so they can use
    # the already-computed values above without ordering issues).
    extension_vars: dict[str, str] = run_extensions(entry, reader)
    for var_name, var_value in extension_vars.items():
        list_of_replacements.append({f"{{{{{var_name}}}}}": var_value})

    for replacement in list_of_replacements:
        for template, replace_with in replacement.items():
            _replace_embed_tags(embed, template, replace_with)

    embed.title = embed.title.replace("\\n", "\n")
    embed.description = embed.description.replace("\\n", "\n")
    embed.author_name = embed.author_name.replace("\\n", "\n")
    embed.author_url = embed.author_url.replace("\\n", "\n")
    embed.author_icon_url = embed.author_icon_url.replace("\\n", "\n")
    embed.image_url = embed.image_url.replace("\\n", "\n")
    embed.thumbnail_url = embed.thumbnail_url.replace("\\n", "\n")
    embed.footer_text = embed.footer_text.replace("\\n", "\n")
    embed.footer_icon_url = embed.footer_icon_url.replace("\\n", "\n")
    return embed


def _replace_embed_tags(embed: CustomEmbed, template: str, replace_with: str) -> None:
    """Replace tags in embed.

    Args:
        embed: The embed to replace tags in.
        template: The tag to replace.
        replace_with: What to replace the tag with.
    """
    embed.title = try_to_replace(embed.title, template, replace_with)
    embed.description = try_to_replace(embed.description, template, replace_with)
    embed.author_name = try_to_replace(embed.author_name, template, replace_with)
    embed.author_url = try_to_replace(embed.author_url, template, replace_with)
    embed.author_icon_url = try_to_replace(embed.author_icon_url, template, replace_with)
    embed.image_url = try_to_replace(embed.image_url, template, replace_with)
    embed.thumbnail_url = try_to_replace(embed.thumbnail_url, template, replace_with)
    embed.footer_text = try_to_replace(embed.footer_text, template, replace_with)
    embed.footer_icon_url = try_to_replace(embed.footer_icon_url, template, replace_with)
    embed.avatar_url = try_to_replace(embed.avatar_url, template, replace_with)
    embed.username = try_to_replace(embed.username, template, replace_with)


def get_custom_message(reader: Reader, feed: Feed) -> str:
    """Get custom_message tag from feed.

    Args:
        reader: What Reader to use.
        feed: The feed to get the tag from.

    Returns:
        Returns the contents from the custom_message tag.
    """
    try:
        custom_message: str = str(reader.get_tag(feed, "custom_message", ""))
    except ValueError:
        custom_message = ""

    return custom_message


def get_message_username(reader: Reader, feed: Feed) -> str:
    """Get the stored custom webhook username for a feed.

    Returns:
        Stored username (may be empty or invalid for Discord).
    """
    try:
        return str(reader.get_tag(feed, "message_username", ""))
    except ValueError:
        return ""


def get_message_avatar_url(reader: Reader, feed: Feed) -> str:
    """Get the stored custom webhook avatar URL for a feed.

    Returns:
        Stored avatar URL (may be empty or invalid for Discord).
    """
    try:
        return str(reader.get_tag(feed, "message_avatar_url", ""))
    except ValueError:
        return ""


def normalize_message_username(username: str | None) -> str:
    """Return a Discord-safe webhook username, or empty string if unusable.

    Blank or invalid values are rejected so Discord uses the webhook default.

    Returns:
        Valid username, or empty string when the override should not be sent.
    """
    if not username:
        return ""

    cleaned: str = username.strip()
    if not cleaned:
        return ""
    if len(cleaned) > DISCORD_WEBHOOK_USERNAME_MAX_LENGTH:
        return ""
    if any(character in cleaned for character in DISCORD_WEBHOOK_USERNAME_FORBIDDEN_CHARS):
        return ""
    lowered: str = cleaned.lower()
    if any(forbidden in lowered for forbidden in DISCORD_WEBHOOK_USERNAME_FORBIDDEN_SUBSTRINGS):
        return ""
    return cleaned


def normalize_message_avatar_url(avatar_url: str | None) -> str:
    """Return a usable webhook avatar URL, or empty string if unusable.

    Blank or invalid values are rejected so Discord uses the webhook default.

    Returns:
        Valid http(s) URL, or empty string when the override should not be sent.
    """
    if not avatar_url:
        return ""

    cleaned: str = avatar_url.strip()
    if not cleaned:
        return ""
    if not cleaned.lower().startswith(("http://", "https://")):
        return ""
    if not is_url_valid(cleaned):
        return ""
    return cleaned


def get_validated_message_username(reader: Reader, feed: Feed) -> str:
    """Get a Discord-safe custom webhook username for a feed, if configured.

    Returns:
        Valid username to send, or empty string to use the webhook default.
    """
    return normalize_message_username(get_message_username(reader, feed))


def get_validated_message_avatar_url(reader: Reader, feed: Feed) -> str:
    """Get a usable custom webhook avatar URL for a feed, if configured.

    Returns:
        Valid avatar URL to send, or empty string to use the webhook default.
    """
    return normalize_message_avatar_url(get_message_avatar_url(reader, feed))


def save_embed(reader: Reader, feed: Feed, embed: CustomEmbed) -> None:
    """Set embed tag in feed.

    Args:
        reader: What Reader to use.
        feed: The feed to set the tag in.
        embed: The embed to set.
    """
    embed_dict: dict[str, str | int | bool] = {
        "title": embed.title,
        "description": embed.description,
        "color": embed.color,
        "author_name": embed.author_name,
        "author_url": embed.author_url,
        "author_icon_url": embed.author_icon_url,
        "image_url": embed.image_url,
        "thumbnail_url": embed.thumbnail_url,
        "footer_text": embed.footer_text,
        "footer_icon_url": embed.footer_icon_url,
        "show_steam_game_icon_in_thumbnail": embed.show_steam_game_icon_in_thumbnail,
        "avatar_url": embed.avatar_url,
        "username": embed.username,
    }
    reader.set_tag(feed, "embed", json.dumps(embed_dict))  # pyright: ignore[reportArgumentType]


def get_embed(reader: Reader, feed: Feed) -> CustomEmbed:
    """Get embed tag from feed.

    Args:
        reader: What Reader to use.
        feed: The feed to get the tag from.

    Returns:
        Returns the contents from the embed tag.
    """
    embed = reader.get_tag(feed, "embed", "")

    if embed:
        if not isinstance(embed, str):
            return get_embed_data(embed)  # pyright: ignore[reportArgumentType]
        embed_data: dict[str, str | int | bool] = json.loads(embed)
        return get_embed_data(embed_data)

    return CustomEmbed(
        title="",
        description="",
        color="#469ad9",
        author_name="",
        author_url="",
        author_icon_url="",
        image_url="",
        thumbnail_url="",
        footer_text="",
        footer_icon_url="",
        show_steam_game_icon_in_thumbnail=True,
        avatar_url="",
        username="",
    )


def get_embed_data(embed_data: dict[str, str | int | bool]) -> CustomEmbed:
    """Get embed data from embed_data.

    Args:
        embed_data: The embed_data to get the data from.

    Returns:
        Returns the embed data.
    """
    title: str = str(embed_data.get("title", ""))
    description: str = str(embed_data.get("description", ""))
    color: str = str(embed_data.get("color", ""))
    author_name: str = str(embed_data.get("author_name", ""))
    author_url: str = str(embed_data.get("author_url", ""))
    author_icon_url: str = str(embed_data.get("author_icon_url", ""))
    image_url: str = str(embed_data.get("image_url", ""))
    thumbnail_url: str = str(embed_data.get("thumbnail_url", ""))
    footer_text: str = str(embed_data.get("footer_text", ""))
    footer_icon_url: str = str(embed_data.get("footer_icon_url", ""))
    show_steam_game_icon_in_thumbnail: bool = embed_data.get(  # pyright: ignore[reportAssignmentType]
        "show_steam_game_icon_in_thumbnail",
        True,
    )
    avatar_url: str = str(embed_data.get("avatar_url", ""))
    username: str = str(embed_data.get("username", ""))

    return CustomEmbed(
        title=title,
        description=description,
        color=color,
        author_name=author_name,
        author_url=author_url,
        author_icon_url=author_icon_url,
        image_url=image_url,
        thumbnail_url=thumbnail_url,
        footer_text=footer_text,
        footer_icon_url=footer_icon_url,
        show_steam_game_icon_in_thumbnail=show_steam_game_icon_in_thumbnail,
        avatar_url=avatar_url,
        username=username,
    )
