from discord_webhook import DiscordWebhook

from discord_rss_bot.settings import logger, reader


def check_feeds() -> None:
    """Check all feeds"""
    reader.update_feeds()
    entries = reader.get_entries(read=False)
    _check_feed(entries)


def check_feed(feed_url: str) -> None:
    """Check a single feed"""
    reader.update_feeds()
    entry = reader.get_entries(feed=feed_url, read=False)
    _check_feed(entry)


def _check_feed(entries) -> None:
    for entry in entries:
        reader.mark_entry_as_read(entry)
        logger.debug(f"New entry: {entry.title}")

        webhook_url = reader.get_tag(entry.feed.url, "webhook")
        if webhook_url:
            logger.debug(f"Sending to webhook: {webhook_url}")
            webhook = DiscordWebhook(url=str(webhook_url), content=f":robot: :mega: New entry: {entry.title}\n"
                                                                   f"{entry.link}", rate_limit_retry=True)
            response = webhook.execute()
            if not response.ok:
                # TODO: Send error to discord
                logger.error(f"Error: {response.status_code} {response.reason}")
                reader.mark_entry_as_unread(entry)
