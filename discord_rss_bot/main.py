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
import urllib.parse
from datetime import datetime
from typing import Any, Iterable

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from reader import (
    Entry,
    EntryCounts,
    EntrySearchCounts,
    EntrySearchResult,
    Feed,
    FeedCounts,
    Reader,
    TagNotFoundError,
)
from starlette.responses import RedirectResponse
from starlette.templating import _TemplateResponse  # noqa

from discord_rss_bot.feeds import send_to_discord
from discord_rss_bot.search import create_html_for_search_results
from discord_rss_bot.settings import get_reader, list_webhooks

app: FastAPI = FastAPI()
app.mount("/static", StaticFiles(directory="discord_rss_bot/static"), name="static")
templates: Jinja2Templates = Jinja2Templates(directory="discord_rss_bot/templates")

reader: Reader = get_reader()


def encode_url(url_to_quote: str) -> str:
    """%-escape the URL so it can be used in a URL. If we didn't do this, we couldn't go to feeds with a ? in the URL.

    You can use this in templates with {{ url | encode_url }}.

    Args:
        url_to_quote: The url to encode.

    Returns:
        The encoded url.
    """
    if url_to_quote:
        return urllib.parse.quote(url_to_quote)
    print("url_to_quote is None")  # TODO: Send error to Discord.


templates.env.filters["encode_url"] = encode_url


@app.post("/add_webhook")
async def add_webhook(webhook_name: str = Form(), webhook_url: str = Form()) -> RedirectResponse | dict[str, str]:
    """
    Add a feed to the database.

    Args:
        webhook_name: The name of the webhook.
        webhook_url: The url of the webhook.

    Returns:
        dict: The feed that was added.
    """
    # Remove leading and trailing whitespace.
    clean_webhook_name: str = webhook_name.strip()
    clean_webhook_url: str = webhook_url.strip()

    # Get current webhooks from the database if they exist otherwise use an empty list.
    webhooks = list_webhooks(reader)

    # Only add the webhook if it doesn't already exist.
    if not any(webhook["name"] == clean_webhook_name for webhook in webhooks):
        # Create a dict with webhook name and URL.
        new_webhook: dict[str, str] = {"name": clean_webhook_name, "url": clean_webhook_url}

        # Add the new webhook to the list of webhooks.
        webhooks.append(new_webhook)

        # Add our new list of webhooks to the database.
        reader.set_tag((), "webhooks", webhooks)

        return RedirectResponse(url="/", status_code=303)

    # TODO: Show this error on the page.
    return {"error": "Webhook already exists."}


@app.post("/delete_webhook")
async def delete_webhook(webhook_url: str = Form()) -> RedirectResponse | dict[str, str]:
    """
    Delete a webhook from the database.

    Args:
        webhook_url: The url of the webhook.

    Returns:
        dict: The feed that was added.
    """
    # Remove leading and trailing whitespace.
    clean_webhook_url: str = webhook_url.strip()

    # Get current webhooks from the database if they exist otherwise use an empty list.
    webhooks = list_webhooks(reader)

    # Only add the webhook if it doesn't already exist.
    for webhook in webhooks:
        if webhook["url"] == clean_webhook_url:
            # Add the new webhook to the list of webhooks.
            webhooks.remove(webhook)

            print(f"Removed webhook {webhook['name']}.")

            # Add our new list of webhooks to the database.
            reader.set_tag((), "webhooks", webhooks)

            return RedirectResponse(url="/", status_code=303)

    # TODO: Show this error on the page.
    return {"error": "Could not find webhook."}


@app.post("/add")
async def create_feed(feed_url: str = Form(), webhook_dropdown: str = Form()) -> dict[str, str] | RedirectResponse:
    """
    Add a feed to the database.

    Args:
        feed_url: The feed to add.
        webhook_dropdown: The webhook to use.

    Returns:
        dict: The feed that was added.
    """
    clean_feed_url: str = feed_url.strip()

    reader.add_feed(clean_feed_url)
    reader.update_feed(clean_feed_url)

    # Mark every entry as read, so we don't send all the old entries to Discord.
    entries: Iterable[Entry] = reader.get_entries(feed=clean_feed_url, read=False)
    for entry in entries:
        reader.set_entry_read(entry, True)  # type: ignore

    try:
        hooks = reader.get_tag((), "webhooks")
    except TagNotFoundError:
        hooks = []

    webhook_url = None
    if len(hooks) > 0:
        # Get the webhook URL from the dropdown.
        for hook in hooks:
            if hook["name"] == webhook_dropdown:
                webhook_url = hook["url"]
                break

    if webhook_url is None:
        # TODO: Show this error on the page.
        return {"error": "No webhook URL found."}

    reader.set_tag(clean_feed_url, "webhook", webhook_url)  # type: ignore
    reader.get_tag(clean_feed_url, "webhook")

    reader.update_search()

    return RedirectResponse(url=f"/feed/?feed_url={feed_url}", status_code=303)


@app.post("/pause")
async def pause_feed(feed_url: str = Form()) -> dict[str, str] | RedirectResponse:
    # Disable/pause the feed.
    reader.disable_feed_updates(feed_url)

    # Clean URL is used to redirect to the feed page.
    clean_url: str = urllib.parse.quote(feed_url)

    return RedirectResponse(url=f"/feed/?feed_url={clean_url}", status_code=303)


@app.post("/unpause")
async def unpause_feed(feed_url: str = Form()) -> dict[str, str] | RedirectResponse:
    # Enable/unpause the feed.
    reader.enable_feed_updates(feed_url)

    # Clean URL is used to redirect to the feed page.
    clean_url: str = urllib.parse.quote(feed_url)

    return RedirectResponse(url=f"/feed/?feed_url={clean_url}", status_code=303)


@app.post("/whitelist")
async def set_whitelist(whitelist_title: str, whitelist_summary: str, whitelist_content: str, feed_url: str = Form()):
    # Add the whitelist to the feed.

    if whitelist_title:
        reader.set_tag(feed_url, "whitelist_title", whitelist)  # type: ignore
    if whitelist_summary:
        reader.set_tag(feed_url, "whitelist_summary", whitelist)  # type: ignore
    if whitelist_content:
        reader.set_tag(feed_url, "whitelist_content", whitelist)  # type: ignore

    # Clean URL is used to redirect to the feed page.
    clean_url: str = urllib.parse.quote(feed_url)

    return RedirectResponse(url=f"/feed/?feed_url={clean_url}", status_code=303)


@app.get("/whitelist", response_class=HTMLResponse)
async def get_whitelist(feed_url: str, request: Request) -> _TemplateResponse:
    # Make feed_url a valid URL.
    url: str = urllib.parse.unquote(feed_url)

    feed: Feed = reader.get_feed(url)
    try:
        whitelist = reader.get_tag(url, "whitelist")
    except TagNotFoundError:
        whitelist = ""

    context = {"request": request, "feed": feed, "whitelist": whitelist}
    return templates.TemplateResponse("whitelist.html", context)


@app.post("/blacklist")
async def set_blacklist(blacklist_title: str, blacklist_summary: str, blacklist_content: str, feed_url: str = Form()):
    # Add the blacklist to the feed.

    if blacklist_title:
        reader.set_tag(feed_url, "blacklist_title", blacklist)  # type: ignore
    if blacklist_summary:
        reader.set_tag(feed_url, "blacklist_summary", blacklist)  # type: ignore
    if blacklist_content:
        reader.set_tag(feed_url, "blacklist_content", blacklist)  # type: ignore

    # Clean URL is used to redirect to the feed page.
    clean_url: str = urllib.parse.quote(feed_url)

    return RedirectResponse(url=f"/feed/?feed_url={clean_url}", status_code=303)


@app.get("/blacklist", response_class=HTMLResponse)
async def get_blacklist(feed_url: str, request: Request) -> _TemplateResponse:
    # Make feed_url a valid URL.
    url: str = urllib.parse.unquote(feed_url)

    feed: Feed = reader.get_feed(url)
    try:
        blacklist = reader.get_tag(url, "blacklist")
    except TagNotFoundError:
        blacklist = ""

    context = {"request": request, "feed": feed, "blacklist": blacklist}
    return templates.TemplateResponse("blacklist.html", context)


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


@app.get("/feed", response_class=HTMLResponse)
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
    url: str = urllib.parse.unquote(feed_url)

    feed: Feed = reader.get_feed(url)

    # Get entries from the feed.
    entries: Iterable[Entry] = reader.get_entries(feed=url)

    # Get the entries in the feed.
    feed_counts: FeedCounts = reader.get_feed_counts(feed=url)

    context = {"request": request, "feed": feed, "entries": entries, "feed_counts": feed_counts}
    return templates.TemplateResponse("feed.html", context)


@app.get("/webhooks", response_class=HTMLResponse)
async def get_webhooks(request: Request) -> _TemplateResponse:
    """
    Page for adding a new webhook.

    Args:
        request: The request.

    Returns:
        HTMLResponse: The HTML response.
    """
    return templates.TemplateResponse("webhooks.html", {"request": request})


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
    # Get webhooks name and url from the database.
    try:
        hooks = reader.get_tag((), "webhooks")
    except TagNotFoundError:
        hooks = []

    feed_list = []
    broken_feed = []
    feeds: Iterable[Feed] = reader.get_feeds()
    for feed in feeds:
        try:
            hook = reader.get_tag(feed.url, "webhook")
            feed_list.append({"feed": feed, "webhook": hook})
        except TagNotFoundError:
            broken_feed.append({"feed": feed, "webhook": None})
            continue

    # Sort feed_list by when the feed was added.
    feed_list.sort(key=lambda x: x["feed"].added)

    feed_count: FeedCounts = reader.get_feed_counts()
    entry_count: EntryCounts = reader.get_entry_counts()
    context: dict[str, Any] = {
        "request": request,
        "feeds": feed_list,
        "feed_count": feed_count,
        "entry_count": entry_count,
        "webhooks": hooks,
        "broken_feed": broken_feed,
    }
    return context


@app.post("/remove", response_class=HTMLResponse)
async def remove_feed(feed_url: str = Form()) -> RedirectResponse:
    """
    Get a feed by URL.

    Args:
        feed_url: The feed to add.

    Returns:
        HTMLResponse: The HTML response.
    """
    reader.delete_feed(feed_url)
    reader.update_search()

    return RedirectResponse(url="/", status_code=303)


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
    search_results: Iterable[EntrySearchResult] = reader.search_entries(query)
    search_amount: EntrySearchCounts = reader.search_entry_counts(query)

    search_html: str = create_html_for_search_results(search_results)

    context: dict[str, Request | str | EntrySearchCounts] = {
        "request": request,
        "search_html": search_html,
        "query": query,
        "search_amount": search_amount,
    }
    return templates.TemplateResponse("search.html", context)


@app.on_event("startup")
def startup() -> None:
    """This is called when the server starts.

    It reads the settings file and starts the scheduler."""
    scheduler: BackgroundScheduler = BackgroundScheduler()

    # Update all feeds every 15 minutes.
    scheduler.add_job(send_to_discord, "interval", minutes=15, next_run_time=datetime.now())

    scheduler.start()


if __name__ == "__main__":
    uvicorn.run("main:app", log_level="debug", reload=True)
