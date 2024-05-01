from __future__ import annotations

import typing

from django.db import models


class LemonFeed(models.Model):
    """For reading the db from https://github.com/lemon24/reader."""

    url = models.TextField()
    title = models.TextField()
    link = models.TextField()
    updated = models.TextField()
    author = models.TextField()
    subtitle = models.TextField()
    version = models.TextField()
    user_title = models.TextField()
    http_etag = models.TextField()
    http_last_modified = models.TextField()
    data_hash = models.TextField()
    stale = models.TextField()
    updates_enabled = models.TextField()
    last_updated = models.TextField()
    added = models.TextField()
    last_exception = models.TextField()

    class Meta:
        db_table: str = "feeds"
        managed = False
        ordering: typing.ClassVar[list] = ["-last_updated"]
        verbose_name: str = "Feed"
        verbose_name_plural: str = "Feeds"

    def __str__(self) -> str:
        return self.title


class LemonEntry(models.Model):
    """For reading the db from https://github.com/lemon24/reader."""

    id = models.TextField(primary_key=True)
    feed = models.TextField()
    title = models.TextField()
    link = models.TextField()
    updated = models.TextField()
    author = models.TextField()
    published = models.TextField()
    summary = models.TextField()
    content = models.TextField()
    enclosures = models.TextField()
    original_feed = models.TextField()
    data_hash = models.TextField()
    data_hash_changed = models.TextField()
    read = models.TextField()
    read_modified = models.TextField()
    important = models.TextField()
    important_modified = models.TextField()
    added_by = models.TextField()
    last_updated = models.TextField()
    first_updated = models.TextField()
    first_updated_epoch = models.TextField()
    feed_order = models.TextField()
    recent_sort = models.TextField()
    sequence = models.TextField()

    class Meta:
        db_table: str = "entries"
        managed = False
        ordering: typing.ClassVar[list] = ["-updated"]
        verbose_name: str = "Entry"
        verbose_name_plural: str = "Entries"

    def __str__(self) -> str:
        return self.title


class LemonFeedTags(models.Model):
    feed = models.TextField()
    key = models.TextField()
    value = models.TextField()

    class Meta:
        db_table: str = "feed_tags"
        managed = False
        ordering: typing.ClassVar[list] = ["feed", "key"]

    def __str__(self) -> str:
        return f"{self.feed} - {self.key}: {self.value}"


class LemonGlobalTags(models.Model):
    key = models.TextField()
    value = models.TextField()

    class Meta:
        db_table: str = "global_tags"
        managed = False
        ordering: typing.ClassVar[list] = ["key"]

    def __str__(self) -> str:
        return f"{self.key}: {self.value}"

    def save(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003, ARG002
        msg = "This model is read-only."
        raise NotImplementedError(msg)

    def delete(self, *args, **kwargs) -> None:  # type: ignore # noqa: ANN002, ANN003, ARG002, PGH003
        msg = "This model is read-only."
        raise NotImplementedError(msg)
