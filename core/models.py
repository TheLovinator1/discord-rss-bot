from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Self

import httpx
from django.db import models, transaction
from httpx import Response

if TYPE_CHECKING:
    from reader import Feed as ReaderFeed
    from reader import Reader
    from reader.types import JSONValue

logger: logging.Logger = logging.getLogger(__name__)


class Entry(models.Model):
    id = models.TextField(primary_key=True)
    feed = models.TextField()
    title = models.TextField()
    link = models.TextField()
    updated = models.DateTimeField()
    author = models.TextField()
    published = models.DateTimeField()
    summary = models.TextField()
    content = models.TextField()
    enclosures = models.TextField()
    source = models.TextField()
    original_feed = models.TextField()
    data_hash = models.BinaryField()
    data_hash_changed = models.IntegerField()
    read = models.IntegerField()
    read_modified = models.DateTimeField()
    important = models.IntegerField()
    important_modified = models.DateTimeField()
    added_by = models.TextField()
    last_updated = models.DateTimeField()
    first_updated = models.DateTimeField()
    first_updated_epoch = models.DateTimeField()
    feed_order = models.IntegerField()
    recent_sort = models.IntegerField()
    sequence = models.BinaryField()

    class Meta:
        db_table = "entries"
        app_label = "reader"
        managed = False

    def __str__(self) -> str:
        return self.title


class Feed(models.Model):
    url = models.TextField(primary_key=True)
    title = models.TextField()
    link = models.TextField()
    updated = models.DateTimeField()
    author = models.TextField()
    subtitle = models.TextField()
    version = models.TextField()
    user_title = models.TextField()
    caching_info = models.TextField()
    data_hash = models.BinaryField()
    stale = models.IntegerField()
    updates_enabled = models.IntegerField()
    update_after = models.DateTimeField()
    last_retrieved = models.DateTimeField()
    last_updated = models.DateTimeField()
    added = models.DateTimeField()
    last_exception = models.TextField()

    class Meta:
        db_table = "feeds"
        app_label = "reader"
        managed = False

    def __str__(self) -> str:
        return f"<Feed: {self.title} ({self.url})>"


class EntryTag(models.Model):
    id = models.TextField(primary_key=True)
    feed = models.TextField()
    key = models.TextField()
    value = models.TextField()

    class Meta:
        db_table = "entry_tags"
        app_label = "reader"
        managed = False

    def __str__(self) -> str:
        return f"Tag: {self.key} = {self.value}"


class FeedTag(models.Model):
    feed = models.TextField()
    key = models.TextField()
    value = models.TextField()

    class Meta:
        db_table = "feed_tags"
        app_label = "reader"
        managed = False
        unique_together = ("feed", "key", "value")

    def __str__(self) -> str:
        return f"Feed Tag: {self.key} = {self.value}"


class WebhookData(models.Model):
    custom_name = models.TextField()
    url = models.TextField()

    # Data from Discord API
    webhook_type = models.BigIntegerField()
    webhook_id = models.TextField()
    name = models.TextField()
    avatar = models.TextField()
    channel_id = models.TextField()
    guild_id = models.TextField()
    token = models.TextField()
    avatar_mod = models.BigIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "webhooks"
        unique_together = ("url", "custom_name")

    def __str__(self) -> str:
        return self.name

    def populate_data(self) -> Self:
        response: Response = httpx.get(self.url)
        if response.is_success:
            webhook_json = json.loads(response.text)
            self.webhook_type = webhook_json["type"]
            self.webhook_id = webhook_json["id"]
            self.name = webhook_json["name"]
            self.avatar = webhook_json["avatar"]
            self.channel_id = webhook_json["channel_id"]
            self.guild_id = webhook_json["guild_id"]
            self.token = webhook_json["token"]
            self.avatar_mod = int(webhook_json["channel_id"] or 0) % 5

        self.save()
        return self

    @classmethod
    def import_webhooks_from_reader_to_django_db(cls, reader: Reader) -> None:
        """Import webhooks from the Reader model into the Webhook model.

        Args:
            reader (Reader): The Reader instance to import webhooks from.
        """
        old_data: dict[str, JSONValue] | list[JSONValue] = reader.get_tag((), "webhooks", [])

        if not old_data:
            logger.debug("Checking for old webhooks, but no data found.")
            return

        with transaction.atomic():
            for entry in old_data:
                if not isinstance(entry, dict):
                    logger.warning("Invalid webhook entry found: '%s', skipping.", entry)
                    continue

                url = str(entry.get("url", ""))
                custom_name = str(entry.get("name", ""))

                if not url:
                    logger.warning("Skipping webhook with empty URL: %s", entry)
                    continue

                # Check if the webhook already exists
                webhook, created = cls.objects.get_or_create(url=url, defaults={"custom_name": custom_name})
                if created:
                    try:
                        webhook.populate_data()
                    except (httpx.RequestError, json.JSONDecodeError, KeyError, ValueError):
                        webhook.custom_name = custom_name or ""
                        webhook.save()

                    logger.info("Created new webhook: %s", webhook)
                    logger.debug("Webhook data populated: %s", webhook)
                else:
                    logger.debug("Webhook already exists: %s", webhook)

        logger.info("Migrated %d webhooks from Reader tags to Webhook model.", len(old_data))


class CustomEmbed(models.Model):
    title = models.TextField(default="")
    description = models.TextField(default="")
    color = models.TextField(default="#469ad9")
    author_name = models.TextField(default="")
    author_url = models.TextField(default="")
    author_icon_url = models.TextField(default="")
    image_url = models.TextField(default="")
    thumbnail_url = models.TextField(default="")
    footer_text = models.TextField(default="")
    footer_icon_url = models.TextField(default="")

    def __str__(self) -> str:
        msg: str = "<CustomEmbed "
        for field in self._meta.fields:
            if field.name != "id":
                msg += f"{field.name}: {getattr(self, field.name)} "
        msg += ">"
        return msg

    @classmethod
    def import_from_reader(cls, reader: Reader) -> None:
        """Import custom embeds from the Reader model into the CustomEmbed model.

        Args:
            reader (Reader): The Reader instance to import custom embeds from.
        """
        feeds: list[ReaderFeed] = list(reader.get_feeds())
        if not feeds:
            logger.debug("No feeds found in Reader, skipping custom embed migration.")
            return

        for feed in feeds:
            with transaction.atomic():
                # Find the corresponding feed in the database
                feed_in_db: Feed | None = Feed.objects.filter(url=feed.url).first()
                if not feed_in_db:
                    logger.warning("Feed '%s' not found in the database, skipping custom embed migration for this feed.", feed.url)
                    continue

                # Get the data
                # {"description": "{{entry_text}}", "author_name": "{{entry_title}}", "author_url": "{{entry_link}}", "image_url": "{{image_1}}", "color": "#469ad9"}
                old_data: dict[str, JSONValue] | list[JSONValue] = json.loads(str(reader.get_tag(feed, "custom_embeds", {})))
                if not old_data:
                    logger.debug("Checking for old custom embeds, but no data found.")
                    return

                if not isinstance(old_data, dict):
                    logger.debug("Old custom embeds data is not a dictionary.")
                    return

                # If it is the default custom embed, we should just skip importing it so we can change the default in the future
                default_custom_embed: dict[str, str] = {
                    "description": "{{entry_text}}",
                    "author_name": "{{entry_title}}",
                    "author_url": "{{entry_link}}",
                    "image_url": "{{image_1}}",
                    "color": "#469ad9",
                }
                if old_data.get("custom_embed") == default_custom_embed:
                    logger.debug("Old custom embed is the default, skipping import.")
                    continue

                # Create or update the custom embed
                embed, created = cls.objects.get_or_create(
                    feed=feed_in_db,
                    defaults={
                        "title": old_data.get("title", ""),
                        "description": old_data.get("description", ""),
                        "color": old_data.get("color", "#469ad9"),
                        "author_name": old_data.get("author_name", ""),
                        "author_url": old_data.get("author_url", ""),
                        "author_icon_url": old_data.get("author_icon_url", ""),
                        "image_url": old_data.get("image_url", ""),
                        "thumbnail_url": old_data.get("thumbnail_url", ""),
                        "footer_text": old_data.get("footer_text", ""),
                        "footer_icon_url": old_data.get("footer_icon_url", ""),
                    },
                )
                if created:
                    logger.info("Created new custom embed: %s", embed)
                else:
                    logger.debug("Custom embed already exists: %s", embed)

            logger.info("Migrated %d custom embeds from Reader tags to CustomEmbed model.", len(old_data))


class FeedData(models.Model):
    feed = models.ForeignKey(Feed, on_delete=models.CASCADE, related_name="feed_data")
    custom_message = models.TextField()
    custom_embed = models.ForeignKey(CustomEmbed, on_delete=models.CASCADE, related_name="feed_data")
