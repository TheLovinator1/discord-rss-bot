import urllib.parse
from datetime import datetime
from typing import Any, Iterable

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from reader import Entry, EntryCounts, EntrySearchCounts, EntrySearchResult, Feed, FeedCounts, Reader, TagNotFoundError
from starlette.responses import RedirectResponse

from discord_rss_bot.custom_filters import encode_url, entry_is_blacklisted, entry_is_whitelisted
from discord_rss_bot.custom_message import get_custom_message
from discord_rss_bot.feeds import send_to_discord
from discord_rss_bot.filter.blacklist import get_blacklist_content, get_blacklist_summary, get_blacklist_title
from discord_rss_bot.filter.whitelist import get_whitelist_content, get_whitelist_summary, get_whitelist_title
from discord_rss_bot.search import create_html_for_search_results
from discord_rss_bot.settings import get_reader, list_webhooks

app: FastAPI = FastAPI()
app.mount("/static", StaticFiles(directory="discord_rss_bot/static"), name="static")
templates: Jinja2Templates = Jinja2Templates(directory="discord_rss_bot/templates")

reader: Reader = get_reader()


# Add the filters to the Jinja2 environment so they can be used in html templates.
templates.env.filters["encode_url"] = encode_url  # type: ignore
templates.env.filters["entry_is_whitelisted"] = entry_is_whitelisted  # type: ignore
templates.env.filters["entry_is_blacklisted"] = entry_is_blacklisted  # type: ignore


@app.post("/add_webhook")
async def add_webhook(webhook_name: str = Form(), webhook_url: str = Form()):
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
    webhooks: list[dict[str, str]] = list_webhooks(reader)

    # Only add the webhook if it doesn't already exist.
    if all(webhook["name"] != clean_webhook_name for webhook in webhooks):
        # Create a dict with webhook name and URL.
        new_webhook: dict[str, str] = {"name": clean_webhook_name, "url": clean_webhook_url}

        # Add the new webhook to the list of webhooks.
        webhooks.append(new_webhook)

        # Add our new list of webhooks to the database.
        reader.set_tag((), "webhooks", webhooks)  # type: ignore

        return RedirectResponse(url="/", status_code=303)

    # TODO: Show this error on the page.
    return {"error": "Webhook already exists."}


@app.post("/delete_webhook")
async def delete_webhook(webhook_url: str = Form()):
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
    webhooks: list[dict[str, str]] = list_webhooks(reader)

    # Only add the webhook if it doesn't already exist.
    for webhook in webhooks:
        if webhook["url"] == clean_webhook_url:
            # Add the new webhook to the list of webhooks.
            webhooks.remove(webhook)

            print(f"Removed webhook {webhook['name']}.")

            # Add our new list of webhooks to the database.
            reader.set_tag((), "webhooks", webhooks)  # type: ignore

            return RedirectResponse(url="/", status_code=303)

    # TODO: Show this error on the page.
    return {"error": "Could not find webhook."}


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
    clean_feed_url: str = feed_url.strip()

    # TODO: Check if the feed is valid, if not return an error or fix it.
    # For example, if the feed is missing the protocol, add it.
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

    webhook_url = ""
    if hooks:
        # Get the webhook URL from the dropdown.
        for hook in hooks:
            if hook["name"] == webhook_dropdown:  # type: ignore
                webhook_url: str = hook["url"]  # type: ignore
                break

    if not webhook_url:
        # TODO: Show this error on the page.
        return {"error": "No webhook URL found."}

    reader.set_tag(clean_feed_url, "webhook", webhook_url)  # type: ignore
    reader.get_tag(clean_feed_url, "webhook")

    reader.update_search()

    return RedirectResponse(url=f"/feed/?feed_url={feed_url}", status_code=303)


@app.post("/pause")
async def pause_feed(feed_url: str = Form()):
    """Pause a feed.

    Args:
        feed_url: The feed to pause. Defaults to Form().

    Returns:
        Redirect the URL to the feed we paused.
    """
    # Disable/pause the feed.
    reader.disable_feed_updates(feed_url)

    # Clean URL is used to redirect to the feed page.
    clean_url: str = urllib.parse.quote(feed_url)

    return RedirectResponse(url=f"/feed/?feed_url={clean_url}", status_code=303)


@app.post("/unpause")
async def unpause_feed(feed_url: str = Form()):
    """Unpause a feed.

    Args:
        feed_url: The feed to unpause. Defaults to Form().

    Returns:
        Redirect to the feed we unpaused.
    """
    # Enable/unpause the feed.
    reader.enable_feed_updates(feed_url)

    # Clean URL is used to redirect to the feed page.
    clean_url: str = urllib.parse.quote(feed_url)

    return RedirectResponse(url=f"/feed/?feed_url={clean_url}", status_code=303)


@app.post("/whitelist")
async def set_whitelist(
    whitelist_title: str = Form(None),
    whitelist_summary: str = Form(None),
    whitelist_content: str = Form(None),
    feed_url: str = Form(),
):
    """Set what the whitelist should be sent, if you have this set only words in the whitelist will be sent.

    Args:
        whitelist_title: Whitelisted words for when checking the title.
        whitelist_summary: Whitelisted words for when checking the title.
        whitelist_content: Whitelisted words for when checking the title.
        feed_url: The feed we should set the whitelist for.

    Returns:
        Redirect back to the feed page.
    """
    if whitelist_title:
        reader.set_tag(feed_url, "whitelist_title", whitelist_title)  # type: ignore
    if whitelist_summary:
        reader.set_tag(feed_url, "whitelist_summary", whitelist_summary)  # type: ignore
    if whitelist_content:
        reader.set_tag(feed_url, "whitelist_content", whitelist_content)  # type: ignore

    # Clean URL is used to redirect to the feed page.
    clean_url: str = urllib.parse.quote(feed_url)

    return RedirectResponse(url=f"/feed/?feed_url={clean_url}", status_code=303)


@app.get("/whitelist", response_class=HTMLResponse)
async def get_whitelist(feed_url: str, request: Request):
    """Get the whitelist.

    Args:
        feed_url: What feed we should get the whitelist for.
        request: The HTTP request.

    Returns:
        _description_
    """
    # Make feed_url a valid URL.
    url: str = urllib.parse.unquote(feed_url)

    feed: Feed = reader.get_feed(url)

    # Get previous data, this is used when creating the form.
    whitelist_title: str = get_whitelist_title(reader, feed)
    whitelist_summary: str = get_whitelist_summary(reader, feed)
    whitelist_content: str = get_whitelist_content(reader, feed)

    context = {
        "request": request,
        "feed": feed,
        "whitelist_title": whitelist_title,
        "whitelist_summary": whitelist_summary,
        "whitelist_content": whitelist_content,
    }
    return templates.TemplateResponse("whitelist.html", context)  # type: ignore


@app.post("/blacklist")
async def set_blacklist(
    blacklist_title: str = Form(None),
    blacklist_summary: str = Form(None),
    blacklist_content: str = Form(None),
    feed_url: str = Form(),
):
    """Set the blacklist, if this is set we will check if words are in the title, summary or content
    and then don't send that entry.

    Args:
        blacklist_title: Blacklisted words for when checking the title.
        blacklist_summary: Blacklisted words for when checking the summary.
        blacklist_content: Blacklisted words for when checking the content.
        feed_url: What feed we should set the blacklist for.

    Returns:
        Redirect to the feed.
    """
    # Add the blacklist to the feed.

    if blacklist_title:
        reader.set_tag(feed_url, "blacklist_title", blacklist_title)  # type: ignore
    if blacklist_summary:
        reader.set_tag(feed_url, "blacklist_summary", blacklist_summary)  # type: ignore
    if blacklist_content:
        reader.set_tag(feed_url, "blacklist_content", blacklist_content)  # type: ignore

    # Clean URL is used to redirect to the feed page.
    clean_url: str = urllib.parse.quote(feed_url)

    return RedirectResponse(url=f"/feed/?feed_url={clean_url}", status_code=303)


@app.get("/blacklist", response_class=HTMLResponse)
async def get_blacklist(feed_url: str, request: Request):
    # Make feed_url a valid URL.
    url: str = urllib.parse.unquote(feed_url)

    feed: Feed = reader.get_feed(url)

    # Get previous data, this is used when creating the form.
    blacklist_title: str = get_blacklist_title(reader, feed)
    blacklist_summary: str = get_blacklist_summary(reader, feed)
    blacklist_content: str = get_blacklist_content(reader, feed)

    context = {
        "request": request,
        "feed": feed,
        "blacklist_title": blacklist_title,
        "blacklist_summary": blacklist_summary,
        "blacklist_content": blacklist_content,
    }
    return templates.TemplateResponse("blacklist.html", context)  # type: ignore


@app.post("/custom")
async def set_custom(custom_message: str = Form(""), feed_url: str = Form()):
    """
    Set the custom message, this is used when sending the message.

    Args:
        custom_message: The custom message.
        feed_url: The feed we should set the custom message for.

        Returns:
            Redirect to the feed.
    """

    # Add the custom_message to the feed.
    if custom_message:
        reader.set_tag(feed_url, "custom_message", custom_message)
        print(f"Set custom message for {feed_url} to {custom_message}")
    else:
        print(f"Removing custom message for {feed_url}")
        reader.delete_tag(feed_url, "custom_message", missing_ok=True)

    # Clean URL is used to redirect to the feed page.
    clean_url: str = urllib.parse.quote(feed_url)

    return RedirectResponse(url=f"/feed/?feed_url={clean_url}", status_code=303)


@app.get("/custom", response_class=HTMLResponse)
async def get_custom(feed_url: str, request: Request):
    """Get the custom message. This is used when sending the message to Discord.

    Args:
        feed_url: What feed we should get the custom message for.
        request: The HTTP request.

    Returns:
        custom.html
    """

    # Make feed_url a valid URL.
    url: str = urllib.parse.unquote(feed_url)

    feed: Feed = reader.get_feed(url)

    # Get previous data, this is used when creating the form.
    custom_message: str = get_custom_message(reader, feed)

    # Get the first entry, this is used to show the user what the custom message will look like.
    first_entry: Entry = reader.get_entries(feed=feed, limit=1)
    for entry in first_entry:
        first_entry = entry

    context = {"request": request, "feed": feed, "custom_message": custom_message, "entry": first_entry}
    return templates.TemplateResponse("custom.html", context)  # type: ignore


@app.get("/add", response_class=HTMLResponse)
def get_add(request: Request):
    """
    Page for adding a new feed.

    Args:
        request: The request.

    Returns:
        HTMLResponse: The HTML response.
    """
    context = make_context_index(request)  # type: ignore
    return templates.TemplateResponse("add.html", context)  # type: ignore


@app.get("/feed", response_class=HTMLResponse)
async def get_feed(feed_url: str, request: Request):
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
    return templates.TemplateResponse("feed.html", context)  # type: ignore


@app.get("/webhooks", response_class=HTMLResponse)
async def get_webhooks(request: Request):
    """
    Page for adding a new webhook.

    Args:
        request: The request.

    Returns:
        HTMLResponse: The HTML response.
    """
    return templates.TemplateResponse("webhooks.html", {"request": request})  # type: ignore


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """
    This is the root of the website.

    Args:
        request: The request.

    Returns:
        HTMLResponse: The HTML response.
    """
    context = make_context_index(request)  # type: ignore
    return templates.TemplateResponse("index.html", context)  # type: ignore


def make_context_index(request: Request) -> dict[str, Any]:
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

    feed_list: list[dict[str, Any]] = []
    broken_feeds: list[Feed] = []
    feeds: Iterable[Feed] = reader.get_feeds()
    for feed in feeds:
        try:
            hook: str = reader.get_tag(feed.url, "webhook")  # type: ignore
            feed_list.append({"feed": feed, "webhook": hook})
        except TagNotFoundError:
            broken_feeds.append(feed)
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
        "broken_feeds": broken_feeds,
    }
    return context


@app.post("/remove", response_class=HTMLResponse)
async def remove_feed(feed_url: str = Form()):
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
async def search(request: Request, query: str):
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
    return templates.TemplateResponse("search.html", context)  # type: ignore


@app.on_event("startup")  # type: ignore
def startup() -> None:
    """This is called when the server starts.

    It reads the settings file and starts the scheduler."""
    scheduler: BackgroundScheduler = BackgroundScheduler()

    # Update all feeds every 15 minutes.
    scheduler.add_job(send_to_discord, "interval", minutes=15, next_run_time=datetime.now())  # type: ignore

    scheduler.start()  # type: ignore


if __name__ == "__main__":
    uvicorn.run("main:app", log_level="debug", reload=True)  # type: ignore
