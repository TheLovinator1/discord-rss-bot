import logging
import os
import sys
import time
from contextlib import closing
from pathlib import Path
from shutil import copyfile

import typer
from discord_webhook import DiscordWebhook
from reader import FeedExistsError, make_reader

# Add logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = typer.Typer()
app_dir = typer.get_app_dir("discord-rss-bot")
logging.debug(f"App dir: {app_dir}")

# Create the data directory if it doesn't exist
os.makedirs(app_dir, exist_ok=True)

# Store the database file in the data directory
db_name = os.getenv("DATABASE_NAME", "db.sqlite")
db_file: Path = Path(os.path.join(app_dir, db_name))
logging.debug(f"Database file: {db_file}")

# Convert Path to string
db_file_str: str = str(db_file)
logging.debug(f"Database file as string: {db_file_str}")


@app.command()
def add(
        feed_url: str = typer.Argument(..., help="RSS or Atom feed URL."),
        notify_discord: bool = typer.Option(True, help="Send message to Discord."),
) -> None:
    """Add a feed to the database

    Args:
        feed_url (str): The url of the feed to add
        notify_discord (bool): Whether to send a message to Discord when
        the feed is added.
    """
    with closing(make_reader(db_file_str)) as reader:
        try:
            # Add the feed to the database
            reader.add_feed(feed_url)
        except FeedExistsError:
            # If the feed already exists, print a message
            typer.echo(f"{feed_url} already exists")
            sys.exit()

        # Update the feeds
        reader.update_feeds()

        # Mark the feed as read
        entries = reader.get_entries(feed=feed_url, read=False)
        for entry in entries:
            logging.debug(f"Marking {entry.title} as read")
            reader.mark_entry_as_read(entry)

        if notify_discord:
            # Send a message to Discord
            webhook_msg = (
                f"discord-rss-bot: {feed_url} added to the database.\n"
                f"You now have {reader.get_feed_counts()} feeds."
            )
            webhook_url = reader.get_tag((), "webhook")
            logging.debug(f"Webhook URL: {webhook_url}")

            if not webhook_url:
                typer.echo("No webhook URL found in the database.")
                sys.exit()

            webhook = DiscordWebhook(url=str(webhook_url), content=webhook_msg, rate_limit_retry=True)

            response = webhook.execute()
            if response.status_code != 204:
                typer.echo(f"Error sending message to Discord - {response.status_code}\n{response.text}")

        typer.echo(f"{feed_url} added")


@app.command()
def stats() -> None:
    """Print the amount feeds and entries in the database"""
    with closing(make_reader(db_file_str)) as reader:
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
    with closing(make_reader(db_file_str)) as reader:
        # Update the feeds
        reader.update_feeds()

        # Get new entries that are not read
        entries = reader.get_entries(read=False)

        for entry in entries:
            # Mark the entry as read
            reader.mark_entry_as_read(entry)
            logging.debug(f"Marking {entry.title} as read")

            webhook_url = reader.get_tag((), "webhook")
            logging.debug(f"Webhook URL: {webhook_url}")
            if not webhook_url:
                typer.echo("No webhook URL found in the database.")
                sys.exit()

            webhook = DiscordWebhook(url=str(webhook_url), content=f":robot: :mega: {entry.title}\n{entry.link}",
                                     rate_limit_retry=True)

            response = webhook.execute()
            if response.status_code != 204:
                typer.echo(f"Error sending message to Discord - {response.status_code}\n{response.text}")


@app.command()
def backup() -> None:
    """Backup the database"""
    backup_dir = os.path.join(app_dir, "backup")
    os.makedirs(backup_dir, exist_ok=True)

    # Get the current time
    current_time = time.strftime("%Y-%m-%d_%H-%M-%S")

    backup_file_location = os.path.join(app_dir, "backup", f"db_{current_time}.sqlite")
    copyfile(db_file, backup_file_location)

    typer.echo(f"{db_file} backed up to {backup_dir}")


@app.command()
def delete() -> None:
    """Delete a feed from the database"""
    feed_dict = {}
    feed_number = 0
    message = ""
    with closing(make_reader(db_file_str)) as reader:
        for feed in reader.get_feeds():
            logging.debug(f"Feed: {feed}")
            feed_number += 1
            logging.debug(f"Feed number: {feed_number}")
            logging.debug(f"Feed URL: {feed.url}")
            feed_dict[str(feed_number)] = feed.url
            logging.debug(f"Feed dict: {feed_dict}")
            message += f"{feed_number}: {feed.title}\n"
        typer.echo(message)

        feed_to_delete: str = typer.prompt("What feed do you want to remove?")
        feed_url = feed_dict.get(str(feed_to_delete))

        if not feed_url:
            typer.echo("Invalid feed number")
            sys.exit()

        logging.debug(f"Feed URL: {feed_url}")
        confirm_delete = typer.confirm(
            f"Are you sure you want to delete {feed_url}?",
        )

        if not confirm_delete:
            typer.echo("Not deleting")
            raise typer.Abort()

        reader.delete_feed(feed_url)

        typer.echo(f"{feed_url} deleted")


@app.command()
def webhook_add(webhook_url: str) -> None:
    """Add a webhook to the database"""
    with closing(make_reader(db_file_str)) as reader:
        reader.set_tag((), "webhook", webhook_url)
        typer.echo(f"Webhook set to {webhook_url}")


@app.command()
def webhook_get() -> None:
    """Get the webhook url"""
    # TODO: Add name to output
    with closing(make_reader(db_file_str)) as reader:
        try:
            webhook_url = reader.get_tag((), "webhook")
            typer.echo(f"Webhook: {webhook_url}")
        except Exception as e:
            typer.echo("No webhook was found. Use `webhook add` to add one.")
            typer.echo(f"Error: {e}\nPlease report this error to the developer.")
            sys.exit()


if __name__ == "__main__":
    app()
