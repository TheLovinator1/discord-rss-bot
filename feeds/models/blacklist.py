from __future__ import annotations

import auto_prefetch
from django.db import models


class Blacklist(auto_prefetch.Model):
    """For blacklisting feeds."""

    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the blacklist was created.")
    feed_url = models.TextField(help_text="The URL of the feed to blacklist.")

    def __str__(self: Blacklist) -> str:
        return f"{self.feed_url}"


class BlacklistTitle(auto_prefetch.Model):
    """For blacklisting feed titles."""

    blacklist = auto_prefetch.ForeignKey(
        Blacklist,
        on_delete=models.CASCADE,
        related_name="titles",
        related_query_name="title",
        help_text="The blacklist to add the title to.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the title was added to the blacklist.")
    title = models.TextField(help_text="Title to blacklist.")

    def __str__(self: BlacklistTitle) -> str:
        return f"{self.blacklist.url} - {self.title}"


class BlacklistSummary(auto_prefetch.Model):
    """For blacklisting feed summaries."""

    blacklist = auto_prefetch.ForeignKey(
        Blacklist,
        on_delete=models.CASCADE,
        related_name="summaries",
        related_query_name="summary",
        help_text="The blacklist to add the summary to.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the summary was added to the blacklist.")
    summary = models.TextField(help_text="Summary to blacklist.")

    def __str__(self: BlacklistSummary) -> str:
        return f"{self.blacklist.url} - {self.summary}"


class BlacklistContent(auto_prefetch.Model):
    """For blacklisting feed content."""

    blacklist = auto_prefetch.ForeignKey(
        Blacklist,
        on_delete=models.CASCADE,
        related_name="contents",
        related_query_name="content",
        help_text="The blacklist to add the content to.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the content was added to the blacklist.")
    content = models.TextField(help_text="Content to blacklist.")

    def __str__(self: BlacklistContent) -> str:
        return f"{self.blacklist.url} - {self.content}"


class BlacklistAuthor(auto_prefetch.Model):
    """For blacklisting feed authors."""

    blacklist = auto_prefetch.ForeignKey(
        Blacklist,
        on_delete=models.CASCADE,
        related_name="authors",
        related_query_name="author",
        help_text="The blacklist to add the author to.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the author was added to the blacklist.")
    author = models.TextField(help_text="Author to blacklist.")

    def __str__(self: BlacklistAuthor) -> str:
        return f"{self.blacklist.url} - {self.author}"
