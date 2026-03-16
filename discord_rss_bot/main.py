from __future__ import annotations

import json
import logging
import logging.config
import typing
import urllib.parse
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from functools import lru_cache
from typing import TYPE_CHECKING
from typing import Annotated
from typing import Any
from typing import cast

import httpx
import sentry_sdk
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends
from fastapi import FastAPI
from fastapi import Form
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from httpx import Response
from markdownify import markdownify
from reader import Entry
from reader import EntryNotFoundError
from reader import Feed
from reader import FeedExistsError
from reader import FeedNotFoundError
from reader import Reader
from reader import ReaderError
from reader import TagNotFoundError
from starlette.responses import RedirectResponse

from discord_rss_bot import settings
from discord_rss_bot.custom_filters import entry_is_blacklisted
from discord_rss_bot.custom_filters import entry_is_whitelisted
from discord_rss_bot.custom_message import CustomEmbed
from discord_rss_bot.custom_message import get_custom_message
from discord_rss_bot.custom_message import get_embed
from discord_rss_bot.custom_message import get_first_image
from discord_rss_bot.custom_message import replace_tags_in_text_message
from discord_rss_bot.custom_message import save_embed
from discord_rss_bot.feeds import create_feed
from discord_rss_bot.feeds import extract_domain
from discord_rss_bot.feeds import send_entry_to_discord
from discord_rss_bot.feeds import send_to_discord
from discord_rss_bot.git_backup import commit_state_change
from discord_rss_bot.git_backup import get_backup_path
from discord_rss_bot.is_url_valid import is_url_valid
from discord_rss_bot.search import create_search_context
from discord_rss_bot.settings import get_reader

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from collections.abc import Iterable

    from reader.types import JSONType


LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] [%(levelname)s] %(name)s: %(message)s",  # noqa: E501
        },
    },
    "handlers": {
        "default": {
            "level": "DEBUG",
            "formatter": "standard",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",  # Default is stderr
        },
    },
    "loggers": {
        "": {  # root logger
            "level": "DEBUG",
            "handlers": ["default"],
            "propagate": False,
        },
        "uvicorn.error": {
            "level": "DEBUG",
            "handlers": ["default"],
        },
        "uvicorn.access": {
            "level": "DEBUG",
            "handlers": ["default"],
        },
    },
}

logging.config.dictConfig(LOGGING_CONFIG)

logger: logging.Logger = logging.getLogger(__name__)


def get_reader_dependency() -> Reader:
    """Provide the app Reader instance as a FastAPI dependency.

    Returns:
        Reader: The shared Reader instance.
    """
    return get_reader()


# Time constants for relative time formatting
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400


def relative_time(dt: datetime | None) -> str:
    """Convert a datetime to a relative time string (e.g., '2 hours ago', 'in 5 minutes').

    Args:
        dt: The datetime to convert (should be timezone-aware).

    Returns:
        A human-readable relative time string.
    """
    if dt is None:
        return "Never"

    now = datetime.now(tz=UTC)
    diff = dt - now
    seconds = int(abs(diff.total_seconds()))
    is_future = diff.total_seconds() > 0

    # Determine the appropriate unit and value
    if seconds < SECONDS_PER_MINUTE:
        value = seconds
        unit = "s"
    elif seconds < SECONDS_PER_HOUR:
        value = seconds // SECONDS_PER_MINUTE
        unit = "m"
    elif seconds < SECONDS_PER_DAY:
        value = seconds // SECONDS_PER_HOUR
        unit = "h"
    else:
        value = seconds // SECONDS_PER_DAY
        unit = "d"

    # Format based on future or past
    return f"in {value}{unit}" if is_future else f"{value}{unit} ago"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Lifespan function for the FastAPI app."""
    reader: Reader = get_reader()
    scheduler: AsyncIOScheduler = AsyncIOScheduler(timezone=UTC)
    scheduler.add_job(
        func=send_to_discord,
        trigger="interval",
        minutes=1,
        id="send_to_discord",
        max_instances=3,
        next_run_time=datetime.now(tz=UTC),
    )
    scheduler.start()
    logger.info("Scheduler started.")
    yield
    reader.close()
    scheduler.shutdown(wait=True)


app: FastAPI = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="discord_rss_bot/static"), name="static")
templates: Jinja2Templates = Jinja2Templates(directory="discord_rss_bot/templates")


# Add the filters to the Jinja2 environment so they can be used in html templates.
templates.env.filters["encode_url"] = lambda url: urllib.parse.quote(url) if url else ""
templates.env.filters["discord_markdown"] = markdownify
templates.env.filters["relative_time"] = relative_time
templates.env.globals["get_backup_path"] = get_backup_path


@app.post("/add_webhook")
async def post_add_webhook(
    webhook_name: Annotated[str, Form()],
    webhook_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Add a feed to the database.

    Args:
        webhook_name: The name of the webhook.
        webhook_url: The url of the webhook.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the index page.

    Raises:
        HTTPException: If the webhook already exists.
    """
    # Get current webhooks from the database if they exist otherwise use an empty list.
    webhooks = list(reader.get_tag((), "webhooks", []))

    # Webhooks are stored as a list of dictionaries.
    # Example: [{"name": "webhook_name", "url": "webhook_url"}]
    webhooks = cast("list[dict[str, str]]", webhooks)

    # Only add the webhook if it doesn't already exist.
    stripped_webhook_name = webhook_name.strip()
    if all(webhook["name"] != stripped_webhook_name for webhook in webhooks):
        # Add the new webhook to the list of webhooks.
        webhooks.append({"name": webhook_name.strip(), "url": webhook_url.strip()})

        reader.set_tag((), "webhooks", webhooks)  # pyright: ignore[reportArgumentType]

        commit_state_change(reader, f"Add webhook {webhook_name.strip()}")

        return RedirectResponse(url="/", status_code=303)

    # TODO(TheLovinator): Show this error on the page.
    # TODO(TheLovinator): Replace HTTPException with WebhookAlreadyExistsError.
    raise HTTPException(status_code=409, detail="Webhook already exists")


@app.post("/delete_webhook")
async def post_delete_webhook(
    webhook_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Delete a webhook from the database.

    Args:
        webhook_url: The url of the webhook.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the index page.

    Raises:
        HTTPException: If the webhook could not be deleted

    """
    # TODO(TheLovinator): Check if the webhook is in use by any feeds before deleting it.
    # TODO(TheLovinator): Replace HTTPException with a custom exception for both of these.
    # Get current webhooks from the database if they exist otherwise use an empty list.
    webhooks = list(reader.get_tag((), "webhooks", []))

    # Webhooks are stored as a list of dictionaries.
    # Example: [{"name": "webhook_name", "url": "webhook_url"}]
    webhooks = cast("list[dict[str, str]]", webhooks)

    # Only add the webhook if it doesn't already exist.
    webhooks_to_remove: list[dict[str, str]] = [
        webhook for webhook in webhooks if webhook["url"] == webhook_url.strip()
    ]

    # Remove the webhooks outside the loop.
    for webhook in webhooks_to_remove:
        webhooks.remove(webhook)

    # Check if any webhooks were removed.
    if not all(webhook not in webhooks for webhook in webhooks_to_remove):
        raise HTTPException(status_code=500, detail="Webhook could not be deleted")

    # Add our new list of webhooks to the database.
    reader.set_tag((), "webhooks", webhooks)  # pyright: ignore[reportArgumentType]

    commit_state_change(reader, f"Delete webhook {webhook_url.strip()}")

    return RedirectResponse(url="/", status_code=303)


@app.post("/add")
async def post_create_feed(
    feed_url: Annotated[str, Form()],
    webhook_dropdown: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Add a feed to the database.

    Args:
        feed_url: The feed to add.
        webhook_dropdown: The webhook to use.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    create_feed(reader, feed_url, webhook_dropdown)
    commit_state_change(reader, f"Add feed {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/pause")
async def post_pause_feed(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Pause a feed.

    Args:
        feed_url: The feed to pause.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.disable_feed_updates(clean_feed_url)
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/unpause")
async def post_unpause_feed(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Unpause a feed.

    Args:
        feed_url: The Feed to unpause.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.enable_feed_updates(clean_feed_url)
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/whitelist")
async def post_set_whitelist(
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    whitelist_title: Annotated[str, Form()] = "",
    whitelist_summary: Annotated[str, Form()] = "",
    whitelist_content: Annotated[str, Form()] = "",
    whitelist_author: Annotated[str, Form()] = "",
    regex_whitelist_title: Annotated[str, Form()] = "",
    regex_whitelist_summary: Annotated[str, Form()] = "",
    regex_whitelist_content: Annotated[str, Form()] = "",
    regex_whitelist_author: Annotated[str, Form()] = "",
    feed_url: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Set what the whitelist should be sent, if you have this set only words in the whitelist will be sent.

    Args:
        whitelist_title: Whitelisted words for when checking the title.
        whitelist_summary: Whitelisted words for when checking the summary.
        whitelist_content: Whitelisted words for when checking the content.
        whitelist_author: Whitelisted words for when checking the author.
        regex_whitelist_title: Whitelisted regex for when checking the title.
        regex_whitelist_summary: Whitelisted regex for when checking the summary.
        regex_whitelist_content: Whitelisted regex for when checking the content.
        regex_whitelist_author: Whitelisted regex for when checking the author.
        feed_url: The feed we should set the whitelist for.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip() if feed_url else ""
    reader.set_tag(clean_feed_url, "whitelist_title", whitelist_title)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "whitelist_summary", whitelist_summary)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "whitelist_content", whitelist_content)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "whitelist_author", whitelist_author)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "regex_whitelist_title", regex_whitelist_title)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "regex_whitelist_summary", regex_whitelist_summary)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "regex_whitelist_content", regex_whitelist_content)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "regex_whitelist_author", regex_whitelist_author)  # pyright: ignore[reportArgumentType][call-overload]

    commit_state_change(reader, f"Update whitelist for {clean_feed_url}")

    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.get("/whitelist", response_class=HTMLResponse)
async def get_whitelist(
    feed_url: str,
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
):
    """Get the whitelist.

    Args:
        feed_url: What feed we should get the whitelist for.
        request: The request object.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The whitelist page.
    """
    clean_feed_url: str = feed_url.strip()
    feed: Feed = reader.get_feed(urllib.parse.unquote(clean_feed_url))

    whitelist_title: str = str(reader.get_tag(feed, "whitelist_title", ""))
    whitelist_summary: str = str(reader.get_tag(feed, "whitelist_summary", ""))
    whitelist_content: str = str(reader.get_tag(feed, "whitelist_content", ""))
    whitelist_author: str = str(reader.get_tag(feed, "whitelist_author", ""))
    regex_whitelist_title: str = str(reader.get_tag(feed, "regex_whitelist_title", ""))
    regex_whitelist_summary: str = str(reader.get_tag(feed, "regex_whitelist_summary", ""))
    regex_whitelist_content: str = str(reader.get_tag(feed, "regex_whitelist_content", ""))
    regex_whitelist_author: str = str(reader.get_tag(feed, "regex_whitelist_author", ""))

    context = {
        "request": request,
        "feed": feed,
        "whitelist_title": whitelist_title,
        "whitelist_summary": whitelist_summary,
        "whitelist_content": whitelist_content,
        "whitelist_author": whitelist_author,
        "regex_whitelist_title": regex_whitelist_title,
        "regex_whitelist_summary": regex_whitelist_summary,
        "regex_whitelist_content": regex_whitelist_content,
        "regex_whitelist_author": regex_whitelist_author,
    }
    return templates.TemplateResponse(request=request, name="whitelist.html", context=context)


@app.post("/blacklist")
async def post_set_blacklist(
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    blacklist_title: Annotated[str, Form()] = "",
    blacklist_summary: Annotated[str, Form()] = "",
    blacklist_content: Annotated[str, Form()] = "",
    blacklist_author: Annotated[str, Form()] = "",
    regex_blacklist_title: Annotated[str, Form()] = "",
    regex_blacklist_summary: Annotated[str, Form()] = "",
    regex_blacklist_content: Annotated[str, Form()] = "",
    regex_blacklist_author: Annotated[str, Form()] = "",
    feed_url: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Set the blacklist.

    If this is set we will check if words are in the title, summary or content
    and then don't send that entry.

    Args:
        blacklist_title: Blacklisted words for when checking the title.
        blacklist_summary: Blacklisted words for when checking the summary.
        blacklist_content: Blacklisted words for when checking the content.
        blacklist_author: Blacklisted words for when checking the author.
        regex_blacklist_title: Blacklisted regex for when checking the title.
        regex_blacklist_summary: Blacklisted regex for when checking the summary.
        regex_blacklist_content: Blacklisted regex for when checking the content.
        regex_blacklist_author: Blacklisted regex for when checking the author.
        feed_url: What feed we should set the blacklist for.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip() if feed_url else ""
    reader.set_tag(clean_feed_url, "blacklist_title", blacklist_title)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "blacklist_summary", blacklist_summary)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "blacklist_content", blacklist_content)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "blacklist_author", blacklist_author)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "regex_blacklist_title", regex_blacklist_title)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "regex_blacklist_summary", regex_blacklist_summary)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "regex_blacklist_content", regex_blacklist_content)  # pyright: ignore[reportArgumentType][call-overload]
    reader.set_tag(clean_feed_url, "regex_blacklist_author", regex_blacklist_author)  # pyright: ignore[reportArgumentType][call-overload]
    commit_state_change(reader, f"Update blacklist for {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.get("/blacklist", response_class=HTMLResponse)
async def get_blacklist(
    feed_url: str,
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
):
    """Get the blacklist.

    Args:
        feed_url: What feed we should get the blacklist for.
        request: The request object.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The blacklist page.
    """
    feed: Feed = reader.get_feed(urllib.parse.unquote(feed_url))

    blacklist_title: str = str(reader.get_tag(feed, "blacklist_title", ""))
    blacklist_summary: str = str(reader.get_tag(feed, "blacklist_summary", ""))
    blacklist_content: str = str(reader.get_tag(feed, "blacklist_content", ""))
    blacklist_author: str = str(reader.get_tag(feed, "blacklist_author", ""))
    regex_blacklist_title: str = str(reader.get_tag(feed, "regex_blacklist_title", ""))
    regex_blacklist_summary: str = str(reader.get_tag(feed, "regex_blacklist_summary", ""))
    regex_blacklist_content: str = str(reader.get_tag(feed, "regex_blacklist_content", ""))
    regex_blacklist_author: str = str(reader.get_tag(feed, "regex_blacklist_author", ""))

    context = {
        "request": request,
        "feed": feed,
        "blacklist_title": blacklist_title,
        "blacklist_summary": blacklist_summary,
        "blacklist_content": blacklist_content,
        "blacklist_author": blacklist_author,
        "regex_blacklist_title": regex_blacklist_title,
        "regex_blacklist_summary": regex_blacklist_summary,
        "regex_blacklist_content": regex_blacklist_content,
        "regex_blacklist_author": regex_blacklist_author,
    }
    return templates.TemplateResponse(request=request, name="blacklist.html", context=context)


@app.post("/custom")
async def post_set_custom(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    custom_message: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Set the custom message, this is used when sending the message.

    Args:
        custom_message: The custom message.
        feed_url: The feed we should set the custom message for.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    our_custom_message: JSONType | str = custom_message.strip()
    our_custom_message = typing.cast("JSONType", our_custom_message)

    default_custom_message: JSONType | str = settings.default_custom_message
    default_custom_message = typing.cast("JSONType", default_custom_message)

    if our_custom_message:
        reader.set_tag(feed_url, "custom_message", our_custom_message)
    else:
        reader.set_tag(feed_url, "custom_message", default_custom_message)

    clean_feed_url: str = feed_url.strip()
    commit_state_change(reader, f"Update custom message for {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.get("/custom", response_class=HTMLResponse)
async def get_custom(
    feed_url: str,
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
):
    """Get the custom message. This is used when sending the message to Discord.

    Args:
        feed_url: What feed we should get the custom message for.
        request: The request object.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The custom message page.
    """
    feed: Feed = reader.get_feed(urllib.parse.unquote(feed_url.strip()))

    context: dict[str, Request | Feed | str | Entry] = {
        "request": request,
        "feed": feed,
        "custom_message": get_custom_message(reader, feed),
    }

    # Get the first entry, this is used to show the user what the custom message will look like.
    for entry in reader.get_entries(feed=feed, limit=1):
        context["entry"] = entry

    return templates.TemplateResponse(request=request, name="custom.html", context=context)


@app.get("/embed", response_class=HTMLResponse)
async def get_embed_page(
    feed_url: str,
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
):
    """Get the custom message. This is used when sending the message to Discord.

    Args:
        feed_url: What feed we should get the custom message for.
        request: The request object.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The embed page.
    """
    feed: Feed = reader.get_feed(urllib.parse.unquote(feed_url.strip()))

    # Get previous data, this is used when creating the form.
    embed: CustomEmbed = get_embed(reader, feed)

    context: dict[str, Request | Feed | str | Entry | CustomEmbed] = {
        "request": request,
        "feed": feed,
        "title": embed.title,
        "description": embed.description,
        "color": embed.color,
        "image_url": embed.image_url,
        "thumbnail_url": embed.thumbnail_url,
        "author_name": embed.author_name,
        "author_url": embed.author_url,
        "author_icon_url": embed.author_icon_url,
        "footer_text": embed.footer_text,
        "footer_icon_url": embed.footer_icon_url,
    }
    if custom_embed := get_embed(reader, feed):
        context["custom_embed"] = custom_embed

    for entry in reader.get_entries(feed=feed, limit=1):
        # Append to context.
        context["entry"] = entry
    return templates.TemplateResponse(request=request, name="embed.html", context=context)


@app.post("/embed", response_class=HTMLResponse)
async def post_embed(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    color: Annotated[str, Form()] = "",
    image_url: Annotated[str, Form()] = "",
    thumbnail_url: Annotated[str, Form()] = "",
    author_name: Annotated[str, Form()] = "",
    author_url: Annotated[str, Form()] = "",
    author_icon_url: Annotated[str, Form()] = "",
    footer_text: Annotated[str, Form()] = "",
    footer_icon_url: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Set the embed settings.

    Args:
        feed_url: What feed we should get the custom message for.
        title: The title of the embed.
        description: The description of the embed.
        color: The color of the embed.
        image_url: The image url of the embed.
        thumbnail_url: The thumbnail url of the embed.
        author_name: The author name of the embed.
        author_url: The author url of the embed.
        author_icon_url: The author icon url of the embed.
        footer_text: The footer text of the embed.
        footer_icon_url: The footer icon url of the embed.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the embed page.
    """
    clean_feed_url: str = feed_url.strip()
    feed: Feed = reader.get_feed(urllib.parse.unquote(clean_feed_url))

    custom_embed: CustomEmbed = get_embed(reader, feed)
    custom_embed.title = title
    custom_embed.description = description
    custom_embed.color = color
    custom_embed.image_url = image_url
    custom_embed.thumbnail_url = thumbnail_url
    custom_embed.author_name = author_name
    custom_embed.author_url = author_url
    custom_embed.author_icon_url = author_icon_url
    custom_embed.footer_text = footer_text
    custom_embed.footer_icon_url = footer_icon_url

    # Save the data.
    save_embed(reader, feed, custom_embed)

    commit_state_change(reader, f"Update embed settings for {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/use_embed")
async def post_use_embed(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Use embed instead of text.

    Args:
        feed_url: The feed to change.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.set_tag(clean_feed_url, "should_send_embed", True)  # pyright: ignore[reportArgumentType]
    commit_state_change(reader, f"Enable embed mode for {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/use_text")
async def post_use_text(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Use text instead of embed.

    Args:
        feed_url: The feed to change.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.set_tag(clean_feed_url, "should_send_embed", False)  # pyright: ignore[reportArgumentType]
    commit_state_change(reader, f"Disable embed mode for {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/set_update_interval")
async def post_set_update_interval(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    interval_minutes: Annotated[int | None, Form()] = None,
    redirect_to: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Set the update interval for a feed.

    Args:
        feed_url: The feed to change.
        interval_minutes: The update interval in minutes (None to reset to global default).
        redirect_to: Optional redirect URL (defaults to feed page).
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the specified page or feed page.
    """
    clean_feed_url: str = feed_url.strip()

    # If no interval specified, reset to global default
    if interval_minutes is None:
        try:
            reader.delete_tag(clean_feed_url, ".reader.update")
            commit_state_change(reader, f"Reset update interval to default for {clean_feed_url}")
        except TagNotFoundError:
            pass
    else:
        # Validate interval (minimum 1 minute, no maximum)
        interval_minutes = max(interval_minutes, 1)
        reader.set_tag(clean_feed_url, ".reader.update", {"interval": interval_minutes})  # pyright: ignore[reportArgumentType]
        commit_state_change(reader, f"Set update interval to {interval_minutes} minutes for {clean_feed_url}")

    # Update the feed immediately to recalculate update_after with the new interval
    try:
        reader.update_feed(clean_feed_url)
        logger.info("Updated feed after interval change: %s", clean_feed_url)
    except Exception:
        logger.exception("Failed to update feed after interval change: %s", clean_feed_url)

    if redirect_to:
        return RedirectResponse(url=redirect_to, status_code=303)
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/change_feed_url")
async def post_change_feed_url(
    old_feed_url: Annotated[str, Form()],
    new_feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Change the URL for an existing feed.

    Args:
        old_feed_url: Current feed URL.
        new_feed_url: New feed URL to change to.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page for the resulting URL.

    Raises:
        HTTPException: If the old feed is not found, the new URL already exists, or change fails.
    """
    clean_old_feed_url: str = old_feed_url.strip()
    clean_new_feed_url: str = new_feed_url.strip()

    if not clean_old_feed_url or not clean_new_feed_url:
        raise HTTPException(status_code=400, detail="Feed URLs cannot be empty")

    if clean_old_feed_url == clean_new_feed_url:
        return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_old_feed_url)}", status_code=303)

    try:
        reader.change_feed_url(clean_old_feed_url, clean_new_feed_url)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Feed not found: {clean_old_feed_url}") from e
    except FeedExistsError as e:
        raise HTTPException(status_code=409, detail=f"Feed already exists: {clean_new_feed_url}") from e
    except ReaderError as e:
        raise HTTPException(status_code=400, detail=f"Failed to change feed URL: {e}") from e

    # Update the feed with the new URL so we can discover what entries it returns.
    # Then mark all unread entries as read so the scheduler doesn't resend them.
    try:
        reader.update_feed(clean_new_feed_url)
    except Exception:
        logger.exception("Failed to update feed after URL change: %s", clean_new_feed_url)

    for entry in reader.get_entries(feed=clean_new_feed_url, read=False):
        try:
            reader.set_entry_read(entry, True)
        except Exception:
            logger.exception("Failed to mark entry as read after URL change: %s", entry.id)

    commit_state_change(reader, f"Change feed URL from {clean_old_feed_url} to {clean_new_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_new_feed_url)}", status_code=303)


@app.post("/reset_update_interval")
async def post_reset_update_interval(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    redirect_to: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Reset the update interval for a feed to use the global default.

    Args:
        feed_url: The feed to change.
        redirect_to: Optional redirect URL (defaults to feed page).
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the specified page or feed page.
    """
    clean_feed_url: str = feed_url.strip()

    try:
        reader.delete_tag(clean_feed_url, ".reader.update")
        commit_state_change(reader, f"Reset update interval to default for {clean_feed_url}")
    except TagNotFoundError:
        # Tag doesn't exist, which is fine
        pass

    # Update the feed immediately to recalculate update_after with the new interval
    try:
        reader.update_feed(clean_feed_url)
        logger.info("Updated feed after interval reset: %s", clean_feed_url)
    except Exception:
        logger.exception("Failed to update feed after interval reset: %s", clean_feed_url)

    if redirect_to:
        return RedirectResponse(url=redirect_to, status_code=303)
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/set_global_update_interval")
async def post_set_global_update_interval(
    interval_minutes: Annotated[int, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Set the global default update interval.

    Args:
        interval_minutes: The update interval in minutes.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the settings page.
    """
    # Validate interval (minimum 1 minute, no maximum)
    interval_minutes = max(interval_minutes, 1)

    reader.set_tag((), ".reader.update", {"interval": interval_minutes})  # pyright: ignore[reportArgumentType]
    commit_state_change(reader, f"Set global update interval to {interval_minutes} minutes")
    return RedirectResponse(url="/settings", status_code=303)


@app.get("/add", response_class=HTMLResponse)
def get_add(
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
):
    """Page for adding a new feed.

    Args:
        request: The request object.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The add feed page.
    """
    context = {
        "request": request,
        "webhooks": reader.get_tag((), "webhooks", []),
    }
    return templates.TemplateResponse(request=request, name="add.html", context=context)


@app.get("/feed", response_class=HTMLResponse)
async def get_feed(  # noqa: C901, PLR0912, PLR0914, PLR0915
    feed_url: str,
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    starting_after: str = "",
):
    """Get a feed by URL.

    Args:
        feed_url: The feed to add.
        request: The request object.
        starting_after: The entry to start after. Used for pagination.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The feed page.

    Raises:
        HTTPException: If the feed is not found.
    """
    entries_per_page: int = 20

    clean_feed_url: str = urllib.parse.unquote(feed_url.strip())

    try:
        feed: Feed = reader.get_feed(clean_feed_url)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Feed '{clean_feed_url}' not found.\n\n{e}") from e

    # Only show button if more than 10 entries.
    total_entries: int = reader.get_entry_counts(feed=feed).total or 0
    is_show_more_entries_button_visible: bool = total_entries > entries_per_page

    # Get entries from the feed.
    if starting_after:
        try:
            start_after_entry: Entry | None = reader.get_entry((str(feed.url), starting_after))
        except FeedNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"Feed '{clean_feed_url}' not found.\n\n{e}") from e
        except EntryNotFoundError as e:
            current_entries = list(reader.get_entries(feed=clean_feed_url))
            msg: str = f"{e}\n\n{[entry.id for entry in current_entries]}"
            html: str = create_html_for_feed(reader=reader, entries=current_entries, current_feed_url=clean_feed_url)

            # Get feed and global intervals for error case too
            feed_interval: int | None = None
            feed_update_config = reader.get_tag(feed, ".reader.update", None)
            if isinstance(feed_update_config, dict) and "interval" in feed_update_config:
                interval_value = feed_update_config["interval"]
                if isinstance(interval_value, int):
                    feed_interval = interval_value

            global_interval: int = 60
            global_update_config = reader.get_tag((), ".reader.update", None)
            if isinstance(global_update_config, dict) and "interval" in global_update_config:
                interval_value = global_update_config["interval"]
                if isinstance(interval_value, int):
                    global_interval = interval_value

            context = {
                "request": request,
                "feed": feed,
                "entries": current_entries,
                "feed_counts": reader.get_feed_counts(feed=clean_feed_url),
                "html": html,
                "should_send_embed": False,
                "last_entry": None,
                "messages": msg,
                "is_show_more_entries_button_visible": is_show_more_entries_button_visible,
                "total_entries": total_entries,
                "feed_interval": feed_interval,
                "global_interval": global_interval,
            }
            return templates.TemplateResponse(request=request, name="feed.html", context=context)

    else:
        start_after_entry = None

    entries: typing.Iterable[Entry] = reader.get_entries(
        feed=clean_feed_url,
        starting_after=start_after_entry,
        limit=entries_per_page,
    )

    entries = list(entries)

    # Get the last entry.
    last_entry: Entry | None = None
    if entries:
        last_entry = entries[-1]

    # Create the html for the entries.
    html: str = create_html_for_feed(reader=reader, entries=entries, current_feed_url=clean_feed_url)

    should_send_embed: bool = bool(reader.get_tag(feed, "should_send_embed", True))

    # Get the update interval for this feed
    feed_interval: int | None = None
    feed_update_config = reader.get_tag(feed, ".reader.update", None)
    if isinstance(feed_update_config, dict) and "interval" in feed_update_config:
        interval_value = feed_update_config["interval"]
        if isinstance(interval_value, int):
            feed_interval = interval_value

    # Get the global default update interval
    global_interval: int = 60  # Default to 60 minutes if not set
    global_update_config = reader.get_tag((), ".reader.update", None)
    if isinstance(global_update_config, dict) and "interval" in global_update_config:
        interval_value = global_update_config["interval"]
        if isinstance(interval_value, int):
            global_interval = interval_value

    context = {
        "request": request,
        "feed": feed,
        "entries": entries,
        "feed_counts": reader.get_feed_counts(feed=clean_feed_url),
        "html": html,
        "should_send_embed": should_send_embed,
        "last_entry": last_entry,
        "is_show_more_entries_button_visible": is_show_more_entries_button_visible,
        "total_entries": total_entries,
        "feed_interval": feed_interval,
        "global_interval": global_interval,
    }
    return templates.TemplateResponse(request=request, name="feed.html", context=context)


def create_html_for_feed(  # noqa: C901, PLR0914
    reader: Reader,
    entries: Iterable[Entry],
    current_feed_url: str = "",
) -> str:
    """Create HTML for the search results.

    Args:
        reader: The Reader instance to use.
        entries: The entries to create HTML for.
        current_feed_url: The feed URL currently being viewed in /feed.

    Returns:
        str: The HTML for the search results.
    """
    html: str = ""
    for entry in entries:
        first_image: str = ""
        summary: str | None = entry.summary
        content = ""
        if entry.content:
            for content_item in entry.content:
                content: str = content_item.value

        first_image = get_first_image(summary, content)

        text: str = replace_tags_in_text_message(entry, reader=reader) or (
            "<div class='text-muted'>No content available.</div>"
        )
        published = ""
        if entry.published:
            published: str = entry.published.strftime("%Y-%m-%d %H:%M:%S")

        blacklisted: str = ""
        if entry_is_blacklisted(entry, reader=reader):
            blacklisted = "<span class='badge bg-danger'>Blacklisted</span>"

        whitelisted: str = ""
        if entry_is_whitelisted(entry, reader=reader):
            whitelisted = "<span class='badge bg-success'>Whitelisted</span>"

        source_feed_url: str = getattr(entry, "original_feed_url", None) or entry.feed.url

        from_another_feed: str = ""
        if current_feed_url and source_feed_url != current_feed_url:
            from_another_feed = f"<span class='badge bg-warning text-dark'>From another feed: {source_feed_url}</span>"

        # Add feed link when viewing from webhook_entries or aggregated views
        feed_link: str = ""
        if not current_feed_url or source_feed_url != current_feed_url:
            encoded_feed_url: str = urllib.parse.quote(source_feed_url)
            feed_title: str = entry.feed.title if hasattr(entry.feed, "title") and entry.feed.title else source_feed_url
            feed_link = (
                f"<a class='text-muted' style='font-size: 0.85em;' "
                f"href='/feed?feed_url={encoded_feed_url}'>{feed_title}</a><br>"
            )

        entry_id: str = urllib.parse.quote(entry.id)
        encoded_source_feed_url: str = urllib.parse.quote(source_feed_url)
        to_discord_html: str = (
            f"<a class='text-muted' href='/post_entry?entry_id={entry_id}&feed_url={encoded_source_feed_url}'>"
            "Send to Discord</a>"
        )

        # Check if this is a YouTube feed entry and the entry has a link
        is_youtube_feed = "youtube.com/feeds/videos.xml" in entry.feed.url
        video_embed_html = ""

        if is_youtube_feed and entry.link:
            # Extract the video ID and create an embed if possible
            video_id: str | None = extract_youtube_video_id(entry.link)
            if video_id:
                video_embed_html: str = f"""
                <div class="ratio ratio-16x9 mt-3 mb-3">
                    <iframe src="https://www.youtube.com/embed/{video_id}"
                        title="{entry.title}"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowfullscreen>
                    </iframe>
                </div>
                """
                # Don't use the first image if we have a video embed
                first_image = ""

        image_html: str = f"<img src='{first_image}' class='img-fluid'>" if first_image else ""

        html += f"""<div class="p-2 mb-2 border border-dark">
{blacklisted}{whitelisted}{from_another_feed}<a class="text-muted text-decoration-none" href="{entry.link}"><h2>{entry.title}</h2></a>
{feed_link}{f"By {entry.author} @" if entry.author else ""}{published} - {to_discord_html}

{text}
{video_embed_html}
{image_html}
</div>
"""  # noqa: E501
    return html.strip()


@app.get("/add_webhook", response_class=HTMLResponse)
async def get_add_webhook(request: Request):
    """Page for adding a new webhook.

    Args:
        request: The request object.

    Returns:
    HTMLResponse: The add webhook page.
    """
    return templates.TemplateResponse(request=request, name="add_webhook.html", context={"request": request})


@dataclass()
class WebhookInfo:
    custom_name: str
    url: str
    webhook_type: int | None = None
    webhook_id: str | None = None
    name: str | None = None
    avatar: str | None = None
    channel_id: str | None = None
    guild_id: str | None = None
    token: str | None = None
    avatar_mod: int | None = None


@lru_cache
def get_data_from_hook_url(hook_name: str, hook_url: str) -> WebhookInfo:
    """Get data from a webhook URL.

    Args:
        hook_name (str): The webhook name.
        hook_url (str): The webhook URL.


    Returns:
        WebhookInfo: The webhook username, avatar, guild id, etc.
    """
    our_hook: WebhookInfo = WebhookInfo(custom_name=hook_name, url=hook_url)

    if hook_url:
        response: Response = httpx.get(hook_url)
        if response.is_success:
            webhook_json = json.loads(response.text)
            our_hook.webhook_type = webhook_json["type"] or None
            our_hook.webhook_id = webhook_json["id"] or None
            our_hook.name = webhook_json["name"] or None
            our_hook.avatar = webhook_json["avatar"] or None
            our_hook.channel_id = webhook_json["channel_id"] or None
            our_hook.guild_id = webhook_json["guild_id"] or None
            our_hook.token = webhook_json["token"] or None
            our_hook.avatar_mod = int(webhook_json["channel_id"] or 0) % 5
    return our_hook


@app.get("/settings", response_class=HTMLResponse)
async def get_settings(
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
):
    """Settings page.

    Args:
        request: The request object.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The settings page.
    """
    # Get the global default update interval
    global_interval: int = 60  # Default to 60 minutes if not set
    global_update_config = reader.get_tag((), ".reader.update", None)
    if isinstance(global_update_config, dict) and "interval" in global_update_config:
        interval_value = global_update_config["interval"]
        if isinstance(interval_value, int):
            global_interval = interval_value

    # Get all feeds with their intervals
    feeds: Iterable[Feed] = reader.get_feeds()
    feed_intervals = []
    for feed in feeds:
        feed_interval: int | None = None
        feed_update_config = reader.get_tag(feed, ".reader.update", None)
        if isinstance(feed_update_config, dict) and "interval" in feed_update_config:
            interval_value = feed_update_config["interval"]
            if isinstance(interval_value, int):
                feed_interval = interval_value

        feed_intervals.append({
            "feed": feed,
            "interval": feed_interval,
            "effective_interval": feed_interval or global_interval,
            "domain": extract_domain(feed.url),
        })

    context = {
        "request": request,
        "global_interval": global_interval,
        "feed_intervals": feed_intervals,
    }
    return templates.TemplateResponse(request=request, name="settings.html", context=context)


@app.get("/webhooks", response_class=HTMLResponse)
async def get_webhooks(
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
):
    """Page for adding a new webhook.

    Args:
        request: The request object.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The add webhook page.
    """
    hooks_with_data: list[WebhookInfo] = []

    webhook_list = list(reader.get_tag((), "webhooks", []))
    for hook in webhook_list:
        if not isinstance(hook, dict):
            logger.error("Webhook is not a dict: %s", hook)
            continue

        our_hook: WebhookInfo = get_data_from_hook_url(hook_url=hook["url"], hook_name=hook["name"])
        hooks_with_data.append(our_hook)

    context = {"request": request, "hooks_with_data": hooks_with_data}
    return templates.TemplateResponse(request=request, name="webhooks.html", context=context)


@app.get("/", response_class=HTMLResponse)
def get_index(
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    message: str = "",
):
    """This is the root of the website.

    Args:
        request: The request object.
        message: Optional message to display to the user.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The index page.
    """
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=make_context_index(request, message, reader),
    )


def make_context_index(request: Request, message: str = "", reader: Reader | None = None):
    """Create the needed context for the index page.

    Args:
        request: The request object.
        message: Optional message to display to the user.
        reader: The Reader instance.

    Returns:
            dict: The context for the index page.
    """
    effective_reader: Reader = reader or get_reader_dependency()
    hooks: list[dict[str, str]] = cast("list[dict[str, str]]", list(effective_reader.get_tag((), "webhooks", [])))

    feed_list: list[dict[str, JSONType | Feed | str]] = []
    broken_feeds: list[Feed] = []
    feeds_without_attached_webhook: list[Feed] = []

    # Get all feeds and organize them
    feeds: Iterable[Feed] = effective_reader.get_feeds()
    for feed in feeds:
        webhook: str = str(effective_reader.get_tag(feed.url, "webhook", ""))
        if not webhook:
            broken_feeds.append(feed)
            continue

        feed_list.append({"feed": feed, "webhook": webhook, "domain": extract_domain(feed.url)})

        webhook_list: list[str] = [hook["url"] for hook in hooks]
        if webhook not in webhook_list:
            feeds_without_attached_webhook.append(feed)

    return {
        "request": request,
        "feeds": feed_list,
        "feed_count": effective_reader.get_feed_counts(),
        "entry_count": effective_reader.get_entry_counts(),
        "webhooks": hooks,
        "broken_feeds": broken_feeds,
        "feeds_without_attached_webhook": feeds_without_attached_webhook,
        "messages": message or None,
    }


@app.post("/remove", response_class=HTMLResponse)
async def remove_feed(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
):
    """Get a feed by URL.

    Args:
        feed_url: The feed to add.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the index page.

    Raises:
        HTTPException: Feed not found
    """
    try:
        reader.delete_feed(urllib.parse.unquote(feed_url))
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail="Feed not found") from e

    commit_state_change(reader, f"Remove feed {urllib.parse.unquote(feed_url)}")

    return RedirectResponse(url="/", status_code=303)


@app.get("/update", response_class=HTMLResponse)
async def update_feed(
    request: Request,
    feed_url: str,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
):
    """Update a feed.

    Args:
        request: The request object.
        feed_url: The feed URL to update.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.

    Raises:
        HTTPException: If the feed is not found.
    """
    try:
        reader.update_feed(urllib.parse.unquote(feed_url))
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail="Feed not found") from e

    logger.info("Manually updated feed: %s", feed_url)
    return RedirectResponse(url="/feed?feed_url=" + urllib.parse.quote(feed_url), status_code=303)


@app.post("/backup")
async def manual_backup(
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Manually trigger a git backup of the current state.

    Args:
        request: The request object.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the index page with a success or error message.
    """
    backup_path = get_backup_path()
    if backup_path is None:
        message = "Git backup is not configured. Set GIT_BACKUP_PATH environment variable to enable backups."
        logger.warning("Manual git backup attempted but GIT_BACKUP_PATH is not configured")
        return RedirectResponse(url=f"/?message={urllib.parse.quote(message)}", status_code=303)

    try:
        commit_state_change(reader, "Manual backup triggered from web UI")
        message = "Successfully created git backup!"
        logger.info("Manual git backup completed successfully")
    except Exception as e:
        message = f"Failed to create git backup: {e}"
        logger.exception("Manual git backup failed")

    return RedirectResponse(url=f"/?message={urllib.parse.quote(message)}", status_code=303)


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    query: str,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
):
    """Get entries matching a full-text search query.

    Args:
        query: The query to search for.
        request: The request object.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The search page.
    """
    reader.update_search()
    context = create_search_context(query, reader=reader)
    return templates.TemplateResponse(request=request, name="search.html", context={"request": request, **context})


@app.get("/post_entry", response_class=HTMLResponse)
async def post_entry(
    entry_id: str,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    feed_url: str = "",
):
    """Send single entry to Discord.

    Args:
        entry_id: The entry to send.
        feed_url: Optional feed URL used to disambiguate entries with identical IDs.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    unquoted_entry_id: str = urllib.parse.unquote(entry_id)
    clean_feed_url: str = urllib.parse.unquote(feed_url.strip()) if feed_url else ""

    # Prefer feed-scoped lookup when feed_url is provided. This avoids ambiguity when
    # multiple feeds contain entries with the same ID.
    entry: Entry | None = None
    if clean_feed_url:
        entry = next(
            (entry for entry in reader.get_entries(feed=clean_feed_url) if entry.id == unquoted_entry_id),
            None,
        )
    else:
        entry = next((entry for entry in reader.get_entries() if entry.id == unquoted_entry_id), None)

    if entry is None:
        return HTMLResponse(status_code=404, content=f"Entry '{entry_id}' not found.")

    if result := send_entry_to_discord(entry=entry, reader=reader):
        return result

    # Redirect to the feed page.
    redirect_feed_url: str = entry.feed.url.strip()
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(redirect_feed_url)}", status_code=303)


@app.post("/modify_webhook", response_class=HTMLResponse)
def modify_webhook(
    old_hook: Annotated[str, Form()],
    new_hook: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    redirect_to: Annotated[str, Form()] = "",
):
    """Modify a webhook.

    Args:
        old_hook: The webhook to modify.
        new_hook: The new webhook.
        redirect_to: Optional redirect URL after the update.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the webhook page.

    Raises:
        HTTPException: Webhook could not be modified.

    """
    # Get current webhooks from the database if they exist otherwise use an empty list.
    webhooks = list(reader.get_tag((), "webhooks", []))

    # Webhooks are stored as a list of dictionaries.
    # Example: [{"name": "webhook_name", "url": "webhook_url"}]
    webhooks = cast("list[dict[str, str]]", webhooks)
    old_hook_clean: str = old_hook.strip()
    new_hook_clean: str = new_hook.strip()
    webhook_modified: bool = False

    for hook in webhooks:
        if hook["url"] in old_hook_clean:
            hook["url"] = new_hook_clean

            # Check if it has been modified.
            if hook["url"] != new_hook_clean:
                raise HTTPException(status_code=500, detail="Webhook could not be modified")

            webhook_modified = True

            # Add our new list of webhooks to the database.
            reader.set_tag((), "webhooks", webhooks)  # pyright: ignore[reportArgumentType]

            # Loop through all feeds and update the webhook if it
            # matches the old one.
            feeds: Iterable[Feed] = reader.get_feeds()
            for feed in feeds:
                webhook: str = str(reader.get_tag(feed, "webhook", ""))

                if webhook == old_hook_clean:
                    reader.set_tag(feed.url, "webhook", new_hook_clean)  # pyright: ignore[reportArgumentType]

    if webhook_modified and old_hook_clean != new_hook_clean:
        commit_state_change(reader, f"Modify webhook URL from {old_hook_clean} to {new_hook_clean}")

    redirect_url: str = redirect_to.strip() or "/webhooks"
    if redirect_to:
        redirect_url = redirect_url.replace(urllib.parse.quote(old_hook_clean), urllib.parse.quote(new_hook_clean))
        redirect_url = redirect_url.replace(old_hook_clean, new_hook_clean)

    # Redirect to the requested page.
    return RedirectResponse(url=redirect_url, status_code=303)


def extract_youtube_video_id(url: str) -> str | None:
    """Extract YouTube video ID from a YouTube video URL.

    Args:
        url: The YouTube video URL.

    Returns:
        The video ID if found, None otherwise.
    """
    if not url:
        return None

    # Handle standard YouTube URLs (youtube.com/watch?v=VIDEO_ID)
    if "youtube.com/watch" in url and "v=" in url:
        return url.split("v=")[1].split("&", maxsplit=1)[0]

    # Handle shortened YouTube URLs (youtu.be/VIDEO_ID)
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?", maxsplit=1)[0]

    return None


def resolve_final_feed_url(url: str) -> tuple[str, str | None]:
    """Resolve a feed URL by following redirects.

    Args:
        url: The feed URL to resolve.

    Returns:
        tuple[str, str | None]: A tuple with (resolved_url, error_message).
        error_message is None when resolution succeeded.
    """
    clean_url: str = url.strip()
    if not clean_url:
        return "", "URL is empty"

    if not is_url_valid(clean_url):
        return clean_url, "URL is invalid"

    try:
        response: Response = httpx.get(clean_url, follow_redirects=True, timeout=10.0)
    except httpx.HTTPError as e:
        return clean_url, str(e)

    if not response.is_success:
        return clean_url, f"HTTP {response.status_code}"

    return str(response.url), None


def create_webhook_feed_url_preview(
    webhook_feeds: list[Feed],
    replace_from: str,
    replace_to: str,
    resolve_urls: bool,  # noqa: FBT001
    force_update: bool = False,  # noqa: FBT001, FBT002
    existing_feed_urls: set[str] | None = None,
) -> list[dict[str, str | bool | None]]:
    """Create preview rows for bulk feed URL replacement.

    Args:
        webhook_feeds: Feeds attached to a webhook.
        replace_from: Text to replace in each URL.
        replace_to: Replacement text.
        resolve_urls: Whether to resolve resulting URLs via HTTP redirects.
        force_update: Whether conflicts should be marked as force-overwritable.
        existing_feed_urls: Optional set of all tracked feed URLs used for conflict detection.

    Returns:
        list[dict[str, str | bool | None]]: Rows used in the preview table.
    """
    known_feed_urls: set[str] = existing_feed_urls or {feed.url for feed in webhook_feeds}
    preview_rows: list[dict[str, str | bool | None]] = []
    for feed in webhook_feeds:
        old_url: str = feed.url
        has_match: bool = bool(replace_from and replace_from in old_url)

        candidate_url: str = old_url
        if has_match:
            candidate_url = old_url.replace(replace_from, replace_to)

        resolved_url: str = candidate_url
        resolution_error: str | None = None
        if has_match and candidate_url != old_url and resolve_urls:
            resolved_url, resolution_error = resolve_final_feed_url(candidate_url)

        will_force_ignore_errors: bool = bool(
            force_update and bool(resolution_error) and has_match and old_url != candidate_url,
        )

        target_exists: bool = bool(
            has_match and not resolution_error and resolved_url != old_url and resolved_url in known_feed_urls,
        )
        will_force_overwrite: bool = bool(target_exists and force_update)
        will_change: bool = bool(
            has_match
            and old_url != (candidate_url if will_force_ignore_errors else resolved_url)
            and (not target_exists or will_force_overwrite)
            and (not resolution_error or will_force_ignore_errors),
        )

        preview_rows.append({
            "old_url": old_url,
            "candidate_url": candidate_url,
            "resolved_url": resolved_url,
            "has_match": has_match,
            "will_change": will_change,
            "target_exists": target_exists,
            "will_force_overwrite": will_force_overwrite,
            "will_force_ignore_errors": will_force_ignore_errors,
            "resolution_error": resolution_error,
        })

    return preview_rows


def build_webhook_mass_update_context(
    webhook_feeds: list[Feed],
    all_feeds: list[Feed],
    replace_from: str,
    replace_to: str,
    resolve_urls: bool,  # noqa: FBT001
    force_update: bool = False,  # noqa: FBT001, FBT002
) -> dict[str, str | bool | int | list[dict[str, str | bool | None]] | dict[str, int]]:
    """Build context data used by the webhook mass URL update preview UI.

    Args:
        webhook_feeds: Feeds attached to the selected webhook.
        all_feeds: All tracked feeds.
        replace_from: Text to replace in URLs.
        replace_to: Replacement text.
        resolve_urls: Whether to resolve resulting URLs.
        force_update: Whether to allow overwriting existing target URLs.

    Returns:
        dict[str, ...]: Context values for rendering preview controls and table.
    """
    clean_replace_from: str = replace_from.strip()
    clean_replace_to: str = replace_to.strip()

    preview_rows: list[dict[str, str | bool | None]] = []
    if clean_replace_from:
        preview_rows = create_webhook_feed_url_preview(
            webhook_feeds=webhook_feeds,
            replace_from=clean_replace_from,
            replace_to=clean_replace_to,
            resolve_urls=resolve_urls,
            force_update=force_update,
            existing_feed_urls={feed.url for feed in all_feeds},
        )

    preview_summary: dict[str, int] = {
        "total": len(preview_rows),
        "matched": sum(1 for row in preview_rows if row["has_match"]),
        "will_update": sum(1 for row in preview_rows if row["will_change"]),
        "conflicts": sum(1 for row in preview_rows if row["target_exists"] and not row["will_force_overwrite"]),
        "force_overwrite": sum(1 for row in preview_rows if row["will_force_overwrite"]),
        "force_ignore_errors": sum(1 for row in preview_rows if row["will_force_ignore_errors"]),
        "resolve_errors": sum(1 for row in preview_rows if row["resolution_error"]),
    }
    preview_summary["no_match"] = preview_summary["total"] - preview_summary["matched"]
    preview_summary["no_change"] = sum(
        1 for row in preview_rows if row["has_match"] and not row["resolution_error"] and not row["will_change"]
    )

    return {
        "replace_from": clean_replace_from,
        "replace_to": clean_replace_to,
        "resolve_urls": resolve_urls,
        "force_update": force_update,
        "preview_rows": preview_rows,
        "preview_summary": preview_summary,
        "preview_change_count": preview_summary["will_update"],
    }


@app.get("/webhook_entries_mass_update_preview", response_class=HTMLResponse)
async def get_webhook_entries_mass_update_preview(
    webhook_url: str,
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    replace_from: str = "",
    replace_to: str = "",
    resolve_urls: bool = True,  # noqa: FBT001, FBT002
    force_update: bool = False,  # noqa: FBT001, FBT002
) -> HTMLResponse:
    """Render the mass-update preview fragment for a webhook using HTMX.

    Args:
        webhook_url: Webhook URL whose feeds are being updated.
        request: The request object.
        reader: The Reader instance.
        replace_from: Text to find in URLs.
        replace_to: Replacement text.
        resolve_urls: Whether to resolve resulting URLs.
        force_update: Whether to allow overwriting existing target URLs.

    Returns:
        HTMLResponse: Rendered partial template containing summary + preview table.
    """
    clean_webhook_url: str = urllib.parse.unquote(webhook_url.strip())
    all_feeds: list[Feed] = list(reader.get_feeds())
    webhook_feeds: list[Feed] = [
        feed for feed in all_feeds if str(reader.get_tag(feed.url, "webhook", "")) == clean_webhook_url
    ]

    context = {
        "request": request,
        "webhook_url": clean_webhook_url,
        **build_webhook_mass_update_context(
            webhook_feeds=webhook_feeds,
            all_feeds=all_feeds,
            replace_from=replace_from,
            replace_to=replace_to,
            resolve_urls=resolve_urls,
            force_update=force_update,
        ),
    }
    return templates.TemplateResponse(request=request, name="_webhook_mass_update_preview.html", context=context)


@app.get("/webhook_entries", response_class=HTMLResponse)
async def get_webhook_entries(  # noqa: C901, PLR0914
    webhook_url: str,
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    starting_after: str = "",
    replace_from: str = "",
    replace_to: str = "",
    resolve_urls: bool = True,  # noqa: FBT001, FBT002
    force_update: bool = False,  # noqa: FBT001, FBT002
    message: str = "",
) -> HTMLResponse:
    """Get all latest entries from all feeds for a specific webhook.

    Args:
        webhook_url: The webhook URL to get entries for.
        request: The request object.
        starting_after: The entry to start after. Used for pagination.
        replace_from: Optional URL substring to find for bulk URL replacement preview.
        replace_to: Optional replacement substring used in bulk URL replacement preview.
        resolve_urls: Whether to resolve replaced URLs by following redirects.
        force_update: Whether to allow overwriting existing target URLs during apply.
        message: Optional status message shown in the UI.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The webhook entries page.

    Raises:
        HTTPException: If no feeds are found for this webhook or webhook doesn't exist.
    """
    entries_per_page: int = 20
    clean_webhook_url: str = urllib.parse.unquote(webhook_url.strip())

    # Get the webhook name from the webhooks list
    webhooks: list[dict[str, str]] = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))
    webhook_name: str = ""
    for hook in webhooks:
        if hook["url"] == clean_webhook_url:
            webhook_name = hook["name"]
            break

    if not webhook_name:
        raise HTTPException(status_code=404, detail=f"Webhook not found: {clean_webhook_url}")

    hook_info: WebhookInfo = get_data_from_hook_url(hook_name=webhook_name, hook_url=clean_webhook_url)

    # Get all feeds associated with this webhook
    all_feeds: list[Feed] = list(reader.get_feeds())
    webhook_feeds: list[Feed] = []

    for feed in all_feeds:
        feed_webhook: str = str(reader.get_tag(feed.url, "webhook", ""))
        if feed_webhook == clean_webhook_url:
            webhook_feeds.append(feed)

    # Get all entries from all feeds for this webhook, sorted by published date
    all_entries: list[Entry] = [entry for feed in webhook_feeds for entry in reader.get_entries(feed=feed)]

    # Sort entries by published date (newest first), with undated entries last.
    all_entries.sort(
        key=lambda e: (
            e.published is not None,
            e.published or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )

    # Handle pagination
    if starting_after:
        try:
            start_after_entry: Entry | None = reader.get_entry((
                starting_after.split("|", maxsplit=1)[0],
                starting_after.split("|")[1],
            ))
        except (FeedNotFoundError, EntryNotFoundError):
            start_after_entry = None
    else:
        start_after_entry = None

    # Find the index of the starting entry
    start_index: int = 0
    if start_after_entry:
        for idx, entry in enumerate(all_entries):
            if entry.id == start_after_entry.id and entry.feed.url == start_after_entry.feed.url:
                start_index = idx + 1
                break

    # Get the page of entries
    paginated_entries: list[Entry] = all_entries[start_index : start_index + entries_per_page]

    # Get the last entry for pagination
    last_entry: Entry | None = None
    if paginated_entries:
        last_entry = paginated_entries[-1]

    # Create the html for the entries
    html: str = create_html_for_feed(reader=reader, entries=paginated_entries)

    mass_update_context = build_webhook_mass_update_context(
        webhook_feeds=webhook_feeds,
        all_feeds=all_feeds,
        replace_from=replace_from,
        replace_to=replace_to,
        resolve_urls=resolve_urls,
        force_update=force_update,
    )

    # Check if there are more entries available
    total_entries: int = len(all_entries)
    is_show_more_entries_button_visible: bool = (start_index + entries_per_page) < total_entries

    context = {
        "request": request,
        "hook_info": hook_info,
        "webhook_name": webhook_name,
        "webhook_url": clean_webhook_url,
        "webhook_feeds": webhook_feeds,
        "entries": paginated_entries,
        "html": html,
        "last_entry": last_entry,
        "is_show_more_entries_button_visible": is_show_more_entries_button_visible,
        "total_entries": total_entries,
        "feeds_count": len(webhook_feeds),
        "message": urllib.parse.unquote(message) if message else "",
        **mass_update_context,
    }
    return templates.TemplateResponse(request=request, name="webhook_entries.html", context=context)


@app.post("/bulk_change_feed_urls", response_class=HTMLResponse)
async def post_bulk_change_feed_urls(  # noqa: C901, PLR0914, PLR0912, PLR0915
    webhook_url: Annotated[str, Form()],
    replace_from: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    replace_to: Annotated[str, Form()] = "",
    resolve_urls: Annotated[bool, Form()] = True,  # noqa: FBT002
    force_update: Annotated[bool, Form()] = False,  # noqa: FBT002
) -> RedirectResponse:
    """Bulk-change feed URLs attached to a webhook.

    Args:
        webhook_url: The webhook URL whose feeds should be updated.
        replace_from: Text to find in each URL.
        replace_to: Text to replace with.
        resolve_urls: Whether to resolve resulting URLs via redirects.
        force_update: Whether existing target feed URLs should be overwritten.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to webhook detail with status message.

    Raises:
        HTTPException: If webhook is missing or replace_from is empty.
    """
    clean_webhook_url: str = urllib.parse.unquote(webhook_url.strip())
    clean_replace_from: str = replace_from.strip()
    clean_replace_to: str = replace_to.strip()

    if not clean_replace_from:
        raise HTTPException(status_code=400, detail="replace_from cannot be empty")

    webhooks: list[dict[str, str]] = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))
    if not any(hook["url"] == clean_webhook_url for hook in webhooks):
        raise HTTPException(status_code=404, detail=f"Webhook not found: {clean_webhook_url}")

    all_feeds: list[Feed] = list(reader.get_feeds())
    webhook_feeds: list[Feed] = []
    for feed in all_feeds:
        feed_webhook: str = str(reader.get_tag(feed.url, "webhook", ""))
        if feed_webhook == clean_webhook_url:
            webhook_feeds.append(feed)

    preview_rows: list[dict[str, str | bool | None]] = create_webhook_feed_url_preview(
        webhook_feeds=webhook_feeds,
        replace_from=clean_replace_from,
        replace_to=clean_replace_to,
        resolve_urls=resolve_urls,
        force_update=force_update,
        existing_feed_urls={feed.url for feed in all_feeds},
    )

    changed_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    conflict_count: int = 0
    force_overwrite_count: int = 0

    for row in preview_rows:
        if not row["has_match"]:
            continue

        if row["resolution_error"] and not force_update:
            skipped_count += 1
            continue

        if row["target_exists"] and not force_update:
            conflict_count += 1
            skipped_count += 1
            continue

        old_url: str = str(row["old_url"])
        new_url: str = str(row["candidate_url"] if row["will_force_ignore_errors"] else row["resolved_url"])

        if old_url == new_url:
            skipped_count += 1
            continue

        if row["target_exists"] and force_update:
            try:
                reader.delete_feed(new_url)
                force_overwrite_count += 1
            except FeedNotFoundError:
                pass
            except ReaderError:
                failed_count += 1
                continue

        try:
            reader.change_feed_url(old_url, new_url)
        except FeedExistsError:
            skipped_count += 1
            continue
        except FeedNotFoundError:
            skipped_count += 1
            continue
        except ReaderError:
            failed_count += 1
            continue

        try:
            reader.update_feed(new_url)
        except Exception:
            logger.exception("Failed to update feed after URL change: %s", new_url)

        for entry in reader.get_entries(feed=new_url, read=False):
            try:
                reader.set_entry_read(entry, True)
            except Exception:
                logger.exception("Failed to mark entry as read after URL change: %s", entry.id)

        changed_count += 1

    if changed_count > 0:
        commit_state_change(
            reader,
            f"Bulk change {changed_count} feed URL(s) for webhook {clean_webhook_url}",
        )

    status_message: str = (
        f"Updated {changed_count} feed URL(s). "
        f"Force overwrote {force_overwrite_count}. "
        f"Conflicts {conflict_count}. "
        f"Skipped {skipped_count}. "
        f"Failed {failed_count}."
    )
    redirect_url: str = (
        f"/webhook_entries?webhook_url={urllib.parse.quote(clean_webhook_url)}"
        f"&message={urllib.parse.quote(status_message)}"
    )
    return RedirectResponse(url=redirect_url, status_code=303)


if __name__ == "__main__":
    sentry_sdk.init(
        dsn="https://6e77a0d7acb9c7ea22e85a375e0ff1f4@o4505228040339456.ingest.us.sentry.io/4508792887967744",
        send_default_pii=True,
        traces_sample_rate=1.0,
        _experiments={"continuous_profiling_auto_start": True},
    )

    uvicorn.run(
        "main:app",
        log_level="debug",
        host="0.0.0.0",  # noqa: S104
        port=3000,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
