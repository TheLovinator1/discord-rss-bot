# /// script
# dependencies = ["nanodjango"]
# ///
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from nanodjango import Django
from platformdirs import user_data_dir
from reader import Feed, Reader, make_reader

if TYPE_CHECKING:
    from nanodjango.app import HttpRequest, HttpResponse

load_dotenv()
app = Django(
    app_name="discord-rss-bot",
    ALLOWED_HOSTS=["localhost", "rss.lovinator.space"],
    SECRET_KEY=os.environ["DJANGO_SECRET_KEY"],
)
DATABASE_ROUTERS: list[str] = ["reader.ReaderRouter"]


data_dir: str = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True, ensure_exists=True)
db_reader_location: Path = Path(data_dir) / "db.sqlite"
db_django_location: Path = Path(data_dir) / "db_django.sqlite"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(db_django_location),
    },
    "reader": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(db_reader_location),
    },
}


reader: Reader = make_reader(url=str(db_reader_location))


@app.route("/")
def index(request: HttpRequest) -> HttpResponse:
    """Index page for the Discord RSS bot.

    Args:
        request: The HTTP request object.

    Returns:
        The rendered HTML response for the index page.
    """
    feeds: list[Feed] = list(reader.get_feeds())
    return app.render(request, "index.html", {"feeds": feeds})


if __name__ == "__main__":
    app.run()
