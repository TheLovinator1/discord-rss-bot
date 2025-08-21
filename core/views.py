# Create your views here.
from __future__ import annotations

from django.views.generic import ListView

from core.models import Feed, WebhookData


class FeedListView(ListView):
    model = Feed


class WebhookListView(ListView):
    model = WebhookData
