from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

from feeds.markdown import convert_html_to_md
from feeds.models.message import MessageCustomization

if TYPE_CHECKING:
    from reader import Entry, Feed

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


def try_to_replace(custom_message: str | None, template: str | None, replace_with: str | None) -> str:
    """Try to replace a tag in custom_message.

    Args:
        custom_message: The custom_message to replace tags in.
        template: The tag to replace.
        replace_with: What to replace the tag with.

    Returns:
        Returns the custom_message with the tag replaced.
    """
    if not custom_message or not template or not replace_with:
        logger.error("Failed to replace tag in custom_message")
        return custom_message or "N/A"

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
    custom_message: str = MessageCustomization.objects.get(feed_url=feed.url).custom_message

    content = ""
    if entry.content:
        for content_item in entry.content:
            content: str = content_item.value

    summary: str = entry.summary or ""

    first_image = get_first_image(summary, content)

    summary = convert_html_to_md(summary)
    content = convert_html_to_md(content)

    feed_added: str = feed.added.strftime("%Y-%m-%d %H:%M:%S") if feed.added else "Never"
    feed_last_updated: str = feed.last_updated.strftime("%Y-%m-%d %H:%M:%S") if feed.last_updated else "Never"
    feed_updated: str = feed.updated.strftime("%Y-%m-%d %H:%M:%S") if feed.updated else "Never"
    entry_added: str = entry.added.strftime("%Y-%m-%d %H:%M:%S") if entry.added else "Never"
    entry_published: str = entry.published.strftime("%Y-%m-%d %H:%M:%S") if entry.published else "Never"
    entry_read_modified: str = entry.read_modified.strftime("%Y-%m-%d %H:%M:%S") if entry.read_modified else "Never"
    entry_updated: str = entry.updated.strftime("%Y-%m-%d %H:%M:%S") if entry.updated else "Never"

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
        {"{{entry_text}}": content or summary or ""},
        {"{{entry_title}}": entry.title or ""},
        {"{{entry_updated}}": entry_updated or ""},
        {"{{image_1}}": first_image or ""},
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
    # TODO(TheLovinator): Don't grab the first image if it's a tracking pixel  # noqa: TD003
    # TODO(TheLovinator): Don't grab the first for Genshin when it is just a line  # noqa: TD003
    # TODO(TheLovinator): Return "" if we fail here  # noqa: TD003
    if content and (images := BeautifulSoup(content, features="lxml").find_all("img")):
        return str(images[0].attrs["src"])
    if summary and (images := BeautifulSoup(summary, features="lxml").find_all("img")):
        return str(images[0].attrs["src"])
    return ""


def replace_tags_in_embed(feed: Feed, entry: Entry) -> CustomEmbed:
    """Replace tags in embed.

    Args:
        feed: The feed to get the tags from.
        entry: The entry to get the tags from.

    Returns:
        Returns the embed with the tags replaced.
    """
    message_customization: MessageCustomization = MessageCustomization.objects.get(feed_url=feed.url)

    content = ""
    if entry.content:
        for content_item in entry.content:
            content: str = content_item.value

    summary: str = entry.summary or ""

    first_image: str = get_first_image(summary=summary, content=content)

    summary = convert_html_to_md(html=summary)
    content = convert_html_to_md(html=content)

    feed_added: str = feed.added.strftime("%Y-%m-%d %H:%M:%S") if feed.added else "Never"
    feed_last_updated: str = feed.last_updated.strftime("%Y-%m-%d %H:%M:%S") if feed.last_updated else "Never"
    feed_updated: str = feed.updated.strftime("%Y-%m-%d %H:%M:%S") if feed.updated else "Never"
    entry_added: str = entry.added.strftime("%Y-%m-%d %H:%M:%S") if entry.added else "Never"
    entry_published: str = entry.published.strftime("%Y-%m-%d %H:%M:%S") if entry.published else "Never"
    entry_read_modified: str = entry.read_modified.strftime("%Y-%m-%d %H:%M:%S") if entry.read_modified else "Never"
    entry_updated: str = entry.updated.strftime("%Y-%m-%d %H:%M:%S") if entry.updated else "Never"

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
        {"{{entry_content_raw}}": entry.content[0].value if entry.content else "" or ""},
        {"{{entry_id}}": entry.id or ""},
        {"{{entry_important}}": "True" if entry.important else "False"},
        {"{{entry_link}}": entry.link or ""},
        {"{{entry_published}}": entry_published or ""},
        {"{{entry_read}}": "True" if entry.read else "False"},
        {"{{entry_read_modified}}": entry_read_modified or ""},
        {"{{entry_summary}}": summary or ""},
        {"{{entry_summary_raw}}": entry.summary or "" or ""},
        {"{{entry_title}}": entry.title or ""},
        {"{{entry_text}}": content or summary or ""},
        {"{{entry_updated}}": entry_updated or ""},
        {"{{image_1}}": first_image or ""},
    ]

    embed = CustomEmbed()
    for replacement in list_of_replacements:
        for template, replace_with in replacement.items():
            embed.title = try_to_replace(
                custom_message=message_customization.custom_embed_title,
                template=template,
                replace_with=replace_with,
            )
            embed.description = try_to_replace(
                custom_message=message_customization.custom_embed_description,
                template=template,
                replace_with=replace_with,
            )
            embed.author_name = try_to_replace(
                custom_message=message_customization.custom_embed_author_name,
                template=template,
                replace_with=replace_with,
            )
            embed.author_url = try_to_replace(
                custom_message=message_customization.custom_embed_author_url,
                template=template,
                replace_with=replace_with,
            )
            embed.author_icon_url = try_to_replace(
                custom_message=message_customization.custom_embed_author_icon_url,
                template=template,
                replace_with=replace_with,
            )
            embed.image_url = try_to_replace(
                custom_message=message_customization.custom_embed_image_url,
                template=template,
                replace_with=replace_with,
            )
            embed.thumbnail_url = try_to_replace(
                custom_message=message_customization.custom_embed_thumbnail_url,
                template=template,
                replace_with=replace_with,
            )
            embed.footer_text = try_to_replace(
                custom_message=message_customization.custom_embed_footer_text,
                template=template,
                replace_with=replace_with,
            )
            embed.footer_icon_url = try_to_replace(
                custom_message=message_customization.custom_embed_footer_icon_url,
                template=template,
                replace_with=replace_with,
            )

    return embed
