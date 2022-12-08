"""
The main file for the discord-rss-bot.

This file is used to start the bot.

Functions:
    check_feed() -> /check
        POST - Update a feed.
    crete_feed() -> /add
        POST - Create a new feed.
    favicon() -> /favicon.ico
        GET - Return the favicon.
    get_add() -> /add
        GET - Page for adding a new feed.
    get_feed() -> /feed
        GET - Page for a single feed.
    index() -> /
        GET - index page.
    remove_feed() -> /remove
        POST - Remove a feed.

    create_list_of_webhooks()
        Create a list with webhooks.
    make_context_index()
        Create the needed context for the index page.
    startup()
        Runs on startup.
"""
import sys
from functools import cache
from typing import Any, Iterable

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from reader import (
    EntryCounts,
    Feed,
    FeedCounts,
)
from starlette.templating import _TemplateResponse
from tomlkit.toml_document import TOMLDocument

from discord_rss_bot.feeds import send_to_discord
from discord_rss_bot.settings import logger, read_settings_file, reader

app: FastAPI = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates: Jinja2Templates = Jinja2Templates(directory="templates")


@app.post("/check", response_class=HTMLResponse)
def check_feed(request: Request, feed_url: str = Form()) -> _TemplateResponse:
    """Check all feeds"""
    send_to_discord(feed_url)

    logger.info(f"Get feed: {feed_url}")
    feed: Feed = reader.get_feed(feed_url)

    return templates.TemplateResponse("feed.html", {"request": request, "feed": feed})


@app.post("/add")
async def create_feed(feed_url: str = Form(), webhook_dropdown: str = Form()) -> HTTPException | dict[str, str]:
    """
    Add a feed to the database.

    Args:
        feed_url: The feed to add.
        webhook_dropdown: The webhook to use.

    Returns:
        dict: The feed that was added.
    """

    # Remove spaces from feed_url
    feed_url = feed_url.strip()
    logger.debug(f"Stripped feed_url: {feed_url}")

    logger.info(f"Adding feed {feed_url} for {webhook_dropdown}")
    reader.add_feed(feed_url)
    reader.update_feed(feed_url)

    # Mark every entry as read, so we don't send all the old entries to Discord.
    entries = reader.get_entries(feed=feed_url, read=False)
    for entry in entries:
        logger.debug(f"Marking {entry.title} as read")
        reader.set_entry_read(entry, True)

    settings: TOMLDocument = read_settings_file()

    logger.debug(f"Webhook name: {webhook_dropdown} with URL: {settings['webhooks'][webhook_dropdown]}")
    webhook_url: str = str(settings["webhooks"][webhook_dropdown])
    reader.set_tag(feed_url, "webhook", webhook_url)

    # TODO: Go to the feed page.
    return {"feed_url": str(feed_url), "status": "added"}


def create_list_of_webhooks() -> list[dict[str, str]]:
    """List with webhooks."""
    logger.info("Creating list with webhooks.")
    settings: TOMLDocument = read_settings_file()
    list_of_webhooks = []
    for hook in settings["webhooks"]:
        logger.info(f"Webhook name: {hook} with URL: {settings['webhooks'][hook]}")
        list_of_webhooks.append({"name": hook, "url": settings["webhooks"][hook]})
        logger.debug(f"Hook: {hook}, URL: {settings['webhooks'][hook]}")
    logger.info(f"List of webhooks: {list_of_webhooks}")
    return list_of_webhooks


@cache
@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    """Return favicon."""
    return FileResponse("static/favicon.ico")


@app.get("/add", response_class=HTMLResponse)
def get_add(request: Request) -> _TemplateResponse:
    """
    Page for adding a new feed.

    Args:
        request: The request.

    Returns:
        HTMLResponse: The HTML response.
    """
    context = make_context_index(request)
    return templates.TemplateResponse("add.html", context)


@app.get("/feed/{feed_url:path}", response_class=HTMLResponse)
async def get_feed(feed_url: str, request: Request) -> _TemplateResponse:
    """
    Get a feed by URL.

    Args:
        request: The request.
        feed_url: The feed to add.

    Returns:
        HTMLResponse: The HTML response.
    """
    # Convert the URL to a valid URL.
    logger.info(f"Got feed: {feed_url}")

    feed: Feed = reader.get_feed(feed_url)

    # Get entries from the feed.
    entries: Iterable[EntryCounts] = reader.get_entries(feed=feed_url)

    # Get the entries in the feed.
    feed_counts: FeedCounts = reader.get_feed_counts(feed=feed_url)

    return templates.TemplateResponse(
        "feed.html", {"request": request, "feed": feed, "entries": entries, "feed_counts": feed_counts}
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> _TemplateResponse:
    """
    This is the root of the website.

    Args:
        request: The request.

    Returns:
        HTMLResponse: The HTML response.
    """
    context = make_context_index(request)
    return templates.TemplateResponse("index.html", context)


def make_context_index(request) -> dict:
    """
    Create the needed context for the index page.

    Used by / and /add.
    Args:
        request: The request.

    Returns:
        dict: The context.

    """
    hooks = create_list_of_webhooks()
    feed_list = []
    feeds: Iterable[Feed] = reader.get_feeds()
    for feed in feeds:
        logger.debug(f"Feed: {feed}")
        hook = reader.get_tag(feed.url, "webhook")
        feed_list.append({"feed": feed, "webhook": hook})

    feed_count: FeedCounts = reader.get_feed_counts()
    entry_count: EntryCounts = reader.get_entry_counts()
    context: dict[str, Any] = {
        "request": request,
        "feeds": feed_list,
        "feed_count": feed_count,
        "entry_count": entry_count,
        "webhooks": hooks,
    }
    return context


@app.post("/remove", response_class=HTMLResponse)
async def remove_feed(request: Request, feed_url: str = Form()):
    """
    Get a feed by URL.

    Args:
        request: The request.
        feed_url: The feed to add.

    Returns:
        HTMLResponse: The HTML response.
    """

    reader.delete_feed(feed_url)

    logger.info(f"Deleted feed: {feed_url}")
    context = make_context_index(request)
    return templates.TemplateResponse("index.html", context)


@app.on_event("startup")
def startup() -> None:
    """This is called when the server starts.

    It reads the settings file and starts the scheduler."""
    settings: TOMLDocument = read_settings_file()

    if not settings["webhooks"]:
        logger.critical("No webhooks found in settings file.")
        sys.exit()
    webhooks = settings["webhooks"]
    for key in webhooks:
        logger.info(f"Webhook name: {key} with URL: {settings['webhooks'][key]}")

    scheduler: BackgroundScheduler = BackgroundScheduler()

    # Update all feeds every 15 minutes.
    scheduler.add_job(send_to_discord, "interval", minutes=15)

    scheduler.start()


@app.on_event("shutdown")
def shutdown() -> None:
    """This is called when the server shuts down.

    It stops the scheduler."""
    scheduler: BackgroundScheduler = BackgroundScheduler()
    scheduler.shutdown()
    reader.close()


if __name__ == "__main__":
    uvicorn.run("main:app", log_level="debug", reload=True)
