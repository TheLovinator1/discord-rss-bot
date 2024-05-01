from __future__ import annotations

import typing

from django.db import models


class WhitelistTitle(models.Model):
    """For whitelisting feed titles."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    whitelist = models.ForeignKey("Whitelist", on_delete=models.CASCADE)
    title = models.TextField(primary_key=True)

    class Meta:
        ordering: typing.ClassVar[list] = ["title"]
        verbose_name: str = "Whitelist Title"
        verbose_name_plural: str = "Whitelist Titles"

    def __str__(self: WhitelistTitle) -> str:
        return self.title


class WhitelistAuthor(models.Model):
    """For whitelisting feed authors."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    whitelist = models.ForeignKey("Whitelist", on_delete=models.CASCADE)
    author = models.TextField(primary_key=True)

    class Meta:
        ordering: typing.ClassVar[list] = ["author"]
        verbose_name: str = "Whitelist Author"
        verbose_name_plural: str = "Whitelist Authors"

    def __str__(self: WhitelistAuthor) -> str:
        return self.author


class WhitelistSummary(models.Model):
    """For whitelisting feed summaries."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    whitelist = models.ForeignKey("Whitelist", on_delete=models.CASCADE)
    summary = models.TextField(primary_key=True)

    class Meta:
        ordering: typing.ClassVar[list] = ["summary"]
        verbose_name: str = "Whitelist Summary"
        verbose_name_plural: str = "Whitelist Summaries"

    def __str__(self: WhitelistSummary) -> str:
        return self.summary


class WhitelistContent(models.Model):
    """For whitelisting feed content."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    whitelist = models.ForeignKey("Whitelist", on_delete=models.CASCADE)
    content = models.TextField(primary_key=True)

    class Meta:
        ordering: typing.ClassVar[list] = ["content"]
        verbose_name: str = "Whitelist Content"
        verbose_name_plural: str = "Whitelist Contents"

    def __str__(self: WhitelistContent) -> str:
        return self.content


class Whitelist(models.Model):
    """For whitelisting feeds.

    It has a one-to-many relationship with WhitelistTitle, WhitelistAuthor, WhitelistSummary, and WhitelistContent.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    url = models.TextField(primary_key=True)

    class Meta:
        ordering: typing.ClassVar[list] = ["url"]
        verbose_name: str = "Whitelist"
        verbose_name_plural: str = "Whitelist"

    def __str__(self: Whitelist) -> str:
        return self.url
