import enum
import sys
from functools import cache

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from reader import FeedExistsError

from discord_rss_bot.feeds import _check_feed
from discord_rss_bot.settings import logger, read_settings_file, reader

app = FastAPI()
templates = Jinja2Templates(directory="templates")


@cache
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Return favicon."""
    return FileResponse('static/favicon.ico')


@app.post("/check", response_class=HTMLResponse)
def check_feed(request: Request, feed_url: str = Form()):
    """Check all feeds"""
    reader.update_feeds()
    entry = reader.get_entries(feed=feed_url, read=False)
    _check_feed(entry, feed_url)

    logger.info(f"Get feed: {feed_url}")
    feed = reader.get_feed(feed_url)

    return templates.TemplateResponse("feed.html", {"request": request, "feed": feed})


@app.on_event('startup')
def startup():
    """This is called when the server starts.

    It reads the settings file and starts the scheduler."""
    settings = read_settings_file()

    if not settings["webhooks"]:
        logger.critical("No webhooks found in settings file.")
        sys.exit()
    for key in settings["webhooks"]:
        logger.info(f"Webhook name: {key} with URL: {settings['webhooks'][key]}")

    scheduler = BackgroundScheduler()
    scheduler.start()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """
    This is the root of the website.

    Args:
        request:

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
    for hook in hooks:
        logger.info(f"Webhook name: {hook.name}")

    feed_list = list()
    feeds = reader.get_feeds()
    for feed in feeds:
        feed_list.append(feed)

    feed_count = reader.get_feed_counts()
    entry_count = reader.get_entry_counts()
    context = {"request": request,
               "feeds": feed_list,
               "feed_count": feed_count,
               "entry_count": entry_count,
               "webhooks": hooks}
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

    logger.info(f"Get feed: {feed_url}")
    feed = reader.get_feed(feed_url)

    reader.delete_feed(feed_url)
    return templates.TemplateResponse("index.html", {"request": request, "feed": feed})


@app.post("/feed", response_class=HTMLResponse)
async def get_feed(request: Request, feed_url: str = Form()):
    """
    Get a feed by URL.

    Args:
        request: The request.
        feed_url: The feed to add.

    Returns:
        HTMLResponse: The HTML response.
    """
    logger.info(f"Get feed: {feed_url}")
    feed = reader.get_feed(feed_url)
    return templates.TemplateResponse("feed.html", {"request": request, "feed": feed})


def create_list_of_webhooks():
    """List with webhooks."""
    logger.info("Creating list with webhooks.")
    settings = read_settings_file()
    list_of_webhooks = dict()
    for hook in settings["webhooks"]:
        logger.info(f"Webhook name: {hook} with URL: {settings['webhooks'][hook]}")
        list_of_webhooks[hook] = settings["webhooks"][hook]

    logger.info(f"List of webhooks: {list_of_webhooks}")
    return enum.Enum("DiscordWebhooks", list_of_webhooks)


def get_hook_by_name(name):
    """Get a webhook by name."""
    settings = read_settings_file()
    logger.debug(f"Webhook name: {name} with URL: {settings['webhooks'][name]}")
    return settings["webhooks"][name]


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
    logger.info(f"Add feed: {feed_url}")
    logger.info(f"Webhook: {webhook_dropdown}")
    try:
        reader.add_feed(feed_url)
    except FeedExistsError as error:
        logger.error(f"Feed already exists: {error}")
        return {"error": "Feed already exists."}
    reader.update_feed(feed_url)
    webhook_url = get_hook_by_name(webhook_dropdown)
    reader.set_tag(feed_url, "webhook", webhook_url)

    new_tag = reader.get_tag(feed_url, "webhook")
    logger.info(f"New tag: {new_tag}")
    return {"feed_url": str(feed_url), "status": "added", "webhook": webhook_url}


@app.get("/add", response_class=HTMLResponse)
def get_add(request: Request):
    """
    This is the root of the website.

    Args:
        request:

    Returns:
        HTMLResponse: The HTML response.
    """
    context = make_context_index(request)
    return templates.TemplateResponse("add.html", context)


if __name__ == "__main__":
    uvicorn.run("main:app", log_level="debug")
