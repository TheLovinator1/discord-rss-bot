from __future__ import annotations

import auto_prefetch
from django.db import models


class MessageCustomization(auto_prefetch.Model):
    """For customizing the message sent to the webhooks."""

    feed_url = models.TextField(help_text="The URL of the feed to customize the message for.")
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the message customization was created.")

    custom_message = models.TextField(default="{{entry_title}}\n{{entry_link}}", help_text="The message to send.")

    should_be_embed = models.BooleanField(default=False, help_text="Whether the message should be an embed.")
    custom_embed_title = models.TextField(default="{{entry_title}}", help_text="The title of the embed.")
    custom_embed_description = models.TextField(default="{{entry_link}}", help_text="The description of the embed.")
    custom_embed_color = models.TextField(default="#ecff80", help_text="The color of the embed.")
    custom_embed_author_name = models.TextField(default="", help_text="The author of the embed.")
    custom_embed_author_url = models.TextField(default="", help_text="The author URL of the embed.")
    custom_embed_author_icon_url = models.TextField(default="", help_text="The author icon URL of the embed.")
    custom_embed_image_url = models.TextField(default="{{image_1}}", help_text="The image URL of the embed.")
    custom_embed_thumbnail_url = models.TextField(default="", help_text="The thumbnail URL of the embed.")
    custom_embed_footer_text = models.TextField(default="", help_text="The footer text of the embed.")
    custom_embed_footer_icon_url = models.TextField(default="", help_text="The footer icon URL of the embed.")

    def __str__(self: MessageCustomization) -> str:
        msg: str = f"{self.feed_url=}"
        msg += f"\n{self.custom_message=}"
        msg += f"\n{self.should_be_embed=}"
        msg += f"\n{self.custom_embed_title=}"
        msg += f"\n{self.custom_embed_description=}"
        msg += f"\n{self.custom_embed_color=}"
        msg += f"\n{self.custom_embed_author_name=}"
        msg += f"\n{self.custom_embed_author_url=}"
        msg += f"\n{self.custom_embed_author_icon_url=}"
        msg += f"\n{self.custom_embed_image_url=}"
        msg += f"\n{self.custom_embed_thumbnail_url=}"
        msg += f"\n{self.custom_embed_footer_text=}"
        msg += f"\n{self.custom_embed_footer_icon_url=}"
        return msg
