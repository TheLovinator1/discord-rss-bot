from __future__ import annotations

import contextlib
import json
import re
import urllib.parse
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from typing import cast
from unittest.mock import MagicMock
from unittest.mock import patch

from fastapi.testclient import TestClient

import discord_rss_bot.main as main_module
from discord_rss_bot import feeds
from discord_rss_bot.main import app
from discord_rss_bot.main import create_html_for_feed
from discord_rss_bot.main import get_reader_dependency

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from httpx2 import Response
    from reader import Entry
    from reader import Reader

client: TestClient = TestClient(app)
webhook_name: str = "Hello, I am a webhook!"
webhook_url: str = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"
feed_url: str = "https://lovinator.space/rss_test.xml"
type TestTagValue = str | bool | int | list[dict[str, str]] | feeds.JsonValue | None
type TestKwargValue = str | int | None


def encoded_feed_url(url: str) -> str:
    return urllib.parse.quote(feed_url) if url else ""


def ensure_preview_feed_exists() -> Reader:
    reader: Reader = get_reader_dependency()
    with contextlib.suppress(Exception):
        reader.add_feed(feed_url)
    with contextlib.suppress(Exception):
        reader.update_feed(feed_url)
    return reader


def assert_social_preview_metadata(
    response: Response,
    *,
    title: str,
    description: str,
) -> None:
    assert title in response.text
    assert description in response.text


def test_search() -> None:
    """Test the /search page."""
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get("/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Delete the webhook if it already exists before we run the test.
    response: Response = client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    assert response.status_code == 200, f"Failed to delete webhook: {response.text}"

    # Add the webhook.
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Check that the feed was added.
    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert encoded_feed_url(feed_url) in response.text, f"Feed not found in /: {response.text}"

    # Search for an entry.
    response: Response = client.get(url="/search/?query=a")
    assert response.status_code == 200, f"Failed to search for entry: {response.text}"


def test_add_webhook() -> None:
    """Test the /add_webhook page."""
    # Delete the webhook if it already exists before we run the test.
    response: Response = client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    assert response.status_code == 200, f"Failed to delete webhook: {response.text}"

    # Add the webhook.
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Check that the webhook was added.
    response = client.get(url="/webhooks")
    assert response.status_code == 200, f"Failed to get /webhooks: {response.text}"
    assert webhook_name in response.text, f"Webhook not found in /webhooks: {response.text}"


def test_add_webhook_rejects_invalid_url() -> None:
    """Adding a webhook with a non-URL value should fail validation."""
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": "Invalid URL Hook", "webhook_url": "not-a-url"},
    )

    assert response.status_code == 400, f"Expected invalid webhook URL to be rejected: {response.text}"
    assert "Invalid webhook URL" in response.text


def test_add_webhook_allows_valid_url_after_invalid_attempt() -> None:
    """A rejected invalid webhook URL should not prevent a later valid add."""
    response: Response = client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    assert response.status_code == 200, f"Failed to delete webhook: {response.text}"

    response = client.post(
        url="/add_webhook",
        data={"webhook_name": "Invalid URL Hook", "webhook_url": "not-a-url"},
    )
    assert response.status_code == 400, f"Expected invalid webhook URL to be rejected: {response.text}"
    assert "Invalid webhook URL" in response.text

    response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook after invalid attempt: {response.text}"

    response = client.get(url="/webhooks")
    assert response.status_code == 200, f"Failed to get /webhooks: {response.text}"
    assert webhook_name in response.text, f"Webhook not found in /webhooks: {response.text}"

    response = client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    assert response.status_code == 200, f"Failed to delete webhook: {response.text}"


def test_webhooks_page_handles_invalid_stored_webhook_url() -> None:
    """/webhooks should render even if a malformed webhook URL is present in storage."""
    reader: Reader = get_reader_dependency()
    malformed_webhook_name = "Malformed hook"
    malformed_webhook_url = "definitely-not-a-url"

    reader.set_tag((), "webhooks", [{"name": malformed_webhook_name, "url": malformed_webhook_url}])  # pyright: ignore[reportArgumentType]
    response: Response = client.get(url="/webhooks")

    assert response.status_code == 200, f"/webhooks should not crash for malformed URLs: {response.text}"
    assert malformed_webhook_name in response.text


def test_create_feed() -> None:
    """Test the /create_feed page."""
    # Ensure webhook exists for this test regardless of test order.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Check that the feed was added.
    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert encoded_feed_url(feed_url) in response.text, f"Feed not found in /: {response.text}"


def test_create_feed_suggests_autodiscovered_links() -> None:
    """A page URL that fails to parse should render its advertised feed links."""
    submitted_url = "https://example.com/blog"
    discovered_url = "https://example.com/rss.xml"
    stub_reader = MagicMock()

    def get_tag(resource: str | tuple[()], key: str, default: TestTagValue = None) -> TestTagValue:
        if resource == () and key == "webhooks":
            return [{"name": webhook_name, "url": webhook_url}]
        if resource == () and key == "delivery_mode":
            return "embed"
        return default

    stub_reader.get_tag.side_effect = get_tag
    app.dependency_overrides[get_reader_dependency] = lambda: stub_reader

    try:
        with patch.object(
            main_module,
            "create_feed",
            side_effect=feeds.FeedUpdateError(
                status_code=404,
                detail="Error updating feed",
                autodiscover_links=[
                    {
                        "href": discovered_url,
                        "title": "Example feed",
                        "type": "application/rss+xml",
                    },
                ],
            ),
        ):
            response: Response = client.post(
                url="/add",
                data={"feed_url": submitted_url, "webhook_dropdown": webhook_name},
            )
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 404
    assert "Discovered feed links" in response.text
    assert "Example feed" in response.text
    assert discovered_url in response.text
    assert "application/rss+xml" in response.text
    assert f'value="{submitted_url}"' in response.text
    assert f'value="{webhook_name}"' in response.text


def test_get() -> None:
    """Test the /create_feed page."""
    # Ensure webhook exists for this test regardless of test order.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get("/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Check that the feed was added.
    response = client.get("/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert encoded_feed_url(feed_url) in response.text, f"Feed not found in /: {response.text}"

    response: Response = client.get(url="/add")
    assert response.status_code == 200, f"/add failed: {response.text}"

    response: Response = client.get(url="/add_webhook")
    assert response.status_code == 200, f"/add_webhook failed: {response.text}"

    response: Response = client.get(url="/blacklist", params={"feed_url": encoded_feed_url(feed_url)})
    assert response.status_code == 200, f"/blacklist failed: {response.text}"

    response: Response = client.get(url="/custom", params={"feed_url": encoded_feed_url(feed_url)})
    assert response.status_code == 200, f"/custom failed: {response.text}"

    response: Response = client.get(url="/embed", params={"feed_url": encoded_feed_url(feed_url)})
    assert response.status_code == 200, f"/embed failed: {response.text}"

    response: Response = client.get(url="/feed", params={"feed_url": encoded_feed_url(feed_url)})
    assert response.status_code == 200, f"/feed failed: {response.text}"
    assert "Feed Summary" in response.text
    assert "This feed" in response.text
    assert "Screenshot Delivery" in response.text
    assert "Image Delivery" in response.text
    assert 'type="range"' in response.text
    assert 'max="10"' in response.text

    response: Response = client.get(url="/")
    assert response.status_code == 200, f"/ failed: {response.text}"

    response: Response = client.get(url="/webhooks")
    assert response.status_code == 200, f"/webhooks failed: {response.text}"

    response = client.get(url="/webhook_entries", params={"webhook_url": webhook_url})
    assert response.status_code == 200, f"/webhook_entries failed: {response.text}"

    response: Response = client.get(url="/whitelist", params={"feed_url": encoded_feed_url(feed_url)})
    assert response.status_code == 200, f"/whitelist failed: {response.text}"


def test_blacklist_page_uses_live_preview_layout() -> None:
    ensure_preview_feed_exists()

    response: Response = client.get(url="/blacklist", params={"feed_url": encoded_feed_url(feed_url)})

    assert response.status_code == 200, f"/blacklist failed: {response.text}"
    assert 'hx-get="/blacklist_preview"' in response.text
    assert 'id="filter-preview"' in response.text
    assert "Blacklist Rules" in response.text


def test_whitelist_page_uses_live_preview_layout() -> None:
    ensure_preview_feed_exists()

    response: Response = client.get(url="/whitelist", params={"feed_url": encoded_feed_url(feed_url)})

    assert response.status_code == 200, f"/whitelist failed: {response.text}"
    assert 'hx-get="/whitelist_preview"' in response.text
    assert 'id="filter-preview"' in response.text
    assert "Whitelist Rules" in response.text


def test_blacklist_preview_does_not_persist_unsaved_rules() -> None:
    reader: Reader = ensure_preview_feed_exists()
    reader.set_tag(feed_url, "blacklist_title", "saved-blacklist")  # pyright: ignore[reportArgumentType]

    try:
        response: Response = client.get(
            url="/blacklist_preview",
            params={
                "feed_url": feed_url,
                "blacklist_title": "fvnnnfnfdnfdnfd",
            },
        )

        assert response.status_code == 200, f"/blacklist_preview failed: {response.text}"
        assert "Live preview" in response.text
        assert reader.get_tag(feed_url, "blacklist_title", "") == "saved-blacklist"
    finally:
        with contextlib.suppress(Exception):
            reader.delete_tag(feed_url, "blacklist_title")


def test_whitelist_preview_shows_blacklist_precedence() -> None:
    reader: Reader = ensure_preview_feed_exists()
    reader.set_tag(feed_url, "blacklist_title", "fvnnnfnfdnfdnfd")  # pyright: ignore[reportArgumentType]

    try:
        response: Response = client.get(
            url="/whitelist_preview",
            params={
                "feed_url": feed_url,
                "whitelist_title": "fvnnnfnfdnfdnfd",
            },
        )

        assert response.status_code == 200, f"/whitelist_preview failed: {response.text}"
        assert "blacklist overrides whitelist" in response.text
        assert "Skipped" in response.text
    finally:
        with contextlib.suppress(Exception):
            reader.delete_tag(feed_url, "blacklist_title")


def test_blacklist_preview_uses_50_entry_limit() -> None:
    @dataclass(slots=True)
    class DummyContent:
        value: str

    @dataclass(slots=True)
    class DummyFeed:
        url: str
        title: str

    @dataclass(slots=True)
    class DummyEntry:
        id: str
        feed: DummyFeed
        title: str
        summary: str
        author: str
        authors_str: str
        link: str
        published: datetime | None
        content: list[DummyContent] = field(default_factory=lambda: [DummyContent("content")])

    class StubReader:
        def __init__(self) -> None:
            self.feed = DummyFeed(url="https://example.com/filter-preview.xml", title="Preview Feed")
            self.recorded_limit: int | None = None
            self.entries: list[Entry] = [
                cast(
                    "Entry",
                    DummyEntry(
                        id=f"entry-{index}",
                        feed=self.feed,
                        title=f"Entry {index}",
                        summary=f"Summary {index}",
                        author="Author",
                        authors_str="Author",
                        link=f"https://example.com/entry-{index}",
                        published=datetime(2024, 1, 1, tzinfo=UTC),
                    ),
                )
                for index in range(60)
            ]

        def get_feed(self, _feed_url: str) -> DummyFeed:
            return self.feed

        def get_entries(self, **kwargs: TestKwargValue) -> list[Entry]:
            limit = kwargs.get("limit")
            self.recorded_limit = limit if isinstance(limit, int) else None
            if isinstance(limit, int):
                return self.entries[:limit]
            return self.entries

        def get_tag(self, _resource: str | DummyFeed, _key: str, default: TestTagValue = None) -> TestTagValue:
            return default

    stub_reader = StubReader()
    app.dependency_overrides[get_reader_dependency] = lambda: stub_reader

    try:
        with patch("discord_rss_bot.main.create_html_for_feed", return_value="<div>Rendered</div>"):
            response: Response = client.get(
                url="/blacklist_preview",
                params={"feed_url": stub_reader.feed.url},
            )

        assert response.status_code == 200, f"/blacklist_preview failed: {response.text}"
        assert stub_reader.recorded_limit == 50, (
            f"Expected preview to request 50 entries, got {stub_reader.recorded_limit}"
        )
        assert "50 checked" in response.text
    finally:
        app.dependency_overrides = {}


def test_blacklist_preview_shows_labeled_field_values_for_substring_match() -> None:
    @dataclass(slots=True)
    class DummyContent:
        value: str

    @dataclass(slots=True)
    class DummyFeed:
        url: str
        title: str

    @dataclass(slots=True)
    class DummyEntry:
        id: str
        feed: DummyFeed
        title: str
        summary: str
        author: str
        authors_str: str
        link: str
        published: datetime | None
        content: list[DummyContent] = field(default_factory=list)

    class StubReader:
        def __init__(self) -> None:
            self.feed = DummyFeed(url="https://example.com/wow.xml", title="Warcraft Feed")
            self.entries: list[Entry] = [
                cast(
                    "Entry",
                    DummyEntry(
                        id="wow-1",
                        feed=self.feed,
                        title="World of Warcraft",
                        summary="<p>Massive MMO news update</p>",
                        author="Legacy Blizzard Author",
                        authors_str="Blizzard Author One, Blizzard Author Two",
                        link="https://example.com/wow-1",
                        published=datetime(2024, 1, 1, tzinfo=UTC),
                        content=[DummyContent("<p>The expansion launches soon.</p>")],
                    ),
                ),
            ]

        def get_feed(self, _feed_url: str) -> DummyFeed:
            return self.feed

        def get_entries(self, **_kwargs: TestKwargValue) -> list[Entry]:
            return self.entries

        def get_tag(self, _resource: str | DummyFeed, _key: str, default: TestTagValue = None) -> TestTagValue:
            return default

    stub_reader = StubReader()
    app.dependency_overrides[get_reader_dependency] = lambda: stub_reader

    try:
        with patch("discord_rss_bot.main.create_html_for_feed", return_value="<div>Rendered</div>"):
            response: Response = client.get(
                url="/blacklist_preview",
                params={
                    "feed_url": stub_reader.feed.url,
                    "blacklist_title": "orld",
                },
            )

        assert response.status_code == 200, f"/blacklist_preview failed: {response.text}"
        assert "Skipped" in response.text
        assert "World of Warcraft" in response.text
        assert "Title" in response.text
        assert "Author" in response.text
        assert "Description" in response.text
        assert "Content" in response.text
        assert "filter-preview__field-row" in response.text
        assert "filter-preview__match" in response.text
        assert '<mark class="filter-preview__match filter-preview__match--danger">orld</mark>' in response.text
        assert "Massive MMO news update" in response.text
        assert "The expansion launches soon." in response.text
        assert "By Blizzard Author One, Blizzard Author Two |" in response.text
        assert "Legacy Blizzard Author" not in response.text
    finally:
        app.dependency_overrides = {}


def test_author_templates_render_authors_str() -> None:
    request = SimpleNamespace(url="https://example.com/page", base_url="https://example.com/")
    feed = SimpleNamespace(
        title="Example Feed",
        url="https://example.com/feed.xml",
        author="Legacy Feed Author",
        authors_str="Feed Author One, Feed Author Two",
        added=None,
        last_exception=None,
        last_updated=None,
        link="https://example.com/feed",
        subtitle="",
        updated=None,
        updates_enabled=True,
        user_title="",
        version="atom10",
    )
    entry = SimpleNamespace(
        id="entry-1",
        title="Entry Title",
        link="https://example.com/entry-1",
        author="Legacy Entry Author",
        authors_str="Entry Author One, Entry Author Two",
        added=None,
        content=[],
        important=False,
        published=None,
        read=False,
        read_modified=None,
        summary="Summary",
        updated=None,
    )
    filter_row = SimpleNamespace(
        entry=entry,
        published_label="Never",
        status_class="success",
        status_label="Sent",
        decision=SimpleNamespace(reason="Sent", blacklist_match=None, whitelist_match=None),
        field_rows=[],
        first_image="",
    )
    preview_summary = SimpleNamespace(
        total=1,
        sent=1,
        skipped=0,
        blacklist_matches=0,
        whitelist_matches=0,
    )

    custom_html: str = main_module.templates.get_template("custom.html").render(
        request=request,
        feed=feed,
        entry=entry,
        custom_message="",
    )
    embed_html: str = main_module.templates.get_template("embed.html").render(
        request=request,
        feed=feed,
        entry=entry,
    )
    filter_preview_html: str = main_module.templates.get_template("_filter_preview.html").render(
        feed=feed,
        preview_limit=50,
        preview_summary=preview_summary,
        preview_helper_text="",
        preview_rows=[filter_row],
    )

    for html in (custom_html, embed_html):
        assert "Feed Author One, Feed Author Two" in html
        assert "Entry Author One, Entry Author Two" in html
        assert "Legacy Feed Author" not in html
        assert "Legacy Entry Author" not in html

    assert "By Entry Author One, Entry Author Two |" in filter_preview_html
    assert "Legacy Entry Author" not in filter_preview_html


def test_settings_page_shows_screenshot_layout_setting() -> None:
    response: Response = client.get(url="/settings")
    assert response.status_code == 200, f"/settings failed: {response.text}"
    assert "Default delivery mode for new feeds" in response.text
    assert "Default screenshot layout for new feeds" in response.text
    assert "uv run playwright install chromium" in response.text


def test_set_global_delivery_mode() -> None:
    response: Response = client.post(url="/set_global_delivery_mode", data={"delivery_mode": "text"})
    assert response.status_code == 200, f"Failed to set global delivery mode: {response.text}"

    response = client.get(url="/settings")
    assert response.status_code == 200, f"/settings failed after setting delivery mode: {response.text}"
    assert re.search(r"<option\s+value=\"text\"[^>]*\bselected\b", response.text)


def test_add_page_shows_global_default_delivery_mode_hint() -> None:
    response: Response = client.post(url="/set_global_delivery_mode", data={"delivery_mode": "text"})
    assert response.status_code == 200, f"Failed to set global delivery mode: {response.text}"

    response = client.get(url="/add")
    assert response.status_code == 200, f"/add failed: {response.text}"
    assert "text" in response.text


def test_navbar_add_feed_visible_only_when_webhooks_exist() -> None:
    reader: Reader = get_reader_dependency()
    reader.set_tag((), "webhooks", [])  # pyright: ignore[reportArgumentType]

    response: Response = client.get(url="/")
    assert response.status_code == 200, f"/ failed: {response.text}"
    assert '<a class="nav-link" href="/add">Add feed</a>' not in response.text

    response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    response = client.get(url="/")
    assert response.status_code == 200, f"/ failed: {response.text}"
    assert '<a class="nav-link" href="/add">Add feed</a>' in response.text

    cleanup_response: Response = client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    assert cleanup_response.status_code == 200, f"Failed to clean up webhook: {cleanup_response.text}"


def test_c3kay_feed_delivery_mode_toggle_routes_update_stored_tags() -> None:
    reader = get_reader_dependency()
    c3kay_feed_url = "https://feeds.c3kay.de/hoyolab-ui-toggle-test.xml"

    with contextlib.suppress(Exception):
        reader.add_feed(c3kay_feed_url)

    response: Response = client.post(url="/use_text", data={"feed_url": c3kay_feed_url})
    assert response.status_code == 200, f"Failed to set text mode: {response.text}"
    assert reader.get_tag(c3kay_feed_url, "delivery_mode") == "text"
    assert reader.get_tag(c3kay_feed_url, "should_send_embed") is False

    response = client.post(url="/use_screenshot_mobile", data={"feed_url": c3kay_feed_url})
    assert response.status_code == 200, f"Failed to set screenshot mobile mode: {response.text}"
    assert reader.get_tag(c3kay_feed_url, "delivery_mode") == "screenshot"
    assert reader.get_tag(c3kay_feed_url, "screenshot_layout") == "mobile"
    assert reader.get_tag(c3kay_feed_url, "should_send_embed") is False
    assert "Disable screenshot delivery" in response.text
    assert "Send embed instead of screenshot" not in response.text

    response = client.post(url="/use_embed", data={"feed_url": c3kay_feed_url})
    assert response.status_code == 200, f"Failed to set embed mode: {response.text}"
    assert reader.get_tag(c3kay_feed_url, "delivery_mode") == "embed"
    assert reader.get_tag(c3kay_feed_url, "should_send_embed") is True


def test_set_feed_save_sent_webhooks_route_updates_stored_tag() -> None:
    @dataclass(slots=True)
    class DummyFeed:
        url: str
        title: str

    class StubReader:
        def __init__(self) -> None:
            self.feed = DummyFeed(url="https://example.com/feed.xml", title="Example")
            self.tags: dict[tuple[str, str], bool] = {}

        def get_feed(self, feed_url: str) -> DummyFeed:
            assert feed_url == self.feed.url
            return self.feed

        def set_tag(self, resource: str, key: str, value: bool) -> None:  # noqa: FBT001
            self.tags[resource, key] = value

    stub_reader = StubReader()
    app.dependency_overrides[get_reader_dependency] = lambda: stub_reader

    try:
        with patch("discord_rss_bot.main.commit_state_change"):
            response: Response = client.post(
                url="/set_feed_save_sent_webhooks",
                data={"feed_url": stub_reader.feed.url, "enabled": "false"},
                follow_redirects=False,
            )

        assert response.status_code == 303, f"/set_feed_save_sent_webhooks failed: {response.text}"
        assert stub_reader.tags[stub_reader.feed.url, "save_sent_webhooks"] is False
    finally:
        app.dependency_overrides = {}


def test_set_feed_media_gallery_image_limit_route_updates_stored_tag() -> None:
    @dataclass(slots=True)
    class DummyFeed:
        url: str
        title: str

    class StubReader:
        def __init__(self) -> None:
            self.feed = DummyFeed(url="https://example.com/feed.xml", title="Example")
            self.tags: dict[tuple[str, str], int] = {}

        def get_feed(self, feed_url: str) -> DummyFeed:
            assert feed_url == self.feed.url
            return self.feed

        def set_tag(self, resource: str, key: str, value: int) -> None:
            self.tags[resource, key] = value

    stub_reader = StubReader()
    app.dependency_overrides[get_reader_dependency] = lambda: stub_reader

    try:
        with patch("discord_rss_bot.main.commit_state_change"):
            response: Response = client.post(
                url="/set_feed_media_gallery_image_limit",
                data={"feed_url": stub_reader.feed.url, "image_limit": "7"},
                follow_redirects=False,
            )

        assert response.status_code == 303, f"/set_feed_media_gallery_image_limit failed: {response.text}"
        assert stub_reader.tags[stub_reader.feed.url, "media_gallery_image_limit"] == 7
    finally:
        app.dependency_overrides = {}


def test_sent_webhooks_view_shows_saved_records() -> None:
    @dataclass(slots=True)
    class DummyFeed:
        url: str
        title: str

    sent_webhook_url = "https://discord.com/api/webhooks/123/abc"
    sent_feed_url = "https://example.com/feed.xml"

    class StubReader:
        def __init__(self) -> None:
            self.feed = DummyFeed(url=sent_feed_url, title="Example feed")

        def get_tag(
            self,
            resource: str | tuple[()],
            key: str,
            default: feeds.JsonValue = None,
        ) -> feeds.JsonValue:
            if resource == () and key == "sent_webhooks":
                return [
                    {
                        "feed_url": sent_feed_url,
                        "feed_title": "Example feed",
                        "entry_id": "entry-1",
                        "entry_title": "Fixed typo",
                        "entry_link": "https://example.com/entry-1",
                        "webhook_url": sent_webhook_url,
                        "message_id": "message-1",
                        "delivery_mode": "text",
                        "payload": {"content": "Fixed typo", "embeds": [], "attachments": []},
                        "discord_response": {"id": "message-1", "channel_id": "channel-1"},
                        "response_text": '{"id": "message-1", "channel_id": "channel-1"}',
                        "last_updated_at": "2026-05-08T12:00:00+00:00",
                        "last_status_code": 200,
                        "update_count": 1,
                    },
                ]
            if resource == () and key == "webhooks":
                return [{"name": "Main", "url": sent_webhook_url}]
            return default

        def get_feeds(self) -> list[DummyFeed]:
            return [self.feed]

    app.dependency_overrides[get_reader_dependency] = StubReader

    try:
        response: Response = client.get(url="/sent_webhooks")

        assert response.status_code == 200, f"/sent_webhooks failed: {response.text}"
        assert "Fixed typo" in response.text
        assert "message-1" in response.text
        assert "channel-1" in response.text
        assert sent_webhook_url not in response.text
        assert "HTTP 200" in response.text
        assert "Example feed" in response.text
        assert "Main" in response.text
    finally:
        app.dependency_overrides = {}


def test_set_global_screenshot_layout() -> None:
    response: Response = client.post(url="/set_global_screenshot_layout", data={"screenshot_layout": "mobile"})
    assert response.status_code == 200, f"Failed to set global screenshot layout: {response.text}"

    response = client.get(url="/settings")
    assert response.status_code == 200, f"/settings failed after setting layout: {response.text}"
    assert re.search(r"<option\s+value=\"mobile\"[^>]*\bselected\b", response.text)


def test_pause_feed() -> None:
    """Test the /pause_feed page."""
    # Ensure webhook exists for this test regardless of test order.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Unpause the feed if it is paused.
    feeds: Response = client.get(url="/")
    if "Paused" in feeds.text:
        response: Response = client.post(url="/unpause", data={"feed_url": feed_url})
        assert response.status_code == 200, f"Failed to unpause feed: {response.text}"

    # Pause the feed.
    response: Response = client.post(url="/pause", data={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to pause feed: {response.text}"

    # Check that the feed was paused.
    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert encoded_feed_url(feed_url) in response.text, f"Feed not found in /: {response.text}"


def test_unpause_feed() -> None:
    """Test the /unpause_feed page."""
    # Ensure webhook exists for this test regardless of test order.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get("/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Pause the feed if it is unpaused.
    feeds: Response = client.get(url="/")
    if "Paused" not in feeds.text:
        response: Response = client.post(url="/pause", data={"feed_url": feed_url})
        assert response.status_code == 200, f"Failed to pause feed: {response.text}"

    # Unpause the feed.
    response: Response = client.post(url="/unpause", data={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to unpause feed: {response.text}"

    # Check that the feed was unpaused.
    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert encoded_feed_url(feed_url) in response.text, f"Feed not found in /: {response.text}"


def test_remove_feed() -> None:
    """Test the /remove page."""
    # Ensure webhook exists for this test regardless of test order.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})
        client.post(url="/remove", data={"feed_url": encoded_feed_url(feed_url)})

    # Add the feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Remove the feed.
    response: Response = client.post(url="/remove", data={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to remove feed: {response.text}"

    # Check that the feed was removed.
    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert feed_url not in response.text, f"Feed found in /: {response.text}"


def test_change_feed_url() -> None:
    """Test changing a feed URL from the feed page endpoint."""
    new_feed_url = "https://lovinator.space/rss_test_small.xml"

    # Ensure test feeds do not already exist.
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/remove", data={"feed_url": new_feed_url})

    # Ensure webhook exists.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Add the original feed.
    response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Change feed URL.
    response = client.post(
        url="/change_feed_url",
        data={"old_feed_url": feed_url, "new_feed_url": new_feed_url},
    )
    assert response.status_code == 200, f"Failed to change feed URL: {response.text}"

    # New feed should be accessible.
    response = client.get(url="/feed", params={"feed_url": new_feed_url})
    assert response.status_code == 200, f"New feed URL is not accessible: {response.text}"

    # Old feed should no longer be accessible.
    response = client.get(url="/feed", params={"feed_url": feed_url})
    assert response.status_code == 404, "Old feed URL should no longer exist"

    # Cleanup.
    client.post(url="/remove", data={"feed_url": new_feed_url})


def test_change_feed_url_marks_entries_as_read() -> None:
    """After changing a feed URL all entries on the new feed should be marked read to prevent resending."""
    new_feed_url = "https://lovinator.space/rss_test_small.xml"

    # Ensure feeds do not already exist.
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/remove", data={"feed_url": new_feed_url})

    # Ensure webhook exists.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    client.post(url="/add_webhook", data={"webhook_name": webhook_name, "webhook_url": webhook_url})

    # Add the original feed.
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Patch reader on the main module so we can observe calls.
    mock_entry_a = MagicMock()
    mock_entry_a.id = "entry-a"
    mock_entry_b = MagicMock()
    mock_entry_b.id = "entry-b"

    real_reader = main_module.get_reader_dependency()

    # Use a no-redirect client so the POST response is inspected directly; the
    # redirect target (/feed?feed_url=…) would 404 because change_feed_url is mocked.
    no_redirect_client = TestClient(app, follow_redirects=False)

    with (
        patch.object(real_reader, "get_entries", return_value=[mock_entry_a, mock_entry_b]) as mock_get_entries,
        patch.object(real_reader, "set_entry_read") as mock_set_read,
        patch.object(real_reader, "update_feed") as mock_update_feed,
        patch.object(real_reader, "change_feed_url"),
    ):
        response = no_redirect_client.post(
            url="/change_feed_url",
            data={"old_feed_url": feed_url, "new_feed_url": new_feed_url},
        )
        assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"

        # update_feed should have been called with the new URL.
        mock_update_feed.assert_called_once_with(new_feed_url)

        # get_entries should have been called to fetch unread entries on the new URL.
        mock_get_entries.assert_called_once_with(feed=new_feed_url, read=False)

        # Every returned entry should have been marked as read.
        assert mock_set_read.call_count == 2, f"Expected 2 set_entry_read calls, got {mock_set_read.call_count}"
        mock_set_read.assert_any_call(mock_entry_a, True)
        mock_set_read.assert_any_call(mock_entry_b, True)

    # Cleanup.
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/remove", data={"feed_url": new_feed_url})


def test_change_feed_url_empty_old_url_returns_400() -> None:
    """Submitting an empty old_feed_url should return HTTP 400."""
    response: Response = client.post(
        url="/change_feed_url",
        data={"old_feed_url": "   ", "new_feed_url": "https://example.com/feed.xml"},
    )
    assert response.status_code == 400, f"Expected 400 for empty old URL, got {response.status_code}"


def test_change_feed_url_empty_new_url_returns_400() -> None:
    """Submitting a blank new_feed_url should return HTTP 400."""
    response: Response = client.post(
        url="/change_feed_url",
        data={"old_feed_url": feed_url, "new_feed_url": "   "},
    )
    assert response.status_code == 400, f"Expected 400 for blank new URL, got {response.status_code}"


def test_change_feed_url_nonexistent_old_url_returns_404() -> None:
    """Trying to rename a feed that does not exist should return HTTP 404."""
    non_existent = "https://does-not-exist.example.com/rss.xml"
    # Make sure it really is absent.
    client.post(url="/remove", data={"feed_url": non_existent})

    response: Response = client.post(
        url="/change_feed_url",
        data={"old_feed_url": non_existent, "new_feed_url": "https://example.com/new.xml"},
    )
    assert response.status_code == 404, f"Expected 404 for non-existent feed, got {response.status_code}"


def test_change_feed_url_new_url_already_exists_returns_409() -> None:
    """Changing to a URL that is already tracked should return HTTP 409."""
    second_feed_url = "https://example.com/existing.xml"

    class StubReader:
        def change_feed_url(self, _old_url: str, new_url: str) -> None:
            raise feeds.FeedExistsError(new_url)

    app.dependency_overrides[get_reader_dependency] = StubReader
    try:
        response: Response = client.post(
            url="/change_feed_url",
            data={"old_feed_url": feed_url, "new_feed_url": second_feed_url},
        )
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 409, f"Expected 409 when new URL already exists, got {response.status_code}"


def test_change_feed_url_same_url_redirects_without_error() -> None:
    """Changing a feed's URL to itself should redirect cleanly without any error."""
    # Ensure webhook exists.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    client.post(url="/add_webhook", data={"webhook_name": webhook_name, "webhook_url": webhook_url})

    # Add the feed.
    client.post(url="/remove", data={"feed_url": feed_url})
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Submit the same URL as both old and new.
    response = client.post(
        url="/change_feed_url",
        data={"old_feed_url": feed_url, "new_feed_url": feed_url},
    )
    assert response.status_code == 200, f"Expected 200 redirect for same URL, got {response.status_code}"

    # Feed should still be accessible.
    response = client.get(url="/feed", params={"feed_url": feed_url})
    assert response.status_code == 200, f"Feed should still exist after no-op URL change: {response.text}"

    # Cleanup.
    client.post(url="/remove", data={"feed_url": feed_url})


def test_delete_webhook() -> None:
    """Test the /delete_webhook page."""
    # Remove the feed if it already exists before we run the test.
    feeds: Response = client.get(url="/webhooks")
    if webhook_url in feeds.text:
        client.post(url="/delete_webhook", data={"webhook_url": webhook_url})

    # Add the webhook.
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Delete the webhook.
    response2: Response = client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    assert response2.status_code == 200, f"Failed to delete webhook: {response2.text}"

    # Check that the webhook was added.
    response3 = client.get(url="/webhooks")
    assert response3.status_code == 200, f"Failed to get /webhooks: {response3.text}"
    assert webhook_name not in response3.text, f"Webhook found in /webhooks: {response3.text}"


def test_attach_feed_webhook_from_index() -> None:
    """Feeds without attached webhook should be attachable from the index page."""
    original_webhook_name = "original-webhook"
    original_webhook_url = "https://discord.com/api/webhooks/111/original"
    replacement_webhook_name = "replacement-webhook"
    replacement_webhook_url = "https://discord.com/api/webhooks/222/replacement"

    # Start clean.
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/delete_webhook", data={"webhook_url": original_webhook_url})
    client.post(url="/delete_webhook", data={"webhook_url": replacement_webhook_url})

    # Add a webhook and a feed attached to it.
    response = client.post(
        url="/add_webhook",
        data={"webhook_name": original_webhook_name, "webhook_url": original_webhook_url},
    )
    assert response.status_code == 200, f"Failed to add original webhook: {response.text}"

    response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": original_webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Remove the original webhook so feed becomes "without attached webhook".
    response = client.post(url="/delete_webhook", data={"webhook_url": original_webhook_url})
    assert response.status_code == 200, f"Failed to delete original webhook: {response.text}"

    # Add a replacement webhook we can attach to.
    response = client.post(
        url="/add_webhook",
        data={"webhook_name": replacement_webhook_name, "webhook_url": replacement_webhook_url},
    )
    assert response.status_code == 200, f"Failed to add replacement webhook: {response.text}"

    # The feed should now be listed in "Feeds without attached webhook" section.
    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"
    assert "Feeds without attached webhook:" in response.text
    assert "/attach_feed_webhook" in response.text

    # Attach the feed to the new webhook.
    response = client.post(
        url="/attach_feed_webhook",
        data={"feed_url": feed_url, "webhook_dropdown": replacement_webhook_name, "redirect_to": "/"},
    )
    assert response.status_code == 200, f"Failed to attach feed to webhook: {response.text}"

    reader = get_reader_dependency()
    assert reader.get_tag(feed_url, "webhook", "") == replacement_webhook_url

    # Cleanup.
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/delete_webhook", data={"webhook_url": replacement_webhook_url})


def test_attach_feed_webhook_from_feed_page() -> None:
    """Feed detail page should allow attaching/replacing webhook directly."""
    original_webhook_name = "feed-page-original-webhook"
    original_webhook_url = "https://discord.com/api/webhooks/333/original"
    replacement_webhook_name = "feed-page-replacement-webhook"
    replacement_webhook_url = "https://discord.com/api/webhooks/444/replacement"

    # Start clean.
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/delete_webhook", data={"webhook_url": original_webhook_url})
    client.post(url="/delete_webhook", data={"webhook_url": replacement_webhook_url})

    # Create two webhooks and attach feed to original.
    response = client.post(
        url="/add_webhook",
        data={"webhook_name": original_webhook_name, "webhook_url": original_webhook_url},
    )
    assert response.status_code == 200, f"Failed to add original webhook: {response.text}"

    response = client.post(
        url="/add_webhook",
        data={"webhook_name": replacement_webhook_name, "webhook_url": replacement_webhook_url},
    )
    assert response.status_code == 200, f"Failed to add replacement webhook: {response.text}"

    response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": original_webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Feed page should show the webhook form and current webhook label.
    response = client.get(url="/feed", params={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to get /feed: {response.text}"
    assert "Current webhook:" in response.text
    assert "/attach_feed_webhook" in response.text

    # Reattach to replacement webhook via endpoint used by feed page form.
    response = client.post(
        url="/attach_feed_webhook",
        data={
            "feed_url": feed_url,
            "webhook_dropdown": replacement_webhook_name,
            "redirect_to": f"/feed?feed_url={urllib.parse.quote(feed_url)}",
        },
    )
    assert response.status_code == 200, f"Failed to reattach feed webhook: {response.text}"

    reader = get_reader_dependency()
    assert reader.get_tag(feed_url, "webhook", "") == replacement_webhook_url

    # Cleanup.
    client.post(url="/remove", data={"feed_url": feed_url})
    client.post(url="/delete_webhook", data={"webhook_url": original_webhook_url})
    client.post(url="/delete_webhook", data={"webhook_url": replacement_webhook_url})


def test_update_feed_not_found() -> None:
    """Test updating a non-existent feed."""
    # Generate a feed URL that does not exist
    nonexistent_feed_url = "https://nonexistent-feed.example.com/rss.xml"

    # Try to update the non-existent feed
    response: Response = client.get(url="/update", params={"feed_url": urllib.parse.quote(nonexistent_feed_url)})

    # Check that it returns a 404 status code
    assert response.status_code == 404, f"Expected 404 for non-existent feed, got: {response.status_code}"
    assert "Feed not found" in response.text


def test_update_feed_updates_saved_webhooks_for_modified_entries() -> None:
    class StubReader:
        pass

    stub_reader = StubReader()
    modified_entries = [("https://example.com/feed.xml", "entry-1")]
    app.dependency_overrides[get_reader_dependency] = lambda: stub_reader

    try:
        with (
            patch(
                "discord_rss_bot.main.update_feed_and_collect_modified_entries",
                return_value=modified_entries,
            ) as mock_update_feed,
            patch("discord_rss_bot.main.update_sent_webhooks_for_modified_entries") as mock_update_webhooks,
        ):
            response: Response = client.get(
                url="/update",
                params={"feed_url": "https://example.com/feed.xml"},
                follow_redirects=False,
            )

        assert response.status_code == 303, f"Expected redirect after update, got: {response.text}"
        mock_update_feed.assert_called_once_with(stub_reader, "https://example.com/feed.xml")
        mock_update_webhooks.assert_called_once_with(stub_reader, modified_entries)
    finally:
        app.dependency_overrides = {}


def test_post_entry_send_to_discord() -> None:
    """Test that /post_entry sends an entry to Discord and redirects to the feed page.

    Regression test for the bug where the injected reader was not passed to
    send_entry_to_discord, meaning the dependency-injected reader was silently ignored.
    """
    # Ensure webhook and feed exist.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Retrieve an entry from the feed to get a valid entry ID.
    reader: main_module.Reader = main_module.get_reader_dependency()
    entries: list[Entry] = list(reader.get_entries(feed=feed_url, limit=1))
    assert entries, "Feed should have at least one entry to send"
    entry_to_send: main_module.Entry = entries[0]
    encoded_id: str = urllib.parse.quote(entry_to_send.id)

    no_redirect_client = TestClient(app, follow_redirects=False)

    # Patch execute_webhook so no real HTTP requests are made to Discord.
    with patch("discord_rss_bot.feeds.execute_webhook") as mock_execute:
        response = no_redirect_client.get(
            url="/post_entry",
            params={"entry_id": encoded_id, "feed_url": urllib.parse.quote(feed_url)},
        )

    assert response.status_code == 303, f"Expected redirect after sending, got {response.status_code}: {response.text}"
    location: str = response.headers.get("location", "")
    assert "feed?feed_url=" in location, f"Should redirect to feed page, got: {location}"
    assert mock_execute.called, "execute_webhook should have been called to deliver the entry to Discord"

    # Cleanup.
    client.post(url="/remove", data={"feed_url": feed_url})


def test_post_entry_unknown_id_returns_404() -> None:
    """Test that /post_entry returns 404 when the entry ID does not exist."""
    response: Response = client.get(
        url="/post_entry",
        params={"entry_id": "https://nonexistent.example.com/entry-that-does-not-exist"},
    )
    assert response.status_code == 404, f"Expected 404 for unknown entry, got {response.status_code}"


def test_post_entry_uses_feed_url_to_disambiguate_duplicate_ids() -> None:
    """When IDs collide across feeds, /post_entry should pick the entry from provided feed_url."""

    @dataclass(slots=True)
    class DummyFeed:
        url: str

    @dataclass(slots=True)
    class DummyEntry:
        id: str
        feed: DummyFeed
        feed_url: str

    feed_a = "https://example.com/feed-a.xml"
    feed_b = "https://example.com/feed-b.xml"
    shared_id = "https://example.com/shared-entry-id"

    entry_a: Entry = cast("Entry", DummyEntry(id=shared_id, feed=DummyFeed(feed_a), feed_url=feed_a))
    entry_b: Entry = cast("Entry", DummyEntry(id=shared_id, feed=DummyFeed(feed_b), feed_url=feed_b))

    class StubReader:
        def get_entries(self, feed: str | None = None) -> list[Entry]:
            if feed == feed_a:
                return [entry_a]
            if feed == feed_b:
                return [entry_b]
            return [entry_a, entry_b]

    selected_feed_urls: list[str] = []

    def fake_send_entry_to_discord(entry: Entry, reader: Reader) -> None:
        selected_feed_urls.append(entry.feed.url)

    app.dependency_overrides[get_reader_dependency] = StubReader
    no_redirect_client = TestClient(app, follow_redirects=False)

    try:
        with patch("discord_rss_bot.main.send_entry_to_discord", side_effect=fake_send_entry_to_discord):
            response: Response = no_redirect_client.get(
                url="/post_entry",
                params={"entry_id": urllib.parse.quote(shared_id), "feed_url": urllib.parse.quote(feed_b)},
            )

        assert response.status_code == 303, f"Expected redirect after sending, got {response.status_code}"
        assert selected_feed_urls == [feed_b], f"Expected feed-b entry, got: {selected_feed_urls}"

        location = response.headers.get("location", "")
        assert urllib.parse.quote(feed_b) in location, f"Expected redirect to feed-b page, got: {location}"
    finally:
        app.dependency_overrides = {}


def test_navbar_backup_link_hidden_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the backup link is not shown in the navbar when GIT_BACKUP_PATH is not set."""
    # Ensure GIT_BACKUP_PATH is not set
    monkeypatch.delenv("GIT_BACKUP_PATH", raising=False)

    # Get the index page
    response: Response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"

    # Check that the backup button is not in the response
    assert "Backup" not in response.text or 'action="/backup"' not in response.text, (
        "Backup button should not be visible when GIT_BACKUP_PATH is not configured"
    )


def test_navbar_backup_link_visible_when_configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test that the backup link is shown in the navbar when GIT_BACKUP_PATH is set."""
    # Set GIT_BACKUP_PATH
    monkeypatch.setenv("GIT_BACKUP_PATH", str(tmp_path))

    # Get the index page
    response: Response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"

    # Check that the backup button is in the response
    assert "Backup" in response.text, "Backup button text should be visible when GIT_BACKUP_PATH is configured"
    assert 'action="/backup"' in response.text, "Backup form should be visible when GIT_BACKUP_PATH is configured"


def test_backup_endpoint_returns_error_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the backup endpoint returns an error when GIT_BACKUP_PATH is not set."""
    # Ensure GIT_BACKUP_PATH is not set
    monkeypatch.delenv("GIT_BACKUP_PATH", raising=False)

    # Try to trigger a backup
    response: Response = client.post(url="/backup")

    # Should redirect to index with error message
    assert response.status_code == 200, f"Failed to post /backup: {response.text}"
    assert "Git backup is not configured" in response.text or "GIT_BACKUP_PATH" in response.text, (
        "Error message about backup not being configured should be shown"
    )


def test_show_more_entries_button_visible_when_many_entries() -> None:
    """Test that the 'Show more entries' button is visible when there are more than 20 entries."""
    # Add the webhook first
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})

    # Add the feed
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get the feed page
    response: Response = client.get(url="/feed", params={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to get /feed: {response.text}"

    # Check if the feed has more than 20 entries by looking at the response
    # The button should be visible if there are more than 20 entries
    # We check for both the button text and the link structure
    if "Show more entries" in response.text:
        # Button is visible - verify it has the correct structure
        assert "starting_after=" in response.text, "Show more entries button should contain starting_after parameter"
        # The button should be a link to the feed page with pagination
        assert (
            f'href="/feed?feed_url={urllib.parse.quote(feed_url)}' in response.text
            or f'href="/feed?feed_url={encoded_feed_url(feed_url)}' in response.text
        ), "Show more entries button should link back to the feed page"


def test_show_more_entries_button_not_visible_when_few_entries() -> None:
    """Test that the 'Show more entries' button is not visible when there are 20 or fewer entries."""
    # Ensure webhook exists for this test regardless of test order.
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Use a feed with very few entries
    small_feed_url = "https://lovinator.space/rss_test_small.xml"

    # Clean up if exists
    client.post(url="/remove", data={"feed_url": small_feed_url})

    # Add a small feed (this may not exist, so this test is conditional)
    response: Response = client.post(url="/add", data={"feed_url": small_feed_url, "webhook_dropdown": webhook_name})

    if response.status_code == 200:
        # Get the feed page
        response: Response = client.get(url="/feed", params={"feed_url": small_feed_url})
        assert response.status_code == 200, f"Failed to get /feed: {response.text}"

        # If the feed has 20 or fewer entries, the button should not be visible
        # We check the total entry count in the page
        if "0 entries" in response.text or " entries)" in response.text:
            # Extract entry count and verify button visibility

            match: re.Match[str] | None = re.search(r"\((\d+) entries\)", response.text)
            if match:
                entry_count = int(match.group(1))
                if entry_count <= 20:
                    assert "Show more entries" not in response.text, (
                        f"Show more entries button should not be visible when there are {entry_count} entries"
                    )

        # Clean up
        client.post(url="/remove", data={"feed_url": small_feed_url})


def test_show_more_entries_pagination_works() -> None:
    """Test that pagination with starting_after parameter works correctly."""
    # Add the webhook first
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})

    # Add the feed
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get the first page
    response: Response = client.get(url="/feed", params={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to get /feed: {response.text}"

    # Check if pagination is available
    if "Show more entries" in response.text and "starting_after=" in response.text:
        # Extract the starting_after parameter from the button link
        match: re.Match[str] | None = re.search(r'starting_after=([^"&]+)', response.text)
        if match:
            starting_after_id: str = match.group(1)

            # Request the second page
            response: Response = client.get(
                url="/feed",
                params={"feed_url": feed_url, "starting_after": starting_after_id},
            )
            assert response.status_code == 200, f"Failed to get paginated feed: {response.text}"

            # Verify we got a valid response (the page should contain entries)
            assert "entries)" in response.text, "Paginated page should show entry count"


def test_show_more_entries_button_context_variable() -> None:
    """Test that the button visibility variable is correctly passed to the template context."""
    # Add the webhook first
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove the feed if it already exists
    feeds: Response = client.get(url="/")
    if feed_url in feeds.text:
        client.post(url="/remove", data={"feed_url": feed_url})

    # Add the feed
    response: Response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get the feed page
    response: Response = client.get(url="/feed", params={"feed_url": feed_url})
    assert response.status_code == 200, f"Failed to get /feed: {response.text}"

    # Extract the total entries count from the page
    match: re.Match[str] | None = re.search(r"\((\d+) entries\)", response.text)
    if match:
        entry_count = int(match.group(1))

        # If more than 20 entries, button should be visible
        if entry_count > 20:
            assert "Show more entries" in response.text, (
                f"Button should be visible when there are {entry_count} entries (more than 20)"
            )
        # If 20 or fewer entries, button should not be visible
        else:
            assert "Show more entries" not in response.text, (
                f"Button should not be visible when there are {entry_count} entries (20 or fewer)"
            )


def test_create_html_marks_entries_from_another_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Entries from another feed should be marked in /feed html output."""

    @dataclass(slots=True)
    class DummyContent:
        value: str

    @dataclass(slots=True)
    class DummyFeed:
        url: str

    @dataclass(slots=True)
    class DummyEntry:
        feed: DummyFeed
        id: str
        original_feed_url: str | None = None
        link: str = "https://example.com/post"
        title: str = "Example title"
        author: str = "Legacy Author"
        authors_str: str = "Author One, Author Two"
        summary: str = "Summary"
        content: list[DummyContent] = field(default_factory=lambda: [DummyContent("Content")])
        published: None = None

        def __post_init__(self) -> None:
            if self.original_feed_url is None:
                self.original_feed_url = self.feed.url

    selected_feed_url = "https://example.com/feed-a.xml"
    same_feed_entry = DummyEntry(DummyFeed(selected_feed_url), "same")
    # feed.url matches selected feed, but original_feed_url differs; marker should still show.
    other_feed_entry = DummyEntry(
        DummyFeed(selected_feed_url),
        "other",
        original_feed_url="https://example.com/feed-b.xml",
    )

    monkeypatch.setattr(
        "discord_rss_bot.main.replace_tags_in_text_message",
        lambda _entry, **_kwargs: "Rendered content",
    )
    monkeypatch.setattr("discord_rss_bot.main.entry_is_blacklisted", lambda _entry, **_kwargs: False)
    monkeypatch.setattr("discord_rss_bot.main.entry_is_whitelisted", lambda _entry, **_kwargs: False)

    same_feed_entry_typed: Entry = cast("Entry", same_feed_entry)
    other_feed_entry_typed: Entry = cast("Entry", other_feed_entry)

    html: str = create_html_for_feed(
        reader=MagicMock(),
        current_feed_url=selected_feed_url,
        entries=[
            same_feed_entry_typed,
            other_feed_entry_typed,
        ],
    )

    assert "From another feed: https://example.com/feed-b.xml" in html
    assert "From another feed: https://example.com/feed-a.xml" not in html
    assert "By Author One, Author Two @" in html
    assert "By Legacy Author @" not in html


@patch("discord_rss_bot.main.httpx2.get")
def test_get_data_from_hook_url_fetches_metadata_with_httpx2(mock_get: MagicMock) -> None:
    hook_url = "https://discord.com/api/webhooks/123/token"
    response = MagicMock(is_success=True)
    response.text = (
        '{"type": 1, "id": "123", "name": "Discord Hook", "avatar": "avatar", '
        '"channel_id": "456", "guild_id": "789", "token": "token"}'
    )
    mock_get.return_value = response
    main_module.get_data_from_hook_url.cache_clear()

    hook_info = main_module.get_data_from_hook_url("Saved Hook", f" {hook_url} ")

    mock_get.assert_called_once_with(hook_url, timeout=10.0)
    assert hook_info.custom_name == "Saved Hook"
    assert hook_info.name == "Discord Hook"
    assert hook_info.channel_id == "456"
    main_module.get_data_from_hook_url.cache_clear()


@patch("discord_rss_bot.main.httpx2.get")
def test_resolve_final_feed_url_follows_redirects_with_httpx2(mock_get: MagicMock) -> None:
    response = MagicMock(is_success=True)
    response.url = "https://example.com/final.xml"
    mock_get.return_value = response

    resolved_url, error = main_module.resolve_final_feed_url(" https://example.com/original.xml ")

    mock_get.assert_called_once_with("https://example.com/original.xml", follow_redirects=True, timeout=10.0)
    assert resolved_url == "https://example.com/final.xml"
    assert error is None


def test_webhook_entries_webhook_not_found() -> None:
    """Test webhook_entries endpoint returns 404 when webhook doesn't exist."""
    nonexistent_webhook_url = "https://discord.com/api/webhooks/999999/nonexistent"

    response: Response = client.get(
        url="/webhook_entries",
        params={"webhook_url": nonexistent_webhook_url},
    )

    assert response.status_code == 404, f"Expected 404 for non-existent webhook, got: {response.status_code}"
    assert "Webhook not found" in response.text


def test_webhook_entries_no_feeds() -> None:
    """Test webhook_entries endpoint displays message when webhook has no feeds."""
    # Clean up any existing feeds first
    client.post(url="/remove", data={"feed_url": feed_url})

    # Clean up and create a webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Get webhook_entries without adding any feeds
    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
    assert webhook_name in response.text, "Webhook name not found in response"
    assert "No feeds found" in response.text or "Add feeds" in response.text, "Expected message about no feeds"


def test_webhook_entries_no_feeds_still_shows_webhook_settings() -> None:
    """The webhook detail view should show settings/actions even with no attached feeds."""
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
    assert "Settings" in response.text, "Expected settings card on webhook detail view"
    assert "Modify Webhook" in response.text, "Expected modify form on webhook detail view"
    assert "Delete Webhook" in response.text, "Expected delete action on webhook detail view"
    assert "Back to dashboard" in response.text, "Expected dashboard navigation link"
    assert "All webhooks" in response.text, "Expected all webhooks navigation link"
    assert f'name="old_hook" value="{webhook_url}"' in response.text, "Expected old_hook hidden input"
    assert f'value="/webhook_entries?webhook_url={urllib.parse.quote(webhook_url)}"' in response.text, (
        "Expected modify form to redirect back to the current webhook detail view"
    )


def test_webhook_entries_with_feeds_no_entries() -> None:
    """Test webhook_entries endpoint when webhook has feeds but no entries yet."""
    # Clean up and create fresh webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Use a feed URL that exists but has no entries (or clean feed)
    empty_feed_url = "https://lovinator.space/empty_feed.xml"
    client.post(url="/remove", data={"feed_url": empty_feed_url})

    # Add the feed
    response = client.post(
        url="/add",
        data={"feed_url": empty_feed_url, "webhook_dropdown": webhook_name},
    )

    # Get webhook_entries
    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
    assert webhook_name in response.text, "Webhook name not found in response"

    # Clean up
    client.post(url="/remove", data={"feed_url": empty_feed_url})


def test_webhook_entries_with_entries() -> None:
    """Test webhook_entries endpoint displays entries correctly."""
    # Clean up and create webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove and add the feed
    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(
        url="/add",
        data={"feed_url": feed_url, "webhook_dropdown": webhook_name},
    )
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get webhook_entries
    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
    assert webhook_name in response.text, "Webhook name not found in response"
    # Should show entries (the feed has entries)
    assert "total from" in response.text, "Expected to see entry count"
    assert "Modify Webhook" in response.text, "Expected webhook settings to be visible"
    assert "Attached feeds" in response.text, "Expected attached feeds section to be visible"


def test_webhook_entries_shows_attached_feed_link() -> None:
    """The webhook detail view should list attached feeds linking to their feed pages."""
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(
        url="/add",
        data={"feed_url": feed_url, "webhook_dropdown": webhook_name},
    )
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
    assert f"/feed?feed_url={urllib.parse.quote(feed_url)}" in response.text, (
        "Expected attached feed to link to its feed detail page"
    )
    assert "Latest entries" in response.text, "Expected latest entries heading on webhook detail view"

    client.post(url="/remove", data={"feed_url": feed_url})


def test_webhook_entries_multiple_feeds() -> None:
    """Test webhook_entries endpoint shows feed count correctly."""
    # Clean up and create webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove and add feed
    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(
        url="/add",
        data={"feed_url": feed_url, "webhook_dropdown": webhook_name},
    )
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get webhook_entries
    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
    assert webhook_name in response.text, "Webhook name not found in response"
    # Should show entries and feed count
    assert "feed" in response.text.lower(), "Expected to see feed information"

    # Clean up
    client.post(url="/remove", data={"feed_url": feed_url})


def test_webhook_entries_sort_newest_and_non_null_published_first() -> None:
    """Webhook entries should be sorted newest-first with published=None entries placed last."""

    @dataclass(slots=True)
    class DummyFeed:
        url: str
        title: str | None = None
        updates_enabled: bool = True
        last_exception: None = None

    @dataclass(slots=True)
    class DummyEntry:
        id: str
        feed: DummyFeed
        published: datetime | None

    dummy_feed = DummyFeed(url="https://example.com/feed.xml", title="Example Feed")

    # Intentionally unsorted input with two dated entries and two undated entries.
    unsorted_entries: list[Entry] = [
        cast("Entry", DummyEntry(id="old", feed=dummy_feed, published=datetime(2024, 1, 1, tzinfo=UTC))),
        cast("Entry", DummyEntry(id="none-1", feed=dummy_feed, published=None)),
        cast("Entry", DummyEntry(id="new", feed=dummy_feed, published=datetime(2024, 2, 1, tzinfo=UTC))),
        cast("Entry", DummyEntry(id="none-2", feed=dummy_feed, published=None)),
    ]

    class StubReader:
        def get_tag(
            self,
            resource: str | tuple[()] | DummyFeed,
            key: str,
            default: TestTagValue = None,
        ) -> TestTagValue:
            if resource == () and key == "webhooks":
                return [{"name": webhook_name, "url": webhook_url}]
            if key == "webhook" and isinstance(resource, str):
                return webhook_url
            return default

        def get_feeds(self) -> list[DummyFeed]:
            return [dummy_feed]

        def get_entries(self, **_kwargs: TestKwargValue) -> list[Entry]:
            return unsorted_entries

    observed_order: list[str] = []

    def capture_entries(*, reader: Reader, entries: list[Entry], current_feed_url: str = "") -> str:
        del reader, current_feed_url
        observed_order.extend(entry.id for entry in entries)
        return ""

    app.dependency_overrides[get_reader_dependency] = StubReader
    try:
        with (
            patch(
                "discord_rss_bot.main.get_data_from_hook_url",
                return_value=main_module.WebhookInfo(custom_name=webhook_name, url=webhook_url),
            ),
            patch("discord_rss_bot.main.create_html_for_feed", side_effect=capture_entries),
        ):
            response: Response = client.get(
                url="/webhook_entries",
                params={"webhook_url": webhook_url},
            )

        assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"
        assert observed_order == ["new", "old", "none-1", "none-2"], (
            "Expected newest published entries first and published=None entries last"
        )
    finally:
        app.dependency_overrides = {}


def test_webhook_entries_pagination() -> None:
    """Test webhook_entries endpoint pagination functionality."""
    # Clean up and create webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove and add the feed
    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(
        url="/add",
        data={"feed_url": feed_url, "webhook_dropdown": webhook_name},
    )
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get first page of webhook_entries
    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries: {response.text}"

    # Check if pagination button is shown when there are many entries
    # The button should be visible if total_entries > 20 (entries_per_page)
    if "Load More Entries" in response.text:
        # Extract the starting_after parameter from the pagination form
        # This is a simple check that pagination elements exist
        assert 'name="starting_after"' in response.text, "Expected pagination form with starting_after parameter"

    # Clean up
    client.post(url="/remove", data={"feed_url": feed_url})


def test_webhook_entries_url_encoding() -> None:
    """Test webhook_entries endpoint handles URL encoding correctly."""
    # Clean up and create webhook
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    # Remove and add the feed
    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(
        url="/add",
        data={"feed_url": feed_url, "webhook_dropdown": webhook_name},
    )
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    # Get webhook_entries with URL-encoded webhook URL
    encoded_webhook_url = urllib.parse.quote(webhook_url)
    response = client.get(
        url="/webhook_entries",
        params={"webhook_url": encoded_webhook_url},
    )

    assert response.status_code == 200, f"Failed to get /webhook_entries with encoded URL: {response.text}"
    assert webhook_name in response.text, "Webhook name not found in response"

    # Clean up
    client.post(url="/remove", data={"feed_url": feed_url})


def test_dashboard_webhook_name_links_to_webhook_detail() -> None:
    """Webhook names on the dashboard should open the webhook detail view."""
    client.post(url="/delete_webhook", data={"webhook_url": webhook_url})
    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    client.post(url="/remove", data={"feed_url": feed_url})
    response = client.post(url="/add", data={"feed_url": feed_url, "webhook_dropdown": webhook_name})
    assert response.status_code == 200, f"Failed to add feed: {response.text}"

    response = client.get(url="/")
    assert response.status_code == 200, f"Failed to get /: {response.text}"

    expected_link = f"/webhook_entries?webhook_url={urllib.parse.quote(webhook_url)}"
    assert expected_link in response.text, "Expected dashboard webhook link to point to the webhook detail view"

    client.post(url="/remove", data={"feed_url": feed_url})


def test_modify_webhook_redirects_back_to_webhook_detail() -> None:
    """Webhook updates from the detail view should redirect back to that view with the new URL."""
    original_webhook_url = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"
    new_webhook_url = "https://discord.com/api/webhooks/1234567890/updated-token"

    client.post(url="/delete_webhook", data={"webhook_url": original_webhook_url})
    client.post(url="/delete_webhook", data={"webhook_url": new_webhook_url})


def test_modify_webhook_triggers_git_backup_commit() -> None:
    """Modifying a webhook URL should record a state change for git backup."""
    original_webhook_url = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"
    new_webhook_url = "https://discord.com/api/webhooks/1234567890/updated-token"

    client.post(url="/delete_webhook", data={"webhook_url": original_webhook_url})
    client.post(url="/delete_webhook", data={"webhook_url": new_webhook_url})

    response: Response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": original_webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    no_redirect_client = TestClient(app, follow_redirects=False)
    with patch("discord_rss_bot.main.commit_state_change") as mock_commit_state_change:
        response = no_redirect_client.post(
            url="/modify_webhook",
            data={
                "old_hook": original_webhook_url,
                "new_hook": new_webhook_url,
                "redirect_to": f"/webhook_entries?webhook_url={urllib.parse.quote(original_webhook_url)}",
            },
        )

    assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"
    assert mock_commit_state_change.call_count == 1, "Expected webhook modification to trigger git backup commit"

    client.post(url="/delete_webhook", data={"webhook_url": new_webhook_url})

    response = client.post(
        url="/add_webhook",
        data={"webhook_name": webhook_name, "webhook_url": original_webhook_url},
    )
    assert response.status_code == 200, f"Failed to add webhook: {response.text}"

    no_redirect_client = TestClient(app, follow_redirects=False)
    response = no_redirect_client.post(
        url="/modify_webhook",
        data={
            "old_hook": original_webhook_url,
            "new_hook": new_webhook_url,
            "redirect_to": f"/webhook_entries?webhook_url={urllib.parse.quote(original_webhook_url)}",
        },
    )

    assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"
    assert response.headers["location"] == (f"/webhook_entries?webhook_url={urllib.parse.quote(new_webhook_url)}"), (
        f"Unexpected redirect location: {response.headers['location']}"
    )

    client.post(url="/delete_webhook", data={"webhook_url": new_webhook_url})


def test_webhook_entries_mass_update_preview_shows_old_and_new_urls() -> None:
    """Preview should list old->new feed URLs for webhook bulk replacement."""

    @dataclass(slots=True)
    class DummyFeed:
        url: str
        title: str | None = None
        updates_enabled: bool = True
        last_exception: None = None

    class StubReader:
        def __init__(self) -> None:
            self._feeds: list[DummyFeed] = [
                DummyFeed(url="https://old.example.com/rss/a.xml", title="A"),
                DummyFeed(url="https://old.example.com/rss/b.xml", title="B"),
                DummyFeed(url="https://unchanged.example.com/rss/c.xml", title="C"),
            ]

        def get_tag(
            self,
            resource: str | tuple[()] | DummyFeed,
            key: str,
            default: TestTagValue = None,
        ) -> TestTagValue:
            if resource == () and key == "webhooks":
                return [{"name": webhook_name, "url": webhook_url}]
            if key == "webhook" and isinstance(resource, str):
                if resource.startswith("https://old.example.com"):
                    return webhook_url
                if resource.startswith("https://unchanged.example.com"):
                    return webhook_url
            return default

        def get_feeds(self) -> list[DummyFeed]:
            return self._feeds

        def get_entries(self, **_kwargs: TestKwargValue) -> list[Entry]:
            return []

    app.dependency_overrides[get_reader_dependency] = StubReader
    try:
        with (
            patch(
                "discord_rss_bot.main.get_data_from_hook_url",
                return_value=main_module.WebhookInfo(custom_name=webhook_name, url=webhook_url),
            ),
            patch(
                "discord_rss_bot.main.resolve_final_feed_url",
                side_effect=lambda url: (url.replace("old.example.com", "new.example.com"), None),
            ),
        ):
            response: Response = client.get(
                url="/webhook_entries",
                params={
                    "webhook_url": webhook_url,
                    "replace_from": "old.example.com",
                    "replace_to": "new.example.com",
                    "resolve_urls": "true",
                },
            )

        assert response.status_code == 200, f"Failed to get preview: {response.text}"
        assert "Mass update feed URLs" in response.text
        assert "old.example.com/rss/a.xml" in response.text
        assert "new.example.com/rss/a.xml" in response.text
        assert "Will update" in response.text
        assert "Matched: 2" in response.text
        assert "Will update: 2" in response.text
    finally:
        app.dependency_overrides = {}


def test_bulk_change_feed_urls_updates_matching_feeds() -> None:
    """Mass updater should change all matching feed URLs for a webhook."""

    @dataclass(slots=True)
    class DummyFeed:
        url: str

    class StubReader:
        def __init__(self) -> None:
            self._feeds = [
                DummyFeed(url="https://old.example.com/rss/a.xml"),
                DummyFeed(url="https://old.example.com/rss/b.xml"),
                DummyFeed(url="https://unchanged.example.com/rss/c.xml"),
            ]
            self.change_calls: list[tuple[str, str]] = []
            self.updated_feeds: list[str] = []

        def get_tag(
            self,
            resource: str | tuple[()] | DummyFeed,
            key: str,
            default: TestTagValue = None,
        ) -> TestTagValue:
            if resource == () and key == "webhooks":
                return [{"name": webhook_name, "url": webhook_url}]
            if key == "webhook" and isinstance(resource, str):
                return webhook_url
            return default

        def get_feeds(self) -> list[DummyFeed]:
            return self._feeds

        def change_feed_url(self, old_url: str, new_url: str) -> None:
            self.change_calls.append((old_url, new_url))

        def update_feed(self, feed_url: str) -> None:
            self.updated_feeds.append(feed_url)

        def get_entries(self, **_kwargs: TestKwargValue) -> list[Entry]:
            return []

        def set_entry_read(self, _entry: Entry, _value: bool) -> None:  # noqa: FBT001
            return

    stub_reader = StubReader()
    app.dependency_overrides[get_reader_dependency] = lambda: stub_reader
    no_redirect_client = TestClient(app, follow_redirects=False)

    try:
        with patch(
            "discord_rss_bot.main.resolve_final_feed_url",
            side_effect=lambda url: (url.replace("old.example.com", "new.example.com"), None),
        ):
            response: Response = no_redirect_client.post(
                url="/bulk_change_feed_urls",
                data={
                    "webhook_url": webhook_url,
                    "replace_from": "old.example.com",
                    "replace_to": "new.example.com",
                    "resolve_urls": "true",
                },
            )

        assert response.status_code == 303, f"Expected redirect, got {response.status_code}: {response.text}"
        assert "Updated%202%20feed%20URL%28s%29" in response.headers.get("location", "")
        assert sorted(stub_reader.change_calls) == sorted([
            ("https://old.example.com/rss/a.xml", "https://new.example.com/rss/a.xml"),
            ("https://old.example.com/rss/b.xml", "https://new.example.com/rss/b.xml"),
        ])
        assert sorted(stub_reader.updated_feeds) == sorted([
            "https://new.example.com/rss/a.xml",
            "https://new.example.com/rss/b.xml",
        ])
    finally:
        app.dependency_overrides = {}


def test_webhook_entries_mass_update_preview_fragment_endpoint() -> None:
    """HTMX preview endpoint should render only the mass-update preview fragment."""

    @dataclass(slots=True)
    class DummyFeed:
        url: str
        title: str | None = None
        updates_enabled: bool = True
        last_exception: None = None

    class StubReader:
        def __init__(self) -> None:
            self._feeds: list[DummyFeed] = [
                DummyFeed(url="https://old.example.com/rss/a.xml", title="A"),
                DummyFeed(url="https://old.example.com/rss/b.xml", title="B"),
            ]

        def get_tag(self, resource: str | DummyFeed, key: str, default: TestTagValue = None) -> TestTagValue:
            if key == "webhook" and isinstance(resource, str):
                return webhook_url
            return default

        def get_feeds(self) -> list[DummyFeed]:
            return self._feeds

    app.dependency_overrides[get_reader_dependency] = StubReader
    try:
        with patch(
            "discord_rss_bot.main.resolve_final_feed_url",
            side_effect=lambda url: (url.replace("old.example.com", "new.example.com"), None),
        ):
            response: Response = client.get(
                url="/webhook_entries_mass_update_preview",
                params={
                    "webhook_url": webhook_url,
                    "replace_from": "old.example.com",
                    "replace_to": "new.example.com",
                    "resolve_urls": "true",
                },
            )

        assert response.status_code == 200, f"Failed to get HTMX preview fragment: {response.text}"
        assert "Will update: 2" in response.text
        assert "<table" in response.text
        assert "Mass update feed URLs" not in response.text, "Fragment should not include full page wrapper text"
    finally:
        app.dependency_overrides = {}


def test_bulk_change_feed_urls_force_update_overwrites_conflict() -> None:  # noqa: C901
    """Force update should overwrite conflicting target URLs instead of skipping them."""

    @dataclass(slots=True)
    class DummyFeed:
        url: str

    class StubReader:
        def __init__(self) -> None:
            self._feeds = [
                DummyFeed(url="https://old.example.com/rss/a.xml"),
                DummyFeed(url="https://new.example.com/rss/a.xml"),
            ]
            self.delete_calls: list[str] = []
            self.change_calls: list[tuple[str, str]] = []

        def get_tag(
            self,
            resource: str | tuple[()] | DummyFeed,
            key: str,
            default: TestTagValue = None,
        ) -> TestTagValue:
            if resource == () and key == "webhooks":
                return [{"name": webhook_name, "url": webhook_url}]
            if key == "webhook" and isinstance(resource, str):
                return webhook_url
            return default

        def get_feeds(self) -> list[DummyFeed]:
            return self._feeds

        def delete_feed(self, feed_url: str) -> None:
            self.delete_calls.append(feed_url)

        def change_feed_url(self, old_url: str, new_url: str) -> None:
            self.change_calls.append((old_url, new_url))

        def update_feed(self, _feed_url: str) -> None:
            return

        def get_entries(self, **_kwargs: TestKwargValue) -> list[Entry]:
            return []

        def set_entry_read(self, _entry: Entry, _value: bool) -> None:  # noqa: FBT001
            return

    stub_reader = StubReader()
    app.dependency_overrides[get_reader_dependency] = lambda: stub_reader
    no_redirect_client = TestClient(app, follow_redirects=False)

    try:
        with patch(
            "discord_rss_bot.main.resolve_final_feed_url",
            side_effect=lambda url: (url.replace("old.example.com", "new.example.com"), None),
        ):
            response: Response = no_redirect_client.post(
                url="/bulk_change_feed_urls",
                data={
                    "webhook_url": webhook_url,
                    "replace_from": "old.example.com",
                    "replace_to": "new.example.com",
                    "resolve_urls": "true",
                    "force_update": "true",
                },
            )

        assert response.status_code == 303, f"Expected redirect, got {response.status_code}: {response.text}"
        assert stub_reader.delete_calls == ["https://new.example.com/rss/a.xml"]
        assert stub_reader.change_calls == [
            (
                "https://old.example.com/rss/a.xml",
                "https://new.example.com/rss/a.xml",
            ),
        ]
        assert "Force%20overwrote%201" in response.headers.get("location", "")
    finally:
        app.dependency_overrides = {}


def test_bulk_change_feed_urls_force_update_ignores_resolution_error() -> None:
    """Force update should proceed even when URL resolution returns an error (e.g. HTTP 404)."""

    @dataclass(slots=True)
    class DummyFeed:
        url: str

    class StubReader:
        def __init__(self) -> None:
            self._feeds = [
                DummyFeed(url="https://old.example.com/rss/a.xml"),
            ]
            self.change_calls: list[tuple[str, str]] = []

        def get_tag(
            self,
            resource: str | tuple[()] | DummyFeed,
            key: str,
            default: TestTagValue = None,
        ) -> TestTagValue:
            if resource == () and key == "webhooks":
                return [{"name": webhook_name, "url": webhook_url}]
            if key == "webhook" and isinstance(resource, str):
                return webhook_url
            return default

        def get_feeds(self) -> list[DummyFeed]:
            return self._feeds

        def change_feed_url(self, old_url: str, new_url: str) -> None:
            self.change_calls.append((old_url, new_url))

        def update_feed(self, _feed_url: str) -> None:
            return

        def get_entries(self, **_kwargs: TestKwargValue) -> list[Entry]:
            return []

        def set_entry_read(self, _entry: Entry, _value: bool) -> None:  # noqa: FBT001
            return

    stub_reader = StubReader()
    app.dependency_overrides[get_reader_dependency] = lambda: stub_reader
    no_redirect_client = TestClient(app, follow_redirects=False)

    try:
        with patch(
            "discord_rss_bot.main.resolve_final_feed_url",
            return_value=("https://new.example.com/rss/a.xml", "HTTP 404"),
        ):
            response: Response = no_redirect_client.post(
                url="/bulk_change_feed_urls",
                data={
                    "webhook_url": webhook_url,
                    "replace_from": "old.example.com",
                    "replace_to": "new.example.com",
                    "resolve_urls": "true",
                    "force_update": "true",
                },
            )

        assert response.status_code == 303, f"Expected redirect, got {response.status_code}: {response.text}"
        assert stub_reader.change_calls == [
            (
                "https://old.example.com/rss/a.xml",
                "https://new.example.com/rss/a.xml",
            ),
        ]
        location = response.headers.get("location", "")
        assert "Updated%201%20feed%20URL%28s%29" in location
        assert "Failed%200" in location
    finally:
        app.dependency_overrides = {}


def test_reader_dependency_override_is_used() -> None:
    """Reader should be injectable and overridable via FastAPI dependency overrides."""

    class StubReader:
        def get_tag(self, _resource: str, _key: str, default: str | None = None) -> str | None:
            """Stub get_tag that always returns the default value.

            Args:
                _resource: Ignored.
                _key: Ignored.
                default: The value to return.

            Returns:
                The default value, simulating a missing tag.
            """
            return default

    app.dependency_overrides[get_reader_dependency] = StubReader
    try:
        response: Response = client.get(url="/add")
        assert response.status_code == 200, f"Expected /add to render with overridden reader: {response.text}"
    finally:
        app.dependency_overrides = {}


# ---------------------------------------------------------------------------
# Tests for post_embed — saving embed fields (including clearing to "")
# ---------------------------------------------------------------------------


def _make_stub_reader_for_embed(
    *,
    stored_embed: str | None = None,
) -> MagicMock:
    """Create a stub reader that tracks embed tag writes.

    Args:
        stored_embed: JSON string to return from get_tag for the "embed" key,
            or None to return an empty string (simulating no saved embed).

    Returns:
        A MagicMock stub reader.
    """
    stub = MagicMock()
    # Simulate get_feed returning a feed-like object.
    stub.get_feed.return_value = SimpleNamespace(
        url=feed_url,
        title="Example Feed",
    )
    # Simulate get_tag for the "embed" key.
    embed_value: str = stored_embed if stored_embed is not None else ""
    stub.get_tag.return_value = embed_value
    return stub


def test_post_embed_saves_all_fields() -> None:
    """Saving a fully populated embed should persist every field."""
    stub = _make_stub_reader_for_embed()
    app.dependency_overrides[get_reader_dependency] = lambda: stub

    try:
        with patch("discord_rss_bot.main.commit_state_change"):
            response: Response = client.post(
                url="/embed",
                data={
                    "feed_url": feed_url,
                    "title": "Custom Title",
                    "description": "Custom Description",
                    "color": "#ff0000",
                    "author_name": "Author Name",
                    "author_url": "https://example.com/author",
                    "author_icon_url": "https://example.com/author.png",
                    "image_url": "https://example.com/image.png",
                    "thumbnail_url": "https://example.com/thumb.png",
                    "footer_text": "Footer Text",
                    "footer_icon_url": "https://example.com/footer.png",
                },
                follow_redirects=False,
            )

        assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"

        # Verify set_tag was called with the correct serialized embed.
        stub.set_tag.assert_called_once()
        _feed_arg, key_arg, json_arg = stub.set_tag.call_args.args
        assert key_arg == "embed"

        saved: dict[str, str] = json.loads(json_arg)
        assert saved["title"] == "Custom Title"
        assert saved["description"] == "Custom Description"
        assert saved["color"] == "#ff0000"
        assert saved["author_name"] == "Author Name"
        assert saved["author_url"] == "https://example.com/author"
        assert saved["author_icon_url"] == "https://example.com/author.png"
        assert saved["image_url"] == "https://example.com/image.png"
        assert saved["thumbnail_url"] == "https://example.com/thumb.png"
        assert saved["footer_text"] == "Footer Text"
        assert saved["footer_icon_url"] == "https://example.com/footer.png"
    finally:
        app.dependency_overrides = {}


def test_post_embed_allows_clearing_description() -> None:
    """Clearing the description field (submitting "") should persist the empty string."""
    # Simulate an existing embed with a non-empty description.

    existing = json.dumps({
        "title": "",
        "description": "{{entry_text}}",
        "color": "#469ad9",
        "author_name": "{{entry_title}}",
        "author_url": "{{entry_link}}",
        "author_icon_url": "",
        "image_url": "{{image_1}}",
        "thumbnail_url": "",
        "footer_text": "",
        "footer_icon_url": "",
    })
    stub = _make_stub_reader_for_embed(stored_embed=existing)
    app.dependency_overrides[get_reader_dependency] = lambda: stub

    try:
        with patch("discord_rss_bot.main.commit_state_change"):
            response: Response = client.post(
                url="/embed",
                data={
                    "feed_url": feed_url,
                    # User clears the description — submits empty string.
                    "description": "",
                    # All other fields re-submit their stored values
                    # (as the form template would pre-fill them).
                    "title": "",
                    "color": "#469ad9",
                    "author_name": "{{entry_title}}",
                    "author_url": "{{entry_link}}",
                    "author_icon_url": "",
                    "image_url": "{{image_1}}",
                    "thumbnail_url": "",
                    "footer_text": "",
                    "footer_icon_url": "",
                },
                follow_redirects=False,
            )

        assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"
        stub.set_tag.assert_called_once()
        _feed_arg, key_arg, json_arg = stub.set_tag.call_args.args
        assert key_arg == "embed"

        saved: dict[str, str] = json.loads(json_arg)
        # The description should be cleared to "".
        assert not saved["description"], f"Expected empty description, got {saved['description']!r}"
        # Other fields should retain their values.
        assert saved["author_name"] == "{{entry_title}}"
        assert saved["author_url"] == "{{entry_link}}"
        assert saved["image_url"] == "{{image_1}}"
        assert saved["color"] == "#469ad9"
    finally:
        app.dependency_overrides = {}


def test_post_embed_allows_clearing_all_fields() -> None:
    """Submitting all fields as empty strings should persist them all as empty."""
    existing = json.dumps({
        "title": "Old Title",
        "description": "Old Description",
        "color": "#469ad9",
        "author_name": "Old Author",
        "author_url": "https://old.example.com",
        "author_icon_url": "https://old.example.com/icon.png",
        "image_url": "https://old.example.com/img.png",
        "thumbnail_url": "https://old.example.com/thumb.png",
        "footer_text": "Old Footer",
        "footer_icon_url": "https://old.example.com/footer.png",
    })
    stub = _make_stub_reader_for_embed(stored_embed=existing)
    app.dependency_overrides[get_reader_dependency] = lambda: stub

    try:
        with patch("discord_rss_bot.main.commit_state_change"):
            response: Response = client.post(
                url="/embed",
                data={
                    "feed_url": feed_url,
                    "title": "",
                    "description": "",
                    "color": "",
                    "author_name": "",
                    "author_url": "",
                    "author_icon_url": "",
                    "image_url": "",
                    "thumbnail_url": "",
                    "footer_text": "",
                    "footer_icon_url": "",
                },
                follow_redirects=False,
            )

        assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"
        stub.set_tag.assert_called_once()
        _feed_arg, _key_arg, json_arg = stub.set_tag.call_args.args
        saved: dict[str, str] = json.loads(json_arg)

        assert not saved["title"]
        assert not saved["description"]
        assert not saved["color"]
        assert not saved["author_name"]
        assert not saved["author_url"]
        assert not saved["author_icon_url"]
        assert not saved["image_url"]
        assert not saved["thumbnail_url"]
        assert not saved["footer_text"]
        assert not saved["footer_icon_url"]
    finally:
        app.dependency_overrides = {}


def test_post_embed_untouched_fields_retain_values() -> None:
    """Changing only one field should leave all other fields unchanged."""
    existing = json.dumps({
        "title": "Keep Me",
        "description": "{{entry_text}}",
        "color": "#00ff00",
        "author_name": "Author",
        "author_url": "https://a.example.com",
        "author_icon_url": "",
        "image_url": "",
        "thumbnail_url": "",
        "footer_text": "Old Footer",
        "footer_icon_url": "",
    })
    stub = _make_stub_reader_for_embed(stored_embed=existing)
    app.dependency_overrides[get_reader_dependency] = lambda: stub

    try:
        with patch("discord_rss_bot.main.commit_state_change"):
            response: Response = client.post(
                url="/embed",
                data={
                    "feed_url": feed_url,
                    # Only change the title; all other fields re-submit
                    # their stored values (as the form pre-fills them).
                    "title": "New Title",
                    "description": "{{entry_text}}",
                    "color": "#00ff00",
                    "author_name": "Author",
                    "author_url": "https://a.example.com",
                    "author_icon_url": "",
                    "image_url": "",
                    "thumbnail_url": "",
                    "footer_text": "Old Footer",
                    "footer_icon_url": "",
                },
                follow_redirects=False,
            )

        assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"
        stub.set_tag.assert_called_once()
        _feed_arg, _key_arg, json_arg = stub.set_tag.call_args.args
        saved: dict[str, str] = json.loads(json_arg)

        # The title should be changed.
        assert saved["title"] == "New Title"
        # All other fields should remain unchanged.
        assert saved["description"] == "{{entry_text}}"
        assert saved["color"] == "#00ff00"
        assert saved["author_name"] == "Author"
        assert saved["author_url"] == "https://a.example.com"
        assert saved["footer_text"] == "Old Footer"
    finally:
        app.dependency_overrides = {}


def test_post_embed_saves_empty_description_when_no_prior_embed_exists() -> None:
    """Clearing description should work even when no embed was previously saved."""
    stub = _make_stub_reader_for_embed(stored_embed=None)
    app.dependency_overrides[get_reader_dependency] = lambda: stub

    try:
        with patch("discord_rss_bot.main.commit_state_change"):
            response: Response = client.post(
                url="/embed",
                data={
                    "feed_url": feed_url,
                    # User only fills in a title, leaves description empty.
                    "title": "Just a Title",
                    "description": "",
                    "color": "#469ad9",
                    "author_name": "",
                    "author_url": "",
                    "author_icon_url": "",
                    "image_url": "",
                    "thumbnail_url": "",
                    "footer_text": "",
                    "footer_icon_url": "",
                },
                follow_redirects=False,
            )

        assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"
        stub.set_tag.assert_called_once()
        _feed_arg, _key_arg, json_arg = stub.set_tag.call_args.args

        saved: dict[str, str] = json.loads(json_arg)
        assert saved["title"] == "Just a Title"
        assert not saved["description"], f"Expected empty description, got {saved['description']!r}"
    finally:
        app.dependency_overrides = {}


def _make_stub_reader_for_custom(
    *,
    stored_custom_message: str = "",
) -> MagicMock:
    """Create a stub reader that tracks custom_message tag writes.

    Args:
        stored_custom_message: Value to return from get_tag for the
            "custom_message" key.

    Returns:
        A MagicMock stub reader.
    """
    stub = MagicMock()
    stub.get_feed.return_value = SimpleNamespace(
        url=feed_url,
        title="Example Feed",
    )

    def get_tag(resource: str | object, key: str, default: str = "") -> str:
        if key == "custom_message":
            return stored_custom_message
        return default

    stub.get_tag.side_effect = get_tag
    return stub


def test_post_set_custom_saves_message() -> None:
    """Saving a custom message should persist it."""
    stub = _make_stub_reader_for_custom()
    app.dependency_overrides[get_reader_dependency] = lambda: stub

    try:
        with patch("discord_rss_bot.main.commit_state_change"):
            response: Response = client.post(
                url="/custom",
                data={
                    "feed_url": feed_url,
                    "custom_message": "Hello {{entry_title}}!",
                },
                follow_redirects=False,
            )

        assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"
        stub.set_tag.assert_called_once()
        _feed_arg, key_arg, value_arg = stub.set_tag.call_args.args
        assert key_arg == "custom_message"
        assert value_arg == "Hello {{entry_title}}!"
    finally:
        app.dependency_overrides = {}


def test_post_set_custom_allows_clearing_message() -> None:
    """Clearing the custom message (submitting "") should persist the empty string."""
    stub = _make_stub_reader_for_custom(
        stored_custom_message="{{entry_title}}\n{{entry_link}}",
    )
    app.dependency_overrides[get_reader_dependency] = lambda: stub

    try:
        with patch("discord_rss_bot.main.commit_state_change"):
            response: Response = client.post(
                url="/custom",
                data={
                    "feed_url": feed_url,
                    # User clears the custom message.
                    "custom_message": "",
                },
                follow_redirects=False,
            )

        assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"
        stub.set_tag.assert_called_once()
        _feed_arg, key_arg, value_arg = stub.set_tag.call_args.args
        assert key_arg == "custom_message"
        assert not value_arg, f"Expected empty custom_message to be saved, got {value_arg!r}"
    finally:
        app.dependency_overrides = {}


def test_post_set_custom_unchanged_message_does_not_write() -> None:
    """Submitting the same value should not trigger a set_tag call."""
    existing = "{{entry_title}}\n{{entry_link}}"
    stub = _make_stub_reader_for_custom(stored_custom_message=existing)
    app.dependency_overrides[get_reader_dependency] = lambda: stub

    try:
        with patch("discord_rss_bot.main.commit_state_change"):
            response: Response = client.post(
                url="/custom",
                data={
                    "feed_url": feed_url,
                    "custom_message": existing,
                },
                follow_redirects=False,
            )

        assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"
        stub.set_tag.assert_not_called()
    finally:
        app.dependency_overrides = {}


def test_post_set_custom_clearing_from_default_message() -> None:
    """Clearing a message that matches the default should save "" not re-apply the default."""
    stub = _make_stub_reader_for_custom(
        stored_custom_message="{{entry_title}}\n{{entry_link}}",
    )
    app.dependency_overrides[get_reader_dependency] = lambda: stub

    try:
        with patch("discord_rss_bot.main.commit_state_change"):
            response: Response = client.post(
                url="/custom",
                data={
                    "feed_url": feed_url,
                    "custom_message": "",
                },
                follow_redirects=False,
            )

        assert response.status_code == 303, f"Expected 303 redirect, got {response.status_code}: {response.text}"
        stub.set_tag.assert_called_once()
        _feed_arg, _key_arg, value_arg = stub.set_tag.call_args.args
        # Must be "" not the default.
        assert not value_arg, f"Expected empty string to be saved, got {value_arg!r}"
    finally:
        app.dependency_overrides = {}
