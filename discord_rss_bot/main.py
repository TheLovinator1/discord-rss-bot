import json
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Dict, Iterable

import httpx
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from httpx import Response
from reader import (
    Entry,
    EntryCounts,
    EntrySearchCounts,
    EntrySearchResult,
    Feed,
    FeedCounts,
    FeedNotFoundError,
    Reader,
    TagNotFoundError,
)
from starlette.responses import RedirectResponse

from discord_rss_bot import settings
from discord_rss_bot.custom_filters import encode_url, entry_is_blacklisted, entry_is_whitelisted
from discord_rss_bot.custom_message import (
    CustomEmbed,
    get_custom_message,
    get_embed,
    get_images_from_entry,
    replace_tags_in_text_message,
    save_embed,
)
from discord_rss_bot.feeds import create_feed, get_entry_from_id, send_entry_to_discord, send_to_discord
from discord_rss_bot.filter.blacklist import get_blacklist_content, get_blacklist_summary, get_blacklist_title
from discord_rss_bot.filter.whitelist import get_whitelist_content, get_whitelist_summary, get_whitelist_title
from discord_rss_bot.markdown import convert_html_to_md
from discord_rss_bot.missing_tags import add_missing_tags
from discord_rss_bot.search import create_html_for_search_results
from discord_rss_bot.settings import get_reader
from discord_rss_bot.webhook import add_webhook, remove_webhook

app: FastAPI = FastAPI()
app.mount("/static", StaticFiles(directory="discord_rss_bot/static"), name="static")
templates: Jinja2Templates = Jinja2Templates(directory="discord_rss_bot/templates")

reader: Reader = get_reader()

# Add the filters to the Jinja2 environment so they can be used in html templates.
templates.env.filters["encode_url"] = encode_url
templates.env.filters["entry_is_whitelisted"] = entry_is_whitelisted
templates.env.filters["entry_is_blacklisted"] = entry_is_blacklisted
templates.env.filters["discord_markdown"] = convert_html_to_md


@app.post("/add_webhook")
async def post_add_webhook(webhook_name=Form(), webhook_url=Form()):
    """
    Add a feed to the database.

    Args:
        webhook_name: The name of the webhook.
        webhook_url: The url of the webhook.
    """
    if add_webhook(reader, webhook_name, webhook_url):
        return RedirectResponse(url="/", status_code=303)


@app.post("/delete_webhook")
async def post_delete_webhook(webhook_url=Form()):
    """
    Delete a webhook from the database.

    Args:
        webhook_url: The url of the webhook.
    """
    if remove_webhook(reader, webhook_url):
        return RedirectResponse(url="/", status_code=303)


@app.post("/add")
async def post_create_feed(feed_url=Form(), webhook_dropdown=Form()):
    """
    Add a feed to the database.

    Args:
        feed_url: The feed to add.
        webhook_dropdown: The webhook to use.

    Returns:
        dict: The feed that was added.
    """
    create_feed(reader, feed_url, webhook_dropdown)
    return RedirectResponse(url=f"/feed/?feed_url={feed_url}", status_code=303)


@app.post("/pause")
async def post_pause_feed(feed_url=Form()):
    """Pause a feed.

    Args:
        feed_url: The feed to pause.
    """
    reader.disable_feed_updates(feed_url)
    return RedirectResponse(url=f"/feed/?feed_url={urllib.parse.quote(feed_url)}", status_code=303)


@app.post("/unpause")
async def post_unpause_feed(feed_url=Form()):
    """Unpause a feed.

    Args:
        feed_url: The Feed to unpause.
    """
    reader.enable_feed_updates(feed_url)
    return RedirectResponse(url=f"/feed/?feed_url={urllib.parse.quote(feed_url)}", status_code=303)


@app.post("/whitelist")
async def post_set_whitelist(
    whitelist_title=Form(None),
    whitelist_summary=Form(None),
    whitelist_content=Form(None),
    feed_url=Form(),
):
    """Set what the whitelist should be sent, if you have this set only words in the whitelist will be sent.

    Args:
        whitelist_title: Whitelisted words for when checking the title.
        whitelist_summary: Whitelisted words for when checking the title.
        whitelist_content: Whitelisted words for when checking the title.
        feed_url: The feed we should set the whitelist for.
    """
    if whitelist_title:
        reader.set_tag(feed_url, "whitelist_title", whitelist_title)
    if whitelist_summary:
        reader.set_tag(feed_url, "whitelist_summary", whitelist_summary)
    if whitelist_content:
        reader.set_tag(feed_url, "whitelist_content", whitelist_content)

    return RedirectResponse(url=f"/feed/?feed_url={urllib.parse.quote(feed_url)}", status_code=303)


@app.get("/whitelist", response_class=HTMLResponse)
async def get_whitelist(feed_url, request: Request):
    """Get the whitelist.

    Args:
        feed_url: What feed we should get the whitelist for.
        request: The HTTP request.
    """
    feed: Feed = reader.get_feed(urllib.parse.unquote(feed_url))

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
    return templates.TemplateResponse("whitelist.html", context)


@app.post("/blacklist")
async def post_set_blacklist(
    blacklist_title=Form(None),
    blacklist_summary=Form(None),
    blacklist_content=Form(None),
    feed_url=Form(),
):
    """Set the blacklist, if this is set we will check if words are in the title, summary or content
    and then don't send that entry.

    Args:
        blacklist_title: Blacklisted words for when checking the title.
        blacklist_summary: Blacklisted words for when checking the summary.
        blacklist_content: Blacklisted words for when checking the content.
        feed_url: What feed we should set the blacklist for.
    """
    if blacklist_title:
        reader.set_tag(feed_url, "blacklist_title", blacklist_title)
    if blacklist_summary:
        reader.set_tag(feed_url, "blacklist_summary", blacklist_summary)
    if blacklist_content:
        reader.set_tag(feed_url, "blacklist_content", blacklist_content)

    return RedirectResponse(url=f"/feed/?feed_url={urllib.parse.quote(feed_url)}", status_code=303)


@app.get("/blacklist", response_class=HTMLResponse)
async def get_blacklist(feed_url, request: Request):
    feed: Feed = reader.get_feed(urllib.parse.unquote(feed_url))

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
    return templates.TemplateResponse("blacklist.html", context)


@app.post("/custom")
async def post_set_custom(custom_message=Form(""), feed_url=Form()):
    """
    Set the custom message, this is used when sending the message.

    Args:
        custom_message: The custom message.
        feed_url: The feed we should set the custom message for.
    """
    if custom_message := custom_message.strip():
        reader.set_tag(feed_url, "custom_message", custom_message)  # type: ignore
    else:
        reader.set_tag(feed_url, "custom_message", settings.default_custom_message)  # type: ignore

    clean_url: str = urllib.parse.quote(feed_url)

    return RedirectResponse(url=f"/feed/?feed_url={clean_url}", status_code=303)


@app.get("/custom", response_class=HTMLResponse)
async def get_custom(feed_url, request: Request):
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

    context = {"request": request, "feed": feed, "custom_message": custom_message}

    # Get the first entry, this is used to show the user what the custom message will look like.
    entries: Iterable[Entry] = reader.get_entries(feed=feed, limit=1)

    for entry in entries:
        # Append to context.
        context["entry"] = entry
    return templates.TemplateResponse("custom.html", context)


@app.get("/embed", response_class=HTMLResponse)
async def get_embed_page(feed_url, request: Request):
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
    embed: CustomEmbed = get_embed(reader, feed)

    context = {
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

    # Get the first entry, this is used to show the user what the custom message will look like.
    entries: Iterable[Entry] = reader.get_entries(feed=feed, limit=1)

    if custom_embed := get_embed(reader, feed_url):
        context["custom_embed"] = custom_embed

    for entry in entries:
        # Append to context.
        context["entry"] = entry
    return templates.TemplateResponse("embed.html", context)


@app.post("/embed", response_class=HTMLResponse)
async def post_embed(
    feed_url=Form(),
    title=Form(""),
    description=Form(""),
    color=Form(""),
    image_url=Form(""),
    thumbnail_url=Form(""),
    author_name=Form(""),
    author_url=Form(""),
    author_icon_url=Form(""),
    footer_text=Form(""),
    footer_icon_url=Form(""),
):
    """Set the embed settings.

    Args:
        feed_url: What feed we should get the custom message for.
        request: The HTTP request.

    Returns:
        custom.html
    """

    # Make feed_url a valid URL.
    url: str = urllib.parse.unquote(feed_url)

    feed: Feed = reader.get_feed(url)

    custom_embed: CustomEmbed = get_embed(reader, feed)

    # Get the data from the form.
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
    save_embed(reader, feed_url, custom_embed)

    clean_url: str = urllib.parse.quote(feed_url)

    return RedirectResponse(url=f"/feed/?feed_url={clean_url}", status_code=303)


@app.post("/use_embed")
async def post_use_embed(feed_url=Form()):
    url: str = urllib.parse.unquote(feed_url)

    feed: Feed = reader.get_feed(url)
    reader.set_tag(feed, "should_send_embed", True)  # type: ignore
    return RedirectResponse(url=f"/feed/?feed_url={feed_url}", status_code=303)


@app.post("/use_text")
async def post_use_text(feed_url=Form()):
    url: str = urllib.parse.unquote(feed_url)

    feed: Feed = reader.get_feed(url)
    reader.set_tag(feed, "should_send_embed", False)  # type: ignore
    return RedirectResponse(url=f"/feed/?feed_url={feed_url}", status_code=303)


@app.get("/add", response_class=HTMLResponse)
def get_add(request: Request):
    """
    Page for adding a new feed.

    Args:
        request: The request.
    """
    context = make_context_index(request)
    return templates.TemplateResponse("add.html", context)


@app.get("/feed", response_class=HTMLResponse)
async def get_feed(feed_url, request: Request):
    """
    Get a feed by URL.

    Args:
        request: The request.
        feed_url: The feed to add.
    """
    # Make feed_url a valid URL.
    url: str = urllib.parse.unquote(feed_url)

    feed: Feed = reader.get_feed(url)

    # Get entries from the feed.
    entries: Iterable[Entry] = reader.get_entries(feed=url)

    # Get the entries in the feed.
    feed_counts: FeedCounts = reader.get_feed_counts(feed=url)

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
        "feed_counts": feed_counts,
        "html": html,
        "should_send_embed": should_send_embed,
    }
    return templates.TemplateResponse("feed.html", context)


def create_html_for_feed(entries: Iterable[Entry]) -> str:
    """Create HTML for the search results.

    Args:
        search_results: The search results.
        custom_reader: The reader. If None, we will get the reader from the settings.
    """
    html: str = ""
    for entry in entries:

        # Get first image.
        first_image = ""
        first_image_text = ""
        if images := get_images_from_entry(entry=entry):
            first_image: str = images[0][0]
            first_image_text: str = images[0][1]

        # Get the text from the entry.
        text = replace_tags_in_text_message(entry.feed, entry)
        if not text:
            text = "<div class='text-muted'>No content available.</div>"

        published = ""
        if entry.published:
            published: str = entry.published.strftime("%Y-%m-%d %H:%M:%S")

        blacklisted = ""
        if entry_is_blacklisted(entry):
            blacklisted = "<span class='badge bg-danger'>Blacklisted</span>"

        whitelisted = ""
        if entry_is_whitelisted(entry):
            whitelisted = "<span class='badge bg-success'>Whitelisted</span>"

        entry_id: str = urllib.parse.quote(entry.id)
        to_disord_html: str = f"<a class='text-muted' href='/post_entry?entry_id={entry_id}'>Send to Discord</a>"
        image_html: str = f"<img src='{first_image}' class='img-fluid' alt='{first_image_text}'>" if first_image else ""

        html += f"""<div class="p-2 mb-2 border border-dark">
{blacklisted}{whitelisted}<a class="text-muted text-decoration-none" href="{entry.link}"><h2>{entry.title}</h2></a>
{f"By { entry.author } @" if entry.author else ""}{published} - {to_disord_html}

{text}
{image_html}
</div>
"""

    return html.strip()


@app.get("/add_webhook", response_class=HTMLResponse)
async def get_add_webhook(request: Request):
    """
    Page for adding a new webhook.

    Args:
        request: The request.
    """
    return templates.TemplateResponse("add_webhook.html", {"request": request})


@dataclass()
class WebhookInfo:
    custom_name: str
    url: str
    type: int | None = None
    id: str | None = None
    name: str | None = None
    avatar: str | None = None
    channel_id: str | None = None
    guild_id: str | None = None
    token: str | None = None


@lru_cache()
def get_data_from_hook_url(hook_name: str, hook_url: str):
    our_hook: WebhookInfo = WebhookInfo(custom_name=hook_name, url=hook_url)

    if hook_url:
        response: Response = httpx.get(hook_url)
        if response.status_code == 200:
            webhook_json = json.loads(response.text)
            our_hook.type = webhook_json["type"] or None
            our_hook.id = webhook_json["id"] or None
            our_hook.name = webhook_json["name"] or None
            our_hook.avatar = webhook_json["avatar"] or None
            our_hook.channel_id = webhook_json["channel_id"] or None
            our_hook.guild_id = webhook_json["guild_id"] or None
            our_hook.token = webhook_json["token"] or None
    return our_hook


@app.get("/webhooks", response_class=HTMLResponse)
async def get_webhooks(request: Request):
    """
    Page for adding a new webhook.

    Args:
        request: The request.
    """
    hooks: Dict[str, str] = reader.get_tag((), "webhooks", "")  # type: ignore
    hooks_with_data = []

    for hook in hooks:
        hook_url: str = hook["url"]  # type: ignore
        hook_name: str = hook["name"]  # type: ignore
        our_hook: WebhookInfo = get_data_from_hook_url(hook_url=hook_url, hook_name=hook_name)
        hooks_with_data.append(our_hook)
    return templates.TemplateResponse(
        "webhooks.html",
        {
            "request": request,
            "hooks_with_data": hooks_with_data,
        },
    )


@app.get("/", response_class=HTMLResponse)
def get_index(request: Request):
    """
    This is the root of the website.

    Args:
        request: The request.
    """
    context = make_context_index(request)
    return templates.TemplateResponse("index.html", context)


def make_context_index(request: Request):
    """
    Create the needed context for the index page.

    Used by / and /add.
    Args:
        request: The request.
    """
    # Get webhooks name and url from the database.
    try:
        hooks: list[dict] = reader.get_tag((), "webhooks")  # type: ignore
    except TagNotFoundError:
        hooks = []

    feed_list = []
    broken_feeds = []
    feeds_without_corresponding_webhook = []

    feeds: Iterable[Feed] = reader.get_feeds()
    for feed in feeds:
        try:
            webhook = reader.get_tag(feed.url, "webhook")
            feed_list.append({"feed": feed, "webhook": webhook})
        except TagNotFoundError:
            broken_feeds.append(feed)
            continue

        webhook_list = [hook["url"] for hook in hooks]
        if webhook not in webhook_list:
            feeds_without_corresponding_webhook.append(feed)

    # Sort feed_list by when the feed was added.
    feed_list.sort(key=lambda x: x["feed"].added)

    feed_count: FeedCounts = reader.get_feed_counts()
    entry_count: EntryCounts = reader.get_entry_counts()
    return {
        "request": request,
        "feeds": feed_list,
        "feed_count": feed_count,
        "entry_count": entry_count,
        "webhooks": hooks,
        "broken_feeds": broken_feeds,
        "feeds_without_corresponding_webhook": feeds_without_corresponding_webhook,
    }


@app.post("/remove", response_class=HTMLResponse)
async def remove_feed(feed_url=Form()):
    """
    Get a feed by URL.

    Args:
        feed_url: The feed to add.
    """
    # Unquote the url
    unquoted_feed_url: str = urllib.parse.unquote(feed_url)
    try:
        reader.delete_feed(unquoted_feed_url)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail="Feed not found") from e

    reader.update_search()

    return RedirectResponse(url="/", status_code=303)


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, query: str):
    """
    Get entries matching a full-text search query.

    Args:
        request: The request.
        query: The query to search for.
    """
    reader.update_search()
    search_results: Iterable[EntrySearchResult] = reader.search_entries(query)
    search_amount: EntrySearchCounts = reader.search_entry_counts(query)

    search_html: str = create_html_for_search_results(search_results)

    context = {
        "request": request,
        "search_html": search_html,
        "query": query,
        "search_amount": search_amount,
    }
    return templates.TemplateResponse("search.html", context)


@app.get("/post_entry", response_class=HTMLResponse)
async def post_entry(entry_id: str):
    """
    Send a feed to Discord."""
    # Unquote the entry id.
    unquoted_entry_id: str = urllib.parse.unquote(entry_id)

    print(f"Sending entry '{unquoted_entry_id}' to Discord.")
    entry: Entry | None = get_entry_from_id(entry_id=unquoted_entry_id)
    if entry is None:
        return {"error": f"Failed to get entry '{entry_id}' when posting to Discord."}

    if result := send_entry_to_discord(entry=entry):
        return result

    # Redirect to the feed page.
    clean_url: str = entry.feed.url.strip()
    return RedirectResponse(url=f"/feed/?feed_url={clean_url}", status_code=303)


@app.on_event("startup")
def startup() -> None:
    """This is called when the server starts.

    It reads the settings file and starts the scheduler."""
    add_missing_tags(reader=reader)

    scheduler: BackgroundScheduler = BackgroundScheduler()

    # Update all feeds every 15 minutes.
    # TODO: Make this configurable.
    scheduler.add_job(send_to_discord, "interval", minutes=15, next_run_time=datetime.now())
    scheduler.start()


if __name__ == "__main__":
    # TODO: Make this configurable.
    uvicorn.run("main:app", log_level="info", host="0.0.0.0", port=5000, proxy_headers=True, forwarded_allow_ips="*")
