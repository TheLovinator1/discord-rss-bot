from __future__ import annotations

import concurrent.futures
import io
import json
import logging
import logging.config
import re
import tempfile
import typing
import urllib.parse
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from functools import lru_cache
from html import escape
from html import unescape
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Annotated
from typing import TypedDict
from typing import cast

import httpx2
import sentry_sdk
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends
from fastapi import FastAPI
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import Request
from fastapi import UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from httpx2 import HTTPError
from httpx2 import Response
from markdownify import markdownify
from reader import Entry
from reader import EntryNotFoundError
from reader import Feed
from reader import FeedExistsError
from reader import FeedImportError
from reader import FeedNotFoundError
from reader import Reader
from reader import ReaderError
from reader import TagNotFoundError
from reader import opml
from starlette.responses import RedirectResponse
from starlette.responses import Response as StarletteResponse

from discord_rss_bot.custom_filters import entry_is_blacklisted
from discord_rss_bot.custom_filters import entry_is_whitelisted
from discord_rss_bot.custom_message import CustomEmbed
from discord_rss_bot.custom_message import get_custom_message
from discord_rss_bot.custom_message import get_embed
from discord_rss_bot.custom_message import get_first_image
from discord_rss_bot.custom_message import get_message_avatar_url
from discord_rss_bot.custom_message import get_message_username
from discord_rss_bot.custom_message import replace_tags_in_text_message
from discord_rss_bot.custom_message import save_embed
from discord_rss_bot.feeds import FeedUpdateError
from discord_rss_bot.feeds import JsonValue
from discord_rss_bot.feeds import SentWebhookRecord
from discord_rss_bot.feeds import coerce_media_gallery_image_limit
from discord_rss_bot.feeds import coerce_webhook_text_length_limit
from discord_rss_bot.feeds import create_feed
from discord_rss_bot.feeds import extract_domain
from discord_rss_bot.feeds import feed_saves_sent_webhooks
from discord_rss_bot.feeds import get_feed_delivery_mode
from discord_rss_bot.feeds import get_feed_media_gallery_image_limit
from discord_rss_bot.feeds import get_feed_webhook_text_length_limit
from discord_rss_bot.feeds import get_screenshot_layout
from discord_rss_bot.feeds import get_sent_webhook_records
from discord_rss_bot.feeds import is_chromium_installed
from discord_rss_bot.feeds import is_steam_feed_url
from discord_rss_bot.feeds import send_entry_to_discord
from discord_rss_bot.feeds import send_to_discord
from discord_rss_bot.feeds import update_feed_and_collect_modified_entries
from discord_rss_bot.feeds import update_sent_webhooks_for_modified_entries
from discord_rss_bot.filter.evaluator import FILTER_FIELDS
from discord_rss_bot.filter.evaluator import EntryFilterDecision
from discord_rss_bot.filter.evaluator import FilterMatch
from discord_rss_bot.filter.evaluator import coerce_filter_values
from discord_rss_bot.filter.evaluator import evaluate_entry_filters
from discord_rss_bot.filter.evaluator import get_entry_decision_key
from discord_rss_bot.filter.evaluator import get_entry_fields
from discord_rss_bot.filter.evaluator import get_filter_values_from_reader
from discord_rss_bot.filter.evaluator import has_filter_values
from discord_rss_bot.git_backup import commit_state_change
from discord_rss_bot.git_backup import get_backup_path
from discord_rss_bot.is_url_valid import is_url_valid
from discord_rss_bot.search import create_search_context
from discord_rss_bot.settings import data_dir
from discord_rss_bot.settings import default_custom_embed
from discord_rss_bot.settings import default_custom_message
from discord_rss_bot.settings import get_reader
from discord_rss_bot.settings import make_app_reader

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from collections.abc import Iterable

    from reader.types import JSONType


class PreviewFieldRow(TypedDict):
    label: str
    value_html: str
    badges: list[dict[str, str]]


class FilterPreviewRow(TypedDict):
    entry: Entry
    decision: EntryFilterDecision
    field_rows: list[PreviewFieldRow]
    published_label: str
    status_label: str
    status_class: str
    first_image: str


class FilterPreviewSummary(TypedDict):
    total: int
    sent: int
    skipped: int
    blacklist_matches: int
    whitelist_matches: int


class FilterPreviewContext(TypedDict):
    filter_name: str
    filter_label: str
    preview_rendered_count: int
    preview_rows: list[FilterPreviewRow]
    preview_limit: int
    preview_summary: FilterPreviewSummary
    preview_helper_text: str


class AutodiscoverLink(TypedDict):
    href: str
    type: str | None
    title: str | None


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] [%(levelname)s] %(name)s: %(message)s",  # ruff:ignore[line-too-long]
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


def has_webhooks() -> bool:
    """Return whether at least one global webhook is configured."""
    reader: Reader = get_reader()
    webhooks = list(reader.get_tag((), "webhooks", []))
    return bool(webhooks)


# Time constants for relative time formatting
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400
FILTER_PREVIEW_LIMIT = 50
PREVIEW_FIELD_LABELS: dict[str, str] = {
    "title": "Title",
    "author": "Author",
    "summary": "Description",
    "content": "Content",
}
PREVIEW_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
PREVIEW_WHITESPACE_PATTERN = re.compile(r"\s+")


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
        max_instances=1,
        next_run_time=datetime.now(tz=UTC),
    )
    scheduler.start()
    logger.info("Scheduler started.")

    try:
        yield
    finally:
        reader.close()
        scheduler.shutdown(wait=True)


app: FastAPI = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="discord_rss_bot/static"), name="static")
templates: Jinja2Templates = Jinja2Templates(directory="discord_rss_bot/templates")


# Add the filters to the Jinja2 environment so they can be used in html templates.
templates.env.filters["encode_url"] = lambda url: urllib.parse.quote(str(url)) if url else ""
templates.env.filters["discord_markdown"] = markdownify  # pyright: ignore[reportArgumentType]
templates.env.filters["relative_time"] = relative_time
templates.env.globals["get_backup_path"] = get_backup_path  # pyright: ignore[reportArgumentType]
templates.env.globals["has_webhooks"] = has_webhooks  # pyright: ignore[reportArgumentType]


@app.get("/export_opml")
def export_opml(
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> StarletteResponse:
    """Export all feeds as an OPML subscription list.

    Args:
        reader: The Reader instance.

    Returns:
        StarletteResponse: The OPML file for download.
    """
    export = reader.export_feeds()
    return StarletteResponse(
        content=export.content,
        status_code=200,
        headers={
            "Content-Type": "application/xml",
            "Content-Disposition": f'attachment; filename="{export.filename}"',
        },
    )


@app.post("/import_opml", response_model=None)
async def import_opml(
    request: Request,
    file: Annotated[UploadFile, File()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
):
    """Upload an OPML file and show a preview of feeds to import.

    Args:
        request: The request object.
        file: The uploaded OPML file.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The OPML import preview page.
        RedirectResponse: Redirect to settings on error.
    """
    if not file.filename or not file.filename.lower().endswith(".opml"):
        return RedirectResponse(
            url=f"/settings?message={urllib.parse.quote('Please upload a file with a .opml extension.')}",
            status_code=303,
        )

    try:
        content: bytes = await file.read()
        feeds_to_import = opml.parse(io.BytesIO(content))
    except FeedImportError as e:
        return RedirectResponse(
            url=f"/settings?message={urllib.parse.quote(f'Failed to parse OPML file: {e}')}",
            status_code=303,
        )

    # Check which feeds already exist
    existing_urls: set[str] = {feed.url for feed in reader.get_feeds()}
    feed_list = [
        {
            "url": feed.url,
            "title": feed.title or feed.url,
            "already_exists": feed.url in existing_urls,
        }
        for feed in feeds_to_import
    ]

    context = {
        "request": request,
        "feeds": feed_list,
        "total": len(feed_list),
        "new_count": sum(1 for f in feed_list if not f["already_exists"]),
        "existing_count": sum(1 for f in feed_list if f["already_exists"]),
        "webhooks": reader.get_tag((), "webhooks", []),
    }
    return templates.TemplateResponse(request=request, name="import_opml_preview.html", context=context)


@app.post("/import_opml_confirm")
async def import_opml_confirm(
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    feed_urls: Annotated[list[str] | None, Form()] = None,
    webhook_name: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Import the selected feeds from the OPML preview.

    Args:
        request: The request object.
        reader: The Reader instance.
        feed_urls: The selected feed URLs to import.
        webhook_name: Optional webhook name to attach imported feeds to.

    Returns:
        RedirectResponse: Redirect to the settings page with a status message.
    """
    if feed_urls is None:
        feed_urls = []
    if not feed_urls:
        return RedirectResponse(
            url="/settings?message=No%20feeds%20were%20selected%20for%20import.",
            status_code=303,
        )

    webhook_url = _resolve_webhook_url(reader, webhook_name)

    imported, updated_webhook, errors = _import_opml_feeds(reader, feed_urls, webhook_url)
    message = _summarize_opml_import(imported, updated_webhook, errors)

    logger.info("OPML import complete: %s", message)
    commit_state_change(reader, f"OPML import: {imported} feeds")

    return RedirectResponse(url=f"/settings?message={urllib.parse.quote(message)}", status_code=303)


def _resolve_webhook_url(reader: Reader, webhook_name: str | None) -> str:
    """Resolve a webhook name to its URL from reader storage.

    Args:
        reader: The Reader instance.
        webhook_name: The webhook name to look up.

    Returns:
        The webhook URL, or empty string if not found or no name given.
    """
    if not webhook_name:
        return ""
    hooks = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))
    for hook in hooks:
        if hook.get("name") == webhook_name.strip():
            return hook.get("url", "").strip()
    return ""


def _import_opml_feeds(
    reader: Reader,
    feed_urls: list[str],
    webhook_url: str,
) -> tuple[int, int, list[str]]:
    """Add feeds from an OPML import, optionally setting webhooks.

    Args:
        reader: The Reader instance.
        feed_urls: The feed URLs to add.
        webhook_url: Webhook URL to attach, or empty string.

    Returns:
        A tuple of (imported_count, updated_webhook_count, error_messages).
    """
    imported: int = 0
    updated_webhook: int = 0
    errors: list[str] = []

    for feed_url in feed_urls:
        try:
            reader.add_feed(feed_url)
            if webhook_url:
                reader.set_tag(feed_url, "webhook", webhook_url)  # pyright: ignore[reportArgumentType]
            imported += 1
        except FeedExistsError:
            if webhook_url:
                reader.set_tag(feed_url, "webhook", webhook_url)  # pyright: ignore[reportArgumentType]
                updated_webhook += 1
        except Exception as e:
            errors.append(f"{feed_url}: {e}")
            logger.exception("Failed to import feed: %s", feed_url)

    return imported, updated_webhook, errors


def _summarize_opml_import(imported: int, updated_webhook: int, errors: list[str]) -> str:
    """Build a human-readable summary of an OPML import result.

    Args:
        imported: Number of newly imported feeds.
        updated_webhook: Number of existing feeds whose webhook was updated.
        errors: List of error strings.

    Returns:
        A summary string.
    """
    parts: list[str] = []
    if imported:
        parts.append(f"Successfully imported {imported} feed{'s' if imported != 1 else ''}")
    if updated_webhook:
        parts.append(f"Updated webhook for {updated_webhook} existing feed{'s' if updated_webhook != 1 else ''}")
    if errors:
        parts.append(f"{len(errors)} error{'s' if len(errors) != 1 else ''}")
    return ". ".join(parts) + "."


def get_global_delivery_mode(reader: Reader) -> str:
    """Return the normalized default delivery mode for new feeds.

    Args:
        reader: The Reader instance.

    Returns:
        The configured delivery mode, falling back to embed.
    """
    global_delivery_mode: str = str(reader.get_tag((), "delivery_mode", "embed")).strip().lower()
    return global_delivery_mode if global_delivery_mode in {"embed", "text"} else "embed"


def get_autodiscover_links(
    reader: Reader,
    feed_url: str,
    stored_links: object | None = None,
) -> list[AutodiscoverLink]:
    """Return valid autodiscovered links stored for a failed feed update.

    Args:
        reader: The Reader instance.
        feed_url: The URL that failed to parse as a feed.
        stored_links: Optional advertised links preserved before deleting an invalid feed.

    Returns:
        Valid discovered feed link dictionaries.
    """
    if stored_links is None:
        try:
            stored_links = reader.get_tag(feed_url, ".reader.autodiscover", [])
        except ReaderError:
            return []

    if not isinstance(stored_links, list):
        return []

    links: list[AutodiscoverLink] = []
    for stored_link in stored_links:
        if not isinstance(stored_link, dict):
            continue

        href = stored_link.get("href")
        if not isinstance(href, str) or not href:
            continue

        link_type = stored_link.get("type")
        title = stored_link.get("title")
        links.append({
            "href": href,
            "type": link_type if isinstance(link_type, str) else None,
            "title": title if isinstance(title, str) else None,
        })

    return links


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

    clean_webhook_url: str = webhook_url.strip()
    if not is_url_valid(clean_webhook_url):
        raise HTTPException(status_code=400, detail="Invalid webhook URL")

    # Only add the webhook if it doesn't already exist.
    stripped_webhook_name = webhook_name.strip()
    if all(webhook["name"] != stripped_webhook_name for webhook in webhooks):
        # Add the new webhook to the list of webhooks.
        webhooks.append({"name": webhook_name.strip(), "url": clean_webhook_url})

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


@app.post("/add", response_model=None)
async def post_create_feed(
    request: Request,
    feed_url: Annotated[str, Form()],
    webhook_dropdown: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse | HTMLResponse:
    """Add a feed to the database.

    Args:
        request: The request object.
        feed_url: The feed to add.
        webhook_dropdown: The webhook to use.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.

    Raises:
        FeedUpdateError: If updating the feed fails without discovered feed links.
    """
    clean_feed_url: str = feed_url.strip()
    try:
        create_feed(reader, feed_url, webhook_dropdown)
    except FeedUpdateError as exception:
        autodiscover_links = get_autodiscover_links(reader, clean_feed_url, exception.autodiscover_links)
        if not autodiscover_links:
            raise

        context = {
            "request": request,
            "webhooks": reader.get_tag((), "webhooks", []),
            "global_delivery_mode": get_global_delivery_mode(reader),
            "feed_url": clean_feed_url,
            "selected_webhook": webhook_dropdown,
            "messages": exception.detail,
            "autodiscover_links": autodiscover_links,
        }
        return templates.TemplateResponse(
            request=request,
            name="add.html",
            context=context,
            status_code=exception.status_code,
        )

    commit_state_change(reader, f"Add feed {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/attach_feed_webhook")
async def post_attach_feed_webhook(
    feed_url: Annotated[str, Form()],
    webhook_dropdown: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    redirect_to: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Attach an existing feed to one of the configured webhooks.

    Args:
        feed_url: The feed URL to update.
        webhook_dropdown: The webhook name selected from the dropdown.
        reader: The Reader instance.
        redirect_to: Optional redirect URL after update.

    Returns:
        RedirectResponse: Redirect to index or feed page.

    Raises:
        HTTPException: If feed or webhook cannot be found.
    """
    clean_feed_url: str = urllib.parse.unquote(feed_url.strip())
    selected_webhook_name: str = webhook_dropdown.strip()

    try:
        reader.get_feed(clean_feed_url)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail="Feed not found") from e

    webhook_url: str = ""
    hooks = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))
    for hook in hooks:
        if hook.get("name") == selected_webhook_name:
            webhook_url = hook.get("url", "").strip()
            break

    if not webhook_url:
        raise HTTPException(status_code=404, detail="Webhook not found")

    reader.set_tag(clean_feed_url, "webhook", webhook_url)  # pyright: ignore[reportArgumentType]
    commit_state_change(reader, f"Attach feed {clean_feed_url} to webhook {selected_webhook_name}")

    redirect_url: str = redirect_to.strip() or f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}"
    return RedirectResponse(url=redirect_url, status_code=303)


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
    context = {
        "request": request,
        "feed": feed,
        **build_filter_form_context("whitelist", get_filter_values_from_reader(reader, feed, "whitelist")),
        **build_filter_preview_context(reader, feed, "whitelist"),
    }
    return templates.TemplateResponse(request=request, name="whitelist.html", context=context)


@app.get("/whitelist_preview", response_class=HTMLResponse)
async def get_whitelist_preview(
    feed_url: str,
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    whitelist_title: str = "",
    whitelist_summary: str = "",
    whitelist_content: str = "",
    whitelist_author: str = "",
    regex_whitelist_title: str = "",
    regex_whitelist_summary: str = "",
    regex_whitelist_content: str = "",
    regex_whitelist_author: str = "",
) -> HTMLResponse:
    """Render the whitelist preview fragment for HTMX updates.

    Args:
        feed_url: Feed URL whose entries should be previewed.
        request: The request object.
        reader: The Reader instance.
        whitelist_title: Word-based title whitelist.
        whitelist_summary: Word-based summary whitelist.
        whitelist_content: Word-based content whitelist.
        whitelist_author: Word-based author whitelist.
        regex_whitelist_title: Regex title whitelist.
        regex_whitelist_summary: Regex summary whitelist.
        regex_whitelist_content: Regex content whitelist.
        regex_whitelist_author: Regex author whitelist.

    Returns:
        HTMLResponse: Rendered filter preview fragment.
    """
    clean_feed_url: str = urllib.parse.unquote(feed_url.strip())
    feed: Feed = reader.get_feed(clean_feed_url)

    form_values: dict[str, str] = {
        "whitelist_title": whitelist_title,
        "whitelist_summary": whitelist_summary,
        "whitelist_content": whitelist_content,
        "whitelist_author": whitelist_author,
        "regex_whitelist_title": regex_whitelist_title,
        "regex_whitelist_summary": regex_whitelist_summary,
        "regex_whitelist_content": regex_whitelist_content,
        "regex_whitelist_author": regex_whitelist_author,
    }

    return templates.TemplateResponse(
        request=request,
        name="_filter_preview.html",
        context={
            "request": request,
            "feed": feed,
            **build_filter_preview_context(reader, feed, "whitelist", form_values=form_values),
        },
    )


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

    context = {
        "request": request,
        "feed": feed,
        **build_filter_form_context("blacklist", get_filter_values_from_reader(reader, feed, "blacklist")),
        **build_filter_preview_context(reader, feed, "blacklist"),
    }
    return templates.TemplateResponse(request=request, name="blacklist.html", context=context)


@app.get("/blacklist_preview", response_class=HTMLResponse)
async def get_blacklist_preview(
    feed_url: str,
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    blacklist_title: str = "",
    blacklist_summary: str = "",
    blacklist_content: str = "",
    blacklist_author: str = "",
    regex_blacklist_title: str = "",
    regex_blacklist_summary: str = "",
    regex_blacklist_content: str = "",
    regex_blacklist_author: str = "",
) -> HTMLResponse:
    """Render the blacklist preview fragment for HTMX updates.

    Args:
        feed_url: Feed URL whose entries should be previewed.
        request: The request object.
        reader: The Reader instance.
        blacklist_title: Word-based title blacklist.
        blacklist_summary: Word-based summary blacklist.
        blacklist_content: Word-based content blacklist.
        blacklist_author: Word-based author blacklist.
        regex_blacklist_title: Regex title blacklist.
        regex_blacklist_summary: Regex summary blacklist.
        regex_blacklist_content: Regex content blacklist.
        regex_blacklist_author: Regex author blacklist.

    Returns:
        HTMLResponse: Rendered filter preview fragment.
    """
    clean_feed_url: str = urllib.parse.unquote(feed_url.strip())
    feed: Feed = reader.get_feed(clean_feed_url)
    form_values: dict[str, str] = {
        "blacklist_title": blacklist_title,
        "blacklist_summary": blacklist_summary,
        "blacklist_content": blacklist_content,
        "blacklist_author": blacklist_author,
        "regex_blacklist_title": regex_blacklist_title,
        "regex_blacklist_summary": regex_blacklist_summary,
        "regex_blacklist_content": regex_blacklist_content,
        "regex_blacklist_author": regex_blacklist_author,
    }

    return templates.TemplateResponse(
        request=request,
        name="_filter_preview.html",
        context={
            "request": request,
            "feed": feed,
            **build_filter_preview_context(reader, feed, "blacklist", form_values=form_values),
        },
    )


def build_filter_form_context(filter_name: str, values: dict[str, str]) -> dict[str, str]:
    """Return template context keys for a filter form.

    Args:
        filter_name: Either blacklist or whitelist.
        values: Normalized filter values.

    Returns:
        dict[str, str]: Template keys matching current form field names.
    """
    context: dict[str, str] = {}
    for field_name in FILTER_FIELDS:
        context[f"{filter_name}_{field_name}"] = values[field_name]
        context[f"regex_{filter_name}_{field_name}"] = values[f"regex_{field_name}"]
    return context


def build_filter_preview_context(
    reader: Reader,
    feed: Feed,
    filter_name: str,
    form_values: dict[str, str] | None = None,
) -> FilterPreviewContext:
    """Build preview data for the blacklist and whitelist pages.

    Args:
        reader: The Reader instance.
        feed: The feed being previewed.
        filter_name: Either blacklist or whitelist.
        form_values: Optional unsaved values from the current form.

    Returns:
        FilterPreviewContext: Preview context for template rendering.
    """
    saved_blacklist_values: dict[str, str] = get_filter_values_from_reader(reader, feed, "blacklist")
    saved_whitelist_values: dict[str, str] = get_filter_values_from_reader(reader, feed, "whitelist")

    preview_blacklist_values: dict[str, str] = saved_blacklist_values
    preview_whitelist_values: dict[str, str] = saved_whitelist_values
    helper_text: str = "Saved whitelist rules still apply while previewing blacklist changes."

    if filter_name == "blacklist":
        if form_values is not None:
            preview_blacklist_values = coerce_filter_values("blacklist", form_values)
    else:
        if form_values is not None:
            preview_whitelist_values = coerce_filter_values("whitelist", form_values)
        helper_text = "Saved blacklist rules still apply while previewing whitelist changes."

    preview_entries: list[Entry] = list(reader.get_entries(feed=feed, limit=FILTER_PREVIEW_LIMIT))
    preview_rows: list[FilterPreviewRow] = []
    preview_decisions: dict[str, EntryFilterDecision] = {}
    sent_count = 0
    skipped_count = 0
    blacklist_match_count = 0
    whitelist_match_count = 0

    for entry in preview_entries:
        decision: EntryFilterDecision = evaluate_entry_filters(
            entry,
            blacklist_values=preview_blacklist_values,
            whitelist_values=preview_whitelist_values,
        )
        preview_decisions[get_entry_decision_key(entry)] = decision

        if decision.should_send:
            sent_count += 1
        else:
            skipped_count += 1

        if decision.blacklist_match:
            blacklist_match_count += 1
        if decision.whitelist_match:
            whitelist_match_count += 1

        published_label: str = "Unknown date"
        if entry.published:
            published_label = entry.published.strftime("%Y-%m-%d %H:%M:%S")

        preview_rows.append(
            {
                "entry": entry,
                "decision": decision,
                "field_rows": build_preview_field_rows(entry, decision),
                "published_label": published_label,
                "status_label": "Sent" if decision.should_send else "Skipped",
                "status_class": "success" if decision.should_send else "danger",
                "first_image": get_first_image(summary=entry.summary, content=entry.content),
            },
        )

    return {
        "filter_name": filter_name,
        "filter_label": filter_name.title(),
        "preview_rendered_count": sent_count,
        "preview_rows": preview_rows,
        "preview_limit": FILTER_PREVIEW_LIMIT,
        "preview_summary": {
            "total": len(preview_entries),
            "sent": sent_count,
            "skipped": skipped_count,
            "blacklist_matches": blacklist_match_count,
            "whitelist_matches": whitelist_match_count,
        },
        "preview_helper_text": helper_text,
    }


def build_preview_field_rows(entry: Entry, decision: EntryFilterDecision) -> list[PreviewFieldRow]:
    """Build labeled preview fields for the filter UI.

    Args:
        entry: Entry whose values should be shown.
        decision: The final decision for the entry.

    Returns:
        list[PreviewFieldRow]: Labeled field rows for the preview template.
    """
    entry_fields: dict[str, str] = get_entry_fields(entry)
    field_rows: list[PreviewFieldRow] = []

    for field_name in ("title", "author", "summary", "content"):
        badges: list[dict[str, str]] = []
        matches: list[tuple[FilterMatch, str]] = []
        if decision.blacklist_match and decision.blacklist_match.field_name == field_name:
            badges.append({"label": "Blacklist match", "class": "danger"})
            matches.append((decision.blacklist_match, "danger"))
        if decision.whitelist_match and decision.whitelist_match.field_name == field_name:
            badges.append({"label": "Whitelist match", "class": "success"})
            matches.append((decision.whitelist_match, "success"))

        field_rows.append(
            {
                "label": PREVIEW_FIELD_LABELS[field_name],
                "value_html": format_preview_field_value(entry_fields[field_name], matches),
                "badges": badges,
            },
        )

    return field_rows


def format_preview_field_value(
    value: str,
    matches: list[tuple[FilterMatch, str]],
    max_length: int = 280,
) -> str:
    """Convert entry field content into readable preview text with highlight markup.

    Args:
        value: Raw field value from the entry.
        matches: Matching filters for this field and their display classes.
        max_length: Max number of characters to display.

    Returns:
        str: Normalized preview HTML.
    """
    normalized_value: str = normalize_preview_field_value(value)
    if not normalized_value:
        return "No value"

    highlighted_span, highlight_class = get_preview_highlight_span(normalized_value, matches)
    clipped_value, clipped_span = clip_preview_value(normalized_value, highlighted_span, max_length)

    if clipped_span is None or highlight_class is None:
        return escape(clipped_value)

    start, end = clipped_span
    return "".join(
        [
            escape(clipped_value[:start]),
            f'<mark class="filter-preview__match filter-preview__match--{highlight_class}">',
            escape(clipped_value[start:end]),
            "</mark>",
            escape(clipped_value[end:]),
        ],
    )


def normalize_preview_field_value(value: str) -> str:
    """Convert entry field content into readable plain text.

    Args:
        value: Raw field value.

    Returns:
        str: Plain-text preview value.
    """
    if not value:
        return ""

    plain_text: str = PREVIEW_HTML_TAG_PATTERN.sub(" ", value)
    return PREVIEW_WHITESPACE_PATTERN.sub(" ", unescape(plain_text)).strip()


def get_preview_highlight_span(
    value: str,
    matches: list[tuple[FilterMatch, str]],
) -> tuple[tuple[int, int] | None, str | None]:
    """Return the earliest highlight span for the preview field.

    Args:
        value: Normalized field value.
        matches: Matching filters and associated preview classes.

    Returns:
        tuple[tuple[int, int] | None, str | None]: Span and highlight class.
    """
    first_span: tuple[int, int] | None = None
    first_class: str | None = None

    for match, highlight_class in matches:
        span = get_filter_match_span(value, match)
        if span is None:
            continue
        if first_span is None or span[0] < first_span[0]:
            first_span = span
            first_class = highlight_class

    return first_span, first_class


def get_filter_match_span(value: str, match: FilterMatch) -> tuple[int, int] | None:
    """Return the matched substring span for a preview field.

    Args:
        value: Normalized preview value.
        match: Matching filter metadata.

    Returns:
        tuple[int, int] | None: The first matching span if found.
    """
    if match.match_type == "regex":
        return get_regex_match_span(value, match.pattern)
    return get_text_match_span(value, match.pattern)


def get_text_match_span(value: str, pattern: str) -> tuple[int, int] | None:
    """Return the earliest case-insensitive substring span for comma-separated text terms."""
    earliest_span: tuple[int, int] | None = None
    for term in [part.strip() for part in pattern.split(",") if part.strip()]:
        compiled_pattern = re.compile(re.escape(term), re.IGNORECASE)
        match = compiled_pattern.search(value)
        if match and (earliest_span is None or match.start() < earliest_span[0]):
            earliest_span = match.span()
    return earliest_span


def get_regex_match_span(value: str, pattern: str) -> tuple[int, int] | None:
    """Return the earliest regex match span for newline/comma-separated patterns."""
    earliest_span: tuple[int, int] | None = None
    for pattern_str in split_regex_patterns(pattern):
        try:
            compiled_pattern = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            continue

        match = compiled_pattern.search(value)
        if match and match.start() != match.end():
            current_span = match.span()
            if earliest_span is None or current_span[0] < earliest_span[0]:
                earliest_span = current_span
    return earliest_span


def split_regex_patterns(pattern: str) -> list[str]:
    """Split regex filter text using the same newline/comma semantics as the matcher.

    Args:
        pattern: The raw regex pattern string.

    Returns:
        list[str]: A list of individual regex patterns.
    """
    regex_patterns: list[str] = []
    for line in pattern.split("\n"):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        if "," in stripped_line:
            regex_patterns.extend([part.strip() for part in stripped_line.split(",") if part.strip()])
        else:
            regex_patterns.append(stripped_line)
    return regex_patterns


def clip_preview_value(
    value: str,
    highlight_span: tuple[int, int] | None,
    max_length: int,
) -> tuple[str, tuple[int, int] | None]:
    """Clip a preview value while keeping the highlighted match visible when possible.

    Args:
        value: The normalized preview value.
        highlight_span: The span of the highlighted match within the value.
        max_length: The maximum length of the clipped value.

    Returns:
        tuple[str, tuple[int, int] | None]: The clipped preview value and adjusted highlight
    """
    if len(value) <= max_length:
        return value, highlight_span

    if highlight_span is None:
        return f"{value[: max_length - 1].rstrip()}…", None

    match_start, match_end = highlight_span
    window_start = max(0, match_start - (max_length // 3))
    window_end = min(len(value), window_start + max_length)
    if match_end > window_end:
        window_end = min(len(value), match_end + (max_length // 3))
        window_start = max(0, window_end - max_length)

    clipped_value = value[window_start:window_end]
    clipped_span = (match_start - window_start, match_end - window_start)

    if window_start > 0:
        clipped_value = f"…{clipped_value}"
        clipped_span = (clipped_span[0] + 1, clipped_span[1] + 1)
    if window_end < len(value):
        clipped_value = f"{clipped_value}…"

    return clipped_value, clipped_span


@app.post("/custom")
async def post_set_custom(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    custom_message: Annotated[str, Form()] = "",
    message_username: Annotated[str, Form()] = "",
    message_avatar_url: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Set the custom message, this is used when sending the message.

    Args:
        custom_message: The custom message.
        message_username: Optional Discord webhook username override for this feed.
        message_avatar_url: Optional Discord webhook avatar URL override for this feed.
        feed_url: The feed we should set the custom message for.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    our_custom_message: JSONType | str = custom_message.strip()
    our_custom_message = typing.cast("JSONType", our_custom_message)

    # Store raw values; blank/invalid values are ignored when building the Discord payload.
    reader.set_tag(feed_url, "message_username", typing.cast("JSONType", message_username.strip()))
    reader.set_tag(feed_url, "message_avatar_url", typing.cast("JSONType", message_avatar_url.strip()))

    clean_feed_url: str = feed_url.strip()
    feed: Feed = reader.get_feed(urllib.parse.unquote(clean_feed_url))

    stored_custom_message: str = get_custom_message(reader, feed)
    if our_custom_message != stored_custom_message:
        reader.set_tag(feed_url, "custom_message", our_custom_message)

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
        "message_username": get_message_username(reader, feed),
        "message_avatar_url": get_message_avatar_url(reader, feed),
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

    context: dict[str, Request | Feed | str | Entry | CustomEmbed | bool] = {
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
        "show_steam_game_icon_in_thumbnail": embed.show_steam_game_icon_in_thumbnail,
    }
    if custom_embed := get_embed(reader, feed):
        context["custom_embed"] = custom_embed

    for entry in reader.get_entries(feed=feed, limit=1):
        # Append to context.
        context["entry"] = entry
    return templates.TemplateResponse(request=request, name="embed.html", context=context)


@app.post("/embed", response_class=HTMLResponse)
async def post_embed(  # ruff:ignore[complex-structure]
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
    *,
    show_steam_game_icon_in_thumbnail: Annotated[bool, Form()] = False,
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
        show_steam_game_icon_in_thumbnail: Whether to use the Steam game icon as the embed thumbnail.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the embed page.
    """
    clean_feed_url: str = feed_url.strip()
    feed: Feed = reader.get_feed(urllib.parse.unquote(clean_feed_url))

    custom_embed: CustomEmbed = get_embed(reader, feed)

    if title != custom_embed.title:
        custom_embed.title = title
    if description != custom_embed.description:
        custom_embed.description = description
    if color != custom_embed.color:
        custom_embed.color = color
    if image_url != custom_embed.image_url:
        custom_embed.image_url = image_url
    if thumbnail_url != custom_embed.thumbnail_url:
        custom_embed.thumbnail_url = thumbnail_url
    if author_name != custom_embed.author_name:
        custom_embed.author_name = author_name
    if author_url != custom_embed.author_url:
        custom_embed.author_url = author_url
    if author_icon_url != custom_embed.author_icon_url:
        custom_embed.author_icon_url = author_icon_url
    if footer_text != custom_embed.footer_text:
        custom_embed.footer_text = footer_text
    if footer_icon_url != custom_embed.footer_icon_url:
        custom_embed.footer_icon_url = footer_icon_url
    if show_steam_game_icon_in_thumbnail != custom_embed.show_steam_game_icon_in_thumbnail:
        custom_embed.show_steam_game_icon_in_thumbnail = show_steam_game_icon_in_thumbnail

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
    reader.set_tag(clean_feed_url, "delivery_mode", "embed")  # pyright: ignore[reportArgumentType]
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
    reader.set_tag(clean_feed_url, "delivery_mode", "text")  # pyright: ignore[reportArgumentType]
    reader.set_tag(clean_feed_url, "should_send_embed", False)  # pyright: ignore[reportArgumentType]
    commit_state_change(reader, f"Disable embed mode for {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/use_screenshot")
async def post_use_screenshot(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Use full-page screenshot mode instead of embed or text.

    Args:
        feed_url: The feed to change.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.set_tag(clean_feed_url, "delivery_mode", "screenshot")  # pyright: ignore[reportArgumentType]
    reader.set_tag(clean_feed_url, "screenshot_layout", "desktop")  # pyright: ignore[reportArgumentType]
    reader.set_tag(clean_feed_url, "should_send_embed", False)  # pyright: ignore[reportArgumentType]
    commit_state_change(reader, f"Enable screenshot mode for {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/use_screenshot_mobile")
async def post_use_screenshot_mobile(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Use screenshot mode with mobile layout.

    Args:
        feed_url: The feed to change.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.set_tag(clean_feed_url, "delivery_mode", "screenshot")  # pyright: ignore[reportArgumentType]
    reader.set_tag(clean_feed_url, "screenshot_layout", "mobile")  # pyright: ignore[reportArgumentType]
    reader.set_tag(clean_feed_url, "should_send_embed", False)  # pyright: ignore[reportArgumentType]
    commit_state_change(reader, f"Enable screenshot mobile layout for {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/use_screenshot_desktop")
async def post_use_screenshot_desktop(
    feed_url: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Use screenshot mode with desktop layout.

    Args:
        feed_url: The feed to change.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.set_tag(clean_feed_url, "delivery_mode", "screenshot")  # pyright: ignore[reportArgumentType]
    reader.set_tag(clean_feed_url, "screenshot_layout", "desktop")  # pyright: ignore[reportArgumentType]
    reader.set_tag(clean_feed_url, "should_send_embed", False)  # pyright: ignore[reportArgumentType]
    commit_state_change(reader, f"Enable screenshot desktop layout for {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/set_feed_save_sent_webhooks")
async def post_set_feed_save_sent_webhooks(
    feed_url: Annotated[str, Form()],
    enabled: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Set whether a feed stores sent Discord webhook message records.

    Returns:
        RedirectResponse: Redirect to the specified feed page.

    Raises:
        HTTPException: If Feed does not exists.
    """
    clean_feed_url: str = feed_url.strip()
    should_save: bool = enabled.strip().lower() in {"1", "true", "yes", "on", "enabled"}

    try:
        reader.get_feed(clean_feed_url)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail="Feed not found") from e

    reader.set_tag(clean_feed_url, "save_sent_webhooks", should_save)  # pyright: ignore[reportArgumentType]
    action: str = "Enable" if should_save else "Disable"
    commit_state_change(reader, f"{action} sent webhook storage for {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/set_feed_media_gallery_image_limit")
async def post_set_feed_media_gallery_image_limit(
    feed_url: Annotated[str, Form()],
    image_limit: Annotated[int, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Set whether a feed sends one image or a full media gallery.

    Returns:
        RedirectResponse: Redirect to the feed page.

    Raises:
        HTTPException: If the feed does not exist.
    """
    clean_feed_url: str = feed_url.strip()
    clean_image_limit: int = coerce_media_gallery_image_limit(image_limit)
    clean_image_limit_json: JSONType = cast("JSONType", clean_image_limit)

    try:
        reader.get_feed(clean_feed_url)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail="Feed not found") from e

    reader.set_tag(
        clean_feed_url,
        "media_gallery_image_limit",
        clean_image_limit_json,
    )
    commit_state_change(reader, f"Set media gallery image limit to {clean_image_limit} for {clean_feed_url}")
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/set_feed_webhook_text_length_limit")
async def post_set_feed_webhook_text_length_limit(
    feed_url: Annotated[str, Form()],
    text_length_limit: Annotated[int, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Set the maximum webhook text length for a feed.

    Returns:
        RedirectResponse: Redirect to the feed page.

    Raises:
        HTTPException: If the feed does not exist.
    """
    clean_feed_url: str = feed_url.strip()
    clean_text_length_limit: int = coerce_webhook_text_length_limit(text_length_limit)
    clean_text_length_limit_json: JSONType = cast("JSONType", clean_text_length_limit)

    try:
        reader.get_feed(clean_feed_url)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail="Feed not found") from e

    reader.set_tag(
        clean_feed_url,
        "webhook_text_length_limit",
        clean_text_length_limit_json,
    )
    commit_state_change(reader, f"Set webhook text length limit to {clean_text_length_limit} for {clean_feed_url}")
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


@app.post("/set_global_screenshot_layout")
async def post_set_global_screenshot_layout(
    screenshot_layout: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Set the global default screenshot layout for newly added feeds.

    Args:
        screenshot_layout: The screenshot layout (`desktop` or `mobile`).
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the settings page.
    """
    clean_layout: str = screenshot_layout.strip().lower()
    if clean_layout not in {"desktop", "mobile"}:
        clean_layout = "desktop"

    reader.set_tag((), "screenshot_layout", clean_layout)  # pyright: ignore[reportArgumentType]
    commit_state_change(reader, f"Set global screenshot layout to {clean_layout}")
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/set_global_delivery_mode")
async def post_set_global_delivery_mode(
    delivery_mode: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Set the global default delivery mode for newly added feeds.

    Args:
        delivery_mode: The delivery mode (`embed` or `text`).
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the settings page.
    """
    clean_delivery_mode: str = delivery_mode.strip().lower()
    if clean_delivery_mode not in {"embed", "text"}:
        clean_delivery_mode = "embed"

    reader.set_tag((), "delivery_mode", clean_delivery_mode)  # pyright: ignore[reportArgumentType]
    commit_state_change(reader, f"Set global delivery mode to {clean_delivery_mode}")
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/set_global_webhook_text_length_limit")
async def post_set_global_webhook_text_length_limit(
    text_length_limit: Annotated[int, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> RedirectResponse:
    """Set the global default webhook text length limit for newly added feeds.

    Args:
        text_length_limit: The max webhook text length.
        reader: The Reader instance.

    Returns:
        RedirectResponse: Redirect to the settings page.
    """
    clean_text_length_limit: int = coerce_webhook_text_length_limit(text_length_limit)
    clean_text_length_limit_json: JSONType = cast("JSONType", clean_text_length_limit)

    reader.set_tag((), "webhook_text_length_limit", clean_text_length_limit_json)  # pyright: ignore[reportArgumentType]
    commit_state_change(reader, f"Set global webhook text length limit to {clean_text_length_limit}")
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
        "global_delivery_mode": get_global_delivery_mode(reader),
    }
    return templates.TemplateResponse(request=request, name="add.html", context=context)


@app.get("/feed", response_class=HTMLResponse)
async def get_feed(  # ruff:ignore[complex-structure, too-many-branches, too-many-locals, too-many-statements]
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

    webhooks: list[dict[str, str]] = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))
    current_webhook_url: str = str(reader.get_tag(feed.url, "webhook", "")).strip()
    current_webhook_name: str = ""
    for hook in webhooks:
        if hook.get("url", "").strip() == current_webhook_url:
            current_webhook_name = hook.get("name", "").strip()
            break

    has_blacklist_filters: bool = has_filter_values(get_filter_values_from_reader(reader, feed, "blacklist"))
    has_whitelist_filters: bool = has_filter_values(get_filter_values_from_reader(reader, feed, "whitelist"))

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
                "delivery_mode": "text",
                "screenshot_layout": "desktop",
                "last_entry": None,
                "messages": msg,
                "is_show_more_entries_button_visible": is_show_more_entries_button_visible,
                "total_entries": total_entries,
                "feed_interval": feed_interval,
                "global_interval": global_interval,
                "webhooks": webhooks,
                "current_webhook_url": current_webhook_url,
                "current_webhook_name": current_webhook_name,
                "has_blacklist_filters": has_blacklist_filters,
                "has_whitelist_filters": has_whitelist_filters,
                "media_gallery_image_limit": get_feed_media_gallery_image_limit(reader, feed),
                "max_media_gallery_items": 10,
                "webhook_text_length_limit": get_feed_webhook_text_length_limit(reader, feed),
                "max_webhook_text_length_limit": 4000,
                "save_sent_webhooks": feed_saves_sent_webhooks(reader, feed),
                "is_steam_feed": is_steam_feed_url(feed.url),
                "chromium_installed": is_chromium_installed(),
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

    delivery_mode: str = get_feed_delivery_mode(reader, feed)
    should_send_embed: bool = delivery_mode == "embed"
    screenshot_layout: str = get_screenshot_layout(reader, feed)

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
        "delivery_mode": delivery_mode,
        "screenshot_layout": screenshot_layout,
        "last_entry": last_entry,
        "is_show_more_entries_button_visible": is_show_more_entries_button_visible,
        "total_entries": total_entries,
        "feed_interval": feed_interval,
        "global_interval": global_interval,
        "webhooks": webhooks,
        "current_webhook_url": current_webhook_url,
        "current_webhook_name": current_webhook_name,
        "has_blacklist_filters": has_blacklist_filters,
        "has_whitelist_filters": has_whitelist_filters,
        "media_gallery_image_limit": get_feed_media_gallery_image_limit(reader, feed),
        "max_media_gallery_items": 10,
        "webhook_text_length_limit": get_feed_webhook_text_length_limit(reader, feed),
        "max_webhook_text_length_limit": 4000,
        "save_sent_webhooks": feed_saves_sent_webhooks(reader, feed),
        "is_steam_feed": is_steam_feed_url(feed.url),
        "chromium_installed": is_chromium_installed(),
    }
    return templates.TemplateResponse(request=request, name="feed.html", context=context)


def create_html_for_feed(  # ruff:ignore[complex-structure, too-many-locals]
    reader: Reader,
    entries: Iterable[Entry],
    current_feed_url: str = "",
    entry_decisions: dict[str, EntryFilterDecision] | None = None,
) -> str:
    """Create HTML for the search results.

    Args:
        reader: The Reader instance to use.
        entries: The entries to create HTML for.
        current_feed_url: The feed URL currently being viewed in /feed.
        entry_decisions: Optional preview decisions keyed by feed URL and entry id.

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

        decision: EntryFilterDecision | None = None
        if entry_decisions is not None:
            decision = entry_decisions.get(get_entry_decision_key(entry))

        is_blacklisted: bool = entry_is_blacklisted(entry, reader=reader)
        is_whitelisted: bool = entry_is_whitelisted(entry, reader=reader)
        if decision is not None:
            is_blacklisted = decision.blacklist_match is not None
            is_whitelisted = decision.whitelist_match is not None

        blacklisted: str = ""
        if is_blacklisted:
            blacklisted = "<span class='badge bg-danger'>Blacklisted</span>"

        whitelisted: str = ""
        if is_whitelisted:
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
{feed_link}{f"By {entry.authors_str} @" if entry.authors_str else ""}{published} - {to_discord_html}

{text}
{video_embed_html}
{image_html}
</div>
"""  # ruff:ignore[line-too-long]
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
    clean_hook_url: str = hook_url.strip()
    our_hook: WebhookInfo = WebhookInfo(custom_name=hook_name, url=clean_hook_url)

    # Keep /webhooks usable even if a malformed webhook URL was saved.
    if not clean_hook_url or not is_url_valid(clean_hook_url):
        logger.warning("Skipping webhook metadata fetch for invalid URL: %s", clean_hook_url)
        return our_hook

    try:
        response: Response = httpx2.get(clean_hook_url, timeout=10.0)
    except HTTPError as e:
        logger.warning("Failed to fetch webhook metadata for %s: %s", clean_hook_url, e)
        return our_hook

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
    message: str = "",
):
    """Settings page.

    Args:
        request: The request object.
        reader: The Reader instance.
        message: Optional message to display to the user.

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

    global_screenshot_layout: str = str(reader.get_tag((), "screenshot_layout", "desktop")).strip().lower()
    if global_screenshot_layout not in {"desktop", "mobile"}:
        global_screenshot_layout = "desktop"

    global_delivery_mode: str = str(reader.get_tag((), "delivery_mode", "embed")).strip().lower()
    if global_delivery_mode not in {"embed", "text"}:
        global_delivery_mode = "embed"

    global_webhook_text_length_limit: int = coerce_webhook_text_length_limit(
        reader.get_tag((), "webhook_text_length_limit", 4000),
    )

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
        "global_delivery_mode": global_delivery_mode,
        "global_screenshot_layout": global_screenshot_layout,
        "global_webhook_text_length_limit": global_webhook_text_length_limit,
        "max_webhook_text_length_limit": 4000,
        "feed_intervals": feed_intervals,
        "chromium_installed": is_chromium_installed(),
        "messages": message or None,
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


@app.get("/sent_webhooks", response_class=HTMLResponse)
async def get_sent_webhooks(
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    feed_url: str = "",
    webhook_url: str = "",
) -> HTMLResponse:
    """View sent Discord webhook messages saved for future edits.

    Returns:
        sent_webhooks.html HTML
    """
    clean_feed_url: str = urllib.parse.unquote(feed_url.strip())
    clean_webhook_url: str = urllib.parse.unquote(webhook_url.strip())

    records: list[SentWebhookRecord] = get_sent_webhook_records(reader)
    if clean_feed_url:
        records = [record for record in records if record.get("feed_url") == clean_feed_url]
    if clean_webhook_url:
        records = [record for record in records if record.get("webhook_url") == clean_webhook_url]

    records.sort(
        key=lambda record: str(record.get("last_updated_at") or record.get("last_sent_at") or ""),
        reverse=True,
    )

    webhooks: list[dict[str, str]] = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))
    webhook_names: dict[str, str] = {
        hook.get("url", ""): hook.get("name", "") for hook in webhooks if isinstance(hook, dict)
    }
    feed_titles: dict[str, str] = {feed.url: (feed.title or feed.url) for feed in reader.get_feeds()}

    context = {
        "request": request,
        "records": records,
        "total_records": len(records),
        "feed_url": clean_feed_url,
        "webhook_url": clean_webhook_url,
        "webhook_names": webhook_names,
        "feed_titles": feed_titles,
    }
    return templates.TemplateResponse(request=request, name="sent_webhooks.html", context=context)


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
        clean_feed_url: str = urllib.parse.unquote(feed_url)
        modified_entries: list[tuple[str, str]] = update_feed_and_collect_modified_entries(reader, clean_feed_url)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail="Feed not found") from e

    try:
        update_sent_webhooks_for_modified_entries(reader, modified_entries)
    except (AssertionError, ReaderError, HTTPError, OSError, ValueError):
        logger.exception("Failed to update saved Discord webhooks for manually updated feed: %s", feed_url)

    logger.info("Manually updated feed: %s", feed_url)
    return RedirectResponse(url="/feed?feed_url=" + urllib.parse.quote(feed_url), status_code=303)


@app.get("/export")
def export_database(
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> StarletteResponse:
    """Export the entire database as a compressed SQLite file.

    Args:
        reader: The Reader instance.

    Returns:
        StarletteResponse: The exported database file for download.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_path: Path = reader._storage.export(tmpdir, "discord-rss-bot-export")  # ruff:ignore[private-member-access]
        filename: str = export_path.name
        file_bytes: bytes = export_path.read_bytes()

    return StarletteResponse(
        content=file_bytes,
        status_code=200,
        headers={
            "Content-Type": "application/gzip",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


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
    backup_path: Path | None = get_backup_path()
    if backup_path is None:
        message: str = "Git backup is not configured. Set GIT_BACKUP_PATH environment variable to enable backups."
        logger.warning("Manual git backup attempted but GIT_BACKUP_PATH is not configured")
        return RedirectResponse(url=f"/?message={urllib.parse.quote(message)}", status_code=303)

    try:
        commit_state_change(reader, "Manual backup triggered from web UI")
        message: str = "Successfully created git backup!"
        logger.info("Manual git backup completed successfully")
    except Exception as e:
        message: str = f"Failed to create git backup: {e}"
        logger.exception("Manual git backup failed")

    return RedirectResponse(url=f"/?message={urllib.parse.quote(message)}", status_code=303)


def _get_grouped_feeds(reader: Reader) -> list[dict[str, typing.Any]]:
    """Build a list of webhook groups with pre-computed indices for template use.

    Each group dict contains:
        name: The webhook name (or "Orphaned (no webhook)").
        group_idx: 1-based index for the group.
        feeds: List of dicts with:
            feed: The Feed object.
            feed_idx: 1-based index within the group.

    Returns:
        list[dict]: Grouped feeds with pre-computed indices for template rendering.
    """
    hooks: list[dict[str, str]] = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))

    feeds_by_webhook: dict[str, list[Feed]] = {}
    orphaned: list[Feed] = []

    for feed in reader.get_feeds():
        feed_webhook: str = str(reader.get_tag(feed.url, "webhook", ""))
        hook_name: str = ""
        for hook in hooks:
            if hook["url"] == feed_webhook:
                hook_name = hook["name"]
                break
        if hook_name:
            feeds_by_webhook.setdefault(hook_name, []).append(feed)
        else:
            orphaned.append(feed)

    grouped: list[dict[str, typing.Any]] = []
    for group_idx, (name, feed_list) in enumerate(feeds_by_webhook.items(), start=1):
        grouped.append({
            "name": name,
            "group_idx": group_idx,
            "feeds": [{"feed": f, "feed_idx": idx} for idx, f in enumerate(feed_list, start=1)],
        })
    if orphaned:
        grouped.append({
            "name": "Orphaned (no webhook)",
            "group_idx": len(grouped) + 1,
            "feeds": [{"feed": f, "feed_idx": idx} for idx, f in enumerate(orphaned, start=1)],
        })

    return grouped


@app.get("/mass", response_class=HTMLResponse)
async def get_mass(
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    active_tab: str = "create",
) -> HTMLResponse:
    """Mass operations page: create, delete, or modify feeds in bulk.

    Args:
        request: The request object.
        reader: The Reader instance.
        active_tab: The active tab (create, delete, modify).

    Returns:
        HTMLResponse: The mass operations page.
    """
    hooks: list[dict[str, str]] = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))

    context: dict[str, typing.Any] = {
        "request": request,
        "webhooks": hooks,
        "all_feeds_grouped": _get_grouped_feeds(reader),
        "active_tab": active_tab,
    }
    return templates.TemplateResponse(request=request, name="mass.html", context=context)


def _create_and_tag_feed(reader: Reader, feed_url: str, webhook_url: str) -> str | None:
    """Add a feed and set its tags, without updating.

    Returns:
        The feed URL on success, or None if adding failed.
    """
    clean_url: str = feed_url.strip()
    try:
        reader.add_feed(clean_url)
    except FeedExistsError:
        pass
    except ReaderError:
        return None

    reader.set_tag(clean_url, "webhook", webhook_url)  # pyright: ignore[reportArgumentType]
    reader.set_tag(clean_url, "save_sent_webhooks", True)  # pyright: ignore[reportArgumentType]
    reader.set_tag(clean_url, "media_gallery_image_limit", cast("JSONType", 1))

    global_webhook_text_length_limit: int = coerce_webhook_text_length_limit(
        cast("JsonValue", reader.get_tag((), "webhook_text_length_limit", 4000)),  # pyright: ignore[reportArgumentType]
    )
    reader.set_tag(clean_url, "webhook_text_length_limit", cast("JSONType", global_webhook_text_length_limit))
    reader.set_tag(clean_url, "custom_message", default_custom_message)  # pyright: ignore[reportArgumentType]

    global_screenshot_layout: str = str(reader.get_tag((), "screenshot_layout", "desktop")).strip().lower()
    if global_screenshot_layout not in {"desktop", "mobile"}:
        global_screenshot_layout = "desktop"
    reader.set_tag(clean_url, "screenshot_layout", global_screenshot_layout)  # pyright: ignore[reportArgumentType]

    global_delivery_mode: str = str(reader.get_tag((), "delivery_mode", "embed")).strip().lower()
    if global_delivery_mode not in {"embed", "text"}:
        global_delivery_mode = "embed"
    reader.set_tag(clean_url, "delivery_mode", global_delivery_mode)  # pyright: ignore[reportArgumentType]
    reader.set_tag(clean_url, "should_send_embed", global_delivery_mode == "embed")  # pyright: ignore[reportArgumentType]
    reader.set_tag(clean_url, "embed", json.dumps(default_custom_embed))  # pyright: ignore[reportArgumentType]

    return clean_url


def _modify_single_feed(  # ruff:ignore[complex-structure, too-many-branches, too-many-statements]
    reader: Reader,
    url: str,
    modify_action: str,
    modify_value: str,
) -> dict[str, typing.Any]:
    """Apply a modification action to a single feed and return the result.

    Args:
        reader: The Reader instance.
        url: The feed URL to modify.
        modify_action: The action to perform.
        modify_value: The value for the action.

    Returns:
        dict: Result with url, success, error, and action_taken keys.
    """
    result: dict[str, typing.Any] = {
        "url": url,
        "success": False,
        "error": "",
        "action_taken": "",
    }

    try:
        reader.get_feed(url)
    except FeedNotFoundError:
        result["error"] = "Feed not found"
        return result

    if modify_action == "pause":
        reader.disable_feed_updates(url)
        result["success"] = True
        result["action_taken"] = "Paused"
    elif modify_action == "unpause":
        reader.enable_feed_updates(url)
        result["success"] = True
        result["action_taken"] = "Unpaused"
    elif modify_action == "change_webhook":
        webhooks: list[dict[str, str]] = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))
        webhook_url: str = ""
        for hook in webhooks:
            if hook["name"] == modify_value:
                webhook_url = hook["url"]
                break
        if webhook_url:
            reader.set_tag(url, "webhook", webhook_url)  # pyright: ignore[reportArgumentType]
            result["success"] = True
            result["action_taken"] = f"Webhook changed to {modify_value}"
        else:
            result["error"] = f"Webhook '{modify_value}' not found"
    elif modify_action == "delivery_mode":
        if modify_value == "embed":
            reader.set_tag(url, "delivery_mode", "embed")  # pyright: ignore[reportArgumentType]
            reader.set_tag(url, "should_send_embed", True)  # pyright: ignore[reportArgumentType]
            result["success"] = True
            result["action_taken"] = "Delivery mode set to embed"
        elif modify_value == "text":
            reader.set_tag(url, "delivery_mode", "text")  # pyright: ignore[reportArgumentType]
            reader.set_tag(url, "should_send_embed", False)  # pyright: ignore[reportArgumentType]
            result["success"] = True
            result["action_taken"] = "Delivery mode set to text"
        elif modify_value == "screenshot_desktop":
            reader.set_tag(url, "delivery_mode", "screenshot")  # pyright: ignore[reportArgumentType]
            reader.set_tag(url, "screenshot_layout", "desktop")  # pyright: ignore[reportArgumentType]
            result["success"] = True
            result["action_taken"] = "Delivery mode set to screenshot (desktop)"
        elif modify_value == "screenshot_mobile":
            reader.set_tag(url, "delivery_mode", "screenshot")  # pyright: ignore[reportArgumentType]
            reader.set_tag(url, "screenshot_layout", "mobile")  # pyright: ignore[reportArgumentType]
            result["success"] = True
            result["action_taken"] = "Delivery mode set to screenshot (mobile)"
        else:
            result["error"] = f"Unknown delivery mode: {modify_value}"
    elif modify_action == "screenshot_layout":
        if modify_value in {"desktop", "mobile"}:
            reader.set_tag(url, "screenshot_layout", modify_value)  # pyright: ignore[reportArgumentType]
            result["success"] = True
            result["action_taken"] = f"Screenshot layout set to {modify_value}"
        else:
            result["error"] = f"Unknown layout: {modify_value}"
    elif modify_action == "update_interval":
        try:
            interval: int = int(modify_value)
        except ValueError as e:
            result["error"] = str(e)
            return result
        if interval < 1:
            result["error"] = "Interval must be at least 1 minute"
        else:
            reader.set_tag(url, ".reader.update", {"interval": interval})  # pyright: ignore[reportArgumentType]
            result["success"] = True
            result["action_taken"] = f"Update interval set to {interval} minute(s)"  # ruff:ignore[hardcoded-sql-expression]
    else:
        result["error"] = f"Unknown action: {modify_action}"

    return result


def _update_and_mark_read(db_path: Path, feed_url: str) -> tuple[str, bool, str]:
    """Update a feed and mark entries as read, in its own reader instance.

    Called from worker threads to parallelize HTTP fetches.

    Returns:
        (feed_url, success, error_message)
    """
    worker_reader: Reader = make_app_reader(db_path)
    try:
        worker_reader.update_feed(feed_url)
        for entry in worker_reader.get_entries(feed=feed_url, read=False):
            worker_reader.set_entry_read(entry, True)
    except ReaderError as e:
        logger.warning("Failed to update feed %s: %s", feed_url, e)
        return feed_url, False, str(e)[:200]
    except Exception as e:
        logger.exception("Unexpected error updating feed %s", feed_url)
        return feed_url, False, str(e)[:200]
    finally:
        worker_reader.close()
    return feed_url, True, ""


@app.post("/mass/create", response_class=HTMLResponse)
async def post_mass_create(  # ruff:ignore[complex-structure]
    request: Request,
    feed_urls: Annotated[str, Form()],
    webhook_dropdown: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> HTMLResponse:
    """Create multiple feeds at once.

    Phase 1: Add feeds and set tags (sequential, fast, no HTTP).
    Phase 2: Update feeds in parallel via a thread pool.

    Args:
        request: The request object.
        feed_urls: Feed URLs (one per line).
        webhook_dropdown: The webhook to attach feeds to.
        reader: The Reader instance.

    Returns:
        HTMLResponse: The mass operations page with results.

    Raises:
        HTTPException: If the selected webhook is not found.
    """
    urls: list[str] = [url.strip() for url in feed_urls.strip().split("\n") if url.strip()]
    results: list[dict[str, typing.Any]] = []

    webhooks: list[dict[str, str]] = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))

    # Resolve webhook name to URL once for all feeds
    webhook_url: str = ""
    for hook in webhooks:
        if hook["name"] == webhook_dropdown:
            webhook_url = hook["url"]
            break

    if not webhook_url:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Phase 1: Add feeds and set tags (sequential, fast)
    urls_to_update: list[str] = []
    for url in urls:
        added_url: str | None = _create_and_tag_feed(reader, url, webhook_url)
        if added_url:
            urls_to_update.append(added_url)
            results.append({"url": url, "success": False, "feed_url": None, "error": ""})
            continue
        results.append({"url": url, "success": False, "feed_url": None, "error": "Failed to add feed"})

    # Phase 2: Update feeds in parallel
    if urls_to_update:
        db_path: Path = Path(data_dir) / "db.sqlite"
        max_workers: int = min(10, len(urls_to_update))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(_update_and_mark_read, db_path, u): u for u in urls_to_update}
            for future in concurrent.futures.as_completed(future_to_url):
                original_url: str = future_to_url[future]
                feed_url, update_success, error_msg = future.result()
                # Find and update the matching result entry
                for result in results:
                    if result["url"] == original_url:
                        result["success"] = update_success
                        result["feed_url"] = feed_url if update_success else None
                        result["error"] = error_msg
                        break

        reader.update_search()

    success_count: int = sum(1 for r in results if r["success"])
    if success_count > 0:
        commit_state_change(reader, f"Mass create {success_count} feed(s)")

    context: dict[str, typing.Any] = {
        "request": request,
        "webhooks": webhooks,
        "all_feeds_grouped": _get_grouped_feeds(reader),
        "active_tab": "create",
        "feed_urls": feed_urls,
        "selected_webhook": webhook_dropdown,
        "create_results": results,
        "message": f"Created {success_count} of {len(results)} feed(s).",
    }
    return templates.TemplateResponse(request=request, name="mass.html", context=context)


@app.post("/mass/delete", response_class=HTMLResponse)
async def post_mass_delete(
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    feed_urls: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse:
    """Delete multiple feeds at once.

    Args:
        request: The request object.
        reader: The Reader instance.
        feed_urls: List of feed URLs to delete.

    Returns:
        HTMLResponse: The mass operations page with results.
    """
    if feed_urls is None:
        feed_urls = []
    results: list[dict[str, typing.Any]] = []

    for url in feed_urls:
        result: dict[str, typing.Any] = {"url": url, "success": False, "error": ""}
        try:
            reader.delete_feed(url)
            result["success"] = True
        except FeedNotFoundError:
            result["error"] = "Feed not found"
        except Exception as e:  # ruff:ignore[blind-except]
            result["error"] = str(e)[:200]
        results.append(result)

    deleted_count: int = sum(1 for r in results if r["success"])
    if deleted_count > 0:
        commit_state_change(reader, f"Mass delete {deleted_count} feed(s)")

    webhooks: list[dict[str, str]] = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))

    failed_count: int = len(results) - deleted_count
    context: dict[str, typing.Any] = {
        "request": request,
        "webhooks": webhooks,
        "all_feeds_grouped": _get_grouped_feeds(reader),
        "active_tab": "delete",
        "delete_results": results,
        "delete_summary": {"deleted": deleted_count, "failed": failed_count},
        "message": f"Deleted {deleted_count} feed(s). {failed_count} failed.",
    }
    return templates.TemplateResponse(request=request, name="mass.html", context=context)


@app.post("/mass/modify", response_class=HTMLResponse)
async def post_mass_modify(
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    feed_urls: Annotated[list[str] | None, Form()] = None,
    modify_action: Annotated[str, Form()] = "",
    modify_value: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Modify multiple feeds at once.

    Args:
        request: The request object.
        reader: The Reader instance.
        feed_urls: List of feed URLs to modify.
        modify_action: The action to perform (pause, unpause, change_webhook, etc.).
        modify_value: The value for the action.

    Returns:
        HTMLResponse: The mass operations page with results.
    """
    feed_urls_list: list[str] = feed_urls if feed_urls is not None else []
    results: list[dict[str, typing.Any]] = []

    for url in feed_urls_list:
        try:
            result = _modify_single_feed(reader, url, modify_action, modify_value)
        except Exception as e:
            logger.exception("Failed to modify feed %s", url)
            result = {"url": url, "success": False, "error": str(e)[:200], "action_taken": ""}
        results.append(result)

    modified_count: int = sum(1 for r in results if r["success"])
    failed_count: int = sum(1 for r in results if not r["success"])
    if modified_count > 0:
        commit_state_change(reader, f"Mass modify {modified_count} feed(s)")

    webhooks = cast("list[dict[str, str]]", list(reader.get_tag((), "webhooks", [])))

    context: dict[str, typing.Any] = {
        "request": request,
        "webhooks": webhooks,
        "all_feeds_grouped": _get_grouped_feeds(reader),
        "active_tab": "modify",
        "modify_results": results,
        "modify_action": modify_action,
        "modify_value": modify_value,
        "modify_summary": {
            "modified": modified_count,
            "failed": failed_count,
            "skipped": 0,
        },
        "message": f"Modified {modified_count} feed(s). {failed_count} failed.",
    }
    return templates.TemplateResponse(request=request, name="mass.html", context=context)


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    query: str,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
) -> HTMLResponse:
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
    if not is_url_valid(new_hook_clean):
        raise HTTPException(status_code=400, detail="Invalid webhook URL")

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
        response: Response = httpx2.get(clean_url, follow_redirects=True, timeout=10.0)
    except HTTPError as e:
        return clean_url, str(e)

    if not response.is_success:
        return clean_url, f"HTTP {response.status_code}"

    return str(response.url), None


def create_webhook_feed_url_preview(
    webhook_feeds: list[Feed],
    replace_from: str,
    replace_to: str,
    resolve_urls: bool,  # ruff:ignore[boolean-type-hint-positional-argument]
    force_update: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]
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
    resolve_urls: bool,  # ruff:ignore[boolean-type-hint-positional-argument]
    force_update: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]
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
    resolve_urls: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]
    force_update: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]
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
async def get_webhook_entries(  # ruff:ignore[complex-structure, too-many-locals]
    webhook_url: str,
    request: Request,
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    starting_after: str = "",
    replace_from: str = "",
    replace_to: str = "",
    resolve_urls: bool = True,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]
    force_update: bool = False,  # ruff:ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]
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
async def post_bulk_change_feed_urls(  # ruff:ignore[complex-structure, too-many-locals, too-many-branches, too-many-statements]
    webhook_url: Annotated[str, Form()],
    replace_from: Annotated[str, Form()],
    reader: Annotated[Reader, Depends(get_reader_dependency)],
    replace_to: Annotated[str, Form()] = "",
    resolve_urls: Annotated[bool, Form()] = True,  # ruff:ignore[boolean-default-value-positional-argument]
    force_update: Annotated[bool, Form()] = False,  # ruff:ignore[boolean-default-value-positional-argument]
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
        host="0.0.0.0",  # ruff:ignore[hardcoded-bind-all-interfaces]
        port=3000,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
