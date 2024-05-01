import os

from django.core.handlers.wsgi import WSGIHandler
from django.core.wsgi import get_wsgi_application

os.environ.setdefault(key="DJANGO_SETTINGS_MODULE", value="discord_rss_bot.settings")

application: WSGIHandler = get_wsgi_application()
