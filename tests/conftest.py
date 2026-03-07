from __future__ import annotations

import os
import shutil
import sys
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any


def pytest_configure() -> None:
    """Isolate persistent app state per xdist worker to avoid cross-worker test interference."""
    worker_id: str = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
    worker_data_dir: Path = Path(tempfile.gettempdir()) / "discord-rss-bot-tests" / worker_id

    # Start each worker from a clean state.
    shutil.rmtree(worker_data_dir, ignore_errors=True)
    worker_data_dir.mkdir(parents=True, exist_ok=True)

    os.environ["DISCORD_RSS_BOT_DATA_DIR"] = str(worker_data_dir)

    # If modules were imported before this hook (unlikely), force them to use
    # the worker-specific location.
    settings_module: Any = sys.modules.get("discord_rss_bot.settings")
    if settings_module is not None:
        settings_module.data_dir = str(worker_data_dir)
        get_reader: Any = getattr(settings_module, "get_reader", None)
        if get_reader is not None and hasattr(get_reader, "cache_clear"):
            get_reader.cache_clear()

    main_module: Any = sys.modules.get("discord_rss_bot.main")
    if main_module is not None and settings_module is not None:
        with suppress(Exception):
            current_reader = getattr(main_module, "reader", None)
            if current_reader is not None:
                current_reader.close()
        get_reader: Any = getattr(settings_module, "get_reader", None)
        if callable(get_reader):
            main_module.reader = get_reader()
