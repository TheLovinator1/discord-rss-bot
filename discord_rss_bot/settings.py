import configparser
import os
import sys

from platformdirs import user_data_dir


class Settings:
    data_dir = user_data_dir(
        appname="discord-rss-bot",  # The name of application.
        appauthor="TheLovinator",  # The name of the app author or distributing body for this application
        roaming=True,  # Whether to use the roaming appdata directory on Windows
    )

    # Create the data directory if it doesn't exist
    os.makedirs(data_dir, exist_ok=True)

    # Store the database file in the data directory
    db_file = os.path.join(data_dir, "db.sqlite")

    # Store the config in the data directory
    config_location = os.path.join(data_dir, "config.conf")

    if not os.path.isfile(config_location):
        # TODO: Add config for db_file and config_location
        print("No config file found, creating one...")
        with open(config_location, "w") as config_file:
            config = configparser.ConfigParser()
            config.add_section("config")
            config.set(
                "config",
                "webhook_url",
                "https://discord.com/api/webhooks/1234/567890/ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz",
            )

            config.write(config_file)
        sys.exit(f"Please edit the config file at {config_location}")

    # Read the config file
    config = configparser.ConfigParser()
    config.read(config_location)

    # Get the webhook url from the config file
    webhook_url = config.get("config", "webhook_url")
