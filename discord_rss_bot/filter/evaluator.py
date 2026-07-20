from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING

from discord_rss_bot.filter.utils import is_regex_match
from discord_rss_bot.filter.utils import is_word_in_text

if TYPE_CHECKING:
    from collections.abc import Mapping

    from reader import Entry
    from reader import Feed
    from reader import Reader


FILTER_FIELDS: tuple[str, str, str, str] = ("title", "summary", "content", "author")
FilterValues = dict[str, str]


@dataclass(frozen=True, slots=True)
class FilterMatch:
    filter_name: str
    field_name: str
    match_type: str
    pattern: str

    @property
    def description(self) -> str:
        field_label: str = self.field_name.replace("_", " ")
        return f"{self.filter_name} {self.match_type} match on {field_label}"


@dataclass(frozen=True, slots=True)
class EntryFilterDecision:
    should_send: bool
    reason: str
    blacklist_match: FilterMatch | None
    whitelist_match: FilterMatch | None
    has_blacklist_filters: bool
    has_whitelist_filters: bool


def get_filter_values_from_reader(reader: Reader, feed: Feed, filter_name: str) -> FilterValues:
    """Return stripped filter tag values for a feed.

    Args:
        reader: The reader instance.
        feed: The feed whose filter tags should be loaded.
        filter_name: Either blacklist or whitelist.

    Returns:
        FilterValues: The current saved filter values.
    """
    values: FilterValues = {}
    for field_name in FILTER_FIELDS:
        values[field_name] = str(reader.get_tag(feed, f"{filter_name}_{field_name}", "")).strip()
        values[f"regex_{field_name}"] = str(reader.get_tag(feed, f"regex_{filter_name}_{field_name}", "")).strip()
    return values


def coerce_filter_values(filter_name: str, values: Mapping[str, str] | None = None) -> FilterValues:
    """Normalize incoming filter values from forms or tests.

    Args:
        filter_name: Either blacklist or whitelist.
        values: Optional raw mapping of form or saved values.

    Returns:
        FilterValues: A normalized value mapping.
    """
    source_values: Mapping[str, str] = values or {}
    normalized_values: FilterValues = {}
    for field_name in FILTER_FIELDS:
        normalized_values[field_name] = str(
            source_values.get(f"{filter_name}_{field_name}", source_values.get(field_name, "")),
        ).strip()
        normalized_values[f"regex_{field_name}"] = str(
            source_values.get(
                f"regex_{filter_name}_{field_name}",
                source_values.get(f"regex_{field_name}", ""),
            ),
        ).strip()
    return normalized_values


def has_filter_values(values: Mapping[str, str]) -> bool:
    """Return whether any filter value is configured.

    Args:
        values: Filter values to inspect.

    Returns:
        bool: True when at least one value is non-empty.
    """
    return any(str(value).strip() for value in values.values())


def get_entry_filter_decision_from_reader(reader: Reader, entry: Entry) -> EntryFilterDecision:
    """Evaluate an entry against its saved blacklist and whitelist tags.

    Args:
        reader: The reader instance.
        entry: The entry to evaluate.

    Returns:
        EntryFilterDecision: Final decision plus match details.
    """
    return evaluate_entry_filters(
        entry,
        blacklist_values=get_filter_values_from_reader(reader, entry.feed, "blacklist"),
        whitelist_values=get_filter_values_from_reader(reader, entry.feed, "whitelist"),
    )


def evaluate_entry_filters(
    entry: Entry,
    *,
    blacklist_values: Mapping[str, str] | None = None,
    whitelist_values: Mapping[str, str] | None = None,
) -> EntryFilterDecision:
    """Evaluate one entry against blacklist and whitelist settings.

    Blacklist matches take precedence over whitelist matches.

    Args:
        entry: The entry to evaluate.
        blacklist_values: Blacklist values from saved tags or a form.
        whitelist_values: Whitelist values from saved tags or a form.

    Returns:
        EntryFilterDecision: Final decision plus match details.
    """
    normalized_blacklist_values: FilterValues = coerce_filter_values("blacklist", blacklist_values)
    normalized_whitelist_values: FilterValues = coerce_filter_values("whitelist", whitelist_values)

    blacklist_match: FilterMatch | None = find_filter_match(entry, normalized_blacklist_values, "blacklist")
    whitelist_match: FilterMatch | None = find_filter_match(entry, normalized_whitelist_values, "whitelist")

    has_blacklist_filters: bool = has_filter_values(normalized_blacklist_values)
    has_whitelist_filters: bool = has_filter_values(normalized_whitelist_values)

    if blacklist_match and whitelist_match:
        return EntryFilterDecision(
            should_send=False,
            reason=f"Skipped because {blacklist_match.description}; blacklist overrides whitelist.",
            blacklist_match=blacklist_match,
            whitelist_match=whitelist_match,
            has_blacklist_filters=has_blacklist_filters,
            has_whitelist_filters=has_whitelist_filters,
        )

    if blacklist_match:
        return EntryFilterDecision(
            should_send=False,
            reason=f"Skipped because {blacklist_match.description}.",
            blacklist_match=blacklist_match,
            whitelist_match=whitelist_match,
            has_blacklist_filters=has_blacklist_filters,
            has_whitelist_filters=has_whitelist_filters,
        )

    if whitelist_match:
        return EntryFilterDecision(
            should_send=True,
            reason=f"Sent because {whitelist_match.description}.",
            blacklist_match=blacklist_match,
            whitelist_match=whitelist_match,
            has_blacklist_filters=has_blacklist_filters,
            has_whitelist_filters=has_whitelist_filters,
        )

    if has_whitelist_filters:
        return EntryFilterDecision(
            should_send=False,
            reason="Skipped because no whitelist rule matched.",
            blacklist_match=blacklist_match,
            whitelist_match=whitelist_match,
            has_blacklist_filters=has_blacklist_filters,
            has_whitelist_filters=has_whitelist_filters,
        )

    return EntryFilterDecision(
        should_send=True,
        reason="Sent because no active filter blocked it.",
        blacklist_match=blacklist_match,
        whitelist_match=whitelist_match,
        has_blacklist_filters=has_blacklist_filters,
        has_whitelist_filters=has_whitelist_filters,
    )


def find_filter_match(entry: Entry, values: Mapping[str, str], filter_name: str) -> FilterMatch | None:
    """Return the first matching filter rule for an entry.

    Args:
        entry: The entry to evaluate.
        values: Normalized filter values.
        filter_name: Either blacklist or whitelist.

    Returns:
        FilterMatch | None: The first matching rule, if any.
    """
    entry_fields: dict[str, str] = get_entry_fields(entry)

    for field_name in FILTER_FIELDS:
        pattern: str = str(values.get(field_name, "")).strip()
        field_text: str = entry_fields[field_name]
        if pattern and field_text and is_word_in_text(pattern, field_text):
            return FilterMatch(
                filter_name=filter_name,
                field_name=field_name,
                match_type="text",
                pattern=pattern,
            )

    for field_name in FILTER_FIELDS:
        pattern = str(values.get(f"regex_{field_name}", "")).strip()
        field_text = entry_fields[field_name]
        if pattern and field_text and is_regex_match(pattern, field_text):
            return FilterMatch(
                filter_name=filter_name,
                field_name=field_name,
                match_type="regex",
                pattern=pattern,
            )

    return None


def get_entry_fields(entry: Entry) -> dict[str, str]:
    """Return the entry fields used during filter matching.

    Args:
        entry: The entry to inspect.

    Returns:
        dict[str, str]: The fields used by filter evaluation.
    """
    content_value: str = ""
    if entry.content and entry.content[0].value:
        content_value = entry.content[0].value

    return {
        "title": entry.title or "",
        "summary": entry.summary or "",
        "content": content_value,
        "author": entry.authors_str or "",
    }


def get_entry_decision_key(entry: Entry) -> str:
    """Return a stable key for mapping preview decisions to entries.

    Args:
        entry: The entry to key.

    Returns:
        str: A stable key based on feed URL and entry id.
    """
    return f"{entry.feed.url}|{entry.id}"


# ── Convenience wrappers (formerly in separate modules) ──────────────


def feed_has_blacklist_tags(reader: Reader, feed: Feed) -> bool:
    """Return True if the feed has any blacklist tags."""
    return has_filter_values(get_filter_values_from_reader(reader, feed, "blacklist"))


def entry_should_be_skipped(reader: Reader, entry: Entry) -> bool:
    """Return True if the entry matches a blacklist rule."""
    return bool(find_filter_match(entry, get_filter_values_from_reader(reader, entry.feed, "blacklist"), "blacklist"))


def has_white_tags(reader: Reader, feed: Feed) -> bool:
    """Return True if the feed has any whitelist tags."""
    return has_filter_values(get_filter_values_from_reader(reader, feed, "whitelist"))


def should_be_sent(reader: Reader, entry: Entry) -> bool:
    """Return True if the entry matches a whitelist rule."""
    return bool(find_filter_match(entry, get_filter_values_from_reader(reader, entry.feed, "whitelist"), "whitelist"))


def entry_is_whitelisted(entry_to_check: Entry, reader: Reader) -> bool:
    """Return True if the entry is whitelisted."""
    return get_entry_filter_decision_from_reader(reader, entry_to_check).whitelist_match is not None


def entry_is_blacklisted(entry_to_check: Entry, reader: Reader) -> bool:
    """Return True if the entry is blacklisted."""
    return get_entry_filter_decision_from_reader(reader, entry_to_check).blacklist_match is not None


@cache
def encode_url(url_to_quote: str | None) -> str:
    """%-escape a URL so it can be used in a URL query parameter.

    Returns:
        str: The percent-encoded URL.
    """
    return urllib.parse.quote(string=url_to_quote) if url_to_quote else ""
