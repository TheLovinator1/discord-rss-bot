import logging

from apscheduler.schedulers.background import BackgroundScheduler
from discord_webhook import DiscordWebhook
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from reader import make_reader

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
reader = make_reader("db.sqlite")


@app.post("/check", response_class=HTMLResponse)
def read_check_feed(request: Request, feed_url: str = Form()):
    """Check all feeds"""
    reader.update_feeds()
    entry = reader.get_entries(feed=feed_url, read=False)
    _check_feed(entry)

    logger.info(f"Get feed: {feed_url}")
    feed = reader.get_feed(feed_url)

    return templates.TemplateResponse("feed.html", {"request": request, "feed": feed})


def check_feeds() -> None:
    """Check all feeds"""
    reader.update_feeds()
    entries = reader.get_entries(read=False)
    _check_feed(entries)


def check_feed(feed_url: str) -> None:
    """Check a single feed"""
    reader.update_feeds()
    entry = reader.get_entries(feed=feed_url, read=False)
    _check_feed(entry)


def _check_feed(entries):
    for entry in entries:
        reader.mark_entry_as_read(entry)
        print(f"New entry: {entry.title}")

        webhook_url = reader.get_tag((), "webhook")
        if webhook_url:
            print(f"Sending to webhook: {webhook_url}")
            webhook = DiscordWebhook(url=str(webhook_url), content=f":robot: :mega: New entry: {entry.title}\n"
                                                                   f"{entry.link}", rate_limit_retry=True)
            response = webhook.execute()
            if not response.ok:
                # TODO: Send error to discord
                print(f"Error: {response.status_code} {response.reason}")
                reader.mark_entry_as_unread(entry)


@app.on_event('startup')
def init_data():
    """Run on startup"""
    scheduler = BackgroundScheduler()
    scheduler.start()


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    """
    This is the root of the website.

    Args:
        request:

    Returns:
        HTMLResponse: The HTML response.
    """
    feeds = reader.get_feeds()
    feed_count = reader.get_feed_counts()
    entry_count = reader.get_entry_counts()
    context = {"request": request,
               "feeds": feeds,
               "feed_count": feed_count,
               "entry_count": entry_count}
    return templates.TemplateResponse("index.html", context)


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


@app.post("/global_webhook", response_class=HTMLResponse)
async def add_global_webhook(request: Request, webhook_url: str = Form()):
    """
    Add a global webhook.

    Args:
        request: The request.
        webhook_url: The webhook URL.

    Returns:
        HTMLResponse: The HTML response.
    """
    logger.info(f"Add global webhook: {webhook_url}")
    reader.set_tag("webhook", webhook_url)
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/add")
async def create_feed(feed_url: str = Form()):
    """
    Add a feed to the database.

    Args:
        feed_url: The feed to add.
        default_webhook: The default webhook to use.

    Returns:
        dict: The feed that was added.
    """
    reader.add_feed(feed_url)
    reader.update_feed(feed_url)

    return {"feed_url": str(feed_url), "status": "added"}
