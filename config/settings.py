# ///
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from platformdirs import user_data_dir
from reader import Reader, make_reader

from core.models import WebhookData

load_dotenv()

data_dir: Path = Path(user_data_dir(appname="discord_rss_bot", appauthor="TheLovinator", roaming=True, ensure_exists=True))
db_reader_location: Path = data_dir / "db.sqlite"
db_django_location: Path = data_dir / "django.sqlite"

reader: Reader = make_reader(url=str(db_reader_location))
WebhookData.import_webhooks_from_reader_to_django_db(reader)

ADMINS: list[tuple[str, str]] = [("Joakim Hellsén", "tlovinator@gmail.com")]
AUTH_USER_MODEL = "accounts.User"
BASE_DIR: Path = Path(__file__).resolve().parent.parent
DATABASE_ROUTERS: list[str] = ["config.db_router.ReaderRouter"]
DEBUG: bool = os.getenv(key="DEBUG", default="True").lower() == "true"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
ROOT_URLCONF = "config.urls"
SECRET_KEY: str = os.environ["DJANGO_SECRET_KEY"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
WSGI_APPLICATION = "config.wsgi.application"

DEFAULT_FROM_EMAIL: str | None = os.getenv(key="EMAIL_HOST_USER", default=None)
EMAIL_HOST: str = os.getenv(key="EMAIL_HOST", default="smtp.gmail.com")
EMAIL_HOST_PASSWORD: str | None = os.getenv(key="EMAIL_HOST_PASSWORD", default=None)
EMAIL_HOST_USER: str | None = os.getenv(key="EMAIL_HOST_USER", default=None)
EMAIL_PORT: int = int(os.getenv(key="EMAIL_PORT", default="587"))
EMAIL_SUBJECT_PREFIX = "[TTVDrops] "
EMAIL_TIMEOUT: int = int(os.getenv(key="EMAIL_TIMEOUT", default="10"))
EMAIL_USE_LOCALTIME = True
EMAIL_USE_TLS: bool = os.getenv(key="EMAIL_USE_TLS", default="True").lower() == "true"
EMAIL_USE_SSL: bool = os.getenv(key="EMAIL_USE_SSL", default="False").lower() == "true"
SERVER_EMAIL: str | None = os.getenv(key="EMAIL_HOST_USER", default=None)

LOGIN_REDIRECT_URL = "/"
LOGIN_URL = "/accounts/login/"
LOGOUT_REDIRECT_URL = "/"

ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_AUTHENTICATION_METHOD = "username"
ACCOUNT_EMAIL_REQUIRED = False

MEDIA_ROOT: Path = data_dir / "media"
MEDIA_ROOT.mkdir(exist_ok=True)
MEDIA_URL = "/media/"

STATIC_ROOT: Path = BASE_DIR / "staticfiles"
STATIC_ROOT.mkdir(exist_ok=True)
STATIC_URL = "/static/"
STATICFILES_DIRS: list[Path] = [BASE_DIR / "static"]
for directory in STATICFILES_DIRS:
    directory.mkdir(exist_ok=True)

if DEBUG:
    INTERNAL_IPS: list[str] = ["127.0.0.1", "localhost"]

if not DEBUG:
    ALLOWED_HOSTS: list[str] = ["rss.lovinator.space"]


DATABASES: dict[str, dict[str, str]] = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(db_django_location),
    },
    "reader": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(db_reader_location),
    },
}


INSTALLED_APPS: list[str] = [
    "core.apps.CoreConfig",
    "accounts.apps.AccountsConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
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

TEMPLATES: list[dict[str, Any]] = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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


LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
        "django.utils.autoreload": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
    },
}
