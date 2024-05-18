from __future__ import annotations

import json
import typing
import urllib.parse
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import TYPE_CHECKING, cast

import httpx
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from httpx import Response
from reader import Entry, Feed, FeedNotFoundError, Reader, TagNotFoundError
from reader.types import JSONType
from starlette.responses import RedirectResponse

from discord_rss_bot import settings
from discord_rss_bot.custom_filters import (
    encode_url,
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
from discord_rss_bot.feeds import create_feed, send_entry_to_discord, send_to_discord
from discord_rss_bot.markdown import convert_html_to_md
from discord_rss_bot.missing_tags import add_missing_tags
from discord_rss_bot.search import create_html_for_search_results
from discord_rss_bot.settings import get_reader
from discord_rss_bot.webhook import add_webhook, remove_webhook

if TYPE_CHECKING:
    from collections.abc import Iterable


reader: Reader = get_reader()


@asynccontextmanager
async def lifespan(app: FastAPI) -> typing.AsyncGenerator[None, None]:
    """This is needed for the ASGI server to run."""
    add_missing_tags(reader=reader)
    scheduler: AsyncIOScheduler = AsyncIOScheduler()

    # Update all feeds every 15 minutes.
    # TODO(TheLovinator): Make this configurable.
    scheduler.add_job(send_to_discord, "interval", minutes=15, next_run_time=datetime.now(tz=timezone.utc))
    scheduler.start()
    yield
    reader.close()
    scheduler.shutdown(wait=True)


app: FastAPI = FastAPI()
app.mount("/static", StaticFiles(directory="discord_rss_bot/static"), name="static")
templates: Jinja2Templates = Jinja2Templates(directory="discord_rss_bot/templates")


# Add the filters to the Jinja2 environment so they can be used in html templates.
templates.env.filters["encode_url"] = encode_url
templates.env.filters["entry_is_whitelisted"] = entry_is_whitelisted
templates.env.filters["entry_is_blacklisted"] = entry_is_blacklisted
templates.env.filters["discord_markdown"] = convert_html_to_md


@app.post("/add_webhook")
async def post_add_webhook(webhook_name: str = Form(), webhook_url: str = Form()) -> RedirectResponse:
    """Add a feed to the database.

    Args:
        webhook_name: The name of the webhook.
        webhook_url: The url of the webhook.
    """
    add_webhook(reader, webhook_name, webhook_url)
    return RedirectResponse(url="/", status_code=303)


@app.post("/delete_webhook")
async def post_delete_webhook(webhook_url: str = Form()) -> RedirectResponse:
    """Delete a webhook from the database.

    Args:
        webhook_url: The url of the webhook.
    """
    # TODO(TheLovinator): Check if the webhook is in use by any feeds before deleting it.
    remove_webhook(reader, webhook_url)
    return RedirectResponse(url="/", status_code=303)


@app.post("/add")
async def post_create_feed(feed_url: str = Form(), webhook_dropdown: str = Form()) -> RedirectResponse:
    """Add a feed to the database.

    Args:
        feed_url: The feed to add.
        webhook_dropdown: The webhook to use.
    """
    clean_feed_url: str = feed_url.strip()
    create_feed(reader, feed_url, webhook_dropdown)
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/pause")
async def post_pause_feed(feed_url: str = Form()) -> RedirectResponse:
    """Pause a feed.

    Args:
        feed_url: The feed to pause.
    """
    clean_feed_url: str = feed_url.strip()
    reader.disable_feed_updates(clean_feed_url)
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/unpause")
async def post_unpause_feed(feed_url: str = Form()) -> RedirectResponse:
    """Unpause a feed.

    Args:
        feed_url: The Feed to unpause.
    """
    clean_feed_url: str = feed_url.strip()
    reader.enable_feed_updates(clean_feed_url)
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/whitelist")
async def post_set_whitelist(
    whitelist_title: str = Form(None),
    whitelist_summary: str = Form(None),
    whitelist_content: str = Form(None),
    whitelist_author: str = Form(None),
    feed_url: str = Form(),
) -> RedirectResponse:
    """Set what the whitelist should be sent, if you have this set only words in the whitelist will be sent.

    Args:
        whitelist_title: Whitelisted words for when checking the title.
        whitelist_summary: Whitelisted words for when checking the summary.
        whitelist_content: Whitelisted words for when checking the content.
        whitelist_author: Whitelisted words for when checking the author.
        feed_url: The feed we should set the whitelist for.
    """
    clean_feed_url: str = feed_url.strip()
    if whitelist_title:
        reader.set_tag(clean_feed_url, "whitelist_title", whitelist_title)  # type: ignore[call-overload]
    if whitelist_summary:
        reader.set_tag(clean_feed_url, "whitelist_summary", whitelist_summary)  # type: ignore[call-overload]
    if whitelist_content:
        reader.set_tag(clean_feed_url, "whitelist_content", whitelist_content)  # type: ignore[call-overload]
    if whitelist_author:
        reader.set_tag(clean_feed_url, "whitelist_author", whitelist_author)  # type: ignore[call-overload]

    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.get("/whitelist", response_class=HTMLResponse)
async def get_whitelist(feed_url: str, request: Request):
    """Get the whitelist.

    Args:
        feed_url: What feed we should get the whitelist for.
        request: The request object.
    """
    clean_feed_url: str = feed_url.strip()
    feed: Feed = reader.get_feed(urllib.parse.unquote(clean_feed_url))

    # Get previous data, this is used when creating the form.
    whitelist_title: str = str(reader.get_tag(feed, "whitelist_title", ""))
    whitelist_summary: str = str(reader.get_tag(feed, "whitelist_summary", ""))
    whitelist_content: str = str(reader.get_tag(feed, "whitelist_content", ""))
    whitelist_author: str = str(reader.get_tag(feed, "whitelist_author", ""))

    context = {
        "request": request,
        "feed": feed,
        "whitelist_title": whitelist_title,
        "whitelist_summary": whitelist_summary,
        "whitelist_content": whitelist_content,
        "whitelist_author": whitelist_author,
    }
    return templates.TemplateResponse(request=request, name="whitelist.html", context=context)


@app.post("/blacklist")
async def post_set_blacklist(
    blacklist_title: str = Form(None),
    blacklist_summary: str = Form(None),
    blacklist_content: str = Form(None),
    blacklist_author: str = Form(None),
    feed_url: str = Form(),
) -> RedirectResponse:
    """Set the blacklist.

    If this is set we will check if words are in the title, summary or content
    and then don't send that entry.

    Args:
        blacklist_title: Blacklisted words for when checking the title.
        blacklist_summary: Blacklisted words for when checking the summary.
        blacklist_content: Blacklisted words for when checking the content.
        blacklist_author: Blacklisted words for when checking the author.
        feed_url: What feed we should set the blacklist for.
    """
    clean_feed_url: str = feed_url.strip()
    if blacklist_title:
        reader.set_tag(clean_feed_url, "blacklist_title", blacklist_title)  # type: ignore[call-overload]
    if blacklist_summary:
        reader.set_tag(clean_feed_url, "blacklist_summary", blacklist_summary)  # type: ignore[call-overload]
    if blacklist_content:
        reader.set_tag(clean_feed_url, "blacklist_content", blacklist_content)  # type: ignore[call-overload]
    if blacklist_author:
        reader.set_tag(clean_feed_url, "blacklist_author", blacklist_author)  # type: ignore[call-overload]

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

    # Get previous data, this is used when creating the form.
    blacklist_title: str = str(reader.get_tag(feed, "blacklist_title", ""))
    blacklist_summary: str = str(reader.get_tag(feed, "blacklist_summary", ""))
    blacklist_content: str = str(reader.get_tag(feed, "blacklist_content", ""))
    blacklist_author: str = str(reader.get_tag(feed, "blacklist_author", ""))

    context = {
        "request": request,
        "feed": feed,
        "blacklist_title": blacklist_title,
        "blacklist_summary": blacklist_summary,
        "blacklist_content": blacklist_content,
        "blacklist_author": blacklist_author,
    }
    return templates.TemplateResponse(request=request, name="blacklist.html", context=context)


@app.post("/custom")
async def post_set_custom(custom_message: str = Form(""), feed_url: str = Form()) -> RedirectResponse:
    """Set the custom message, this is used when sending the message.

    Args:
        custom_message: The custom message.
        feed_url: The feed we should set the custom message for.
    """
    our_custom_message: JSONType | str = custom_message.strip()
    our_custom_message = typing.cast(JSONType, our_custom_message)

    default_custom_message: JSONType | str = settings.default_custom_message
    default_custom_message = typing.cast(JSONType, default_custom_message)

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

    return templates.TemplateResponse(request=request, name="custom.html", context=context)


@app.get("/embed", response_class=HTMLResponse)
async def get_embed_page(feed_url: str, request: Request):
    """Get the custom message. This is used when sending the message to Discord.

    Args:
        feed_url: What feed we should get the custom message for.
        request: The request object.
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
    return templates.TemplateResponse(request=request, name="embed.html", context=context)


@app.post("/embed", response_class=HTMLResponse)
async def post_embed(  # noqa: PLR0913, PLR0917
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
async def post_use_embed(feed_url: str = Form()) -> RedirectResponse:
    """Use embed instead of text.

    Args:
        feed_url: The feed to change.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.set_tag(clean_feed_url, "should_send_embed", True)  # type: ignore
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.post("/use_text")
async def post_use_text(feed_url: str = Form()) -> RedirectResponse:
    """Use text instead of embed.

    Args:
        feed_url: The feed to change.

    Returns:
        RedirectResponse: Redirect to the feed page.
    """
    clean_feed_url: str = feed_url.strip()
    reader.set_tag(clean_feed_url, "should_send_embed", False)  # type: ignore
    return RedirectResponse(url=f"/feed?feed_url={urllib.parse.quote(clean_feed_url)}", status_code=303)


@app.get("/add", response_class=HTMLResponse)
def get_add(request: Request):
    """Page for adding a new feed."""
    context = {
        "request": request,
        "webhooks": reader.get_tag((), "webhooks", []),
    }
    return templates.TemplateResponse(request=request, name="add.html", context=context)


@app.get("/feed", response_class=HTMLResponse)
async def get_feed(feed_url: str, request: Request, starting_after: str | None = None):
    """Get a feed by URL.

    Args:
        feed_url: The feed to add.
        request: The request object.
        starting_after: The entry to start after. Used for pagination.

    Returns:
        HTMLResponse: The feed page.
    """
    clean_feed_url: str = urllib.parse.unquote(feed_url.strip())

    feed: Feed = reader.get_feed(clean_feed_url)

    # Get entries from the feed.
    entries: typing.Iterable[Entry] = reader.get_entries(feed=clean_feed_url, limit=10)

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
        "show_more_button": True,
    }
    return templates.TemplateResponse(request=request, name="feed.html", context=context)


@app.get("/feed_more", response_class=HTMLResponse)
async def get_all_entries(feed_url: str, request: Request):
    """Get a feed by URL and show more entries.

    Args:
        feed_url: The feed to add.
        request: The request object.
        starting_after: The entry to start after. Used for pagination.

    Returns:
        HTMLResponse: The feed page.
    """
    clean_feed_url: str = urllib.parse.unquote(feed_url.strip())

    feed: Feed = reader.get_feed(clean_feed_url)

    # Get entries from the feed.
    entries: typing.Iterable[Entry] = reader.get_entries(feed=clean_feed_url, limit=200)

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
        "show_more_button": False,
    }
    return templates.TemplateResponse(request=request, name="feed.html", context=context)


def create_html_for_feed(entries: Iterable[Entry]) -> str:
    """Create HTML for the search results.

    Args:
        entries: The entries to create HTML for.
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
        image_html: str = f"<img src='{first_image}' class='img-fluid'>" if first_image else ""

        html += f"""<div class="p-2 mb-2 border border-dark">
{blacklisted}{whitelisted}<a class="text-muted text-decoration-none" href="{entry.link}"><h2>{entry.title}</h2></a>
{f"By {entry.author} @" if entry.author else ""}{published} - {to_discord_html}

{text}
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
    hooks_with_data = []

    for hook in list(reader.get_tag((), "webhooks", [])):
        our_hook: WebhookInfo = get_data_from_hook_url(hook_url=hook["url"], hook_name=hook["name"])  # type: ignore
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
    hooks: list[dict] = list(reader.get_tag((), "webhooks", []))  # type: ignore

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
    """Get a feed by URL.

    Args:
        feed_url: The feed to add.

    Returns:
        RedirectResponse: Redirect to the index page.
    """
    try:
        reader.delete_feed(urllib.parse.unquote(feed_url))
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail="Feed not found") from e

    return RedirectResponse(url="/", status_code=303)


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
def modify_webhook(old_hook: str = Form(), new_hook: str = Form()):
    """Modify a webhook.

    Args:
        old_hook: The webhook to modify.
        new_hook: The new webhook.

    Raises:
        HTTPException: Webhook could not be modified.
    """
    # Get current webhooks from the database if they exist otherwise use an empty list.
    webhooks = list(reader.get_tag((), "webhooks", []))

    # Webhooks are stored as a list of dictionaries.
    # Example: [{"name": "webhook_name", "url": "webhook_url"}]
    webhooks = cast(list[dict[str, str]], webhooks)

    for hook in webhooks:
        if hook["url"] in old_hook.strip():
            hook["url"] = new_hook.strip()

            # Check if it has been modified.
            if hook["url"] != new_hook.strip():
                raise HTTPException(status_code=500, detail="Webhook could not be modified")

            # Add our new list of webhooks to the database.
            reader.set_tag((), "webhooks", webhooks)  # type: ignore

            # Loop through all feeds and update the webhook if it
            # matches the old one.
            feeds: Iterable[Feed] = reader.get_feeds()
            for feed in feeds:
                try:
                    webhook = reader.get_tag(feed, "webhook")
                except TagNotFoundError:
                    continue

                if webhook == old_hook.strip():
                    reader.set_tag(feed.url, "webhook", new_hook.strip())  # type: ignore

    # Redirect to the webhook page.
    return RedirectResponse(url="/webhooks", status_code=303)


if __name__ == "__main__":
    # TODO(TheLovinator): Make this configurable.
    uvicorn.run(
        "main:app",
        log_level="info",
        host="0.0.0.0",  # noqa: S104
        port=5000,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
