from __future__ import annotations

import json
import logging
import logging.config
import typing
import urllib.parse
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, cast

import httpx
import sentry_sdk
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from httpx import Response
from markdownify import markdownify
from reader import Entry, EntryNotFoundError, Feed, FeedNotFoundError, Reader, TagNotFoundError
from starlette.responses import RedirectResponse

from discord_rss_bot import settings
from discord_rss_bot.custom_filters import (
    entry_is_blacklisted,
    entry_is_whitelisted,
)
from discord_rss_bot.custom_message import (
    CustomEmbed,
    get_custom_message,
    get_embed,
    get_first_image,
    replace_tags_in_text_message,
    save_embed,
)
from discord_rss_bot.feeds import create_feed, extract_domain, send_entry_to_discord, send_to_discord
from discord_rss_bot.missing_tags import add_missing_tags
from discord_rss_bot.search import create_html_for_search_results
from discord_rss_bot.settings import get_reader

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable

    from reader.types import JSONType


LOGGING_CONFIG = {
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
reader: Reader = get_reader()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Lifespan for the FastAPI app.

    Args:
        app: The FastAPI app.

    Yields:
        None: Nothing.
    """
    add_missing_tags(reader)
    scheduler: AsyncIOScheduler = AsyncIOScheduler()

    # Run job every minute to check for new entries. Feeds will be checked every 15 minutes.
    # TODO(TheLovinator): Make this configurable.
    scheduler.add_job(send_to_discord, "interval", minutes=1, next_run_time=datetime.now(tz=UTC))
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
templates.env.filters["entry_is_whitelisted"] = entry_is_whitelisted
templates.env.filters["entry_is_blacklisted"] = entry_is_blacklisted
templates.env.filters["discord_markdown"] = markdownify


@app.post("/add_webhook")
async def post_add_webhook(
    webhook_name: Annotated[str, Form()],
    webhook_url: Annotated[str, Form()],
) -> RedirectResponse:
    """Add a feed to the database.

    Args:
        webhook_name: The name of the webhook.
        webhook_url: The url of the webhook.

    Raises:
        HTTPException: If the webhook already exists.

    Returns:
        RedirectResponse: Redirect to the index page.
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

        return RedirectResponse(url="/", status_code=303)

    # TODO(TheLovinator): Show this error on the page.
    # TODO(TheLovinator): Replace HTTPException with WebhookAlreadyExistsError.
    raise HTTPException(status_code=409, detail="Webhook already exists")


@app.post("/delete_webhook")
async def post_delete_webhook(webhook_url: Annotated[str, Form()]) -> RedirectResponse:
    """Delete a webhook from the database.

    Args:
        webhook_url: The url of the webhook.

    Raises:
        HTTPException: If the webhook could not be deleted

    Returns:
        RedirectResponse: Redirect to the index page.
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

    return RedirectResponse(url="/", status_code=303)


@app.post("/add")
async def post_create_feed(
    feed_url: Annotated[str, Form()],
    webhook_dropdown: Annotated[str, Form()],
) -> RedirectResponse:
    """Add a feed to the database.

    Args:
        feed_url: The feed to add.
        webhook_dropdown: The webhook to use.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    create_feed(reader, feed_url, webhook_dropdown)
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/pause")
async def post_pause_feed(feed_url: Annotated[str, Form()]) -> RedirectResponse:
    """Pause a feed.

    Args:
        feed_url: The feed to pause.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.disable_feed_updates(clean_feed_url)
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/unpause")
async def post_unpause_feed(feed_url: Annotated[str, Form()]) -> RedirectResponse:
    """Unpause a feed.

    Args:
        feed_url: The Feed to unpause.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.enable_feed_updates(clean_feed_url)
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/whitelist")
async def post_set_whitelist(
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

    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.get("/whitelist", response_class=HTMLResponse)
async def get_whitelist(feed_url: str, request: Request):
    """Get the whitelist.

    Args:
        feed_url: What feed we should get the whitelist for.
        request: The request object.

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
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.get("/blacklist", response_class=HTMLResponse)
async def get_blacklist(feed_url: str, request: Request):
    """Get the blacklist.

    Args:
        feed_url: What feed we should get the blacklist for.
        request: The request object.

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
    custom_message: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Set the custom message, this is used when sending the message.

    Args:
        custom_message: The custom message.
        feed_url: The feed we should set the custom message for.

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
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.get("/custom", response_class=HTMLResponse)
async def get_custom(feed_url: str, request: Request):
    """Get the custom message. This is used when sending the message to Discord.

    Args:
        feed_url: What feed we should get the custom message for.
        request: The request object.

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
async def get_embed_page(feed_url: str, request: Request):
    """Get the custom message. This is used when sending the message to Discord.

    Args:
        feed_url: What feed we should get the custom message for.
        request: The request object.

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

    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/use_embed")
async def post_use_embed(feed_url: Annotated[str, Form()]) -> RedirectResponse:
    """Use embed instead of text.

    Args:
        feed_url: The feed to change.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.set_tag(clean_feed_url, "should_send_embed", True)  # pyright: ignore[reportArgumentType]
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/use_text")
async def post_use_text(feed_url: Annotated[str, Form()]) -> RedirectResponse:
    """Use text instead of embed.

    Args:
        feed_url: The feed to change.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.set_tag(clean_feed_url, "should_send_embed", False)  # pyright: ignore[reportArgumentType]
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.get("/add", response_class=HTMLResponse)
def get_add(request: Request):
    """Page for adding a new feed.

    Args:
        request: The request object.

    Returns:
        HTMLResponse: The add feed page.
    """
    context = {
        "request": request,
        "webhooks": reader.get_tag((), "webhooks", []),
    }
    return templates.TemplateResponse(request=request, name="add.html", context=context)


@app.get("/feed", response_class=HTMLResponse)
async def get_feed(feed_url: str, request: Request, starting_after: str = ""):
    """Get a feed by URL.

    Args:
        feed_url: The feed to add.
        request: The request object.
        starting_after: The entry to start after. Used for pagination.

    Raises:
        HTTPException: If the feed is not found.

    Returns:
        HTMLResponse: The feed page.
    """
    entries_per_page: int = 20

    clean_feed_url: str = urllib.parse.unquote(feed_url.strip())

    try:
        feed: Feed = reader.get_feed(clean_feed_url)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Feed '{clean_feed_url}' not found.\n\n{e}") from e

    # Only show button if more than 10 entries.
    total_entries: int = reader.get_entry_counts(feed=feed).total or 0
    show_more_entires_button: bool = total_entries > entries_per_page

    # Get entries from the feed.
    if starting_after:
        try:
            start_after_entry: Entry | None = reader.get_entry((str(feed.url), starting_after))
        except FeedNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"Feed '{clean_feed_url}' not found.\n\n{e}") from e
        except EntryNotFoundError as e:
            current_entries = list(reader.get_entries(feed=clean_feed_url))
            msg: str = f"{e}\n\n{[entry.id for entry in current_entries]}"
            html: str = create_html_for_feed(current_entries)

            context = {
                "request": request,
                "feed": feed,
                "entries": current_entries,
                "feed_counts": reader.get_feed_counts(feed=clean_feed_url),
                "html": html,
                "should_send_embed": False,
                "last_entry": None,
                "messages": msg,
                "show_more_entires_button": show_more_entires_button,
                "total_entries": total_entries,
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
    html: str = create_html_for_feed(entries)

    try:
        should_send_embed: bool = bool(reader.get_tag(feed, "should_send_embed"))
    except TagNotFoundError:
        add_missing_tags(reader)
        should_send_embed: bool = bool(reader.get_tag(feed, "should_send_embed"))

    context = {
        "request": request,
        "feed": feed,
        "entries": entries,
        "feed_counts": reader.get_feed_counts(feed=clean_feed_url),
        "html": html,
        "should_send_embed": should_send_embed,
        "last_entry": last_entry,
        "show_more_entires_button": show_more_entires_button,
        "total_entries": total_entries,
    }
    return templates.TemplateResponse(request=request, name="feed.html", context=context)


def create_html_for_feed(entries: Iterable[Entry]) -> str:
    """Create HTML for the search results.

    Args:
        entries: The entries to create HTML for.

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

        text: str = replace_tags_in_text_message(entry) or "<div class='text-muted'>No content available.</div>"
        published = ""
        if entry.published:
            published: str = entry.published.strftime("%Y-%m-%d %H:%M:%S")

        blacklisted: str = ""
        if entry_is_blacklisted(entry):
            blacklisted = "<span class='badge bg-danger'>Blacklisted</span>"

        whitelisted: str = ""
        if entry_is_whitelisted(entry):
            whitelisted = "<span class='badge bg-success'>Whitelisted</span>"

        entry_id: str = urllib.parse.quote(entry.id)
        to_discord_html: str = f"<a class='text-muted' href='/post_entry?entry_id={entry_id}'>Send to Discord</a>"

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
{blacklisted}{whitelisted}<a class="text-muted text-decoration-none" href="{entry.link}"><h2>{entry.title}</h2></a>
{f"By {entry.author} @" if entry.author else ""}{published} - {to_discord_html}

{text}
{video_embed_html}
{image_html}
</div>
"""
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


@app.get("/webhooks", response_class=HTMLResponse)
async def get_webhooks(request: Request):
    """Page for adding a new webhook.

    Args:
        request: The request object.

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
def get_index(request: Request):
    """This is the root of the website.

    Args:
        request: The request object.

    Returns:
        HTMLResponse: The index page.
    """
    return templates.TemplateResponse(request=request, name="index.html", context=make_context_index(request))


def make_context_index(request: Request):
    """Create the needed context for the index page.

    Args:
        request: The request object.

    Returns:
            dict: The context for the index page.
    """
    hooks: list[dict[str, str]] = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))

    feed_list = []
    broken_feeds = []
    feeds_without_attached_webhook = []

    # Get all feeds and organize them
    feeds: Iterable[Feed] = reader.get_feeds()
    for feed in feeds:
        try:
            webhook = reader.get_tag(feed.url, "webhook")
            feed_list.append({"feed": feed, "webhook": webhook, "domain": extract_domain(feed.url)})
        except TagNotFoundError:
            broken_feeds.append(feed)
            continue

        webhook_list = [hook["url"] for hook in hooks]
        if webhook not in webhook_list:
            feeds_without_attached_webhook.append(feed)

    return {
        "request": request,
        "feeds": feed_list,
        "feed_count": reader.get_feed_counts(),
        "entry_count": reader.get_entry_counts(),
        "webhooks": hooks,
        "broken_feeds": broken_feeds,
        "feeds_without_attached_webhook": feeds_without_attached_webhook,
    }


@app.post("/remove", response_class=HTMLResponse)
async def remove_feed(feed_url: Annotated[str, Form()]):
    """Get a feed by URL.

    Args:
        feed_url: The feed to add.

    Raises:
        HTTPException: Feed not found

    Returns:
        RedirectResponse: Redirect to the index page.
    """
    try:
        reader.delete_feed(urllib.parse.unquote(feed_url))
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail="Feed not found") from e

    return RedirectResponse(url="/", status_code=303)


@app.get("/update", response_class=HTMLResponse)
async def update_feed(request: Request, feed_url: str):
    """Update a feed.

    Args:
        request: The request object.
        feed_url: The feed URL to update.

    Raises:
        HTTPException: If the feed is not found.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    try:
        reader.update_feed(urllib.parse.unquote(feed_url))
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail="Feed not found") from e

    logger.info("Manually updated feed: %s", feed_url)
    return RedirectResponse(url="/feed?feed_url=" + urllib.parse.quote(feed_url), status_code=303)


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, query: str):
    """Get entries matching a full-text search query.

    Args:
        query: The query to search for.
        request: The request object.

    Returns:
        HTMLResponse: The search page.
    """
    reader.update_search()

    context = {
        "request": request,
        "search_html": create_html_for_search_results(query),
        "query": query,
        "search_amount": reader.search_entry_counts(query),
    }
    return templates.TemplateResponse(request=request, name="search.html", context=context)


@app.get("/post_entry", response_class=HTMLResponse)
async def post_entry(entry_id: str):
    """Send single entry to Discord.

    Args:
        entry_id: The entry to send.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    unquoted_entry_id: str = urllib.parse.unquote(entry_id)
    entry: Entry | None = next((entry for entry in reader.get_entries() if entry.id == unquoted_entry_id), None)
    if entry is None:
        return HTMLResponse(status_code=404, content=f"Entry '{entry_id}' not found.")

    if result := send_entry_to_discord(entry=entry):
        return result

    # Redirect to the feed page.
    clean_feed_url: str = entry.feed.url.strip()
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/modify_webhook", response_class=HTMLResponse)
def modify_webhook(old_hook: Annotated[str, Form()], new_hook: Annotated[str, Form()]):
    """Modify a webhook.

    Args:
        old_hook: The webhook to modify.
        new_hook: The new webhook.

    Raises:
        HTTPException: Webhook could not be modified.

    Returns:
        RedirectResponse: Redirect to the webhook page.
    """
    # Get current webhooks from the database if they exist otherwise use an empty list.
    webhooks = list(reader.get_tag((), "webhooks", []))

    # Webhooks are stored as a list of dictionaries.
    # Example: [{"name": "webhook_name", "url": "webhook_url"}]
    webhooks = cast("list[dict[str, str]]", webhooks)

    for hook in webhooks:
        if hook["url"] in old_hook.strip():
            hook["url"] = new_hook.strip()

            # Check if it has been modified.
            if hook["url"] != new_hook.strip():
                raise HTTPException(status_code=500, detail="Webhook could not be modified")

            # Add our new list of webhooks to the database.
            reader.set_tag((), "webhooks", webhooks)  # pyright: ignore[reportArgumentType]

            # Loop through all feeds and update the webhook if it
            # matches the old one.
            feeds: Iterable[Feed] = reader.get_feeds()
            for feed in feeds:
                try:
                    webhook = reader.get_tag(feed, "webhook")
                except TagNotFoundError:
                    continue

                if webhook == old_hook.strip():
                    reader.set_tag(feed.url, "webhook", new_hook.strip())  # pyright: ignore[reportArgumentType]

    # Redirect to the webhook page.
    return RedirectResponse(url="/webhooks", status_code=303)


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
        return url.split("v=")[1].split("&")[0]

    # Handle shortened YouTube URLs (youtu.be/VIDEO_ID)
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]

    return None


if __name__ == "__main__":
    sentry_sdk.init(
        dsn="https://6e77a0d7acb9c7ea22e85a375e0ff1f4@o4505228040339456.ingest.us.sentry.io/4508792887967744",
        send_default_pii=True,
        traces_sample_rate=1.0,
        _experiments={"continuous_profiling_auto_start": True},
    )

    uvicorn.run(
        "main:app",
        log_level="info",
        host="0.0.0.0",  # noqa: S104
        port=5000,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
