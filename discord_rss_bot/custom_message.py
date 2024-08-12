from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from bs4 import BeautifulSoup
from markdownify import markdownify
from reader import Entry, Feed, Reader, TagNotFoundError

from discord_rss_bot.is_url_valid import is_url_valid
from discord_rss_bot.settings import get_reader

logger: logging.Logger = logging.getLogger(__name__)


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
        return custom_message


def replace_tags_in_text_message(entry: Entry) -> str:
    """Replace tags in custom_message.

    Args:
        entry: The entry to get the tags from.

    Returns:
        Returns the custom_message with the tags replaced.
    """
    feed: Feed = entry.feed
    custom_reader: Reader = get_reader()
    custom_message: str = get_custom_message(feed=feed, custom_reader=custom_reader)

    content = ""
    if entry.content:
        for content_item in entry.content:
            content: str = content_item.value

    summary: str = entry.summary or ""

    first_image: str = get_first_image(summary, content)

    summary = markdownify(html=summary, strip=["img", "table", "td", "tr", "tbody", "thead"], escape_misc=False)
    content = markdownify(html=content, strip=["img", "table", "td", "tr", "tbody", "thead"], escape_misc=False)

    if "[https://" in content or "[https://www." in content:
        content = content.replace("[https://", "[")
        content = content.replace("[https://www.", "[")

    if "[https://" in summary or "[https://www." in summary:
        summary = summary.replace("[https://", "[")
        summary = summary.replace("[https://www.", "[")

    list_of_replacements = [
        {"{{feed_author}}": feed.author},
        {"{{feed_added}}": feed.added},
        {"{{feed_last_exception}}": feed.last_exception},
        {"{{feed_last_updated}}": feed.last_updated},
        {"{{feed_link}}": feed.link},
        {"{{feed_subtitle}}": feed.subtitle},
        {"{{feed_title}}": feed.title},
        {"{{feed_updated}}": feed.updated},
        {"{{feed_updates_enabled}}": str(feed.updates_enabled)},
        {"{{feed_url}}": feed.url},
        {"{{feed_user_title}}": feed.user_title},
        {"{{feed_version}}": feed.version},
        {"{{entry_added}}": entry.added},
        {"{{entry_author}}": entry.author},
        {"{{entry_content}}": content},
        {"{{entry_content_raw}}": entry.content[0].value if entry.content else ""},
        {"{{entry_id}}": entry.id},
        {"{{entry_important}}": str(entry.important)},
        {"{{entry_link}}": entry.link},
        {"{{entry_published}}": entry.published},
        {"{{entry_read}}": str(entry.read)},
        {"{{entry_read_modified}}": entry.read_modified},
        {"{{entry_summary}}": summary},
        {"{{entry_summary_raw}}": entry.summary or ""},
        {"{{entry_text}}": summary or content},
        {"{{entry_title}}": entry.title},
        {"{{entry_updated}}": entry.updated},
        {"{{image_1}}": first_image},
    ]

    for replacement in list_of_replacements:
        for template, replace_with in replacement.items():
            custom_message = try_to_replace(custom_message, template, replace_with)

    return custom_message.replace("\\n", "\n")


def get_first_image(summary: str | None, content: str | None) -> str:
    """Get image from summary or content.

    Args:
        summary: The summary from the entry
        content: The content from the entry

    Returns:
        The first image
    """
    # TODO(TheLovinator): We should find a better way to get the image.
    if content and (images := BeautifulSoup(content, features="lxml").find_all("img")):
        for image in images:
            if not is_url_valid(image.attrs["src"]):
                logger.warning("Invalid URL: %s", image.attrs["src"])
                continue

            # Genshins first image is a divider, so we ignore it.
            # https://hyl-static-res-prod.hoyolab.com/divider_config/PC/line_3.png
            skip_images: list[str] = [
                "https://img-os-static.hoyolab.com/divider_config/",
                "https://hyl-static-res-prod.hoyolab.com/divider_config/",
            ]
            if not image.attrs["src"].startswith(tuple(skip_images)):
                return str(image.attrs["src"])
    if summary and (images := BeautifulSoup(summary, features="lxml").find_all("img")):
        for image in images:
            if not is_url_valid(image.attrs["src"]):
                logger.warning("Invalid URL: %s", image.attrs["src"])
                continue

            # Genshins first image is a divider, so we ignore it.
            if not image.attrs["src"].startswith("https://img-os-static.hoyolab.com/divider_config"):
                return str(image.attrs["src"])
    return ""


def replace_tags_in_embed(feed: Feed, entry: Entry) -> CustomEmbed:
    """Replace tags in embed.

    Args:
        feed: The feed to get the tags from.
        entry: The entry to get the tags from.

    Returns:
        Returns the embed with the tags replaced.
    """
    custom_reader: Reader = get_reader()
    embed: CustomEmbed = get_embed(feed=feed, custom_reader=custom_reader)

    content = ""
    if entry.content:
        for content_item in entry.content:
            content: str = content_item.value

    summary: str = entry.summary or ""

    first_image: str = get_first_image(summary, content)

    summary = markdownify(html=summary, strip=["img", "table", "td", "tr", "tbody", "thead"], escape_misc=False)
    content = markdownify(html=content, strip=["img", "table", "td", "tr", "tbody", "thead"], escape_misc=False)

    if "[https://" in content or "[https://www." in content:
        content = content.replace("[https://", "[")
        content = content.replace("[https://www.", "[")

    if "[https://" in summary or "[https://www." in summary:
        summary = summary.replace("[https://", "[")
        summary = summary.replace("[https://www.", "[")

    feed_added: str = feed.added.strftime("%Y-%m-%d %H:%M:%S") if feed.added else "Never"
    feed_last_updated: str = feed.last_updated.strftime("%Y-%m-%d %H:%M:%S") if feed.last_updated else "Never"
    feed_updated: str = feed.updated.strftime("%Y-%m-%d %H:%M:%S") if feed.updated else "Never"
    entry_added: str = entry.added.strftime("%Y-%m-%d %H:%M:%S") if entry.added else "Never"
    entry_published: str = entry.published.strftime("%Y-%m-%d %H:%M:%S") if entry.published else "Never"
    entry_read_modified: str = entry.read_modified.strftime("%Y-%m-%d %H:%M:%S") if entry.read_modified else "Never"
    entry_updated: str = entry.updated.strftime("%Y-%m-%d %H:%M:%S") if entry.updated else "Never"

    if embed.title and not embed.author_name and embed.author_url:
        msg = "You are using author_url without author_name, but has title set. We will use author_name instead of title when sending the embed to Discord."  # noqa: E501
        logger.info(msg)
        embed.author_name = embed.title
        embed.title = ""

    list_of_replacements: list[dict[str, str]] = [
        {"{{feed_author}}": feed.author or ""},
        {"{{feed_added}}": feed_added or ""},
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
        {"{{entry_author}}": entry.author or ""},
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
    for replacement in list_of_replacements:
        for template, replace_with in replacement.items():
            _replace_embed_tags(embed, template, replace_with)
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


def get_custom_message(custom_reader: Reader, feed: Feed) -> str:
    """Get custom_message tag from feed.

    Args:
        custom_reader: What Reader to use.
        feed: The feed to get the tag from.

    Returns:
        Returns the contents from the custom_message tag.
    """
    try:
        custom_message: str = str(custom_reader.get_tag(feed, "custom_message"))
    except TagNotFoundError:
        custom_message = ""
    except ValueError:
        custom_message = ""

    return custom_message


def save_embed(custom_reader: Reader, feed: Feed, embed: CustomEmbed) -> None:
    """Set embed tag in feed.

    Args:
        custom_reader: What Reader to use.
        feed: The feed to set the tag in.
        embed: The embed to set.
    """
    embed_dict: dict[str, str | int] = {
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
    }

    custom_reader.set_tag(feed, "embed", json.dumps(embed_dict))  # type: ignore


def get_embed(custom_reader: Reader, feed: Feed) -> CustomEmbed:
    """Get embed tag from feed.

    Args:
        custom_reader: What Reader to use.
        feed: The feed to get the tag from.

    Returns:
        Returns the contents from the embed tag.
    """
    if embed := custom_reader.get_tag(feed, "embed", ""):
        if not isinstance(embed, str):
            return get_embed_data(embed)  # type: ignore
        embed_data: dict[str, str | int] = json.loads(embed)
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
    )


def get_embed_data(embed_data: dict[str, str | int]) -> CustomEmbed:
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
    )
