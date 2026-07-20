"""Feed extension system: discover, configure, and run per-entry content extensions.

Extensions are Python classes that inherit from ``FeedExtension``,
auto-discovered from the ``EXTENSIONS_DIR`` directory (default: ``extensions/``).

Typical usage::

    from discord_rss_bot.extensions import run_extensions

    extra_vars: dict[str, str] = run_extensions(entry, reader)
    # extra_vars == {"jwplayer_thumbnail": "https://...", ...}
"""

from __future__ import annotations

from discord_rss_bot.extensions.base import FeedExtension
from discord_rss_bot.extensions.discovery import discover_plugins
from discord_rss_bot.extensions.discovery import get_registry
from discord_rss_bot.extensions.discovery import registry_clear
from discord_rss_bot.extensions.runner import auto_enable_extensions_for_feed
from discord_rss_bot.extensions.runner import run_extensions
from discord_rss_bot.extensions.runner import run_modify_webhook

__all__ = [
    "FeedExtension",
    "auto_enable_extensions_for_feed",
    "discover_plugins",
    "get_registry",
    "registry_clear",
    "run_extensions",
    "run_modify_webhook",
]
