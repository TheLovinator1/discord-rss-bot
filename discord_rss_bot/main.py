import typer
from dhooks import Webhook
from reader import FeedExistsError, make_reader

from discord_rss_bot.settings import Settings

app = typer.Typer()  # For CLI (https://typer.tiangolo.com/)
hook = Webhook(Settings.webhook_url)  # For Webhooks (https://github.com/kyb3r/dhooks)
reader = make_reader(Settings.db_file)  # For RSS (https://github.com/lemon24/reader)


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
    feed_count = reader.get_feed_counts()
    entry_count = reader.get_entry_counts()
    print(
        f"Total: {feed_count.total}\nBroken: {feed_count.broken}\nEnabled: {feed_count.updates_enabled}"
    )
    print(
        f"""Total: {entry_count.total} feeds
Read: {entry_count.read} feeds
Important: {entry_count.important} feeds
Has enclosures: {entry_count.has_enclosures} feeds
Average number of entries per day:
\t1 Month: {entry_count.averages[0]:.2f} feeds per day
\t3 Months: {entry_count.averages[1]:.2f} feeds per day
\t12 Months: {entry_count.averages[2]:.2f} feeds per day
"""
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
