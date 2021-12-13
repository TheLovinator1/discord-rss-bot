from contextlib import closing

import typer
from dhooks import Webhook
from reader import FeedExistsError, make_reader

from discord_rss_bot.settings import Settings

app = typer.Typer()
hook = Webhook(Settings.webhook_url)


@app.command()
def add(
    feed_url: str = typer.Argument(..., help="RSS or Atom feed URL."),
    notify_discord: bool = typer.Option(False, help="Send message to Discord."),
) -> None:
    """Add a feed to the database

    Args:
        feed_url (str): The url of the feed to add
        notify_discord (bool): Whether to send a message to Discord when the feed is added
    """
    with closing(make_reader(Settings.db_file)) as reader:
        try:
            # Add the feed to the database
            reader.add_feed(feed_url)

        except FeedExistsError:
            # If the feed already exists, print a message
            typer.echo(f"{feed_url} already exists")
            raise typer.Exit()

        # Update the feeds
        reader.update_feeds()

        # Mark the feed as read
        entries = reader.get_entries(feed=feed_url, read=False)
        for entry in entries:
            reader.mark_entry_as_read(entry)

        if notify_discord:
            # Send a message to Discord
            hook.send(
                f"discord-rss-bot: {feed_url} added to the database.\nYou now have "
                f"{reader.get_feed_counts()} feeds."
            )

        typer.echo(f"{feed_url} added")


@app.command()
def check() -> None:
    """Check new entries for every feed"""
    with closing(make_reader(Settings.db_file)) as reader:
        feed_count = reader.get_feed_counts()
        entry_count = reader.get_entry_counts()

        print(
            f"""Feeds:
        Total: {feed_count.total} feeds
        Broken: {feed_count.broken} feeds
        Enabled: {feed_count.updates_enabled} feeds"""
        )

        print(
            f"""Entries:
        Total: {entry_count.total} entries
        Read: {entry_count.read} entries
        Important: {entry_count.important} entries
        Has enclosures: {entry_count.has_enclosures} entries
        Average number of entries per day:
                1 Month: {entry_count.averages[0]:.2f} entries per day
                3 Months: {entry_count.averages[1]:.2f} entries per day
                12 Months: {entry_count.averages[2]:.2f} entries per day"""
        )

        # Update the feeds
        reader.update_feeds()

        # Get new entries that are not read
        entries = reader.get_entries(read=False)

        for entry in entries:
            # Mark the entry as read
            reader.mark_entry_as_read(entry)

            # Send the entries to Discord
            hook.send(f":robot: :mega: {entry.title}")


if __name__ == "__main__":
    app()
