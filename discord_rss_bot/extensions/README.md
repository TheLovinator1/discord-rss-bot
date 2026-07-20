# Extension System

Extensions are Python plugins that extract data from RSS/Atom entries and/or mutate the Discord webhook payload before messages are sent.

**Two hooks per entry:**

1. **`process_entry()`** → return `{variable_name: string_value}` dict → available as `{{variable_name}}` in templates.
2. **`modify_webhook()`** → mutate the `DiscordWebhook` (files, embeds, author, etc.) after template replacement.

---

## TL;DR — Make an Extension

Drop a `.py` file in your `extensions/` dir (or `$EXTENSIONS_DIR`). Subclass `FeedExtension`:

```python
"""
Word count example — provides {{word_count}} per entry.
"""
from __future__ import annotations
import logging
from typing import ClassVar, TYPE_CHECKING
from discord_rss_bot.extensions.base import FeedExtension

if TYPE_CHECKING:
    from reader import Entry, Reader

logger = logging.getLogger(__name__)


class WordCountExtension(FeedExtension):
    name = "word_count"
    description = "Counts words in each entry's content."
    provides_variables: ClassVar[list[str]] = ["word_count"]

    def process_entry(self, entry: Entry, reader: Reader) -> dict[str, str]:
        text = " ".join(
            c.value for c in (entry.content or []) if hasattr(c, "value") and c.value
        ) or (entry.summary or "")
        return {"word_count": str(len(text.split())) if text else "0"}
```

Then restart the bot, enable it in the web UI's Extensions page, and use `{{word_count}}` in templates.

---

## API Reference

### Class Attributes

| Attribute                  | Type                  | Required | Purpose                                                   |
| -------------------------- | --------------------- | -------- | --------------------------------------------------------- |
| `name`                     | `ClassVar[str]`       | **Yes**  | Unique slug for logs, registry, enable/disable            |
| `description`              | `ClassVar[str]`       | No       | Shown in web UI                                           |
| `provides_variables`       | `ClassVar[list[str]]` | No       | Template variables this extension produces                |
| `auto_enable_url_patterns` | `ClassVar[list[str]]` | No       | Regex patterns; matching feeds auto-enable this extension |

### `process_entry(self, entry: Entry, reader: Reader) -> dict[str, str]` (required)

Called for every entry. Return `{var: value}` pairs. Missing variables from `provides_variables` get filled with `""`.

- `entry.content` — list of `Content` objects (`.value`, `.type`)
- `entry.summary` — plain-text string
- `entry.feed.url`, `entry.link`, `entry.title`, `entry.id`, etc.

### `modify_webhook(self, webhook: DiscordWebhook, entry: Entry, reader: Reader) -> DiscordWebhook` (optional)

Called after template replacement. Return modified `webhook` or it unchanged.

```python
# Content
webhook.content = "..."  # or None to clear

# Author
webhook.username = "Bot Name"
webhook.avatar_url = "https://..."

# Embeds
embed = DiscordEmbed()
embed.set_title("...")
embed.set_description("...")
embed.set_url("https://...")
embed.set_color(0x00FF00)  # or hex str "00FF00"
embed.set_author(name="...", url="...", icon_url="...")
embed.set_thumbnail(url="...")
embed.set_image(url="...")
embed.set_footer(text="...", icon_url="...")
embed.add_embed_field(name="Key", value="Value", inline=True)
embed.set_timestamp(timestamp="1234567890")
webhook.add_embed(embed)
webhook.remove_embeds()

# Files
webhook.add_file(file=bytes_, filename="img.png")
```

### Utility Class Methods

- `matches_feed_url(cls, feed_url) → bool` — checks `feed_url` against `auto_enable_url_patterns`
- `get_enabled_variables(cls, registry, enabled_names) → list[str]` — sorted union of `provides_variables` for enabled extensions

---

## Discovery

Extensions are discovered from two sources (external overrides built-in):

1. **Built-in** — `discord_rss_bot/extensions/*.py` (this dir)
2. **External** — `EXTENSIONS_DIR` env var, default `extensions/` relative to CWD

Every `.py` (except `__init__`) is imported. Concrete `FeedExtension` subclasses with a non-empty `name` go into a global `registry: dict[str, type[FeedExtension]]`. Duplicate names log a warning; last one wins.

| Function                           | Description                                      |
| ---------------------------------- | ------------------------------------------------ |
| `discover_plugins(*, force=False)` | Scan dirs, populate registry, return it          |
| `get_registry()`                   | Return current registry (discover on first call) |
| `registry_clear()`                 | Clear registry (for tests)                       |

---

## Auto-Enable

Set `auto_enable_url_patterns` on your class:

```python
auto_enable_url_patterns: ClassVar[list[str]] = [
    r"store\.steampowered\.com",
    r"youtube\.com/feeds/videos\.xml",
]
```

Uses `re.search()` (matches anywhere in URL). Only applies when the feed's extensions tag was never explicitly saved by the user. Runs on feed creation and lazily on first process for old feeds.

---

## Per-Feed Storage

Enabled extensions stored as a JSON list under reader tag key `"extensions"`.

| Function                                                        | Description                  |
| --------------------------------------------------------------- | ---------------------------- |
| `get_enabled_extensions_for_feed(reader, feed_url) → list[str]` | Get enabled names for a feed |
| `set_enabled_extensions_for_feed(reader, feed_url, names)`      | Persist enabled names        |

Web UI: `GET /extensions?feed_url=...` renders checkboxes; `POST /extensions` saves.

---

## Built-in Extensions

| Extension                                      | `name`               | Variables                                                                                                   | Auto-enable                                    |
| ---------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| [youtube.py](youtube.py)                       | `youtube`            | `youtube_video_id`, `youtube_embed_url`                                                                     | `youtube.com/feeds/videos.xml`                 |
| [steam.py](steam.py)                           | `steam`              | `steam_thumbnail_url`, `steam_app_id`                                                                       | `store.steampowered.com`, `steamcommunity.com` |
| [hoyolab.py](hoyolab.py)                       | `hoyolab`            | `hoyolab_subject`, `hoyolab_description`, `hoyolab_image`, `hoyolab_author`                                 | `feeds.c3kay.de`                               |
| [jwplayer_thumbnail.py](jwplayer_thumbnail.py) | `jwplayer_thumbnail` | `jwplayer_thumbnail`, `jwplayer_file`                                                                       | `hentaigasm.com`, `hgasm[0-9]*.com`            |
| [wordpress.py](wordpress.py)                   | `wordpress`          | `wp_content`, `wp_content_raw`, `wp_excerpt`, `wp_excerpt_raw`, `wp_jwplayer_thumbnail`, `wp_jwplayer_file` | _(none)_                                       |
