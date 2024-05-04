from __future__ import annotations

from django.db import models


class Webhook(models.Model):
    """Where we send the feed updates to."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    name = models.TextField()
    url = models.TextField()

    is_deleted = models.BooleanField(default=False)

    def __str__(self: Webhook) -> str:
        return f"{self.name=}, {self.url=} ({self.is_deleted=}) ({self.created_at=}) ({self.updated_at=})"

    def delete(self, using=None, keep_parents=False) -> None:  # type: ignore # noqa: ANN001, FBT002, ARG002, PGH003
        self.is_deleted = True
        self.save(using=using)
