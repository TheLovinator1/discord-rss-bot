from __future__ import annotations

import typing
from functools import lru_cache
from pathlib import Path

from platformdirs import user_data_dir
from reader import Reader, make_reader

if typing.TYPE_CHECKING:
    from reader.types import JSONType

data_dir: str = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True, ensure_exists=True)


# TODO(TheLovinator): Add default things to the database and make the edible.
default_custom_message: JSONType | str = "{{entry_title}}\n{{entry_link}}"
default_custom_embed: dict[str, str] = {
    "description": "{{entry_text}}",
    "author_name": "{{entry_title}}",
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
