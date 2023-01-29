import json
from dataclasses import dataclass

from bs4 import BeautifulSoup
from reader import Entry, Feed, Reader, TagNotFoundError

from discord_rss_bot.markdown import convert_html_to_md
from discord_rss_bot.settings import get_reader


@dataclass()
class CustomEmbed:
    title: str
    description: str
    color: str
    author_name: str
    author_url: str
    author_icon_url: str
    image_url: str
    thumbnail_url: str
    footer_text: str
    footer_icon_url: str


def return_image(found_images) -> list[tuple[str, str]] | None:
    soup: BeautifulSoup = BeautifulSoup(found_images, features="lxml")
    images = soup.find_all("img")
    for image in images:
        image_src: str = str(image["src"]) or ""
        image_alt: str = "Link to image"
        if image.get("alt"):
            image_alt = image.get("alt")
        return [(image_src, image_alt)]


def get_first_image_html(html: str):
    """Get images from a entry.

    Args:
        html: The HTML to get the images from.

    Returns:
        Returns a list of images.
    """
    if images := BeautifulSoup(html, features="lxml").find_all("img"):
        return images[0].attrs["src"]
    return None


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

    first_image = get_image(summary, content)

    summary = convert_html_to_md(summary)
    content = convert_html_to_md(content)

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
        {"{{entry_text}}": content or summary},
        {"{{entry_title}}": entry.title},
        {"{{entry_updated}}": entry.updated},
        {"{{image_1}}": first_image},
    ]

    for replacement in list_of_replacements:
        for template, replace_with in replacement.items():
            custom_message = try_to_replace(custom_message, template, replace_with)

    return custom_message.replace("\\n", "\n")


def get_image(summary, content):
    """Get image from summary or content

    Args:
        summary: The summary from the entry
        content: The content from the entry

    Returns:
        The first image
    """
    if content:
        if images := BeautifulSoup(content, features="lxml").find_all("img"):
            return images[0].attrs["src"]
    if summary:
        if images := BeautifulSoup(summary, features="lxml").find_all("img"):
            return images[0].attrs["src"]
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

    first_image = get_image(summary, content)

    summary = convert_html_to_md(summary)
    content = convert_html_to_md(content)

    entry_text: str = content or summary

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
        {"{{entry_title}}": entry.title},
        {"{{entry_text}}": entry_text},
        {"{{entry_updated}}": entry.updated},
        {"{{image_1}}": first_image},
    ]

    for replacement in list_of_replacements:
        for template, replace_with in replacement.items():
            embed.title = try_to_replace(embed.title, template, replace_with)
            embed.description = try_to_replace(embed.description, template, replace_with)
            embed.author_name = try_to_replace(embed.author_name, template, replace_with)
            embed.author_url = try_to_replace(embed.author_url, template, replace_with)
            embed.author_icon_url = try_to_replace(embed.author_icon_url, template, replace_with)
            embed.image_url = try_to_replace(embed.image_url, template, replace_with)
            embed.thumbnail_url = try_to_replace(embed.thumbnail_url, template, replace_with)
            embed.footer_text = try_to_replace(embed.footer_text, template, replace_with)
            embed.footer_icon_url = try_to_replace(embed.footer_icon_url, template, replace_with)

    return embed


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
        if type(embed) != str:
            return get_embed_data(embed)
        embed_data: dict[str, str | int] = json.loads(embed)  # type: ignore
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


def get_embed_data(embed_data) -> CustomEmbed:
    """Get embed data from embed_data.

    Args:
        embed_data: The embed_data to get the data from.

    Returns:
        Returns the embed data.
    """
    title: str = embed_data.get("title", "")
    description: str = embed_data.get("description", "")
    color: str = embed_data.get("color", "")
    author_name: str = embed_data.get("author_name", "")
    author_url: str = embed_data.get("author_url", "")
    author_icon_url: str = embed_data.get("author_icon_url", "")
    image_url: str = embed_data.get("image_url", "")
    thumbnail_url: str = embed_data.get("thumbnail_url", "")
    footer_text: str = embed_data.get("footer_text", "")
    footer_icon_url: str = embed_data.get("footer_icon_url", "")

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
