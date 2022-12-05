from fastapi import HTTPException
from reader import ResourceNotFoundError
from tomlkit.toml_document import TOMLDocument

from discord_rss_bot.settings import logger, read_settings_file, reader


def set_hook_by_name(name: str, feed_url: str) -> HTTPException:
    """Set a webhook by name.

    Args:
        name: The name of the webhook.
        feed_url: The feed to set the webhook for.

    Returns:
        HTTPException: The HTTP exception if the webhook was not found, otherwise None.
    """
    settings: TOMLDocument = read_settings_file()
    logger.debug(f"Webhook name: {name} with URL: {settings['webhooks'][name]}")
    webhook_url: str = str(settings["webhooks"][name])
    try:
        reader.set_tag(feed_url, "webhook", webhook_url)

    except ResourceNotFoundError as e:
        error_msg: str = f"ResourceNotFoundError: Could not set webhook: {e}"
        logger.error(error_msg, exc_info=True)
        return HTTPException(status_code=500, detail=error_msg)
