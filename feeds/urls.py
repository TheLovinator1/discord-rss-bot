from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import path

from .views import (
    SearchView,
    delete_feed,
    delete_webhook,
    get_index_view,
    list_feeds,
    undelete_webhook,
    webhooks_view,
)

if TYPE_CHECKING:
    from django.urls.resolvers import URLPattern

urlpatterns: list[URLPattern] = [
    path(route="", view=get_index_view, name="index"),
    path(route="feeds/", view=list_feeds, name="feeds"),
    path(route="feeds/delete/", view=delete_feed, name="delete_feed"),
    path(route="webhooks/", view=webhooks_view, name="webhooks"),
    path(route="webhooks/<int:webhook_id>/delete/", view=delete_webhook, name="delete_webhook"),
    path(route="webhooks/<int:webhook_id>/undelete/", view=undelete_webhook, name="undelete_webhook"),
    path(route="search/", view=SearchView.as_view(), name="search"),
]
