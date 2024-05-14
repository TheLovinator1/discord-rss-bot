from __future__ import annotations

import auto_prefetch
from django.db import models


class FeedInfo(auto_prefetch.Model):
    """Used when viewing a feed on the frontend."""

    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the info was created.")
    feed_url = models.TextField(help_text="The URL of the feed to display the info for.")

    markdown = models.TextField(help_text="The markdown to display for the feed.", verbose_name="Markdown", blank=True)
    html = models.TextField(
        help_text="The HTML to display for the feed. This is generated from the markdown.",
        verbose_name="HTML",
        blank=True,
    )

    def __str__(self: FeedInfo) -> str:
        return self.html
