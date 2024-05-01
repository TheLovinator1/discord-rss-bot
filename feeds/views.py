from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.views.generic.base import View
from reader import Entry, EntrySearchCounts, FeedExistsError

from discord_rss_bot.reader import get_reader
from feeds.models import LemonFeed, Webhook
from feeds.models.blacklist import Blacklist
from feeds.models.message import MessageCustomization
from feeds.models.whitelist import Whitelist
from feeds.webhooks import send_entry_to_webhook

if TYPE_CHECKING:
    from django.db.models.manager import BaseManager
    from django.http import HttpRequest
    from reader import Reader

logger: logging.Logger = logging.getLogger(__name__)


class FeedView(View):
    def get(self: FeedView, request: HttpRequest, feed_url: str) -> HttpResponse:
        feed_url = unquote(feed_url)
        feed: LemonFeed = get_object_or_404(LemonFeed, url=feed_url)
        return render(request=request, template_name="feeds/feed.html", context={"feed": feed})

    def post(self: FeedView, request: HttpRequest, feed_url: str) -> HttpResponse | HttpResponseRedirect:
        feed_url = unquote(feed_url)
        reader: Reader = get_reader()
        try:
            reader.add_feed(feed_url)
        except FeedExistsError:
            return self.get(request, feed_url)
        return HttpResponseRedirect("/")

    def delete(self: FeedView, request: HttpRequest, feed_url: str) -> HttpResponse:  # noqa: ARG002
        feed_url = unquote(feed_url)
        LemonFeed.objects.filter(url=feed_url).delete()
        return HttpResponseRedirect("/")


class WebhooksView(View):
    def get(self: WebhooksView, request: HttpRequest) -> HttpResponse:
        webhooks: BaseManager[Webhook] = Webhook.objects.all()
        return render(request=request, template_name="feeds/webhooks.html", context={"webhooks": webhooks})

    def post(self: WebhooksView, request: HttpRequest) -> HttpResponse:
        webhook_name: str | None = request.POST.get("webhook_name")
        if webhook_name is None:
            return self.get(request)

        webhook_url: str | None = request.POST.get("webhook_url")
        if webhook_url is None:
            return self.get(request)

        webhook_name = webhook_name.strip()
        webhook_url = webhook_url.strip()

        Webhook.objects.update_or_create(name=webhook_name, url=webhook_url)
        return self.get(request)

    def delete(self: WebhooksView, request: HttpRequest) -> HttpResponse:
        webhook_url: str | None = request.POST.get("webhook_url")
        if webhook_url is None:
            return self.get(request)

        Webhook.objects.filter(url=webhook_url).delete()
        return self.get(request)


class PauseView(View):
    def post(self: PauseView, request: HttpRequest, feed_url: str) -> HttpResponse:  # noqa: ARG002
        feed_url = unquote(feed_url)

        feed: LemonFeed = get_object_or_404(LemonFeed, url=feed_url)

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
        return render(request=request, template_name="feeds/search.html")

    def post(self: SearchView, request: HttpRequest) -> HttpResponse:
        reader: Reader = get_reader()
        reader.update_search()

        search_query: str = request.POST.get("search_query", "")
        if not search_query:
            # TODO(TheLovinator): Show all feeds  # noqa: TD003
            return render(request=request, template_name="feeds/search.html")

        search_amount: EntrySearchCounts = reader.search_entry_counts(search_query)
        if search_amount == 0:
            return render(request=request, template_name="feeds/search.html", context={"no_results": True})

        feeds = list(reader.search_entries(search_query))
        return render(request=request, template_name="feeds/search.html", context={"feeds": feeds})


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
