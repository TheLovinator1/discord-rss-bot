from __future__ import annotations

import asyncio
import concurrent.futures
import datetime
import json
import logging
import os
import pprint
import re
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import cast
from urllib.parse import ParseResult
from urllib.parse import urlparse

import tldextract
from discord_webhook import DiscordEmbed
from discord_webhook import DiscordWebhook
from fastapi import HTTPException
from markdownify import markdownify
from playwright.sync_api import Browser
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from reader import Entry
from reader import EntryNotFoundError
from reader import Feed
from reader import FeedExistsError
from reader import FeedNotFoundError
from reader import Reader
from reader import ReaderError
from reader import StorageError

from discord_rss_bot.custom_message import CustomEmbed
from discord_rss_bot.custom_message import get_custom_message
from discord_rss_bot.custom_message import replace_tags_in_embed
from discord_rss_bot.custom_message import replace_tags_in_text_message
from discord_rss_bot.filter.evaluator import get_entry_filter_decision_from_reader
from discord_rss_bot.hoyolab_api import create_hoyolab_webhook
from discord_rss_bot.hoyolab_api import extract_post_id_from_hoyolab_url
from discord_rss_bot.hoyolab_api import fetch_hoyolab_post
from discord_rss_bot.hoyolab_api import is_c3kay_feed
from discord_rss_bot.is_url_valid import is_url_valid
from discord_rss_bot.settings import default_custom_embed
from discord_rss_bot.settings import default_custom_message
from discord_rss_bot.settings import get_reader

if TYPE_CHECKING:
    from collections.abc import Iterable

    from requests import Response

logger: logging.Logger = logging.getLogger(__name__)

type DeliveryMode = Literal["embed", "text", "screenshot"]
type ScreenshotLayout = Literal["desktop", "mobile"]
type ScreenshotFileType = Literal["png", "jpeg"]

MAX_DISCORD_UPLOAD_BYTES: int = 8 * 1024 * 1024
JPEG_QUALITY_STEPS: tuple[int, ...] = (85, 70, 55, 40)


def extract_domain(url: str) -> str:  # noqa: PLR0911
    """Extract the domain name from a URL.

    Args:
        url: The URL to extract the domain from.

    Returns:
        str: The domain name, formatted for display.
    """
    # Check for empty URL first
    if not url:
        return "Other"

    try:
        # Special handling for YouTube feeds
        if "youtube.com/feeds/videos.xml" in url:
            return "YouTube"

        # Special handling for Reddit feeds
        if "reddit.com" in url and ".rss" in url:
            return "Reddit"

        # Parse the URL and extract the domain
        parsed_url: ParseResult = urlparse(url)
        domain: str = parsed_url.netloc

        # If we couldn't extract a domain, return "Other"
        if not domain:
            return "Other"

        # Remove www. prefix if present
        domain = re.sub(r"^www\.", "", domain)

        # Special handling for common domains
        domain_mapping: dict[str, str] = {"github.com": "GitHub"}

        if domain in domain_mapping:
            return domain_mapping[domain]

        # Use tldextract to get the domain (SLD)
        ext = tldextract.extract(url)
        if ext.domain:
            return ext.domain.capitalize()
        return domain.capitalize()
    except (ValueError, AttributeError, TypeError) as e:
        logger.warning("Error extracting domain from %s: %s", url, e)
        return "Other"


def send_entry_to_discord(entry: Entry, reader: Reader) -> str | None:
    """Send a single entry to Discord.

    Args:
        entry: The entry to send to Discord.
        reader: The reader to use.

    Returns:
        str | None: The error message if there was an error, otherwise None.
    """
    # Get the webhook URL for the entry.
    webhook_url: str = str(reader.get_tag(entry.feed_url, "webhook", ""))
    if not webhook_url:
        return "No webhook URL found."

    # If https://discord.com/quests/<quest_id> is in the URL, send a separate message with the URL.
    send_discord_quest_notification(entry, webhook_url, reader=reader)

    delivery_mode: DeliveryMode = get_entry_delivery_mode(reader, entry)
    logger.info(
        "Manual send entry %s from %s using delivery_mode=%s",
        entry.id,
        entry.feed.url,
        delivery_mode,
    )

    # Hoyolab/c3kay feeds use a custom embed only when embed mode is selected.
    if delivery_mode == "embed" and is_c3kay_feed(entry.feed.url):
        entry_link: str | None = entry.link
        if entry_link:
            post_id: str | None = extract_post_id_from_hoyolab_url(entry_link)
            if post_id:
                post_data: dict[str, Any] | None = fetch_hoyolab_post(post_id)
                if post_data:
                    webhook = create_hoyolab_webhook(webhook_url, entry, post_data)
                    execute_webhook(webhook, entry, reader=reader)
                    return None
                logger.warning(
                    "Failed to create Hoyolab webhook for feed %s, falling back to regular processing",
                    entry.feed.url,
                )
        else:
            logger.warning("No entry link found for feed %s, falling back to regular processing", entry.feed.url)

    if delivery_mode == "embed":
        webhook: DiscordWebhook = create_embed_webhook(webhook_url, entry, reader=reader)
    elif delivery_mode == "screenshot":
        webhook = create_screenshot_webhook(webhook_url, entry, reader=reader)
    else:
        webhook = create_text_webhook(webhook_url, entry, reader=reader, use_default_message_on_empty=False)

    execute_webhook(webhook, entry, reader=reader)
    return None


def get_entry_delivery_mode(reader: Reader, entry: Entry) -> DeliveryMode:
    """Resolve the effective delivery mode for an entry.

    Priority order:
    1. YouTube feeds are forced to text mode.
    2. New `delivery_mode` tag when valid.
    3. Legacy `should_send_embed` flag for backwards compatibility.

    Returns:
        DeliveryMode: The effective delivery mode for this entry.
    """
    if is_youtube_feed(entry.feed.url):
        return "text"

    try:
        delivery_mode_raw: str = str(reader.get_tag(entry.feed, "delivery_mode", "")).strip().lower()
    except ReaderError:
        logger.exception("Error getting delivery_mode tag for feed: %s", entry.feed.url)
        delivery_mode_raw = ""

    if delivery_mode_raw in {"embed", "text", "screenshot"}:
        return cast("DeliveryMode", delivery_mode_raw)

    try:
        should_send_embed = bool(reader.get_tag(entry.feed, "should_send_embed", True))
    except ReaderError:
        logger.exception("Error getting should_send_embed tag for feed: %s", entry.feed.url)
        should_send_embed = True

    return "embed" if should_send_embed else "text"


def get_feed_delivery_mode(reader: Reader, feed: Feed) -> DeliveryMode:
    """Resolve the effective delivery mode for a feed.

    This mirrors `get_entry_delivery_mode` and is used by the web UI.

    Returns:
        DeliveryMode: The effective delivery mode for this feed.
    """
    if is_youtube_feed(feed.url):
        return "text"

    try:
        delivery_mode_raw: str = str(reader.get_tag(feed, "delivery_mode", "")).strip().lower()
    except ReaderError:
        logger.exception("Error getting delivery_mode tag for feed: %s", feed.url)
        delivery_mode_raw = ""

    if delivery_mode_raw in {"embed", "text", "screenshot"}:
        return cast("DeliveryMode", delivery_mode_raw)

    try:
        should_send_embed = bool(reader.get_tag(feed, "should_send_embed", True))
    except ReaderError:
        logger.exception("Error getting should_send_embed tag for feed: %s", feed.url)
        should_send_embed = True

    return "embed" if should_send_embed else "text"


def get_screenshot_layout(reader: Reader, feed: Feed) -> ScreenshotLayout:
    """Resolve the screenshot layout for a feed.

    Returns:
        ScreenshotLayout: The screenshot layout (`desktop` or `mobile`).
    """
    try:
        screenshot_layout_raw: str = str(reader.get_tag(feed, "screenshot_layout", "desktop")).strip().lower()
    except ReaderError:
        logger.exception("Error getting screenshot_layout tag for feed: %s", feed.url)
        screenshot_layout_raw = "desktop"

    if screenshot_layout_raw == "mobile":
        return "mobile"
    return "desktop"


def create_text_webhook(
    webhook_url: str,
    entry: Entry,
    reader: Reader,
    *,
    use_default_message_on_empty: bool,
) -> DiscordWebhook:
    """Create a text webhook using the configured custom message for a feed.

    Returns:
        DiscordWebhook: Configured webhook that sends a text message.
    """
    webhook_message: str = ""

    if get_custom_message(reader, entry.feed) != "":  # noqa: PLC1901
        webhook_message = replace_tags_in_text_message(entry=entry, reader=reader)

    if not webhook_message and use_default_message_on_empty:
        webhook_message = str(default_custom_message)

    if not webhook_message:
        webhook_message = "No message found."

    webhook_message = truncate_webhook_message(webhook_message)
    return DiscordWebhook(url=webhook_url, content=webhook_message, rate_limit_retry=True)


def create_screenshot_webhook(webhook_url: str, entry: Entry, reader: Reader) -> DiscordWebhook:
    """Create a webhook that uploads a full-page screenshot of the entry URL.

    Returns:
        DiscordWebhook: Configured webhook with screenshot upload, or text fallback on failure.
    """
    entry_link: str = str(entry.link or "").strip()
    webhook_content: str | None = f"<{entry_link}>" if entry_link else None
    webhook = DiscordWebhook(url=webhook_url, content=webhook_content, rate_limit_retry=True)

    if not entry_link:
        logger.warning("Entry %s has no link. Falling back to text message for screenshot mode.", entry.id)
        return create_text_webhook(webhook_url, entry, reader=reader, use_default_message_on_empty=True)

    screenshot_layout: ScreenshotLayout = get_screenshot_layout(reader, entry.feed)
    logger.info(
        "Attempting screenshot capture for entry %s with layout=%s: %s",
        entry.id,
        screenshot_layout,
        entry_link,
    )
    screenshot_bytes: bytes | None = capture_full_page_screenshot(
        entry_link,
        screenshot_layout=screenshot_layout,
        screenshot_type="png",
    )
    screenshot_extension: str = "png"

    if screenshot_bytes and len(screenshot_bytes) > MAX_DISCORD_UPLOAD_BYTES:
        logger.info(
            "Screenshot for entry %s is too large as PNG (%d bytes). Trying JPEG compression.",
            entry.id,
            len(screenshot_bytes),
        )

        for quality in JPEG_QUALITY_STEPS:
            jpeg_bytes = capture_full_page_screenshot(
                entry_link,
                screenshot_layout=screenshot_layout,
                screenshot_type="jpeg",
                jpeg_quality=quality,
            )
            if jpeg_bytes is None:
                continue

            logger.info(
                "JPEG quality=%d produced %d bytes for entry %s",
                quality,
                len(jpeg_bytes),
                entry.id,
            )
            screenshot_bytes = jpeg_bytes
            screenshot_extension = "jpg"

            if len(screenshot_bytes) <= MAX_DISCORD_UPLOAD_BYTES:
                break

    if screenshot_bytes is None:
        logger.warning(
            "Screenshot capture failed for entry %s (%s). Falling back to text message.",
            entry.id,
            entry_link,
        )
        return create_text_webhook(webhook_url, entry, reader=reader, use_default_message_on_empty=True)

    if len(screenshot_bytes) > MAX_DISCORD_UPLOAD_BYTES:
        logger.warning(
            "Screenshot for entry %s is still too large after compression (%d bytes). Falling back to text message.",
            entry.id,
            len(screenshot_bytes),
        )
        return create_text_webhook(webhook_url, entry, reader=reader, use_default_message_on_empty=True)

    filename: str = screenshot_filename_for_entry(entry, extension=screenshot_extension)
    logger.info("Screenshot capture succeeded for entry %s (%d bytes)", entry.id, len(screenshot_bytes))
    webhook.add_file(file=screenshot_bytes, filename=filename)
    return webhook


def screenshot_filename_for_entry(entry: Entry, *, extension: str = "png") -> str:
    """Build a safe screenshot filename for Discord uploads.

    Args:
        entry: Entry used to derive a stable filename.
        extension: File extension to use.

    Returns:
        str: Safe filename ending in the selected extension.
    """
    base_name: str = str(entry.id or "entry").strip().lower()
    safe_name: str = re.sub(r"[^a-z0-9._-]+", "_", base_name)
    safe_name: str = safe_name.strip("._")
    if not safe_name:
        safe_name = "entry"
    safe_extension: str = re.sub(r"[^a-z0-9]+", "", extension.lower())
    if not safe_extension:
        safe_extension = "png"
    return f"{safe_name[:80]}.{safe_extension}"


def capture_full_page_screenshot(
    url: str,
    *,
    screenshot_layout: ScreenshotLayout = "desktop",
    screenshot_type: ScreenshotFileType = "png",
    jpeg_quality: int = 85,
) -> bytes | None:
    """Capture a full-page PNG screenshot for a URL.

    Returns:
        bytes | None: PNG bytes on success, otherwise None.
    """
    # Playwright sync API cannot run in an active asyncio loop.
    # FastAPI manual routes run on the event loop, so offload to a worker thread.
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _capture_full_page_screenshot_sync,
                url,
                screenshot_layout=screenshot_layout,
                screenshot_type=screenshot_type,
                jpeg_quality=jpeg_quality,
            )
            return future.result()
    except RuntimeError:
        # No running loop in this thread (e.g. scheduler path).
        return _capture_full_page_screenshot_sync(
            url,
            screenshot_layout=screenshot_layout,
            screenshot_type=screenshot_type,
            jpeg_quality=jpeg_quality,
        )


def _capture_full_page_screenshot_sync(
    url: str,
    *,
    screenshot_layout: ScreenshotLayout = "desktop",
    screenshot_type: ScreenshotFileType = "png",
    jpeg_quality: int = 85,
) -> bytes | None:
    """Capture a full-page PNG screenshot for a URL.

    Returns:
        bytes | None: PNG bytes on success, otherwise None.
    """
    try:
        with sync_playwright() as playwright:
            browser: Browser = playwright.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            try:
                if screenshot_layout == "mobile":
                    page = browser.new_page(
                        viewport={"width": 390, "height": 844},
                        is_mobile=True,
                        has_touch=True,
                        device_scale_factor=3,
                        color_scheme="dark",
                        user_agent=(
                            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                            "Mobile/15E148 Safari/604.1"
                        ),
                    )
                else:
                    page = browser.new_page(viewport={"width": 1366, "height": 768}, color_scheme="dark")

                page = cast("Page", page)
                # `networkidle` can hang on pages with long-polling/analytics;
                # load DOM first and then best-effort wait for network idle.
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except PlaywrightTimeoutError:
                    logger.debug("Timed out waiting for network idle for URL: %s", url)

                # Scroll through the page in viewport-sized steps to trigger
                # lazy-loaded images and content before taking the screenshot.
                page.evaluate(
                    """
                    async () => {
                        const viewportHeight = window.innerHeight;
                        const totalHeight = document.body.scrollHeight;
                        let scrolled = 0;
                        while (scrolled < totalHeight) {
                            window.scrollBy(0, viewportHeight);
                            scrolled += viewportHeight;
                            await new Promise(r => setTimeout(r, 200));
                        }
                        window.scrollTo(0, 0);
                    }
                    """,
                )
                # Brief pause for any content revealed by scrolling to settle.
                page.wait_for_timeout(500)

                if screenshot_type == "jpeg":
                    clamped_quality: int = max(1, min(100, jpeg_quality))
                    return page.screenshot(type="jpeg", quality=clamped_quality, full_page=True)

                return page.screenshot(type="png", full_page=True)
            finally:
                browser.close()
    except OSError:
        logger.exception("Playwright browser is not installed. Failed to capture screenshot for URL: %s", url)
    except Exception:
        logger.exception("Failed to capture screenshot for URL: %s", url)
    return None


def send_discord_quest_notification(entry: Entry, webhook_url: str, reader: Reader) -> None:
    """Send a separate message to Discord if the entry is a quest notification."""
    quest_regex: re.Pattern[str] = re.compile(r"https://discord\.com/quests/\d+")

    def send_notification(quest_url: str) -> None:
        """Helper function to send quest notification to Discord."""
        logger.info("Sending quest notification to Discord: %s", quest_url)
        webhook = DiscordWebhook(
            url=webhook_url,
            content=quest_url,
            rate_limit_retry=True,
        )
        execute_webhook(webhook, entry, reader=reader)

    # Iterate through the content of the entry
    for content in entry.content:
        if content.type == "text" and content.value:
            match = quest_regex.search(content.value)
            if match:
                send_notification(match.group(0))
                return

        elif content.type == "text/html" and content.value:
            # Convert HTML to text and check for quest links
            text_value = markdownify(
                html=content.value,
                strip=["img", "table", "td", "tr", "tbody", "thead"],
                escape_misc=False,
                heading_style="ATX",
            )
            match: re.Match[str] | None = quest_regex.search(text_value)
            if match:
                send_notification(match.group(0))
                return

    logger.info("No quest notification found in entry: %s", entry.id)


def set_description(custom_embed: CustomEmbed, discord_embed: DiscordEmbed) -> None:
    """Set the description of the embed.

    Args:
        custom_embed (custom_message.CustomEmbed): The custom embed to get the description from.
        discord_embed (DiscordEmbed): The Discord embed to set the description on.
    """
    # Its actually 2048, but we will use 2000 to be safe.
    max_description_length: int = 2000
    embed_description: str = custom_embed.description
    embed_description = (
        f"{embed_description[:max_description_length]}..."
        if len(embed_description) > max_description_length
        else embed_description
    )
    discord_embed.set_description(embed_description) if embed_description else None


def set_title(custom_embed: CustomEmbed, discord_embed: DiscordEmbed) -> None:
    """Set the title of the embed.

    Args:
        custom_embed: The custom embed to get the title from.
        discord_embed: The Discord embed to set the title on.
    """
    # Its actually 256, but we will use 200 to be safe.
    max_title_length: int = 200
    embed_title: str = custom_embed.title
    embed_title = f"{embed_title[:max_title_length]}..." if len(embed_title) > max_title_length else embed_title
    discord_embed.set_title(embed_title) if embed_title else None


def create_embed_webhook(  # noqa: C901
    webhook_url: str,
    entry: Entry,
    reader: Reader,
) -> DiscordWebhook:
    """Create a webhook with an embed.

    Args:
        webhook_url (str): The webhook URL.
        entry (Entry): The entry to send to Discord.
        reader (Reader): The Reader instance to use for getting embed data.

    Returns:
        DiscordWebhook: The webhook with the embed.
    """
    webhook: DiscordWebhook = DiscordWebhook(url=webhook_url, rate_limit_retry=True)
    feed: Feed = entry.feed

    # Get the embed data from the database.
    custom_embed: CustomEmbed = replace_tags_in_embed(feed=feed, entry=entry, reader=reader)

    discord_embed: DiscordEmbed = DiscordEmbed()

    set_description(custom_embed=custom_embed, discord_embed=discord_embed)
    set_title(custom_embed=custom_embed, discord_embed=discord_embed)

    custom_embed_author_url: str | None = custom_embed.author_url
    if not is_url_valid(custom_embed_author_url):
        custom_embed_author_url = None

    custom_embed_color: str | None = custom_embed.color or None
    if custom_embed_color and custom_embed_color.startswith("#"):
        custom_embed_color = custom_embed_color[1:]
        discord_embed.set_color(int(custom_embed_color, 16))

    if custom_embed.author_name and not custom_embed_author_url and not custom_embed.author_icon_url:
        discord_embed.set_author(name=custom_embed.author_name)

    if custom_embed.author_name and custom_embed_author_url and not custom_embed.author_icon_url:
        discord_embed.set_author(name=custom_embed.author_name, url=custom_embed_author_url)

    if custom_embed.author_name and not custom_embed_author_url and custom_embed.author_icon_url:
        discord_embed.set_author(name=custom_embed.author_name, icon_url=custom_embed.author_icon_url)

    if custom_embed.author_name and custom_embed_author_url and custom_embed.author_icon_url:
        discord_embed.set_author(
            name=custom_embed.author_name,
            url=custom_embed_author_url,
            icon_url=custom_embed.author_icon_url,
        )

    if custom_embed.thumbnail_url:
        discord_embed.set_thumbnail(url=custom_embed.thumbnail_url)

    if custom_embed.image_url:
        discord_embed.set_image(url=custom_embed.image_url)

    if custom_embed.footer_text:
        discord_embed.set_footer(text=custom_embed.footer_text)

    if custom_embed.footer_icon_url and custom_embed.footer_text:
        discord_embed.set_footer(text=custom_embed.footer_text, icon_url=custom_embed.footer_icon_url)

    if custom_embed.footer_icon_url and not custom_embed.footer_text:
        discord_embed.set_footer(text="-", icon_url=custom_embed.footer_icon_url)

    webhook.add_embed(discord_embed)
    return webhook


def get_webhook_url(reader: Reader, entry: Entry) -> str:
    """Get the webhook URL for the entry.

    Args:
        reader: The reader to use.
        entry: The entry to get the webhook URL for.

    Returns:
        str: The webhook URL.
    """
    try:
        webhook_url: str = str(reader.get_tag(entry.feed_url, "webhook", ""))
    except StorageError:
        logger.exception("Storage error getting webhook URL for feed: %s", entry.feed.url)
        return ""

    if not webhook_url:
        logger.error("No webhook URL found for feed: %s", entry.feed.url)
        return ""
    return webhook_url


def set_entry_as_read(reader: Reader, entry: Entry) -> None:
    """Set the webhook to read, so we don't send it again.

    Args:
        reader: The reader to use.
        entry: The entry to set as read.
    """
    try:
        reader.set_entry_read(entry, True)
    except EntryNotFoundError:
        logger.exception("Error setting entry to read: %s", entry.id)
    except StorageError:
        logger.exception("Error setting entry to read: %s", entry.id)


def send_to_discord(reader: Reader | None = None, feed: Feed | None = None, *, do_once: bool = False) -> None:  # noqa: C901, PLR0912
    """Send entries to Discord.

    If response was not ok, we will log the error and mark the entry as unread, so it will be sent again next time.

    Args:
        reader: If we should use a custom reader instead of the default one.
        feed: The feed to send to Discord.
        do_once: If we should only send one entry. This is used in the test.
    """
    logger.info("Starting to send entries to Discord.")
    # Get the default reader if we didn't get a custom one.
    effective_reader: Reader = get_reader() if reader is None else reader

    # Check for new entries for every feed.
    effective_reader.update_feeds(
        scheduled=True,
        workers=os.cpu_count() or 1,
    )

    # Loop through the unread entries.
    entries: Iterable[Entry] = effective_reader.get_entries(feed=feed, read=False)
    for entry in entries:
        set_entry_as_read(effective_reader, entry)

        if entry.added < datetime.datetime.now(tz=entry.added.tzinfo) - datetime.timedelta(days=1):
            logger.info("Entry is older than 24 hours: %s from %s", entry.id, entry.feed.url)
            continue

        webhook_url: str = get_webhook_url(effective_reader, entry)
        if not webhook_url:
            logger.info("No webhook URL found for feed: %s", entry.feed.url)
            continue

        delivery_mode: DeliveryMode = get_entry_delivery_mode(effective_reader, entry)

        if delivery_mode == "embed":
            webhook = create_embed_webhook(webhook_url, entry, reader=effective_reader)
        elif delivery_mode == "screenshot":
            webhook = create_screenshot_webhook(webhook_url, entry, reader=effective_reader)
        else:
            webhook = create_text_webhook(
                webhook_url,
                entry,
                reader=effective_reader,
                use_default_message_on_empty=True,
            )

        decision = get_entry_filter_decision_from_reader(effective_reader, entry)
        if not decision.should_send:
            logger.info("Entry was skipped: %s (%s)", entry.id, decision.reason)
            continue

        # Use a custom webhook for Hoyolab feeds.
        if is_c3kay_feed(entry.feed.url):
            entry_link: str | None = entry.link
            if entry_link:
                post_id: str | None = extract_post_id_from_hoyolab_url(entry_link)
                if post_id:
                    post_data: dict[str, Any] | None = fetch_hoyolab_post(post_id)
                    if post_data:
                        webhook = create_hoyolab_webhook(webhook_url, entry, post_data)
                        execute_webhook(webhook, entry, reader=effective_reader)
                        return
                    logger.warning(
                        "Failed to create Hoyolab webhook for feed %s, falling back to regular processing",
                        entry.feed.url,
                    )
            else:
                logger.warning("No entry link found for feed %s, falling back to regular processing", entry.feed.url)

        # Send the entry to Discord as it is not blacklisted or feed has a whitelist.
        execute_webhook(webhook, entry, reader=effective_reader)

        # If we only want to send one entry, we will break the loop. This is used when testing this function.
        if do_once:
            logger.info("Sent one entry to Discord. Breaking the loop.")
            break


def execute_webhook(webhook: DiscordWebhook, entry: Entry, reader: Reader) -> None:
    """Execute the webhook.

    Args:
        webhook (DiscordWebhook): The webhook to execute.
        entry (Entry): The entry to send to Discord.
        reader (Reader): The Reader instance to use for checking feed status.

    """
    # If the feed has been paused or deleted, we will not send the entry to Discord.
    entry_feed: Feed = entry.feed
    if entry_feed.updates_enabled is False:
        logger.warning("Feed is paused, not sending entry to Discord: %s", entry_feed.url)
        return

    try:
        reader.get_feed(entry_feed.url)
    except FeedNotFoundError:
        logger.warning("Feed not found in reader, not sending entry to Discord: %s", entry_feed.url)
        return

    response: Response = webhook.execute()
    logger.debug("Discord webhook response for entry %s: status=%s", entry.id, response.status_code)
    if response.status_code not in {200, 204}:
        msg: str = f"Error sending entry to Discord: {response.text}\n{pprint.pformat(webhook.json)}"
        if entry:
            msg += f"\n{entry}"

        logger.error(msg)
    else:
        logger.info("Sent entry to Discord: %s", entry.id)


def is_youtube_feed(feed_url: str) -> bool:
    """Check if the feed is a YouTube feed.

    Args:
        feed_url: The feed URL to check.

    Returns:
        bool: True if the feed is a YouTube feed, False otherwise.
    """
    return "youtube.com/feeds/videos.xml" in feed_url


def should_send_embed_check(reader: Reader, entry: Entry) -> bool:
    """Check if we should send an embed to Discord.

    Args:
        reader (Reader): The reader to use.
        entry (Entry): The entry to check.

    Returns:
        bool: True if we should send an embed, False otherwise.
    """
    return get_entry_delivery_mode(reader, entry) == "embed"


def truncate_webhook_message(webhook_message: str) -> str:
    """Truncate the webhook message if it is too long.

    Args:
        webhook_message (str): The webhook message to truncate.

    Returns:
        str: The truncated webhook message.
    """
    max_content_length: int = 4000
    if len(webhook_message) > max_content_length:
        half_length = (max_content_length - 3) // 2  # Subtracting 3 for the "..." in the middle
        webhook_message = f"{webhook_message[:half_length]}...{webhook_message[-half_length:]}"
    return webhook_message


def create_feed(reader: Reader, feed_url: str, webhook_dropdown: str) -> None:  # noqa: C901, PLR0912
    """Add a new feed, update it and mark every entry as read.

    Args:
        reader: The reader to use.
        feed_url: The feed to add.
        webhook_dropdown: The webhook we should send entries to.

    Raises:
        HTTPException: If webhook_dropdown does not equal a webhook or default_custom_message not found.
    """
    clean_feed_url: str = feed_url.strip()
    webhook_url: str = ""
    if hooks := reader.get_tag((), "webhooks", []):
        # Get the webhook URL from the dropdown.
        for hook in hooks:
            if not isinstance(hook, dict):
                logger.error("Webhook is not a dict: %s", hook)
                continue

            if hook["name"] == webhook_dropdown:  # pyright: ignore[reportArgumentType]
                webhook_url = hook["url"]
                break

    if not webhook_url:
        raise HTTPException(status_code=404, detail="Webhook not found")

    try:
        reader.add_feed(clean_feed_url)
    except FeedExistsError:
        # Add the webhook to an already added feed if it doesn't have a webhook instead of trying to create a new.
        if not reader.get_tag(clean_feed_url, "webhook", ""):
            reader.set_tag(clean_feed_url, "webhook", webhook_url)  # pyright: ignore[reportArgumentType]
    except ReaderError as e:
        raise HTTPException(status_code=404, detail=f"Error adding feed: {e}") from e

    try:
        reader.update_feed(clean_feed_url)
    except ReaderError as e:
        raise HTTPException(status_code=404, detail=f"Error updating feed: {e}") from e

    # Mark every entry as read, so we don't send all the old entries to Discord.
    entries: Iterable[Entry] = reader.get_entries(feed=clean_feed_url, read=False)
    for entry in entries:
        reader.set_entry_read(entry, True)

    if not default_custom_message:
        # TODO(TheLovinator): Show this error on the page.
        raise HTTPException(status_code=404, detail="Default custom message couldn't be found.")

    # This is the webhook that will be used to send the feed to Discord.
    reader.set_tag(clean_feed_url, "webhook", webhook_url)  # pyright: ignore[reportArgumentType]

    # This is the default message that will be sent to Discord.
    reader.set_tag(clean_feed_url, "custom_message", default_custom_message)  # pyright: ignore[reportArgumentType]

    global_screenshot_layout: str = str(reader.get_tag((), "screenshot_layout", "desktop")).strip().lower()
    if global_screenshot_layout not in {"desktop", "mobile"}:
        global_screenshot_layout = "desktop"
    reader.set_tag(clean_feed_url, "screenshot_layout", global_screenshot_layout)  # pyright: ignore[reportArgumentType]

    global_delivery_mode: str = str(reader.get_tag((), "delivery_mode", "embed")).strip().lower()
    if global_delivery_mode not in {"embed", "text"}:
        global_delivery_mode = "embed"
    reader.set_tag(clean_feed_url, "delivery_mode", global_delivery_mode)  # pyright: ignore[reportArgumentType]
    reader.set_tag(clean_feed_url, "should_send_embed", global_delivery_mode == "embed")  # pyright: ignore[reportArgumentType]

    # Set the default embed tag when creating the feed
    reader.set_tag(clean_feed_url, "embed", json.dumps(default_custom_embed))  # pyright: ignore[reportArgumentType]

    # Update the full-text search index so our new feed is searchable.
    reader.update_search()
