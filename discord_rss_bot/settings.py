from __future__ import annotations

import logging
import os
from pathlib import Path

from platformdirs import user_data_dir

logger: logging.Logger = logging.getLogger("discord_rss_bot")

data_dir: str = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True, ensure_exists=True)
logger.info("Data is stored in %s", data_dir)


BASE_DIR: Path = Path(__file__).resolve().parent.parent
SECRET_KEY: str = os.environ.get("SECRET_KEY", os.urandom(24).hex())
DEBUG: bool = os.environ.get("DEBUG", "False").lower() == "true"
ALLOWED_HOSTS: list[str] = ["*"]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ROOT_URLCONF = "discord_rss_bot.urls"
WSGI_APPLICATION = "discord_rss_bot.wsgi.application"

INSTALLED_APPS: list[str] = [
    "feeds.apps.FeedsConfig",
    # "django.contrib.admin",
    # "django.contrib.auth",
    # "django.contrib.contenttypes",
    # "django.contrib.sessions",
    # "django.contrib.messages",
    "django.contrib.staticfiles",
    "background_task",
]

MIDDLEWARE: list[str] = [
    # "django.middleware.security.SecurityMiddleware",
    # "django.contrib.sessions.middleware.SessionMiddleware",
    # "django.middleware.common.CommonMiddleware",
    # "django.middleware.csrf.CsrfViewMiddleware",
    # "django.contrib.auth.middleware.AuthenticationMiddleware",
    # "django.contrib.messages.middleware.MessageMiddleware",
    # "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(data_dir) / "django.sqlite3",
    },
    "reader": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(data_dir) / "db.sqlite",
    },
    "search": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(data_dir) / "search.sqlite",
    },
}


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"level": "DEBUG", "class": "logging.StreamHandler"}},
    "loggers": {
        "": {"handlers": ["console"], "level": "DEBUG", "propagate": True},
    },
}
