from reader import Entry, Feed, Reader, TagNotFoundError

from discord_rss_bot.custom_filters import convert_to_md
from discord_rss_bot.settings import get_reader


def try_to_replace(custom_message: str, template: str, replace_with: str) -> str:
    """Try to replace a tag in custom_message.

    Args:
        custom_message: The custom_message to replace tags in.
        feed: The feed to get the tags from.
        entry: The entry to get the tags from.
        tag: The tag to replace.

    Returns:
        Returns the custom_message with the tag replaced.
    """
    if not template:
        return custom_message
    if not replace_with:
        return custom_message
    try:
        return custom_message.replace(template, replace_with)
    except TypeError:
        return custom_message


def replace_tags(feed: Feed, entry: Entry) -> str:
    """Replace tags in custom_message.

    Args:
        feed: The feed to get the tags from.
        entry: The entry to get the tags from.

    Returns:
        Returns the custom_message with the tags replaced.
    """
    custom_reader: Reader = get_reader()
    custom_message: str = get_custom_message(feed=feed, custom_reader=custom_reader)

    summary = ""
    content = ""
    if entry.summary:
        summary: str = entry.summary
    if entry.content:
        content: str = entry.content[0]["value"]  # type: ignore

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
        {"{{entry_content}}": convert_to_md(content)},
        {"{{entry_content_raw}}": content},
        {"{{entry_id}}": entry.id},
        {"{{entry_important}}": str(entry.important)},
        {"{{entry_link}}": entry.link},
        {"{{entry_published}}": entry.published},
        {"{{entry_read}}": str(entry.read)},
        {"{{entry_read_modified}}": entry.read_modified},
        {"{{entry_summary}}": convert_to_md(summary)},
        {"{{entry_summary_raw}}": summary},
        {"{{entry_title}}": entry.title},
        {"{{entry_updated}}": entry.updated},
    ]

    for replacement in list_of_replacements:
        for template, replace_with in replacement.items():
            custom_message = try_to_replace(custom_message, template, replace_with)
    return custom_message


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
