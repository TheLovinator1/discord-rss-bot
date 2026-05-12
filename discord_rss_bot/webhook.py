from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import cast

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True)
class WebhookFile:
    """A file uploaded with a Discord webhook request."""

    filename: str
    content: bytes


class DiscordEmbed:
    """Small Discord embed payload builder used by the webhook sender."""

    def __init__(self) -> None:  # noqa: D107
        self._payload: JsonObject = {}

    def to_dict(self) -> JsonObject:
        """Return the JSON payload for this embed."""
        return cast("JsonObject", dict(self._payload))

    def set_description(self, description: str) -> None:
        self._payload["description"] = description

    def set_title(self, title: str) -> None:
        self._payload["title"] = title

    def set_url(self, url: str) -> None:
        self._payload["url"] = url

    def set_color(self, color: int | str) -> None:
        if isinstance(color, int):
            self._payload["color"] = color
            return

        normalized_color: str = color.removeprefix("#")
        self._payload["color"] = int(normalized_color, 16)

    def set_author(self, *, name: str, url: str | None = None, icon_url: str | None = None) -> None:
        author: JsonObject = {"name": name}
        if url:
            author["url"] = url
        if icon_url:
            author["icon_url"] = icon_url
        self._payload["author"] = author

    def set_thumbnail(self, *, url: str) -> None:
        self._payload["thumbnail"] = {"url": url}

    def set_image(self, *, url: str, **_ignored: Any) -> None:  # noqa: ANN401
        self._payload["image"] = {"url": url}

    def set_footer(self, *, text: str, icon_url: str | None = None) -> None:
        footer: JsonObject = {"text": text}
        if icon_url:
            footer["icon_url"] = icon_url
        self._payload["footer"] = footer

    def add_embed_field(self, *, name: str, value: str, inline: bool | None = None) -> None:
        fields = self._payload.setdefault("fields", [])
        if not isinstance(fields, list):
            fields = []
            self._payload["fields"] = fields

        field: JsonObject = {"name": name, "value": value}
        if inline is not None:
            field["inline"] = inline
        fields.append(field)

    def set_timestamp(self, *, timestamp: str) -> None:
        self._payload["timestamp"] = timestamp


class DiscordWebhook:
    """Discord webhook request data.

    This intentionally mirrors the subset of `discord-webhook` used by the app
    while leaving the actual HTTP transport to `httpx`.
    """

    def __init__(  # noqa: D107
        self,
        url: str,
        *,
        content: str | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        tts: bool | None = None,
        allowed_mentions: JsonObject | None = None,
        flags: int | None = None,
        components: list[JsonValue] | None = None,
        thread_id: str | None = None,
        timeout: float | None = None,
        rate_limit_retry: bool = False,
        **_ignored: Any,  # noqa: ANN401
    ) -> None:
        self.url: str = url
        self.thread_id: str | None = thread_id
        self.timeout: int | float = timeout or 30.0
        self.rate_limit_retry: bool = rate_limit_retry
        self.files: list[WebhookFile] = []
        self._payload: JsonObject = {}

        if content is not None:
            self._payload["content"] = content
        if username:
            self._payload["username"] = username
        if avatar_url:
            self._payload["avatar_url"] = avatar_url
        if tts is not None:
            self._payload["tts"] = tts
        if allowed_mentions is not None:
            self._payload["allowed_mentions"] = allowed_mentions
        if flags is not None:
            self._payload["flags"] = flags
        if components is not None:
            self._payload["components"] = components

    @property
    def json(self) -> JsonObject:
        return self._payload

    @property
    def content(self) -> str | None:
        value = self._payload.get("content")
        return value if isinstance(value, str) else None

    @content.setter
    def content(self, value: str | None) -> None:
        if value is None:
            self._payload.pop("content", None)
        else:
            self._payload["content"] = value

    @property
    def username(self) -> str | None:
        value = self._payload.get("username")
        return value if isinstance(value, str) else None

    @username.setter
    def username(self, value: str | None) -> None:
        if value:
            self._payload["username"] = value
        else:
            self._payload.pop("username", None)

    @property
    def avatar_url(self) -> str | None:
        value = self._payload.get("avatar_url")
        return value if isinstance(value, str) else None

    @avatar_url.setter
    def avatar_url(self, value: str | None) -> None:
        if value:
            self._payload["avatar_url"] = value
        else:
            self._payload.pop("avatar_url", None)

    @property
    def components(self) -> list[JsonValue]:
        value = self._payload.get("components")
        return cast("list[JsonValue]", value) if isinstance(value, list) else []

    @components.setter
    def components(self, value: list[JsonValue]) -> None:
        self._payload["components"] = value

    @property
    def flags(self) -> int | None:
        value = self._payload.get("flags")
        return value if isinstance(value, int) else None

    @flags.setter
    def flags(self, value: int | None) -> None:
        if value is None:
            self._payload.pop("flags", None)
        else:
            self._payload["flags"] = value

    def add_file(self, *, file: bytes, filename: str) -> None:
        self.files.append(WebhookFile(filename=filename, content=file))

    def add_embed(self, embed: DiscordEmbed) -> None:
        embeds = self._payload.setdefault("embeds", [])
        if not isinstance(embeds, list):
            embeds = []
            self._payload["embeds"] = embeds
        embeds.append(embed.to_dict())

    def remove_embeds(self) -> None:
        self._payload.pop("embeds", None)
