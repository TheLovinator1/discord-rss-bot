from __future__ import annotations

import logging

import auto_prefetch
from django.db import models

logger: logging.Logger = logging.getLogger(__name__)


class Webhook(auto_prefetch.Model):
    """Where we send the feed updates to."""

    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the webhook was created.")
    name = models.TextField(help_text="The name of the webhook. This is used to identify the webhook.")
    url = models.TextField(
        help_text="The URL of the webhook. This is where the feed updates are sent to.",
    )

    is_deleted = models.BooleanField(default=False, help_text="Whether the webhook is soft-deleted.")

    def __str__(self: Webhook) -> str:
        return self.name

    def delete(self, using=None, keep_parents=False) -> None:  # type: ignore # noqa: ANN001, FBT002, ARG002, PGH003
        logger.debug("Setting is_deleted to True for %s", self)
        self.is_deleted = True
        self.save(using=using)

    def undelete(self) -> None:
        logger.debug("Setting is_deleted to False for %s", self)
        self.is_deleted = False
        self.save()
