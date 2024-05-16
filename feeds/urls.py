from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import path

from .views import (
    AddFeedView,
    IndexView,
    SearchView,
    ToggleWebhookView,
    WebhookView,
    delete_feed,
    list_feeds,
)

if TYPE_CHECKING:
    from django.urls.resolvers import URLPattern

urlpatterns: list[URLPattern] = [
    path(route="", view=IndexView.as_view(), name="index"),
    path(route="feeds/", view=list_feeds, name="list_feeds"),
    path(route="feeds/delete/", view=delete_feed, name="delete_feed"),
    path(route="feeds/add/", view=AddFeedView.as_view(), name="add_feed"),
    path(route="webhooks/", view=WebhookView.as_view(), name="webhooks"),
    path(route="webhooks/toggle/", view=ToggleWebhookView.as_view(), name="toggle_webhook"),
    path(route="search/", view=SearchView.as_view(), name="search"),
]
