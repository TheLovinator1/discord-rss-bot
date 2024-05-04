from __future__ import annotations

from django.db import models


class MessageCustomization(models.Model):
    """For customizing the message sent to the webhooks."""

    feed_url = models.TextField(primary_key=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    custom_message = models.TextField(primary_key=True, default="{{entry_title}}\n{{entry_link}}")

    should_be_embed = models.BooleanField(default=False)
    custom_embed_title = models.TextField(default="{{entry_title}}")
    custom_embed_description = models.TextField(default="{{entry_link}}")
    custom_embed_color = models.TextField(default="#ecff80")
    custom_embed_author_name = models.TextField(default="")
    custom_embed_author_url = models.TextField(default="")
    custom_embed_author_icon_url = models.TextField(default="")
    custom_embed_image_url = models.TextField(default="{{image_1}}")
    custom_embed_thumbnail_url = models.TextField(default="")
    custom_embed_footer_text = models.TextField(default="")
    custom_embed_footer_icon_url = models.TextField(default="")

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
