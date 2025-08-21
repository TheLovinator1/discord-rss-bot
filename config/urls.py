from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import include, path

if TYPE_CHECKING:
    from django.urls.resolvers import URLResolver

urlpatterns: list[URLResolver] = [
    path(route="accounts/", view=include("accounts.urls", namespace="accounts")),
    path(route="", view=include("core.urls", namespace="core"), name="core"),
]
