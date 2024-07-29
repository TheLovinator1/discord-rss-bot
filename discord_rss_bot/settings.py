from __future__ import annotations

import logging
import sys
import typing
from functools import lru_cache
from pathlib import Path

from platformdirs import user_data_dir
from reader import Reader, make_reader

if typing.TYPE_CHECKING:
    from reader.types import JSONType

data_dir: str = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True, ensure_exists=True)


logger: logging.Logger = logging.getLogger("discord_rss_bot")
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter(
    "%(asctime)s [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] [%(levelname)s] %(name)s: %(message)s",
)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)


# TODO(TheLovinator): Add default things to the database and make the edible.
default_custom_message: JSONType | str = "{{entry_title}}\n{{entry_link}}"
default_custom_embed: dict[str, str] = {
    "title": "{{entry_title}}",
    "description": "{{entry_text}}",
    "author_url": "{{entry_link}}",
    "image_url": "{{image_1}}",
    "color": "#469ad9",
}


@lru_cache
def get_reader(custom_location: Path | None = None) -> Reader:
    """Get the reader.

    Args:
        custom_location: The location of the database file.

    """
    db_location: Path = custom_location or Path(data_dir) / "db.sqlite"

    return make_reader(url=str(db_location))
