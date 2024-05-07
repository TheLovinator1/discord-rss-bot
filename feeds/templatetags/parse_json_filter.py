import json

from django import template

register = template.Library()


@register.filter
def parse_json(json_string: str):  # noqa: ANN201
    """Parse a JSON string."""
    return json.loads(json_string)
