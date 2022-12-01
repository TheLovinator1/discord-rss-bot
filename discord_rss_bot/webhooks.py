import sys
from contextlib import closing

from reader import make_reader

from discord_rss_bot.discord_rss_bot import db_file_str


def webhook_get() -> None:
    """Get the webhook url"""
    # TODO: Add name to output
    with closing(make_reader(db_file_str)) as reader:
        try:
            webhook_url = reader.get_tag((), "webhook")
            print(f"Webhook: {webhook_url}")
        except Exception as e:
            print("No webhook was found. Use `webhook add` to add one.")
            print(f"Error: {e}\nPlease report this error to the developer.")
            sys.exit()


def webhook_add(webhook_url: str) -> None:
    """Add a webhook to the database"""
    with closing(make_reader(db_file_str)) as reader:
        reader.set_tag((), "webhook", webhook_url)
        print(f"Webhook set to {webhook_url}")
