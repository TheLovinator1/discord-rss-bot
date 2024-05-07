from urllib.parse import quote as urllib_quote

from django import template

register = template.Library()


@register.filter
def quote(value: str) -> str:
    """URL-encode a string."""
    return urllib_quote(value)
