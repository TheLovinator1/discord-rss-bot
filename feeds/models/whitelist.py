from __future__ import annotations

import auto_prefetch
from django.db import models


class Whitelist(auto_prefetch.Model):
    """For whitelisting feeds.

    It has a one-to-many relationship with WhitelistTitle, WhitelistAuthor, WhitelistSummary, and WhitelistContent.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    url = models.TextField(primary_key=True)

    def __str__(self: Whitelist) -> str:
        return f"{self.url}"


class WhitelistTitle(auto_prefetch.Model):
    """For whitelisting feed titles."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    whitelist = models.ForeignKey(Whitelist, on_delete=models.CASCADE)
    title = models.TextField(primary_key=True)

    def __str__(self: WhitelistTitle) -> str:
        return self.title


class WhitelistAuthor(auto_prefetch.Model):
    """For whitelisting feed authors."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    whitelist = models.ForeignKey(Whitelist, on_delete=models.CASCADE)
    author = models.TextField(primary_key=True)

    def __str__(self: WhitelistAuthor) -> str:
        return f"{self.whitelist.url} - {self.author}"


class WhitelistSummary(auto_prefetch.Model):
    """For whitelisting feed summaries."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    whitelist = models.ForeignKey(Whitelist, on_delete=models.CASCADE)
    summary = models.TextField(primary_key=True)

    def __str__(self: WhitelistSummary) -> str:
        return f"{self.whitelist.url} - {self.summary}"


class WhitelistContent(auto_prefetch.Model):
    """For whitelisting feed content."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    whitelist = models.ForeignKey(Whitelist, on_delete=models.CASCADE)
    content = models.TextField(primary_key=True)

    def __str__(self: WhitelistContent) -> str:
        return f"{self.whitelist.url} - {self.content}"
