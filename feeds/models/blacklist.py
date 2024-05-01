from __future__ import annotations

import typing

from django.db import models


class Blacklist(models.Model):
    """For blacklisting feeds."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    url = models.TextField(primary_key=True)

    class Meta:
        ordering: typing.ClassVar[list] = ["url"]
        verbose_name: str = "Blacklist"
        verbose_name_plural: str = "Blacklist"

    def __str__(self: Blacklist) -> str:
        return self.url


class BlacklistTitle(models.Model):
    """For blacklisting feed titles."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    blacklist = models.ForeignKey("Blacklist", on_delete=models.CASCADE)
    title = models.TextField(primary_key=True)

    class Meta:
        ordering: typing.ClassVar[list] = ["title"]
        verbose_name: str = "Blacklist Title"
        verbose_name_plural: str = "Blacklist Titles"

    def __str__(self: BlacklistTitle) -> str:
        return self.title


class BlacklistSummary(models.Model):
    """For blacklisting feed summaries."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    blacklist = models.ForeignKey("Blacklist", on_delete=models.CASCADE)
    summary = models.TextField(primary_key=True)

    class Meta:
        ordering: typing.ClassVar[list] = ["summary"]
        verbose_name: str = "Blacklist Summary"
        verbose_name_plural: str = "Blacklist Summaries"

    def __str__(self: BlacklistSummary) -> str:
        return self.summary


class BlacklistContent(models.Model):
    """For blacklisting feed content."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    blacklist = models.ForeignKey("Blacklist", on_delete=models.CASCADE)
    content = models.TextField(primary_key=True)

    class Meta:
        ordering: typing.ClassVar[list] = ["content"]
        verbose_name: str = "Blacklist Content"
        verbose_name_plural: str = "Blacklist Contents"

    def __str__(self: BlacklistContent) -> str:
        return self.content


class BlacklistAuthor(models.Model):
    """For blacklisting feed authors."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    blacklist = models.ForeignKey("Blacklist", on_delete=models.CASCADE)
    author = models.TextField(primary_key=True)

    class Meta:
        ordering: typing.ClassVar[list] = ["author"]
        verbose_name: str = "Blacklist Author"
        verbose_name_plural: str = "Blacklist Authors"

    def __str__(self: BlacklistAuthor) -> str:
        return self.author
