from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import path

from core.views import FeedListView, WebhookListView

if TYPE_CHECKING:
    from django.urls.resolvers import URLPattern

app_name = "core"

urlpatterns: list[URLPattern] = [
    path(route="", view=FeedListView.as_view(), name="feeds"),
    path(route="webhooks/", view=WebhookListView.as_view(), name="webhooks"),
]
