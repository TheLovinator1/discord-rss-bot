from fastapi import HTTPException
from reader import Reader

from discord_rss_bot.missing_tags import add_missing_tags
from discord_rss_bot.settings import list_webhooks


def add_webhook(reader: Reader, webhook_name: str, webhook_url: str):
    """Add new webhook.

    Args:
        reader: The Reader to use
        webhook_name: The name of the webhook, this will be shown on the webpage
        webhook_url: The webhook URL to send entries to

    Raises:
        HTTPException: This is raised when the webhook already exists

    Returns:
        Returns True if everyting was succesful
    """
    # Get current webhooks from the database if they exist otherwise use an empty list.
    webhooks: list[dict[str, str]] = list_webhooks(reader)

    # Only add the webhook if it doesn't already exist.
    if all(webhook["name"] != webhook_name.strip() for webhook in webhooks):
        # Add the new webhook to the list of webhooks.
        webhooks.append({"name": webhook_name.strip(), "url": webhook_url.strip()})

        # Add our new list of webhooks to the database.
        reader.set_tag((), "webhooks", webhooks)  # type: ignore

        add_missing_tags(reader)
        return True

    # TODO: Show this error on the page.
    raise HTTPException(status_code=409, detail="Webhook already exists")


def remove_webhook(reader: Reader, webhook_url: str):
    clean_webhook_url: str = webhook_url.strip()

    # Get current webhooks from the database if they exist otherwise use an empty list.
    webhooks: list[dict[str, str]] = list_webhooks(reader)

    # Only add the webhook if it doesn't already exist.
    for webhook in webhooks:
        if webhook["url"] in clean_webhook_url:
            webhooks.remove(webhook)

            # Check if it has been removed.
            if webhook in webhooks:
                raise HTTPException(status_code=500, detail="Webhook could not be deleted")

            # Add our new list of webhooks to the database.
            reader.set_tag((), "webhooks", webhooks)  # type: ignore
            return True

    # TODO: Show this error on the page.
    raise HTTPException(status_code=404, detail="Webhook not found")
