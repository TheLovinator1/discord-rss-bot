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
from reader import SearchError
from reader.core import Reader
from reader.types import Feed

from discord_rss_bot.reader import get_reader
from feeds.forms import WebhookForm
from feeds.models import Webhook
from feeds.models.blacklist import Blacklist
from feeds.models.message import MessageCustomization
from feeds.models.whitelist import Whitelist

if TYPE_CHECKING:
    from django.db.models.manager import BaseManager
    from django.http import HttpRequest
    from reader import Feed, Reader

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


class WebhookView(View):
    def post(self: WebhookView, request: HttpRequest) -> HttpResponse:
        form = WebhookForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("/webhooks/")
        return HttpResponse(status=400)

    def get(self: WebhookView, request: HttpRequest) -> HttpResponse:
        form = WebhookForm()
        context: dict[str, WebhookForm | BaseManager[Webhook]] = {
            "form": form,
            "webhooks": Webhook.objects.all().filter(is_deleted=False),
            "deleted_webhooks": Webhook.objects.all().filter(is_deleted=True),
        }
        return render(request, "webhooks.html", context)


class ToggleWebhookView(View):
    def get(self: ToggleWebhookView, request: HttpRequest) -> HttpResponse:
        webhook_id: str | None = request.GET.get("webhook_id")
        if not webhook_id:
            return HttpResponse(status=400)

        is_deleted: bool = Webhook.objects.get(pk=webhook_id).is_deleted
        if is_deleted:
            Webhook.objects.get(pk=webhook_id).undelete()
        else:
            Webhook.objects.get(pk=webhook_id).delete()

        return redirect("/webhooks/")


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

        search_query: str = request.POST.get("search_query", default="")
        if not search_query:
            # TODO(TheLovinator): Show all feeds  # noqa: TD003
            return render(request=request, template_name="search.html")

        # Enable search if it is not already enabled.
        # Update the search index.
        reader.enable_search()
        reader.update_search()

        # Search for entries.
        try:
            feeds = list(reader.search_entries(search_query))
        except SearchError as e:
            return HttpResponse(status=500, content=str(e))

        return render(request=request, template_name="search.html", context={"feeds": feeds})


class IndexView(View):
    def get(self: IndexView, request: HttpRequest) -> HttpResponse:
        return render(request=request, template_name="index.html")


class AddFeedView(View):
    def post(self: AddFeedView, request: HttpRequest) -> HttpResponse:
        feed_url: str | None = request.POST.get("feed_url")
        if not feed_url:
            return HttpResponse(status=400, content="Feed URL not provided")

        reader: Reader = get_reader()
        reader.add_feed(feed_url, exist_ok=True)
        return HttpResponseRedirect("/feeds/")

    def get(self: AddFeedView, request: HttpRequest) -> HttpResponse:
        return render(request=request, template_name="add.html")
