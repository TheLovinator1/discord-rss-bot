from fastapi import HTTPException
from reader import ResourceNotFoundError

from discord_rss_bot.settings import logger, read_settings_file, reader


def set_hook_by_name(name: str, feed_url: str) -> None or HTTPException:
    """Set a webhook by name.

    Args:
        name: The name of the webhook.
        feed_url: The feed to set the webhook for.

    Returns:
        HTTPException: The HTTP exception if the webhook was not found, otherwise None.
    """
    settings = read_settings_file()
    logger.debug(f"Webhook name: {name} with URL: {settings['webhooks'][name]}")
    webhook_url = settings["webhooks"][name]
    try:
        reader.set_tag(feed_url, "webhook", webhook_url)
    except ResourceNotFoundError as e:
        logger.error(f"ResourceNotFoundError: {e}")
        return HTTPException(status_code=500, detail=f"ResourceNotFoundError: Could not set webhook: {e}")
