from __future__ import annotations

from django.db import models


class Blacklist(models.Model):
    """For blacklisting feeds."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    url = models.TextField(primary_key=True)

    def __str__(self: Blacklist) -> str:
        return f"{self.url}"


class BlacklistTitle(models.Model):
    """For blacklisting feed titles."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    blacklist = models.ForeignKey(Blacklist, on_delete=models.CASCADE)
    title = models.TextField(primary_key=True)

    def __str__(self: BlacklistTitle) -> str:
        return f"{self.blacklist.url} - {self.title}"


class BlacklistSummary(models.Model):
    """For blacklisting feed summaries."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    blacklist = models.ForeignKey(Blacklist, on_delete=models.CASCADE)
    summary = models.TextField(primary_key=True)

    def __str__(self: BlacklistSummary) -> str:
        return f"{self.blacklist.url} - {self.summary}"


class BlacklistContent(models.Model):
    """For blacklisting feed content."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    blacklist = models.ForeignKey(Blacklist, on_delete=models.CASCADE)
    content = models.TextField(primary_key=True)

    def __str__(self: BlacklistContent) -> str:
        return f"{self.blacklist.url} - {self.content}"


class BlacklistAuthor(models.Model):
    """For blacklisting feed authors."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    blacklist = models.ForeignKey(Blacklist, on_delete=models.CASCADE)
    author = models.TextField(primary_key=True)

    def __str__(self: BlacklistAuthor) -> str:
        return f"{self.blacklist.url} - {self.author}"
