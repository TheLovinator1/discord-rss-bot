import os
from pathlib import Path

from platformdirs import user_data_dir


def get_app_dir(app_dir: str = user_data_dir("discord_rss_bot")) -> Path:
    """
    Get the application directory. This is where the database file is stored.

    Args:
        app_dir: The application directory, defaults to user_data_dir().

    Returns:
        Path: The application directory.
    """
    print(f"Data directory: {app_dir}")

    # Use the environment variable if it exists instead of the default app dir.
    app_dir = os.getenv("DATABASE_LOCATION") or app_dir

    # Create the data directory if it doesn't exist
    os.makedirs(app_dir, exist_ok=True)

    return Path(app_dir)


def get_db_file(custom_db_name: str = "db.sqlite") -> Path:
    """Where we store the database file

    Args:
        custom_db_name: The name of the database file, defaults to db.sqlite.

    Returns:
        Path: The database file.
    """
    # Store the database file in the data directory
    app_dir = get_app_dir()

    # Use the environment variable if it exists instead of the default db name.
    db_name = os.getenv("DATABASE_NAME") or custom_db_name

    db_file: Path = Path(os.path.join(app_dir, db_name))
    print(f"Database file: {db_file}")

    return Path(db_file)
