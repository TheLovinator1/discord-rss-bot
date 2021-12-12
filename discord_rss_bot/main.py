import os
import sys

import typer
from dhooks import Webhook
from reader import FeedExistsError, make_reader

reader = make_reader("db.sqlite")

app = typer.Typer()
hook = Webhook("")


@app.command()
def add(feed_url: str) -> None:
    """Add a feed to the database

    Args:
        feed_url (str): The url of the feed to add
    """
    try:
        # Add the feed to the database
        reader.add_feed(feed_url)

    except FeedExistsError:
        # If the feed already exists, print a message
        typer.echo(f"{feed_url} already exists")

    # Update the feeds
    reader.update_feeds()

    # Mark the feed as read
    entries = reader.get_entries(feed=feed_url, read=False)
    for entry in entries:
        reader.mark_entry_as_read(entry)

    typer.echo(f"{feed_url} added")


@app.command()
def check() -> None:
    """Check new entries for every feed"""
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
