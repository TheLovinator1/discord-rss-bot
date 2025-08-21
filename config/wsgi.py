from __future__ import annotations

import os
from typing import TYPE_CHECKING

from django.core.wsgi import get_wsgi_application

if TYPE_CHECKING:
    from django.core.handlers.wsgi import WSGIHandler

os.environ.setdefault(key="DJANGO_SETTINGS_MODULE", value="config.settings")

application: WSGIHandler = get_wsgi_application()
