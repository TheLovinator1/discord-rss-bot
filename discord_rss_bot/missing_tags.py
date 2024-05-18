from reader import Feed, Reader, TagNotFoundError

from discord_rss_bot.settings import default_custom_embed, default_custom_message


def add_custom_message(reader: Reader, feed: Feed) -> None:
    """Add the custom message tag to the feed if it doesn't exist.

    Args:
        reader: What Reader to use.
        feed: The feed to add the tag to.
    """
    try:
        reader.get_tag(feed, "custom_message")
    except TagNotFoundError:
        reader.set_tag(feed.url, "custom_message", default_custom_message)  # type: ignore
        reader.set_tag(feed.url, "has_custom_message", True)  # type: ignore


def add_has_custom_message(reader: Reader, feed: Feed) -> None:
    """Add the has_custom_message tag to the feed if it doesn't exist.

    Args:
        reader: What Reader to use.
        feed: The feed to add the tag to.
    """
    try:
        reader.get_tag(feed, "has_custom_message")
    except TagNotFoundError:
        if reader.get_tag(feed, "custom_message") == default_custom_message:
            reader.set_tag(feed.url, "has_custom_message", False)  # type: ignore
        else:
            reader.set_tag(feed.url, "has_custom_message", True)  # type: ignore


def add_if_embed(reader: Reader, feed: Feed) -> None:
    """Add the if_embed tag to the feed if it doesn't exist.

    Args:
        reader: What Reader to use.
        feed: The feed to add the tag to.
    """
    try:
        reader.get_tag(feed, "if_embed")
    except TagNotFoundError:
        reader.set_tag(feed.url, "if_embed", True)  # type: ignore


def add_custom_embed(reader: Reader, feed: Feed) -> None:
    """Add the custom embed tag to the feed if it doesn't exist.

    Args:
        reader: What Reader to use.
        feed: The feed to add the tag to.
    """
    try:
        reader.get_tag(feed, "embed")
    except TagNotFoundError:
        reader.set_tag(feed.url, "embed", default_custom_embed)  # type: ignore
        reader.set_tag(feed.url, "has_custom_embed", True)  # type: ignore


def add_has_custom_embed(reader: Reader, feed: Feed) -> None:
    """Add the has_custom_embed tag to the feed if it doesn't exist.

    Args:
        reader: What Reader to use.
        feed: The feed to add the tag to.
    """
    try:
        reader.get_tag(feed, "has_custom_embed")
    except TagNotFoundError:
        if reader.get_tag(feed, "embed") == default_custom_embed:
            reader.set_tag(feed.url, "has_custom_embed", False)  # type: ignore
        else:
            reader.set_tag(feed.url, "has_custom_embed", True)  # type: ignore


def add_should_send_embed(reader: Reader, feed: Feed) -> None:
    """Add the should_send_embed tag to the feed if it doesn't exist.

    Args:
        reader: What Reader to use.
        feed: The feed to add the tag to.
    """
    try:
        reader.get_tag(feed, "should_send_embed")
    except TagNotFoundError:
        reader.set_tag(feed.url, "should_send_embed", True)  # type: ignore


def add_missing_tags(reader: Reader) -> None:
    """Add missing tags to feeds.

    Args:
        reader: What Reader to use.
    """
    for feed in reader.get_feeds():
        add_custom_message(reader, feed)
        add_has_custom_message(reader, feed)
        add_if_embed(reader, feed)
        add_custom_embed(reader, feed)
        add_has_custom_embed(reader, feed)
        add_should_send_embed(reader, feed)
