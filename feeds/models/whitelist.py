from __future__ import annotations

import auto_prefetch
from django.db import models


class Whitelist(auto_prefetch.Model):
    """For whitelisting feeds.

    It has a one-to-many relationship with WhitelistTitle, WhitelistAuthor, WhitelistSummary, and WhitelistContent.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    feed_url = models.TextField(help_text="The URL of the feed to whitelist.")

    def __str__(self: Whitelist) -> str:
        return f"{self.feed_url}"


class WhitelistTitle(auto_prefetch.Model):
    """For whitelisting feed titles."""

    whitelist = auto_prefetch.ForeignKey(Whitelist, on_delete=models.CASCADE, related_name="titles")
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the title was added to the whitelist.")
    title = models.TextField(help_text="Title to whitelist.")

    def __str__(self: WhitelistTitle) -> str:
        return self.title


class WhitelistAuthor(auto_prefetch.Model):
    """For whitelisting feed authors."""

    whitelist = auto_prefetch.ForeignKey(Whitelist, on_delete=models.CASCADE, related_name="authors")
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the author was added to the whitelist.")
    author = models.TextField(help_text="Author to whitelist.")

    def __str__(self: WhitelistAuthor) -> str:
        return f"{self.whitelist} - {self.author}"


class WhitelistSummary(auto_prefetch.Model):
    """For whitelisting feed summaries."""

    whitelist = auto_prefetch.ForeignKey(Whitelist, on_delete=models.CASCADE, related_name="summaries")
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the summary was added to the whitelist.")
    summary = models.TextField(help_text="Summary to whitelist.")

    def __str__(self: WhitelistSummary) -> str:
        return f"{self.whitelist} - {self.summary}"


class WhitelistContent(auto_prefetch.Model):
    """For whitelisting feed content."""

    whitelist = auto_prefetch.ForeignKey(Whitelist, on_delete=models.CASCADE, related_name="contents")
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the content was added to the whitelist.")
    content = models.TextField(help_text="Content to whitelist.")

    def __str__(self: WhitelistContent) -> str:
        return f"{self.whitelist} - {self.content}"
