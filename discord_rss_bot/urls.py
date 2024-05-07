from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import include, path

if TYPE_CHECKING:
    from django.urls.resolvers import URLResolver

urlpatterns: list[URLResolver] = [
    path(route="", view=include(arg="feeds.urls")),
]
