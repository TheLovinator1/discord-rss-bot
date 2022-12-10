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
import urllib.parse
from functools import cache
from typing import Any, Iterable

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from reader import Entry, EntryCounts, Feed, FeedCounts
from starlette.templating import _TemplateResponse
from tomlkit.toml_document import TOMLDocument

from discord_rss_bot.feeds import send_to_discord
from discord_rss_bot.search import create_html_for_search_results
from discord_rss_bot.settings import read_settings_file, reader

app: FastAPI = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates: Jinja2Templates = Jinja2Templates(directory="templates")


def encode_url(url_to_quote: str) -> str:
    """%-escape the URL so it can be used in a URL. If we didn't do this, we couldn't go to feeds with a ? in the URL.

    You can use this in templates with {{ url | encode_url }}.

    Args:
        url_to_quote: The url to encode.

    Returns:
        The encoded url.
    """
    return urllib.parse.quote(url_to_quote)


templates.env.filters["encode_url"] = encode_url


@app.post("/add")
async def create_feed(feed_url: str = Form(), webhook_dropdown: str = Form()):
    """
    Add a feed to the database.

    Args:
        feed_url: The feed to add.
        webhook_dropdown: The webhook to use.

    Returns:
        dict: The feed that was added.
    """
    feed_url = feed_url.strip()

    reader.add_feed(feed_url)
    reader.update_feed(feed_url)

    # Mark every entry as read, so we don't send all the old entries to Discord.
    entries = reader.get_entries(feed=feed_url, read=False)
    for entry in entries:
        reader.set_entry_read(entry, True)

    settings: TOMLDocument = read_settings_file()
    webhook_url: str = str(settings["webhooks"][webhook_dropdown])
    reader.set_tag(feed_url, "webhook", webhook_url)
    reader.get_tag(feed_url, "webhook")

    reader.update_search()

    return RedirectResponse(url=f"/feed/?feed_url={feed_url}", status_code=303)


def create_list_of_webhooks() -> list[dict[str, str]]:
    """List with webhooks."""
    settings: TOMLDocument = read_settings_file()
    list_of_webhooks = []
    for hook in settings["webhooks"]:
        list_of_webhooks.append({"name": hook, "url": settings["webhooks"][hook]})

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


@app.get("/feed/", response_class=HTMLResponse)
async def get_feed(feed_url: str, request: Request) -> _TemplateResponse:
    """
    Get a feed by URL.

    Args:
        request: The request.
        feed_url: The feed to add.

    Returns:
        HTMLResponse: The HTML response.
    """
    # Make feed_url a valid URL.
    feed_url = urllib.parse.unquote(feed_url)

    feed: Feed = reader.get_feed(feed_url)

    # Get entries from the feed.
    entries: Iterable[Entry] = reader.get_entries(feed=feed_url)

    # Get the entries in the feed.
    feed_counts: FeedCounts = reader.get_feed_counts(feed=feed_url)

    context = {"request": request, "feed": feed, "entries": entries, "feed_counts": feed_counts}
    return templates.TemplateResponse("feed.html", context)


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
        hook = reader.get_tag(feed.url, "webhook")
        feed_list.append({"feed": feed, "webhook": hook})

    # Sort feed_list by feed url
    feed_list.sort(key=lambda x: x["feed"].url)

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
    reader.update_search()

    return RedirectResponse(url=f"/", status_code=303)


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, query: str) -> _TemplateResponse:
    """
    Get entries matching a full-text search query.

    Args:
        request: The request.
        query: The query to search for.

    Returns:
        HTMLResponse: The HTML response.
    """
    reader.update_search()
    search_results = reader.search_entries(query)
    search_amount = reader.search_entry_counts(query)

    search_html = create_html_for_search_results(search_results)

    context = {"request": request, "search_html": search_html, "query": query, "search_amount": search_amount}
    return templates.TemplateResponse("search.html", context)


@app.on_event("startup")
def startup() -> None:
    """This is called when the server starts.

    It reads the settings file and starts the scheduler."""
    settings: TOMLDocument = read_settings_file()

    if not settings["webhooks"]:
        sys.exit("No webhooks found in settings file.")

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
