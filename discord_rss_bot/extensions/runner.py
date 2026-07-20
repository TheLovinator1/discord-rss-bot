"""Functions for running extensions against entries.

This module is separated from ``__init__.py`` to keep the package's
public API as pure re-exports (Ruff rule: non-empty-init-module).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from discord_rss_bot.extensions.discovery import discover_plugins
from discord_rss_bot.extensions.discovery import get_registry
from discord_rss_bot.extensions.storage import EXTENSIONS_TAG
from discord_rss_bot.extensions.storage import get_enabled_extensions_for_feed
from discord_rss_bot.extensions.storage import set_enabled_extensions_for_feed

if TYPE_CHECKING:
    from reader import Entry
    from reader import Reader

    from discord_rss_bot.extensions.base import FeedExtension
    from discord_rss_bot.webhook import DiscordWebhook

logger: logging.Logger = logging.getLogger(__name__)

# Auto-discover plugins on first import so the registry is ready.
discover_plugins()


def auto_enable_extensions_for_feed(reader: Reader, feed_url: str) -> list[str]:
    """Enable extensions whose URL patterns match *feed_url*, if not already enabled.

    Auto-enable only runs when the extensions tag has **never** been explicitly
    set for this feed.  Once the user visits the Extensions page and saves
    (even with an empty list), auto-enable is skipped — the user's choice
    is respected.

    This is called automatically when a feed is created, and lazily on first
    processing for existing feeds.

    Args:
        reader: The reader instance.
        feed_url: The feed URL to match against.

    Returns:
        The updated list of enabled extensions for this feed.
    """
    # If the user has ever saved the Extensions page, respect their choice.
    if reader.get_tag(feed_url, EXTENSIONS_TAG, None) is not None:
        return get_enabled_extensions_for_feed(reader, feed_url)

    registry: dict[str, type[FeedExtension]] = get_registry()
    already_enabled: list[str] = get_enabled_extensions_for_feed(reader, feed_url)

    to_add: list[str] = []
    for name, cls in registry.items():
        if name in already_enabled:
            continue
        if not getattr(cls, "auto_enable_url_patterns", None):
            continue
        for pattern in cls.auto_enable_url_patterns:
            if re.search(pattern, feed_url):
                logger.info(
                    "Auto-enabling extension %r for feed %s (matched pattern %r)",
                    name,
                    feed_url,
                    pattern,
                )
                to_add.append(name)
                break

    if not to_add:
        return already_enabled

    updated: list[str] = already_enabled + [n for n in to_add if n not in already_enabled]
    set_enabled_extensions_for_feed(reader, feed_url, updated)
    return updated


def _get_enabled_instances(entry: Entry, reader: Reader) -> list[FeedExtension]:
    """Return enabled extension instances for the given entry.

    Auto-enables extensions whose URL patterns match the feed URL
    (lazy initialisation for feeds that were created before the
    extension system existed).

    Args:
        entry: The feed entry to process.
        reader: The reader instance.

    Returns:
        List of ``FeedExtension`` instances enabled for this entry's feed.
        Empty list if no extensions are enabled.
    """
    feed_url: str = entry.feed.url
    enabled: list[str] = auto_enable_extensions_for_feed(reader, feed_url)
    if not enabled:
        return []

    registry: dict[str, type[FeedExtension]] = get_registry()
    instances: list[FeedExtension] = []

    for name in enabled:
        cls = registry.get(name)
        if cls is None:
            logger.warning(
                "Extension %r is enabled for feed %r but was not found in the registry",
                name,
                feed_url,
            )
            continue
        instances.append(cls())

    return instances


def _process_extension_instance(
    instance: FeedExtension,
    entry: Entry,
    reader: Reader,
    results: dict[str, str],
) -> bool:
    """Process a single extension and update *results* in place.

    The ``try/except`` wrapping belongs in the caller so that this
    helper stays focused on happy-path logic.

    Args:
        instance: The extension instance to process.
        entry: The feed entry to process.
        reader: The reader instance.
        results: Accumulator dict to update with variable values.

    Returns:
        ``True`` if the extension result was processed successfully,
        ``False`` if the result was not a ``dict`` (and was skipped).
    """
    extra: dict[str, str] = instance.process_entry(entry, reader)
    if not isinstance(extra, dict):
        logger.warning(
            "Extension %r returned %s, expected dict — skipping",
            instance.name,
            type(extra).__name__,
        )
        return False
    for var_name, var_value in extra.items():
        if not isinstance(var_value, str):
            logger.warning(
                "Extension %r returned non-string value for %r (%s) — coercing",
                instance.name,
                var_name,
                type(var_value).__name__,
            )
            results[var_name] = str(var_value)
        else:
            results[var_name] = var_value
    return True


def run_extensions(entry: Entry, reader: Reader) -> dict[str, str]:
    """Run all enabled extensions for the given entry.

    For every enabled extension, all of its ``provides_variables`` are
    guaranteed to appear in the result dict.  Variables that the
    extension did not produce (no match in the entry content) are set
    to an empty string so that ``{{variable}}`` tags are always
    replaced rather than left as literal text.

    If an extension raises, its error is logged and processing
    continues with the next one.

    Args:
        entry: The feed entry to process.
        reader: The reader instance (used to load per-feed config).

    Returns:
        Flat dict of ``{variable_name: value}`` pairs.  Always returns a
        dict (possibly empty if no extensions are enabled).
    """
    results: dict[str, str] = {}

    for instance in _get_enabled_instances(entry, reader):
        # Seed with empty strings so every declared variable is at
        # least present (prevents literal ``{{var}}`` in output).
        for var_name in getattr(type(instance), "provides_variables", []):
            results.setdefault(var_name, "")

        try:
            _process_extension_instance(instance, entry, reader, results)
        except Exception:
            logger.exception(
                "Extension %r failed while processing entry %s",
                instance.name,
                entry.id,
            )

    return results


def run_modify_webhook(
    webhook: DiscordWebhook,
    entry: Entry,
    reader: Reader,
) -> DiscordWebhook:
    """Let enabled extensions modify the Discord webhook before sending.

    Each enabled extension's ``modify_webhook()`` is called in order.
    If an extension raises, its error is logged and the webhook is
    passed to the next extension unchanged.

    Args:
        webhook: The fully built webhook payload.
        entry: The feed entry being processed.
        reader: The reader instance.

    Returns:
        The (possibly modified) webhook.
    """
    current: DiscordWebhook = webhook

    for instance in _get_enabled_instances(entry, reader):
        try:
            current = instance.modify_webhook(current, entry, reader)
            if current is None:
                logger.warning(
                    "Extension %r returned None from modify_webhook — skipping",
                    instance.name,
                )
                current = webhook
        except Exception:
            logger.exception(
                "Extension %r modify_webhook failed for entry %s",
                instance.name,
                entry.id,
            )

    return current
