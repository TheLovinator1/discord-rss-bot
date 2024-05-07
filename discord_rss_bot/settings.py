from __future__ import annotations

import logging
import os
from pathlib import Path

from django.contrib import messages
from platformdirs import user_data_dir

logger: logging.Logger = logging.getLogger("discord_rss_bot")

DATA_DIR: str = user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True, ensure_exists=True)
logger.info("Data is stored in %s", DATA_DIR)


BASE_DIR: Path = Path(__file__).resolve().parent.parent
SECRET_KEY: str = os.environ.get("SECRET_KEY", os.urandom(24).hex())
DEBUG: bool = True
ALLOWED_HOSTS: list[str] = ["*"]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATICFILES_DIRS: list[Path] = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ROOT_URLCONF = "discord_rss_bot.urls"
WSGI_APPLICATION = "discord_rss_bot.wsgi.application"
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# So we get nice looking alerts
MESSAGE_TAGS: dict[int, str] = {
    messages.DEBUG: "alert-info",
    messages.INFO: "alert-info",
    messages.SUCCESS: "alert-success",
    messages.WARNING: "alert-warning",
    messages.ERROR: "alert-danger",
}

INSTALLED_APPS: list[str] = [
    "feeds.apps.FeedsConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "crispy_forms",
    "crispy_bootstrap5",
]

MIDDLEWARE: list[str] = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
        },
    },
]


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(DATA_DIR) / "django.sqlite3",
    },
    "reader": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(DATA_DIR) / "db.sqlite",
    },
    "search": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(DATA_DIR) / "search.sqlite",
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
