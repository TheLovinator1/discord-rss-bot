from __future__ import annotations

import os
import typing
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path

from platformdirs import user_data_dir
from reader import Reader
from reader import make_reader

if typing.TYPE_CHECKING:
    from reader.types import JSONType

data_dir: str = os.getenv("DISCORD_RSS_BOT_DATA_DIR", "").strip() or user_data_dir(
    appname="discord_rss_bot",
    appauthor="TheLovinator",
    roaming=True,
    ensure_exists=True,
)


# TODO(TheLovinator): Add default things to the database and make the edible.
default_custom_message: JSONType | str = "{{entry_title}}\n{{entry_link}}"
default_custom_embed: dict[str, str] = {
    "description": "{{entry_text}}",
    "author_name": "{{entry_title}}",
    "author_url": "{{entry_link}}",
    "image_url": "{{image_1}}",
    "color": "#469ad9",
}


def has_plugin(plugin_name: str) -> bool:
    """Return whether the installed reader version provides a built-in plugin.

    We started using .autodiscover, but that is from Reader version 3.25.
    """
    try:
        return find_spec(f"reader.plugins.{plugin_name.removeprefix('.')}") is not None
    except ModuleNotFoundError:
        return False


def make_app_reader(db_location: Path) -> Reader:
    """Create a reader with plugins supported by the installed reader version.

    Returns:
        The configured reader.
    """
    plugins_we_want = (".ua_fallback", ".autodiscover")
    plugins: list[str] = [name for name in plugins_we_want if has_plugin(name)]

    if plugins:
        return make_reader(url=str(db_location), plugins=plugins)
    return make_reader(url=str(db_location))


@lru_cache(maxsize=1)
def get_reader(custom_location: Path | None = None) -> Reader:
    """Get the reader.

    Args:
        custom_location: The location of the database file.

    Returns:
        The reader.
    """
    db_location: Path = custom_location or Path(data_dir) / "db.sqlite"
    reader: Reader = make_app_reader(db_location)

    # https://reader.readthedocs.io/en/latest/api.html#reader.types.UpdateConfig
    # Set the default update interval to 15 minutes if not already configured
    # Users can change this via the Settings page or per-feed in the feed page
    if reader.get_tag((), ".reader.update", None) is None:
        # Set default
        reader.set_tag((), ".reader.update", {"interval": 15})

    # Set the default screenshot layout to desktop if not already configured.
    if reader.get_tag((), "screenshot_layout", None) is None:
        reader.set_tag((), "screenshot_layout", "desktop")  # pyright: ignore[reportArgumentType]

    # Set the default delivery mode for new feeds to embed if not already configured.
    if reader.get_tag((), "delivery_mode", None) is None:
        reader.set_tag((), "delivery_mode", "embed")  # pyright: ignore[reportArgumentType]

    # Set the default webhook text length limit for new feeds if not already configured.
    if reader.get_tag((), "webhook_text_length_limit", None) is None:
        reader.set_tag((), "webhook_text_length_limit", 4000)  # pyright: ignore[reportArgumentType]

    return reader
