"""Abstract base class for feed extensions.

Every extension in the ``EXTENSIONS_DIR`` must inherit from
``FeedExtension`` and implement ``process_entry()``.
"""

from __future__ import annotations

import re
from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING
from typing import ClassVar

if TYPE_CHECKING:
    from reader import Entry
    from reader import Reader

    from discord_rss_bot.webhook import DiscordWebhook


class FeedExtension(ABC):
    """Base class for per-feed content extensions.

    Subclasses are auto-discovered from the ``EXTENSIONS_DIR`` directory.
    Each instance processes one entry and returns template variables
    that become available as ``{{variable_name}}`` in Discord messages
    and embeds.

    Class attributes set by subclasses:

    ``name``:
        Unique identifier (used in logs and per-feed enable/disable config).
        Should be a short slug, e.g. ``"jwplayer_thumbnail"``.

    ``description``:
        Human-readable description shown in the web UI (optional).
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""

    #: List of template variable names this extension provides.
    #: Used by the web UI to show users what ``{{variable}}`` tags
    #: are available when an extension is enabled.
    provides_variables: ClassVar[list[str]] = []

    #: List of regex patterns.  When a feed URL matches any pattern,
    #: this extension is automatically enabled for that feed.
    auto_enable_url_patterns: ClassVar[list[str]] = []

    @abstractmethod
    def process_entry(self, entry: Entry, reader: Reader) -> dict[str, str]:
        """Return template variable pairs extracted from *entry*.

        Args:
            entry: The feed entry to process.
            reader: The reader instance (useful for loading feed tags).

        Returns:
            A dict of ``{variable_name: value}`` pairs.  Return an empty
            dict if this entry does not need any extra variables.
        """

    def modify_webhook(
        self,
        webhook: DiscordWebhook,
        _entry: Entry,
        _reader: Reader,
    ) -> DiscordWebhook:
        """Modify the Discord webhook before it is sent.

        Override this method when your extension needs to change the
        webhook payload itself (e.g. to add files, replace embeds, set
        author information, etc.).  By default it returns the webhook
        unchanged.

        Args:
            webhook: The fully built webhook payload.
            _entry: The feed entry being processed.
            _reader: The reader instance.

        Returns:
            The (possibly modified) ``DiscordWebhook``.  Return the
            original *webhook* unchanged if no modifications are needed.
        """
        return webhook

    @classmethod
    def get_enabled_variables(cls, registry: dict[str, type[FeedExtension]], enabled_names: list[str]) -> list[str]:
        """Return the union of ``provides_variables`` for all enabled extensions.

        Args:
            registry: The extension registry ``{name: class}``.
            enabled_names: List of enabled extension names for a feed.

        Returns:
            Sorted list of unique variable names.
        """
        seen: set[str] = set()
        result: list[str] = []
        for name in enabled_names:
            ext_cls = registry.get(name)
            if ext_cls is None:
                continue
            for var_name in ext_cls.provides_variables:
                if var_name not in seen:
                    seen.add(var_name)
                    result.append(var_name)
        result.sort()
        return result

    @classmethod
    def matches_feed_url(cls, feed_url: str) -> bool:
        """Return ``True`` if *feed_url* matches any of the auto-enable patterns.

        Args:
            feed_url: The feed URL to test.

        Returns:
            ``True`` if a match is found, ``False`` otherwise (including when
            no patterns are defined).
        """
        if not cls.auto_enable_url_patterns:
            return False

        return any(re.search(p, feed_url) for p in cls.auto_enable_url_patterns)
