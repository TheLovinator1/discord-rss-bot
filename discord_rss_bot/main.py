import json
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Iterable

import httpx
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from httpx import Response
from reader import Entry, Feed, FeedNotFoundError, Reader, TagNotFoundError
from starlette.responses import RedirectResponse

from discord_rss_bot import settings
from discord_rss_bot.custom_filters import encode_url, entry_is_blacklisted, entry_is_whitelisted
from discord_rss_bot.custom_message import (
    CustomEmbed,
    get_custom_message,
    get_embed,
    get_image,
    replace_tags_in_text_message,
    save_embed,
)
from discord_rss_bot.feeds import create_feed, send_entry_to_discord, send_to_discord
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
async def post_add_webhook(webhook_name: str = Form(), webhook_url: str = Form()):
    """
    Add a feed to the database.

    Args:
        webhook_name: The name of the webhook.
        webhook_url: The url of the webhook.
    """
    if add_webhook(reader, webhook_name, webhook_url):
        return RedirectResponse(url="/", status_code=303)


@app.post("/delete_webhook")
async def post_delete_webhook(webhook_url: str = Form()):
    """
    Delete a webhook from the database.

    Args:
        webhook_url: The url of the webhook.
    """
    if remove_webhook(reader, webhook_url):
        return RedirectResponse(url="/", status_code=303)


@app.post("/add")
async def post_create_feed(feed_url: str = Form(), webhook_dropdown: str = Form()):
    """
    Add a feed to the database.

    Args:
        feed_url: The feed to add.
        webhook_dropdown: The webhook to use.
    """
    create_feed(reader, feed_url, webhook_dropdown)
    return RedirectResponse(url=f"/feed/?feed_url={feed_url}", status_code=303)


@app.post("/pause")
async def post_pause_feed(feed_url: str = Form()):
    """Pause a feed.

    Args:
        feed_url: The feed to pause.
    """
    clean_feed_url: str = feed_url.strip()
    reader.disable_feed_updates(clean_feed_url)
    return RedirectResponse(url=f"/feed/?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/unpause")
async def post_unpause_feed(feed_url: str = Form()):
    """Unpause a feed.

    Args:
        feed_url: The Feed to unpause.
    """
    clean_feed_url: str = feed_url.strip()
    reader.enable_feed_updates(clean_feed_url)
    return RedirectResponse(url=f"/feed/?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/whitelist")
async def post_set_whitelist(
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
    """
    clean_feed_url: str = feed_url.strip()
    if whitelist_title:
        reader.set_tag(clean_feed_url, "whitelist_title", whitelist_title)  # type: ignore
    if whitelist_summary:
        reader.set_tag(clean_feed_url, "whitelist_summary", whitelist_summary)  # type: ignore
    if whitelist_content:
        reader.set_tag(clean_feed_url, "whitelist_content", whitelist_content)  # type: ignore

    return RedirectResponse(url=f"/feed/?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.get("/whitelist", response_class=HTMLResponse)
async def get_whitelist(feed_url: str, request: Request):
    """Get the whitelist.

    Args:
        feed_url: What feed we should get the whitelist for.
    """
    clean_feed_url: str = feed_url.strip()
    feed: Feed = reader.get_feed(urllib.parse.unquote(clean_feed_url))

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
    """
    clean_feed_url = feed_url.strip()
    if blacklist_title:
        reader.set_tag(clean_feed_url, "blacklist_title", blacklist_title)  # type: ignore
    if blacklist_summary:
        reader.set_tag(clean_feed_url, "blacklist_summary", blacklist_summary)  # type: ignore
    if blacklist_content:
        reader.set_tag(clean_feed_url, "blacklist_content", blacklist_content)  # type: ignore

    return RedirectResponse(url=f"/feed/?feed_url={urllib.parse.quote(feed_url)}", status_code=303)


@app.get("/blacklist", response_class=HTMLResponse)
async def get_blacklist(feed_url: str, request: Request):
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
async def post_set_custom(custom_message: str = Form(""), feed_url: str = Form()):
    """
    Set the custom message, this is used when sending the message.

    Args:
        custom_message: The custom message.
        feed_url: The feed we should set the custom message for.
    """
    if custom_message:
        reader.set_tag(feed_url, "custom_message", custom_message.strip())  # type: ignore
    else:
        reader.set_tag(feed_url, "custom_message", settings.default_custom_message)  # type: ignore

    return RedirectResponse(url=f"/feed/?feed_url={urllib.parse.quote(feed_url)}", status_code=303)


@app.get("/custom", response_class=HTMLResponse)
async def get_custom(feed_url: str, request: Request):
    """Get the custom message. This is used when sending the message to Discord.

    Args:
        feed_url: What feed we should get the custom message for.
    """
    feed: Feed = reader.get_feed(urllib.parse.unquote(feed_url.strip()))

    context = {
        "request": request,
        "feed": feed,
        "custom_message": get_custom_message(reader, feed),
    }

    # Get the first entry, this is used to show the user what the custom message will look like.
    for entry in reader.get_entries(feed=feed, limit=1):
        context["entry"] = entry

    return templates.TemplateResponse("custom.html", context)


@app.get("/embed", response_class=HTMLResponse)
async def get_embed_page(feed_url: str, request: Request):
    """Get the custom message. This is used when sending the message to Discord.

    Args:
        feed_url: What feed we should get the custom message for.
    """
    feed: Feed = reader.get_feed(urllib.parse.unquote(feed_url.strip()))

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
    if custom_embed := get_embed(reader, feed):
        context["custom_embed"] = custom_embed

    for entry in reader.get_entries(feed=feed, limit=1):
        # Append to context.
        context["entry"] = entry
    return templates.TemplateResponse("embed.html", context)


@app.post("/embed", response_class=HTMLResponse)
async def post_embed(
    feed_url: str = Form(),
    title: str = Form(""),
    description: str = Form(""),
    color: str = Form(""),
    image_url: str = Form(""),
    thumbnail_url: str = Form(""),
    author_name: str = Form(""),
    author_url: str = Form(""),
    author_icon_url: str = Form(""),
    footer_text: str = Form(""),
    footer_icon_url: str = Form(""),
):
    """Set the embed settings.

    Args:
        feed_url: What feed we should get the custom message for.
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

    return RedirectResponse(url=f"/feed/?feed_url={clean_feed_url}", status_code=303)


@app.post("/use_embed")
async def post_use_embed(feed_url: str = Form()):
    """Use embed instead of text.

    Args:
        feed_url: The feed to change.
    """
    clean_feed_url: str = feed_url.strip()
    reader.set_tag(clean_feed_url, "should_send_embed", True)  # type: ignore
    return RedirectResponse(url=f"/feed/?feed_url={clean_feed_url}", status_code=303)


@app.post("/use_text")
async def post_use_text(feed_url: str = Form()):
    """Use text instead of embed.

    Args:
        feed_url: The feed to change.
    """
    clean_feed_url: str = feed_url.strip()
    reader.set_tag(clean_feed_url, "should_send_embed", False)  # type: ignore
    return RedirectResponse(url=f"/feed/?feed_url={clean_feed_url}", status_code=303)


@app.get("/add", response_class=HTMLResponse)
def get_add(request: Request):
    """Page for adding a new feed."""
    context = {
        "request": request,
        "webhooks": reader.get_tag((), "webhooks", []),
    }
    return templates.TemplateResponse("add.html", context)


@app.get("/feed", response_class=HTMLResponse)
async def get_feed(feed_url: str, request: Request):
    """
    Get a feed by URL.

    Args:
        feed_url: The feed to add.
    """
    clean_feed_url: str = urllib.parse.unquote(feed_url.strip())

    feed: Feed = reader.get_feed(clean_feed_url)

    # Get entries from the feed.
    entries: Iterable[Entry] = reader.get_entries(feed=clean_feed_url)

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
        first_image = ""
        summary: str | None = entry.summary
        content = ""
        if entry.content:
            for content_item in entry.content:
                content: str = content_item.value

        first_image = get_image(summary, content)

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
        to_disord_html: str = f"<a class='text-muted' href='/post_entry?entry_id={entry_id}'>Send to Discord</a>"
        image_html: str = f"<img src='{first_image}' class='img-fluid'>" if first_image else ""

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
    """Page for adding a new webhook."""
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
    """Page for adding a new webhook."""
    hooks_with_data = []

    for hook in reader.get_tag((), "webhooks", ""):
        our_hook: WebhookInfo = get_data_from_hook_url(hook_url=hook["url"], hook_name=hook["name"])  # type: ignore
        hooks_with_data.append(our_hook)

    context = {"request": request, "hooks_with_data": hooks_with_data}
    return templates.TemplateResponse("webhooks.html", context)


@app.get("/", response_class=HTMLResponse)
def get_index(request: Request):
    """This is the root of the website."""
    return templates.TemplateResponse("index.html", make_context_index(request))


def make_context_index(request: Request):
    """Create the needed context for the index page."""
    hooks: list[dict] = reader.get_tag((), "webhooks", [])  # type: ignore

    feed_list = []
    broken_feeds = []
    feeds_without_attached_webhook = []

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
async def remove_feed(feed_url: str = Form()):
    """
    Get a feed by URL.

    Args:
        feed_url: The feed to add.
    """
    try:
        reader.delete_feed(urllib.parse.unquote(feed_url))
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail="Feed not found") from e

    return RedirectResponse(url="/", status_code=303)


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, query: str):
    """
    Get entries matching a full-text search query.

    Args:
        query: The query to search for.
    """
    reader.update_search()

    context = {
        "request": request,
        "search_html": create_html_for_search_results(query),
        "query": query,
        "search_amount": reader.search_entry_counts(query),
    }
    return templates.TemplateResponse("search.html", context)


@app.get("/post_entry", response_class=HTMLResponse)
async def post_entry(entry_id: str):
    """Send single entry to Discord."""
    unquoted_entry_id: str = urllib.parse.unquote(entry_id)
    entry: Entry | None = next((entry for entry in reader.get_entries() if entry.id == unquoted_entry_id), None)
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

    It reads the settings file and starts the scheduler.
    """
    add_missing_tags(reader=reader)

    scheduler: BackgroundScheduler = BackgroundScheduler()

    # Update all feeds every 15 minutes.
    # TODO: Make this configurable.
    scheduler.add_job(send_to_discord, "interval", minutes=15, next_run_time=datetime.now())
    scheduler.start()


if __name__ == "__main__":
    # TODO: Make this configurable.
    uvicorn.run("main:app", log_level="info", host="0.0.0.0", port=5000, proxy_headers=True, forwarded_allow_ips="*")
