"""HTML formatting utilities for Discord message content.

Converts entry HTML to Discord-friendly markdown while preserving
Discord timestamp tags (``<t:12345:R>``).
"""

from __future__ import annotations

import html
import re

from markdownify import markdownify

DISCORD_TIMESTAMP_TAG_RE: re.Pattern[str] = re.compile(r"<t:\d+(?::[tTdDfFrRsS])?>")

_REDUNDANT_LINK_PREFIX_RE: re.Pattern[str] = re.compile(r"\[https://(www\.)?")


def _preserve_discord_timestamp_tags(text: str) -> tuple[str, dict[str, str]]:
    """Replace Discord timestamp tags with placeholders before markdown conversion.

    Args:
        text: The text to replace tags in.

    Returns:
        The text with Discord timestamp tags replaced by placeholders
        and a mapping of placeholders to original tags.
    """
    replacements: dict[str, str] = {}

    def replace_match(match: re.Match[str]) -> str:
        placeholder: str = f"DISCORDTIMESTAMPPLACEHOLDER{len(replacements)}"
        replacements[placeholder] = match.group(0)
        return placeholder

    return DISCORD_TIMESTAMP_TAG_RE.sub(replace_match, text), replacements


def _restore_discord_timestamp_tags(text: str, replacements: dict[str, str]) -> str:
    """Restore preserved Discord timestamp tags after markdown conversion.

    Args:
        text: The text to restore tags in.
        replacements: A mapping of placeholders to original Discord timestamp tags.

    Returns:
        The text with placeholders replaced by the original Discord timestamp tags.
    """
    for placeholder, original_value in replacements.items():
        text = text.replace(placeholder, original_value)
    return text


def format_entry_html_for_discord(text: str) -> str:
    """Convert entry HTML to Discord-friendly markdown while preserving Discord timestamp tags.

    Args:
        text: The HTML text to format.

    Returns:
        The formatted text with Discord timestamp tags preserved.
    """
    if not text:
        return ""

    unescaped_text: str = html.unescape(text)
    protected_text, replacements = _preserve_discord_timestamp_tags(unescaped_text)
    formatted_text: str = markdownify(
        html=protected_text,
        strip=["img", "table", "td", "tr", "tbody", "thead"],
        escape_misc=False,
        heading_style="ATX",
    )

    formatted_text = _REDUNDANT_LINK_PREFIX_RE.sub("[", formatted_text)

    return _restore_discord_timestamp_tags(formatted_text, replacements)
