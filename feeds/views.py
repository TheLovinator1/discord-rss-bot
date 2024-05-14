from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote

from django.contrib import messages
from django.core.paginator import Page, Paginator
from django.db.models.manager import BaseManager
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.views.generic.base import View
from reader.core import Reader
from reader.types import Entry

from discord_rss_bot.reader import get_reader
from feeds.forms import WebhookForm
from feeds.models import Webhook
from feeds.models.blacklist import Blacklist
from feeds.models.message import MessageCustomization
from feeds.models.whitelist import Whitelist
from feeds.webhooks import send_entry_to_webhook

if TYPE_CHECKING:
    from django.db.models.manager import BaseManager
    from django.http import HttpRequest
    from reader import Entry, EntrySearchCounts, Feed, Reader

logger: logging.Logger = logging.getLogger(__name__)


def list_feeds(request: HttpRequest) -> HttpResponse:
    """List all feeds."""
    feed_url: str = request.GET.get("feed_url", "")
    page_number: int = int(request.GET.get("page", 1))
    if feed_url:
        feed_url = unquote(feed_url).strip()
        if not feed_url:
            return redirect("/feeds/")

        reader: Reader = get_reader()
        feed: Feed = reader.get_feed(feed_url)
        if not feed:
            return redirect("/feeds/")

        entries = list(reader.get_entries(feed=feed))

        current_url: str = f"/feed/?feed_url={quote(feed.url)}"

        paginator = Paginator(entries, 100)
        page_entries: Page = paginator.get_page(page_number)

        return render(
            request=request,
            template_name="feed.html",
            context={"feed": feed, "entries": page_entries, "total_amount": len(entries), "current_url": current_url},
        )

    feeds = list(get_reader().get_feeds())
    return render(request=request, template_name="feeds.html", context={"feeds": feeds})


@require_POST
def delete_feed(request: HttpRequest) -> HttpResponse:
    """Delete a feed."""
    feed_url: str = request.POST.get("feed_url", "")
    if not feed_url:
        return redirect("/feeds/")

    feed_url = unquote(feed_url).strip()

    reader: Reader = get_reader()
    reader.delete_feed(feed_url)
    messages.success(request, "Feed deleted successfully.")
    return redirect("/feeds/")


def webhooks_view(request: HttpRequest) -> HttpResponse:
    """This is the view for the webhooks page."""
    if request.method == "POST":
        form = WebhookForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("/webhooks/")
    else:
        form = WebhookForm()

    context: dict[str, WebhookForm | BaseManager[Webhook]] = {
        "form": form,
        "webhooks": Webhook.objects.all().filter(is_deleted=False),
        "deleted_webhooks": Webhook.objects.all().filter(is_deleted=True),
    }
    return render(request, "webhooks.html", context)


def delete_webhook(request: HttpRequest, webhook_id: str) -> HttpResponse:
    """This is the view for deleting a webhook."""
    Webhook.objects.get(pk=webhook_id).delete()
    messages.success(request, "Webhook deleted successfully.")
    return redirect("/webhooks/")


def undelete_webhook(request: HttpRequest, webhook_id: str) -> HttpResponse:
    """This is the view for undeleting a webhook."""
    Webhook.objects.get(pk=webhook_id).undelete()
    messages.success(request, "Webhook undeleted successfully.")
    return redirect("/webhooks/")


class PauseView(View):
    def post(self: PauseView, request: HttpRequest, feed_url: str) -> HttpResponse:  # noqa: ARG002
        feed_url = unquote(feed_url)

        reader = get_reader()
        feed = reader.get_feed(feed_url)

        reader: Reader = get_reader()
        if feed.updates_enabled:
            reader.disable_feed_updates(feed.url)
            logger.info("Paused feed %s", feed.url)
        else:
            reader.enable_feed_updates(feed.url)
            logger.info("Resumed feed %s", feed.url)
        return HttpResponse(status=204)


class WhitelistView(View):
    def post(self, request: HttpRequest) -> HttpResponseRedirect:
        whitelist_title: str | None = request.POST.get("whitelist_title")
        whitelist_summary: str | None = request.POST.get("whitelist_summary")
        whitelist_content: str | None = request.POST.get("whitelist_content")
        whitelist_author: str | None = request.POST.get("whitelist_author")
        feed_url: str | None = request.POST.get("feed_url")
        if not feed_url:
            return HttpResponseRedirect("/")

        feed_url = feed_url.strip()

        whitelist, _created = Whitelist.objects.update_or_create(
            title=whitelist_title.strip() if whitelist_title else None,
            summary=whitelist_summary.strip() if whitelist_summary else None,
            content=whitelist_content.strip() if whitelist_content else None,
            author=whitelist_author.strip() if whitelist_author else None,
        )

        logger.info("Whitelisted %s", whitelist)

        return HttpResponseRedirect(f"/feed/?feed_url={quote(feed_url)}")


class BlacklistView(View):
    def post(self: BlacklistView, request: HttpRequest) -> HttpResponseRedirect:
        blacklist_title: str | None = request.POST.get("blacklist_title")
        blacklist_summary: str | None = request.POST.get("blacklist_summary")
        blacklist_content: str | None = request.POST.get("blacklist_content")
        feed_url: str | None = request.POST.get("feed_url")

        if not feed_url:
            return HttpResponseRedirect("/")

        clean_feed_url: str = feed_url.strip()

        blacklist, _created = Blacklist.objects.update_or_create(
            title=blacklist_title,
            summary=blacklist_summary,
            content=blacklist_content,
        )

        logger.info("Blacklisted %s", blacklist)

        return HttpResponseRedirect(f"/feed/?feed_url={quote(clean_feed_url)}")


class CustomMessageView(View):
    def post(self: CustomMessageView, request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
        feed_url: str | None = request.POST.get("feed_url")
        if not feed_url:
            return HttpResponse(status=404, content="Feed URL not provided")

        custom: MessageCustomization | None = MessageCustomization.objects.get(feed_url=feed_url)
        if custom is None:
            return HttpResponse(status=404, content=f"No custom message found for {feed_url}")

        custom.custom_message = str(request.POST.get("custom_message"))
        custom.should_be_embed = request.POST.get("should_be_embed") == "true"
        custom.custom_embed_title = str(request.POST.get("custom_embed_title"))
        custom.custom_embed_description = str(request.POST.get("custom_embed_description"))
        custom.custom_embed_color = str(request.POST.get("custom_embed_color"))
        custom.custom_embed_author_name = str(request.POST.get("custom_embed_author_name"))
        custom.custom_embed_author_url = str(request.POST.get("custom_embed_author_url"))
        custom.custom_embed_author_icon_url = str(request.POST.get("custom_embed_author_icon_url"))
        custom.custom_embed_image_url = str(request.POST.get("custom_embed_image_url"))
        custom.custom_embed_thumbnail_url = str(request.POST.get("custom_embed_thumbnail_url"))
        custom.custom_embed_footer_text = str(request.POST.get("custom_embed_footer_text"))
        custom.custom_embed_footer_icon_url = str(request.POST.get("custom_embed_footer_icon_url"))
        custom.save()

        return HttpResponseRedirect(f"/feed/?feed_url={quote(feed_url)}")


class SearchView(View):
    def get(self: SearchView, request: HttpRequest) -> HttpResponse:
        return render(request=request, template_name="search.html")

    def post(self: SearchView, request: HttpRequest) -> HttpResponse:
        reader: Reader = get_reader()
        reader.update_search()

        search_query: str = request.POST.get("search_query", "")
        if not search_query:
            # TODO(TheLovinator): Show all feeds  # noqa: TD003
            return render(request=request, template_name="search.html")

        search_amount: EntrySearchCounts = reader.search_entry_counts(search_query)
        if search_amount == 0:
            return render(request=request, template_name="search.html", context={"no_results": True})

        feeds = list(reader.search_entries(search_query))
        return render(request=request, template_name="search.html", context={"feeds": feeds})


class SendPostToDiscordView(View):
    def post(self: SendPostToDiscordView, request: HttpRequest) -> HttpResponse:
        entry_id: str | None = request.POST.get("entry_id")
        entry_id = entry_id.strip() if entry_id else None
        if not entry_id:
            return HttpResponse(status=404, content="Entry ID not provided")

        webhook_name: str | None = request.POST.get("webhook_name")
        webhook_name = webhook_name.strip() if webhook_name else None
        if not webhook_name:
            return HttpResponse(status=404, content="Webhook name not provided")

        # Get the webhook URL from the webhook name
        webhook_url: str | None = Webhook.objects.get(name=webhook_name).url

        reader: Reader = get_reader()
        entry: Entry | None = next((entry for entry in reader.get_entries() if entry.id == entry_id), None)
        if entry is None:
            return HttpResponse(status=404, content=f"Entry {entry_id} not found")

        response: str = send_entry_to_webhook(entry=entry, webhook_url=webhook_url)
        return HttpResponse(content=response)


def get_index_view(request: HttpRequest) -> HttpResponse:
    """Get home page."""
    return render(request=request, template_name="index.html")


def get_add_view(request: HttpRequest) -> HttpResponse:
    """Add a feed."""
    return render(request=request, template_name="add.html")
