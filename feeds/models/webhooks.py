from __future__ import annotations

import typing

from django.db import models


class Webhook(models.Model):
    """Where we send the feed updates to."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    name = models.TextField()
    url = models.TextField()

    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering: typing.ClassVar[list] = ["name"]
        verbose_name: str = "Webhook"
        verbose_name_plural: str = "Webhooks"

    def __str__(self: Webhook) -> str:
        return self.name

    def delete(self, using=None, keep_parents=False) -> None:  # type: ignore # noqa: ANN001, FBT002, ARG002, PGH003
        self.is_deleted = True
        self.save(using=using)
