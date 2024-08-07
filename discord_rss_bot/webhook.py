from typing import cast

from fastapi import HTTPException
from reader import Reader

from discord_rss_bot.missing_tags import add_missing_tags


def add_webhook(reader: Reader, webhook_name: str, webhook_url: str) -> None:
    """Add new webhook.

    Args:
        reader: The Reader to use
        webhook_name: The name of the webhook, this will be shown on the webpage
        webhook_url: The webhook URL to send entries to

    Raises:
        HTTPException: This is raised when the webhook already exists
    """
    # Get current webhooks from the database if they exist otherwise use an empty list.
    webhooks = list(reader.get_tag((), "webhooks", []))

    # Webhooks are stored as a list of dictionaries.
    # Example: [{"name": "webhook_name", "url": "webhook_url"}]
    webhooks = cast(list[dict[str, str]], webhooks)

    # Only add the webhook if it doesn't already exist.
    if all(webhook["name"] != webhook_name.strip() for webhook in webhooks):
        # Add the new webhook to the list of webhooks.
        webhooks.append({"name": webhook_name.strip(), "url": webhook_url.strip()})

        # Add our new list of webhooks to the database.
        reader.set_tag((), "webhooks", webhooks)  # type: ignore

        add_missing_tags(reader)
        return

    # TODO(TheLovinator): Show this error on the page.
    # TODO(TheLovinator): Replace HTTPException with a custom exception.
    raise HTTPException(status_code=409, detail="Webhook already exists")


def remove_webhook(reader: Reader, webhook_url: str) -> None:
    """Remove webhook.

    Args:
        reader (Reader): The Reader to use
        webhook_url (str): The webhook URL to remove

    Raises:
        HTTPException: If webhook could not be deleted
        HTTPException: Webhook not found
    """
    # TODO(TheLovinator): Replace HTTPException with a custom exception for both of these.
    # Get current webhooks from the database if they exist otherwise use an empty list.
    webhooks = list(reader.get_tag((), "webhooks", []))

    # Webhooks are stored as a list of dictionaries.
    # Example: [{"name": "webhook_name", "url": "webhook_url"}]
    webhooks = cast(list[dict[str, str]], webhooks)

    # Only add the webhook if it doesn't already exist.
    webhooks_to_remove = [webhook for webhook in webhooks if webhook["url"] in webhook_url.strip()]

    # Remove the webhooks outside of the loop.
    for webhook in webhooks_to_remove:
        webhooks.remove(webhook)

    # Check if any webhooks were removed.
    if any(webhook in webhooks for webhook in webhooks_to_remove):
        raise HTTPException(status_code=500, detail="Webhook could not be deleted")

    # Add our new list of webhooks to the database.
    reader.set_tag((), "webhooks", webhooks)  # type: ignore
