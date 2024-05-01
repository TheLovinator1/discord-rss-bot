from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from django.conf import settings
from reader import Reader, make_reader


@lru_cache
def get_reader(custom_location: Path | None = None) -> Reader:
    """Get the reader.

    Args:
        custom_location: The location of the database file.

    Raises:
        ValueError: If the data directory is not set in the Django settings.

    Returns:
        The reader.
    """
    data_dir = settings.data_dir
    if not data_dir:
        msg = "Failed to get data directory from Django settings."
        raise ValueError(msg)

    db_location: Path = custom_location or Path(data_dir) / "db.sqlite"

    return make_reader(url=str(db_location))
