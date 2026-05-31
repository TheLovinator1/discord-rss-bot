from __future__ import annotations

import asyncio
import concurrent.futures
import datetime
import hashlib
import json
import logging
import os
import pprint
import re
import time
from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import Protocol
from typing import cast
from urllib.parse import ParseResult
from urllib.parse import parse_qs
from urllib.parse import urljoin
from urllib.parse import urlparse

import httpx2
import tldextract
from fastapi import HTTPException
from httpx2 import HTTPError
from httpx2 import Response
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
from reader.types import EntryUpdateStatus
from reader.types import UpdatedFeed
from requests import RequestException

from discord_rss_bot.custom_message import CustomEmbed
from discord_rss_bot.custom_message import get_custom_message
from discord_rss_bot.custom_message import get_image_urls
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
from discord_rss_bot.webhook import DiscordEmbed
from discord_rss_bot.webhook import DiscordWebhook
from discord_rss_bot.webhook import WebhookFile

if TYPE_CHECKING:
    from collections.abc import Iterable

    from reader._types import EntryData
    from reader.types import JSONType

logger: logging.Logger = logging.getLogger(__name__)

type DeliveryMode = Literal["embed", "text", "screenshot"]
type ScreenshotLayout = Literal["desktop", "mobile"]
type ScreenshotFileType = Literal["png", "jpeg"]
type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]
type SentWebhookRecord = dict[str, JsonValue]
type UpdateCallback = Callable[[], UpdatedFeed | None]


class FeedUpdateError(HTTPException):
    """Raised when the initial update for a newly added feed fails."""


class JsonResponseLike(Protocol):
    """Response interface needed for Discord webhook JSON parsing."""

    @property
    def status_code(self) -> int:
        """HTTP status code."""
        ...

    @property
    def text(self) -> str:
        """Response body decoded as text."""
        ...

    @property
    def content(self) -> bytes:
        """Raw response body."""
        ...

    def json(self) -> JsonValue:
        """Decode response body as JSON.

        Returns:
            JsonValue: Decoded JSON response body.
        """
        ...


MESSAGE_PAYLOAD_KEYS: tuple[str, ...] = (
    "allowed_mentions",
    "applied_tags",
    "attachments",
    "avatar_url",
    "components",
    "content",
    "embeds",
    "flags",
    "poll",
    "thread_name",
    "tts",
    "username",
)


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

    try:  # noqa: PLW0717
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

    webhook, _delivery_mode = create_webhook_for_entry(
        webhook_url,
        entry,
        reader,
        use_default_message_on_empty=False,
    )

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


def coerce_media_gallery_image_limit(value: JsonValue) -> int:  # noqa: PLR0911
    """Return the supported media gallery image limit for a stored tag value."""
    if isinstance(value, bool):
        return 1
    if isinstance(value, int):
        return min(max(value, 0), 10)
    if isinstance(value, str) and value.strip().lower() in {"1", "first", "first_image", "first-only"}:
        return 1
    if isinstance(value, str) and value.strip().lower() in {"0", "none", "no_images", "off", "disabled"}:
        return 0
    if isinstance(value, str):
        try:
            parsed_value: int = int(value.strip())
        except ValueError:
            return 1
        return min(max(parsed_value, 0), 10)
    return 1


def get_feed_media_gallery_image_limit(reader: Reader, feed: Feed | str) -> int:
    """Resolve how many feed images should be sent in Discord media galleries.

    Returns:
        The configured image limit, normalized to a supported Discord gallery size.
    """
    feed_url: str = str(getattr(feed, "url", feed))
    try:
        value = cast("JsonValue", reader.get_tag(feed, "media_gallery_image_limit", 1))
    except ReaderError:
        logger.exception("Error getting %s tag for feed: %s", "media_gallery_image_limit", feed_url)
        return 1

    return coerce_media_gallery_image_limit(value)


def feed_saves_sent_webhooks(reader: Reader, feed: Feed | str) -> bool:
    """Return whether sent Discord webhook messages should be stored for a feed.

    Missing tags default to enabled so existing feeds start tracking editable Discord messages.
    """
    feed_url: str = feed.url if isinstance(feed, Feed) else str(feed)
    try:
        value = cast("JsonValue", reader.get_tag(feed, "save_sent_webhooks", True))
    except ReaderError:
        logger.exception("Error getting %s tag for feed: %s", "save_sent_webhooks", feed_url)
        return True

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}
    if value is None:
        return True
    return bool(value)


def get_sent_webhook_records(reader: Reader) -> list[SentWebhookRecord]:
    """Get stored sent webhook records from the global reader tag.

    Returns:
        list[SentWebhookRecord]: Saved sent webhook records.
    """
    raw_records = cast("JsonValue", reader.get_tag((), "sent_webhooks", []))
    if not isinstance(raw_records, list):
        return []

    records: list[SentWebhookRecord] = [
        cast("SentWebhookRecord", dict(raw_record)) for raw_record in raw_records if isinstance(raw_record, dict)
    ]
    return records


def save_sent_webhook_records(reader: Reader, records: list[SentWebhookRecord]) -> None:
    """Save sent webhook records to the global reader tag."""
    reader.set_tag((), "sent_webhooks", records)  # pyright: ignore[reportArgumentType]


def get_webhook_request_payload(webhook: DiscordWebhook) -> JsonObject:
    """Return the Discord message payload sent to Discord.

    Runtime fields on the webhook object are intentionally excluded. Unlike
    `get_webhook_message_payload`, this does not add empty defaults because
    Components V2 messages reject otherwise-empty `content` and `embeds` fields.

    Returns:
        JsonObject: Discord request payload.
    """
    raw_payload = cast("JsonValue", webhook.json)
    if not isinstance(raw_payload, dict):
        return {}

    payload: JsonObject = {}
    webhook_payload = cast("JsonObject", raw_payload)
    for key in MESSAGE_PAYLOAD_KEYS:
        if key in webhook_payload:
            payload[key] = webhook_payload[key]

    return cast("JsonObject", json.loads(json.dumps(payload, default=str)))


def get_webhook_message_payload(webhook: DiscordWebhook) -> JsonObject:
    """Return the normalized Discord message payload used to compare saved messages.

    Empty `content`, `embeds`, and `attachments` are kept here so message edits can clear stale content when a feed
    changes delivery mode. Use `get_webhook_request_payload` for the payload sent to Discord.

    Returns:
        JsonObject: Normalized Discord message payload.
    """
    payload: JsonObject = get_webhook_request_payload(webhook)
    payload.setdefault("content", "")
    payload.setdefault("embeds", [])
    payload.setdefault("attachments", [])
    return cast("JsonObject", json.loads(json.dumps(payload, default=str)))


def hash_webhook_payload(payload: JsonObject) -> str:
    """Hash a normalized Discord message payload.

    Returns:
        str: SHA-256 hash of the payload.
    """
    normalized_payload: str = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized_payload.encode()).hexdigest()


def json_object_or_empty(value: JsonValue) -> JsonObject:
    """Return a JSON object value or an empty object."""
    return cast("JsonObject", value) if isinstance(value, dict) else {}


def json_list_or_empty(value: JsonValue) -> list[JsonValue]:
    """Return a JSON list value or an empty list."""
    return cast("list[JsonValue]", value) if isinstance(value, list) else []


def has_media_url(value: JsonValue) -> bool:
    """Return whether an embed media field has a usable URL."""
    return isinstance(value, dict) and isinstance(value.get("url"), str) and bool(value["url"])


def preserve_previous_embed_media(payload: JsonObject, previous_payload: JsonObject) -> JsonObject:
    """Keep existing embed image fields when an entry update cannot extract a replacement.

    Returns:
        JsonObject: Payload with previous embed media restored when the update lacks replacement media.
    """
    embeds: list[JsonValue] = json_list_or_empty(payload.get("embeds"))
    previous_embeds: list[JsonValue] = json_list_or_empty(previous_payload.get("embeds"))
    if not embeds or not previous_embeds:
        return payload

    merged_payload: JsonObject = cast("JsonObject", json.loads(json.dumps(payload, default=str)))
    merged_embeds: list[JsonValue] = json_list_or_empty(merged_payload.get("embeds"))

    for index, embed_value in enumerate(merged_embeds):
        if index >= len(previous_embeds) or not isinstance(embed_value, dict):
            continue

        previous_embed: JsonObject = json_object_or_empty(previous_embeds[index])
        embed: JsonObject = cast("JsonObject", embed_value)
        for media_key in ("image", "thumbnail"):
            previous_media: JsonValue = previous_embed.get(media_key)
            if has_media_url(previous_media) and not has_media_url(embed.get(media_key)):
                embed[media_key] = previous_media

    return merged_payload


def get_webhook_message_edit_payload(payload: JsonObject, record: SentWebhookRecord) -> JsonObject:
    """Return the payload to PATCH to Discord for a saved message edit.

    Returns:
        JsonObject: Payload suitable for a Discord message edit request.
    """
    previous_payload: JsonObject = json_object_or_empty(record.get("payload"))
    edit_payload: JsonObject = preserve_previous_embed_media(payload, previous_payload)

    previous_embeds: list[JsonValue] = json_list_or_empty(previous_payload.get("embeds"))
    if edit_payload.get("embeds") == [] and not previous_embeds:
        edit_payload.pop("embeds", None)

    previous_attachments: list[JsonValue] = json_list_or_empty(previous_payload.get("attachments"))
    if edit_payload.get("attachments") == [] and not previous_attachments:
        edit_payload.pop("attachments", None)

    if json_value_to_int(edit_payload.get("flags")) & 1 << 15:
        edit_payload.pop("content", None)
        edit_payload.pop("embeds", None)
        edit_payload.pop("poll", None)
        if edit_payload.get("attachments") == []:
            edit_payload.pop("attachments", None)

    return edit_payload


def json_value_to_int(value: JsonValue, default: int = 0) -> int:
    """Convert a simple JSON scalar to int.

    Returns:
        int: Converted integer, or default when the value is not scalar-convertible.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float | str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def get_response_json(response: JsonResponseLike) -> JsonObject:
    """Best-effort JSON extraction for requests/httpx response objects.

    Returns:
        JsonObject: Decoded JSON object, or an empty dict.
    """
    try:
        response_json = response.json()
    except (AttributeError, TypeError, ValueError):
        response_text: str = response.text
        if not response_text:
            response_content: bytes = response.content
            if isinstance(response_content, bytes):
                response_text = response_content.decode("utf-8", errors="ignore")
        if not response_text:
            return {}
        try:
            response_json = json.loads(response_text)
        except json.JSONDecodeError:
            return {}

    return cast("JsonObject", dict(response_json)) if isinstance(response_json, dict) else {}


def get_discord_message_id_from_response(response_json: JsonObject, webhook: DiscordWebhook) -> str:
    """Get the Discord message id from a decoded webhook response.

    Returns:
        str: Discord message id, or an empty string.
    """
    message_id: JsonValue = response_json.get("id")
    if isinstance(message_id, str) and message_id:
        return message_id

    raw_webhook_id = getattr(webhook, "id", None)
    webhook_id: str | None = raw_webhook_id if isinstance(raw_webhook_id, str) else None
    return webhook_id if isinstance(webhook_id, str) else ""


def get_discord_message_id(response: JsonResponseLike, webhook: DiscordWebhook) -> str:
    """Get the Discord message id returned by a webhook send/edit response.

    Returns:
        str: Discord message id, or an empty string.
    """
    return get_discord_message_id_from_response(get_response_json(response), webhook)


def get_entry_timestamp(value: datetime.datetime | None) -> str:
    """Return an ISO timestamp when an entry datetime-like value is present.

    Returns:
        str: ISO timestamp, or an empty string.
    """
    if value is not None:
        return value.isoformat()
    return ""


def upsert_sent_webhook_record(
    reader: Reader,
    entry: Entry,
    webhook_url: str,
    webhook: DiscordWebhook,
    response: JsonResponseLike,
    payload: JsonObject,
) -> None:
    """Store the Discord message id and rendered payload for a successfully sent entry."""
    if not feed_saves_sent_webhooks(reader, entry.feed):
        return

    response_json: JsonObject = get_response_json(response)
    message_id: str = get_discord_message_id_from_response(response_json, webhook)
    if not message_id:
        logger.debug("Discord response did not include a message id for entry %s; not storing webhook.", entry.id)
        return

    now: str = datetime.datetime.now(tz=datetime.UTC).isoformat()
    payload_hash: str = hash_webhook_payload(payload)
    delivery_mode: DeliveryMode = get_entry_delivery_mode(reader, entry)
    record: SentWebhookRecord = {
        "feed_url": entry.feed.url,
        "feed_title": entry.feed.title or "",
        "entry_id": entry.id,
        "entry_title": entry.title or "",
        "entry_link": entry.link or "",
        "entry_updated": get_entry_timestamp(entry.updated),
        "webhook_url": webhook_url,
        "message_id": message_id,
        "delivery_mode": delivery_mode,
        "payload": payload,
        "payload_hash": payload_hash,
        "discord_response": response_json,
        "response_text": response.text[:5000],
        "first_sent_at": now,
        "last_sent_at": now,
        "last_updated_at": now,
        "last_status_code": response.status_code,
        "last_error": "",
        "update_count": 0,
    }

    records: list[SentWebhookRecord] = get_sent_webhook_records(reader)
    for index, existing_record in enumerate(records):
        if (
            existing_record.get("feed_url") == entry.feed.url
            and existing_record.get("entry_id") == entry.id
            and existing_record.get("webhook_url") == webhook_url
        ):
            record["first_sent_at"] = existing_record.get("first_sent_at") or now
            record["update_count"] = json_value_to_int(existing_record.get("update_count"))
            records[index] = record
            save_sent_webhook_records(reader, records)
            return

    records.append(record)
    save_sent_webhook_records(reader, records)


def split_webhook_url_for_message_endpoint(webhook_url: str) -> tuple[str, str | None]:
    """Split a webhook URL into the base webhook endpoint and optional thread id.

    Returns:
        tuple[str, str | None]: Clean webhook URL and optional thread id.
    """
    parsed_url = urlparse(webhook_url)
    query = parse_qs(parsed_url.query)
    thread_id_values: list[str] = query.get("thread_id", [])
    thread_id: str | None = thread_id_values[0].strip() if thread_id_values else None
    if not thread_id:
        thread_id = None

    clean_url: str = parsed_url._replace(query="", fragment="").geturl().rstrip("/")
    return clean_url, thread_id


def payload_has_components(payload: JsonObject) -> bool:
    """Return whether a Discord payload includes message components."""
    components: JsonValue = payload.get("components")
    return isinstance(components, list) and bool(components)


def get_webhook_query_params(
    webhook_url: str,
    payload: JsonObject,
    *,
    webhook: DiscordWebhook | None = None,
    wait: bool = True,
) -> tuple[str, dict[str, str]]:
    """Return a clean webhook URL and query params for a Discord webhook request."""
    clean_webhook_url, thread_id = split_webhook_url_for_message_endpoint(webhook_url)
    webhook_thread_id = getattr(webhook, "thread_id", None) if webhook is not None else None
    if isinstance(webhook_thread_id, str) and webhook_thread_id.strip():
        thread_id = webhook_thread_id.strip()

    params: dict[str, str] = {}
    if wait:
        params["wait"] = "true"
    if thread_id:
        params["thread_id"] = thread_id
    if payload_has_components(payload):
        params["with_components"] = "true"

    return clean_webhook_url, params


def get_webhook_files(webhook: DiscordWebhook) -> list[WebhookFile]:  # noqa: C901
    """Return files attached to a webhook object in a normalized shape."""
    raw_files = getattr(webhook, "files", None)
    files: list[WebhookFile] = []

    if isinstance(raw_files, dict):
        for filename, content in raw_files.items():
            if isinstance(filename, str) and isinstance(content, bytes):
                files.append(WebhookFile(filename=filename, content=content))
        return files

    if not isinstance(raw_files, list | tuple):
        return []

    for index, file_value in enumerate(raw_files):
        if isinstance(file_value, WebhookFile):
            files.append(file_value)
            continue

        if not isinstance(file_value, tuple) or len(file_value) < 2:  # noqa: PLR2004
            continue

        first, second = file_value[0], file_value[1]
        if isinstance(first, str) and isinstance(second, bytes):
            files.append(WebhookFile(filename=first, content=second))
            continue

        if isinstance(second, tuple) and len(second) >= 2:  # noqa: PLR2004
            nested_file = cast("tuple[object, ...]", second)
            nested_filename, nested_content = nested_file[0], nested_file[1]
            if isinstance(nested_filename, str) and isinstance(nested_content, bytes):
                files.append(WebhookFile(filename=nested_filename, content=nested_content))
                continue

        if isinstance(second, bytes):
            files.append(WebhookFile(filename=f"file-{index}", content=second))

    return files


def get_retry_after_seconds(response: Response) -> float | None:
    """Return Discord's retry delay for a rate-limited response when available."""
    response_json: JsonObject = get_response_json(response)
    retry_after: JsonValue = response_json.get("retry_after")
    if isinstance(retry_after, int | float | str):
        with suppress(TypeError, ValueError):
            return float(retry_after)

    retry_after_header: str | None = response.headers.get("retry-after")
    if retry_after_header:
        with suppress(TypeError, ValueError):
            return float(retry_after_header)

    return None


def request_discord_webhook(
    method: str,
    url: str,
    *,
    payload: JsonObject,
    params: dict[str, str],
    files: list[WebhookFile] | None,
    timeout: float,
    rate_limit_retry: bool,
) -> Response:
    """Send a Discord webhook request with optional multipart files.

    Returns:
        Discord API response.
    """
    request_kwargs: dict[str, Any] = {"params": params, "timeout": timeout}
    if files:
        request_kwargs["data"] = {"payload_json": json.dumps(payload, default=str)}
        request_kwargs["files"] = [
            (f"files[{index}]", (file.filename, file.content)) for index, file in enumerate(files)
        ]
    else:
        request_kwargs["json"] = payload

    response: Response = httpx2.request(method, url, **request_kwargs)
    if not rate_limit_retry or response.status_code != 429:  # noqa: PLR2004
        return response

    retry_after: float | None = get_retry_after_seconds(response)
    if retry_after is None:
        return response

    time.sleep(max(0.0, retry_after))
    return httpx2.request(method, url, **request_kwargs)


def send_webhook_message(webhook: DiscordWebhook, payload: JsonObject) -> Response:
    """Execute a Discord webhook message create request using httpx2.

    Returns:
        Discord API response.
    """
    clean_webhook_url, params = get_webhook_query_params(webhook.url, payload, webhook=webhook, wait=True)
    return request_discord_webhook(
        "POST",
        clean_webhook_url,
        payload=payload,
        params=params,
        files=get_webhook_files(webhook),
        timeout=cast("int | float", getattr(webhook, "timeout", None) or 30.0),
        rate_limit_retry=bool(getattr(webhook, "rate_limit_retry", False)),
    )


def edit_sent_webhook_message(
    webhook_url: str,
    message_id: str,
    webhook: DiscordWebhook,
    payload: JsonObject,
) -> Response:
    """Edit an already-sent Discord webhook message.

    Returns:
        Response: Discord API response.
    """
    clean_webhook_url, params = get_webhook_query_params(webhook_url, payload, webhook=webhook, wait=True)
    return request_discord_webhook(
        "PATCH",
        f"{clean_webhook_url}/messages/{message_id}",
        payload=payload,
        params=params,
        files=get_webhook_files(webhook),
        timeout=cast("int | float", getattr(webhook, "timeout", None) or 30.0),
        rate_limit_retry=bool(getattr(webhook, "rate_limit_retry", False)),
    )


def create_webhook_for_entry(
    webhook_url: str,
    entry: Entry,
    reader: Reader,
    *,
    use_default_message_on_empty: bool,
) -> tuple[DiscordWebhook, DeliveryMode]:
    """Create the Discord webhook payload for the entry's effective delivery mode.

    Returns:
        tuple[DiscordWebhook, DeliveryMode]: Rendered webhook object and delivery mode.
    """
    delivery_mode: DeliveryMode = get_entry_delivery_mode(reader, entry)

    if delivery_mode == "embed" and is_c3kay_feed(entry.feed.url):
        entry_link: str | None = entry.link
        if entry_link:
            post_id: str | None = extract_post_id_from_hoyolab_url(entry_link)
            if post_id:
                post_data = fetch_hoyolab_post(post_id)
                if post_data:
                    return create_hoyolab_webhook(webhook_url, entry, post_data), delivery_mode
                logger.warning(
                    "Failed to create Hoyolab webhook for feed %s, falling back to regular processing",
                    entry.feed.url,
                )
        else:
            logger.warning("No entry link found for feed %s, falling back to regular processing", entry.feed.url)

    if delivery_mode == "embed":
        return create_embed_webhook(webhook_url, entry, reader=reader), delivery_mode
    if delivery_mode == "screenshot":
        return create_screenshot_webhook(webhook_url, entry, reader=reader), delivery_mode
    return (
        create_text_webhook(
            webhook_url,
            entry,
            reader=reader,
            use_default_message_on_empty=use_default_message_on_empty,
        ),
        delivery_mode,
    )


def collect_modified_entries_during_update(reader: Reader, update_callback: UpdateCallback) -> list[tuple[str, str]]:
    """Run a reader update call and collect entries whose stored content was modified.

    Returns:
        list[tuple[str, str]]: Modified entry `(feed_url, entry_id)` pairs.
    """
    modified_entries: list[tuple[str, str]] = []
    hooks = reader.after_entry_update_hooks

    def collect_modified_entry(_reader: Reader, entry: EntryData, status: EntryUpdateStatus) -> None:
        status_value: str = getattr(status, "value", str(status))
        if status == EntryUpdateStatus.MODIFIED or status_value == EntryUpdateStatus.MODIFIED.value:
            modified_entries.append((entry.feed_url, entry.id))

    hooks.append(collect_modified_entry)
    try:
        update_callback()
    finally:
        with suppress(ValueError):
            hooks.remove(collect_modified_entry)

    return list(dict.fromkeys(modified_entries))


def update_feeds_and_collect_modified_entries(
    reader: Reader,
    *,
    scheduled: bool,
    workers: int,
) -> list[tuple[str, str]]:
    """Update feeds and return reader entries whose stored content was modified.

    Returns:
        list[tuple[str, str]]: Modified entry `(feed_url, entry_id)` pairs.
    """
    return collect_modified_entries_during_update(
        reader,
        lambda: reader.update_feeds(scheduled=scheduled, workers=workers),
    )


def update_feed_and_collect_modified_entries(reader: Reader, feed: Feed | str) -> list[tuple[str, str]]:
    """Update one feed and return reader entries whose stored content was modified.

    Returns:
        list[tuple[str, str]]: Modified entry `(feed_url, entry_id)` pairs.
    """
    return collect_modified_entries_during_update(reader, lambda: reader.update_feed(feed))


def update_sent_webhook_record_for_entry(
    reader: Reader,
    entry: Entry,
    record: SentWebhookRecord,
) -> tuple[SentWebhookRecord, bool, bool]:
    """Edit one saved Discord webhook message record for an updated entry.

    Returns:
        tuple[SentWebhookRecord, bool, bool]: Updated record, whether it changed, and whether Discord was edited.
    """
    webhook_url_value: JsonValue = record.get("webhook_url")
    message_id_value: JsonValue = record.get("message_id")
    if (
        not isinstance(webhook_url_value, str)
        or not isinstance(message_id_value, str)
        or not webhook_url_value
        or not message_id_value
    ):
        return record, False, False

    previous_payload: JsonObject = json_object_or_empty(record.get("payload"))
    webhook, delivery_mode = create_webhook_for_entry(
        webhook_url_value,
        entry,
        reader,
        use_default_message_on_empty=True,
    )
    payload: JsonObject = preserve_previous_embed_media(
        get_webhook_message_payload(webhook),
        previous_payload,
    )
    edit_payload: JsonObject = get_webhook_message_edit_payload(payload, record)
    payload_hash: str = hash_webhook_payload(payload)
    if payload_hash == record.get("payload_hash"):
        return record, False, False
    if previous_payload and payload_hash == hash_webhook_payload(previous_payload):
        return (
            {
                **record,
                "payload": payload,
                "payload_hash": payload_hash,
                "delivery_mode": delivery_mode,
            },
            True,
            False,
        )

    now: str = datetime.datetime.now(tz=datetime.UTC).isoformat()
    try:
        response: Response = edit_sent_webhook_message(
            webhook_url=webhook_url_value,
            message_id=message_id_value,
            webhook=webhook,
            payload=edit_payload,
        )
    except (AssertionError, RequestException, HTTPError, OSError, ValueError) as e:
        logger.exception("Failed to edit Discord webhook message %s for entry %s", message_id_value, entry.id)
        return (
            {
                **record,
                "last_update_attempt_at": now,
                "last_error": str(e),
            },
            True,
            False,
        )

    status_code: int = response.status_code
    response_json: JsonObject = get_response_json(response)
    if status_code in {200, 204}:
        return (
            {
                **record,
                "feed_title": entry.feed.title or "",
                "entry_title": entry.title or "",
                "entry_link": entry.link or "",
                "entry_updated": get_entry_timestamp(entry.updated),
                "delivery_mode": delivery_mode,
                "payload": payload,
                "payload_hash": payload_hash,
                "discord_response": response_json,
                "response_text": response.text[:5000],
                "last_updated_at": now,
                "last_status_code": status_code,
                "last_error": "",
                "update_count": json_value_to_int(record.get("update_count")) + 1,
            },
            True,
            True,
        )

    return (
        {
            **record,
            "last_update_attempt_at": now,
            "last_status_code": status_code,
            "discord_response": response_json,
            "response_text": response.text[:5000],
            "last_error": response.text[:500],
        },
        True,
        False,
    )


def update_sent_webhooks_for_modified_entries(  # noqa: C901
    reader: Reader,
    modified_entries: Iterable[tuple[str, str]],
) -> int:
    """Edit saved Discord webhook messages for modified reader entries.

    Returns:
        int: Number of Discord messages successfully edited.
    """
    modified_entry_keys: set[tuple[str, str]] = set(modified_entries)
    if not modified_entry_keys:
        return 0

    records: list[SentWebhookRecord] = get_sent_webhook_records(reader)
    if not records:
        return 0

    records_changed: bool = False
    updated_count: int = 0

    for feed_url, entry_id in modified_entry_keys:
        matching_record_indexes: list[int] = [
            index
            for index, record in enumerate(records)
            if record.get("feed_url") == feed_url and record.get("entry_id") == entry_id
        ]
        if not matching_record_indexes:
            continue

        try:
            entry: Entry = reader.get_entry((feed_url, entry_id))
        except (FeedNotFoundError, EntryNotFoundError):
            logger.exception("Saved webhook entry no longer exists: %s %s", feed_url, entry_id)
            continue

        if not feed_saves_sent_webhooks(reader, entry.feed):
            continue

        for record_index in matching_record_indexes:
            updated_record, record_changed, message_was_edited = update_sent_webhook_record_for_entry(
                reader,
                entry,
                records[record_index],
            )
            if record_changed:
                records[record_index] = updated_record
                records_changed = True
            if message_was_edited:
                updated_count += 1

    if records_changed:
        save_sent_webhook_records(reader, records)

    return updated_count


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

    if screenshot_bytes and len(screenshot_bytes) > 8 * 1024 * 1024:
        logger.info(
            "Screenshot for entry %s is too large as PNG (%d bytes). Trying JPEG compression.",
            entry.id,
            len(screenshot_bytes),
        )

        for quality in (85, 70, 55, 40):
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

            if len(screenshot_bytes) <= 8 * 1024 * 1024:
                break

    if screenshot_bytes is None:
        logger.warning(
            "Screenshot capture failed for entry %s (%s). Falling back to text message.",
            entry.id,
            entry_link,
        )
        return create_text_webhook(webhook_url, entry, reader=reader, use_default_message_on_empty=True)

    if len(screenshot_bytes) > 8 * 1024 * 1024:
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
    try:  # noqa: PLW0717
        with sync_playwright() as playwright:
            browser: Browser = playwright.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            try:  # noqa: PLW0717
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
        execute_webhook(webhook, entry, reader=reader, save_sent_webhook=False)

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


def add_unique_media_gallery_item(
    media_items: list[JsonObject],
    image_url: str,
    *,
    description: str,
    limit: int = 10,
) -> None:
    """Append a valid media gallery item while preserving order and uniqueness."""
    clean_image_url: str = image_url.strip()
    if (
        len(media_items) >= limit
        or not clean_image_url
        or any(item.get("url") == clean_image_url for item in media_items)
    ):
        return
    if not is_url_valid(clean_image_url):
        logger.warning("Invalid media gallery URL: %s", clean_image_url)
        return
    media_items.append({"url": clean_image_url, "description": description[:1024]})


def normalize_ttvdrops_media_url(image_url: str) -> str:
    """Return an absolute ttvdrops media URL."""
    clean_image_url: str = image_url.strip()
    if not clean_image_url:
        return ""
    return urljoin("https://ttvdrops.lovinator.space/", clean_image_url)


def get_ttvdrops_campaign_api_url(entry: Entry) -> str:
    """Return the ttvdrops campaign API URL for an entry when it can be inferred."""
    candidate_urls: tuple[str | None, ...] = (
        entry.link,
        entry.id,
        entry.feed.url,
    )

    for candidate_url in candidate_urls:
        if not candidate_url:
            continue

        parsed_url = urlparse(str(candidate_url))
        if parsed_url.netloc.lower() != "ttvdrops.lovinator.space":
            continue

        if re.fullmatch(r"/twitch/api/v1/campaigns/[^/]+/?", parsed_url.path):
            return parsed_url._replace(query="", fragment="").geturl()

        campaign_match = re.fullmatch(r"/twitch/campaigns/([^/]+)/?", parsed_url.path)
        if campaign_match:
            campaign_id: str = campaign_match.group(1)
            return parsed_url._replace(
                path=f"/twitch/api/v1/campaigns/{campaign_id}/",
                query="",
                fragment="",
            ).geturl()

    return ""


def get_ttvdrops_reward_description(drop: JsonObject, reward: JsonObject) -> str:
    """Return alt text for a ttvdrops reward image.

    Returns:
        Reward alt text suitable for a Media Gallery description.
    """
    reward_name: str = str(reward.get("name") or drop.get("name") or "Reward")
    required_minutes: int = json_value_to_int(drop.get("required_minutes_watched"))
    required_subs: int = json_value_to_int(drop.get("required_subs"))

    if required_minutes:
        return f"{required_minutes} minutes watched: {reward_name}"
    if required_subs:
        return f"{required_subs} subscriptions: {reward_name}"
    return reward_name


def extract_ttvdrops_media_gallery_items(value: JsonValue, *, hide_paid: bool = False) -> list[JsonObject]:  # noqa: C901
    """Extract benefit/reward media gallery items from a ttvdrops API response.

    Returns:
        Media Gallery items with absolute URLs and reward descriptions.
    """
    media_items: list[JsonObject] = []

    def add_reward_image(drop: JsonObject, reward: JsonObject) -> None:
        if hide_paid and json_value_to_int(drop.get("required_minutes_watched")) <= 0:
            return

        image_url = reward.get("image_url")
        if isinstance(image_url, str):
            add_unique_media_gallery_item(
                media_items,
                normalize_ttvdrops_media_url(image_url),
                description=get_ttvdrops_reward_description(drop, reward),
            )

    def collect_benefit_images(current_value: JsonValue) -> None:
        if isinstance(current_value, dict):
            for key, child_value in current_value.items():
                if key in {"benefits", "rewards"} and isinstance(child_value, list):
                    for item in child_value:
                        if isinstance(item, dict):
                            add_reward_image(cast("JsonObject", current_value), cast("JsonObject", item))
                        collect_benefit_images(item)
                    continue

                collect_benefit_images(child_value)
            return

        if isinstance(current_value, list):
            for item in current_value:
                collect_benefit_images(item)

    collect_benefit_images(value)
    return media_items


def fetch_ttvdrops_campaign_media_items(entry: Entry) -> list[JsonObject]:
    """Fetch extra campaign media gallery items for ttvdrops entries.

    Returns:
        Media Gallery items for ttvdrops rewards, or an empty list.
    """
    api_url: str = get_ttvdrops_campaign_api_url(entry)
    if not api_url:
        return []

    try:
        response: Response = httpx2.get(api_url, follow_redirects=True, timeout=10.0)
        if response.status_code != 200:  # noqa: PLR2004
            logger.warning("Failed to fetch ttvdrops campaign data from %s: %s", api_url, response.text[:500])
            return []

        response_json = cast("JsonValue", response.json())
    except (HTTPError, ValueError, TypeError):
        logger.exception("Failed to fetch ttvdrops campaign data from %s", api_url)
        return []

    hide_paid: bool = "1" in parse_qs(urlparse(entry.feed.url).query).get("hide_paid", [])
    return extract_ttvdrops_media_gallery_items(response_json, hide_paid=hide_paid)


def get_entry_media_gallery_items(
    entry: Entry,
    custom_embed: CustomEmbed,
    *,
    image_limit: int = 10,
) -> list[JsonObject]:
    """Return items for a Discord Media Gallery component.

    Returns:
        Media Gallery items capped to Discord's item limit.
    """
    image_limit = coerce_media_gallery_image_limit(image_limit)
    if image_limit == 0:
        return []

    media_items: list[JsonObject] = []
    ttvdrops_media_items: list[JsonObject] = fetch_ttvdrops_campaign_media_items(entry)
    if ttvdrops_media_items:
        return ttvdrops_media_items[:image_limit]

    description: str = entry.title or entry.id
    for image_url in get_image_urls(entry.summary, entry.content, limit=image_limit):
        add_unique_media_gallery_item(media_items, image_url, description=description)

    add_unique_media_gallery_item(media_items, custom_embed.image_url, description=description)
    add_unique_media_gallery_item(media_items, custom_embed.thumbnail_url, description=description)

    return media_items[:image_limit]


def truncate_component_text(content: str) -> str:
    """Trim a Text Display component to a conservative Discord-safe length.

    Returns:
        Original or truncated component text.
    """
    max_text_display_length: int = 4000
    if len(content) <= max_text_display_length:
        return content
    return f"{content[: max_text_display_length - 3]}..."


def get_component_text_display_content(custom_embed: CustomEmbed, entry: Entry) -> str:
    """Build markdown text for a Components V2 Text Display.

    Returns:
        Markdown content for a Text Display component.
    """
    parts: list[str] = []

    if custom_embed.title:
        parts.append(f"# {custom_embed.title}")

    if custom_embed.author_name and custom_embed.author_url:
        parts.append(f"## [{custom_embed.author_name}]({custom_embed.author_url})")
    elif custom_embed.author_name:
        parts.append(f"## {custom_embed.author_name}")
    elif custom_embed.author_url:
        parts.append(f"<{custom_embed.author_url}>")

    if custom_embed.description:
        parts.append(custom_embed.description)

    if custom_embed.footer_text:
        parts.append(f"-# {custom_embed.footer_text}")

    if not parts:
        fallback_text: str = entry.title or entry.link or entry.id
        if entry.link and fallback_text != entry.link:
            fallback_text = f"[{fallback_text}]({entry.link})"
        parts.append(fallback_text)

    return truncate_component_text("\n\n".join(parts))


def create_media_gallery_component(media_items: list[JsonObject]) -> JsonObject:
    """Build a Discord Media Gallery component.

    Returns:
        Discord Media Gallery component payload.
    """
    return {
        "type": 12,
        "items": [
            {
                "media": {"url": media_item["url"]},
                "description": media_item["description"],
            }
            for media_item in media_items[:10]
            if isinstance(media_item.get("url"), str) and isinstance(media_item.get("description"), str)
        ],
    }


def create_components_v2_webhook(
    webhook_url: str,
    entry: Entry,
    custom_embed: CustomEmbed,
    media_items: list[JsonObject],
) -> DiscordWebhook:
    """Create a Components V2 webhook with text and a media gallery.

    Returns:
        Webhook payload configured for Components V2.
    """
    components: list[JsonValue] = [
        {
            "type": 10,
            "content": get_component_text_display_content(custom_embed, entry),
        },
        create_media_gallery_component(media_items),
    ]
    return DiscordWebhook(
        url=webhook_url,
        flags=1 << 15,
        components=components,
        rate_limit_retry=True,
    )


def create_embed_webhook(  # noqa: C901, PLR0912
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
    media_gallery_image_limit: int = get_feed_media_gallery_image_limit(reader, feed)
    if media_gallery_image_limit == 0:
        custom_embed.image_url = ""
        custom_embed.thumbnail_url = ""

    media_gallery_items: list[JsonObject] = get_entry_media_gallery_items(
        entry,
        custom_embed,
        image_limit=media_gallery_image_limit,
    )
    if media_gallery_items:
        return create_components_v2_webhook(webhook_url, entry, custom_embed, media_gallery_items)

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


def send_to_discord(reader: Reader | None = None, feed: Feed | None = None, *, do_once: bool = False) -> None:
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

    # Check for new and modified entries for every feed.
    modified_entries: list[tuple[str, str]] = update_feeds_and_collect_modified_entries(
        effective_reader,
        scheduled=True,
        workers=os.cpu_count() or 1,
    )
    try:
        update_sent_webhooks_for_modified_entries(effective_reader, modified_entries)
    except (AssertionError, ReaderError, RequestException, HTTPError, OSError, ValueError):
        logger.exception("Failed to update saved Discord webhooks for modified feed entries.")

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

        decision = get_entry_filter_decision_from_reader(effective_reader, entry)
        if not decision.should_send:
            logger.info("Entry was skipped: %s (%s)", entry.id, decision.reason)
            continue

        webhook, _delivery_mode = create_webhook_for_entry(
            webhook_url,
            entry,
            effective_reader,
            use_default_message_on_empty=True,
        )

        # Send the entry to Discord because the combined blacklist/whitelist decision allowed it.
        execute_webhook(webhook, entry, reader=effective_reader)

        # If we only want to send one entry, we will break the loop. This is used when testing this function.
        if do_once:
            logger.info("Sent one entry to Discord. Breaking the loop.")
            break


def execute_webhook(
    webhook: DiscordWebhook,
    entry: Entry,
    reader: Reader,
    *,
    save_sent_webhook: bool = True,
) -> None:
    """Execute the webhook.

    Args:
        webhook (DiscordWebhook): The webhook to execute.
        entry (Entry): The entry to send to Discord.
        reader (Reader): The Reader instance to use for checking feed status.
        save_sent_webhook: Whether to save the sent Discord message metadata for future edits.
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

    request_payload: JsonObject = get_webhook_request_payload(webhook)
    payload: JsonObject = get_webhook_message_payload(webhook)
    response: Response = send_webhook_message(webhook, request_payload)
    logger.debug("Discord webhook response for entry %s: status=%s", entry.id, response.status_code)
    if response.status_code not in {200, 204}:
        msg: str = f"Error sending entry to Discord: {response.text}\n{pprint.pformat(request_payload)}"
        if entry:
            msg += f"\n{entry}"

        logger.error(msg)
    else:
        logger.info("Sent entry to Discord: %s", entry.id)
        if save_sent_webhook:
            webhook_url: str = get_webhook_url(reader, entry)
            if webhook_url:
                upsert_sent_webhook_record(reader, entry, webhook_url, webhook, response, payload)


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
        FeedUpdateError: If the initial feed update fails.
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
        raise FeedUpdateError(status_code=404, detail=f"Error updating feed: {e}") from e

    # Mark every entry as read, so we don't send all the old entries to Discord.
    entries: Iterable[Entry] = reader.get_entries(feed=clean_feed_url, read=False)
    for entry in entries:
        reader.set_entry_read(entry, True)

    if not default_custom_message:
        # TODO(TheLovinator): Show this error on the page.
        raise HTTPException(status_code=404, detail="Default custom message couldn't be found.")

    # This is the webhook that will be used to send the feed to Discord.
    reader.set_tag(clean_feed_url, "webhook", webhook_url)  # pyright: ignore[reportArgumentType]

    # Store sent Discord message ids by default so modified feed entries can edit the original webhook message.
    reader.set_tag(clean_feed_url, "save_sent_webhooks", True)  # pyright: ignore[reportArgumentType]

    # Keep the existing delivery behavior for new feeds unless changed from the feed page.
    reader.set_tag(
        clean_feed_url,
        "media_gallery_image_limit",
        cast("JSONType", 1),
    )

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
