import os
import time
from contextlib import closing
from shutil import copyfile

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
def stats() -> None:
    with closing(make_reader(Settings.db_file)) as reader:
        feed_count = reader.get_feed_counts()
        entry_count = reader.get_entry_counts()

        typer.echo(
            f"""Feeds:
        Total: {feed_count.total} feeds
        Broken: {feed_count.broken} feeds
        Enabled: {feed_count.updates_enabled} feeds"""
        )

        typer.echo(
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


@app.command()
def check() -> None:
    """Check new entries for every feed"""
    with closing(make_reader(Settings.db_file)) as reader:
        # Update the feeds
        reader.update_feeds()

        # Get new entries that are not read
        entries = reader.get_entries(read=False)

        for entry in entries:
            # Mark the entry as read
            reader.mark_entry_as_read(entry)

            # Send the entries to Discord
            hook.send(f":robot: :mega: {entry.title}\n{entry.link}")


@app.command()
def backup() -> None:
    """Backup the database"""
    backup_dir = os.path.join(Settings.data_dir, "backup")
    os.makedirs(backup_dir, exist_ok=True)

    # Get the current time
    current_time = time.strftime("%Y-%m-%d_%H-%M-%S")

    backup_file_location = os.path.join(
        Settings.data_dir, "backup", f"db_{current_time}.sqlite"
    )
    copyfile(Settings.db_file, backup_file_location)

    typer.echo(f"{Settings.db_file} backed up to {backup_dir}")


@app.command()
def delete() -> None:
    feed_dict = {}
    feed_number = 0
    message = ""
    with closing(make_reader(Settings.db_file)) as reader:
        for feed in reader.get_feeds():
            feed_number += 1
            feed_dict[feed_number] = feed.object_id
            message += f"{feed_number}: {feed.title}\n"

        typer.echo(message)

        feed_to_delete: int = typer.prompt("What feed do you want to remove?")
        feed_id = feed_dict.get(int(feed_to_delete))
        delete = typer.confirm(f"Are you sure you want to delete {feed_id}?")

        if not delete:
            typer.echo("Not deleting")
            raise typer.Abort()

        reader.delete_feed(feed_id)

        typer.echo(f"{feed_id} deleted")


if __name__ == "__main__":
    app()
