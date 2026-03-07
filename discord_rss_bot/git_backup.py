"""Git backup module for committing bot state changes to a private repository.

Configure the backup by setting these environment variables:
- ``GIT_BACKUP_PATH``: Local filesystem path for the backup git repository.
  When set, the bot will initialise a git repo there (if one doesn't exist)
  and commit an export of its state after every relevant change.
- ``GIT_BACKUP_REMOTE``: Optional remote URL (e.g. ``git@github.com:you/private-repo.git``).
  When set, every commit is followed by a ``git push`` to this remote.

The exported state is written as ``state.json`` inside the backup repo.  It
contains the list of feeds together with their webhook URL, filter settings
(blacklist / whitelist, regex variants), custom messages and embed settings.
Global webhooks are also included.

Example docker-compose snippet::

    environment:
      - GIT_BACKUP_PATH=/data/backup
      - GIT_BACKUP_REMOTE=git@github.com:you/private-config.git
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess  # noqa: S404
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from reader import TagNotFoundError

if TYPE_CHECKING:
    from reader import Reader

logger: logging.Logger = logging.getLogger(__name__)
GIT_EXECUTABLE: str = shutil.which("git") or "git"


type TAG_VALUE = (
    dict[str, str | int | float | bool | dict[str, Any] | list[Any] | None]
    | list[str | int | float | bool | dict[str, Any] | list[Any] | None]
    | None
)

# Tags that are exported per-feed (empty values are omitted).
_FEED_TAGS: tuple[str, ...] = (
    "webhook",
    "custom_message",
    "should_send_embed",
    "embed",
    "blacklist_title",
    "blacklist_summary",
    "blacklist_content",
    "blacklist_author",
    "regex_blacklist_title",
    "regex_blacklist_summary",
    "regex_blacklist_content",
    "regex_blacklist_author",
    "whitelist_title",
    "whitelist_summary",
    "whitelist_content",
    "whitelist_author",
    "regex_whitelist_title",
    "regex_whitelist_summary",
    "regex_whitelist_content",
    "regex_whitelist_author",
    ".reader.update",
)


def get_backup_path() -> Path | None:
    """Return the configured backup path, or *None* if not configured.

    Returns:
        Path to the backup repository, or None if ``GIT_BACKUP_PATH`` is unset.
    """
    raw: str = os.environ.get("GIT_BACKUP_PATH", "").strip()
    return Path(raw) if raw else None


def get_backup_remote() -> str:
    """Return the configured remote URL, or an empty string if not set.

    Returns:
        The remote URL string from ``GIT_BACKUP_REMOTE``, or ``""`` if unset.
    """
    return os.environ.get("GIT_BACKUP_REMOTE", "").strip()


def setup_backup_repo(backup_path: Path) -> bool:
    """Ensure the backup directory exists and contains a git repository.

    If the directory does not yet contain a ``.git`` folder a new repository is
    initialised.  A basic git identity is configured locally so that commits
    succeed even in environments where a global ``~/.gitconfig`` is absent.

    Args:
        backup_path: Local path for the backup repository.

    Returns:
        ``True`` if the repository is ready, ``False`` on any error.
    """
    try:
        backup_path.mkdir(parents=True, exist_ok=True)
        git_dir: Path = backup_path / ".git"
        if not git_dir.exists():
            subprocess.run([GIT_EXECUTABLE, "init", str(backup_path)], check=True, capture_output=True)  # noqa: S603
            logger.info("Initialised git backup repository at %s", backup_path)

        # Ensure a local identity exists so that `git commit` always works.
        for key, value in (("user.email", "discord-rss-bot@localhost"), ("user.name", "discord-rss-bot")):
            result: subprocess.CompletedProcess[bytes] = subprocess.run(  # noqa: S603
                [GIT_EXECUTABLE, "-C", str(backup_path), "config", "--local", key],
                check=False,
                capture_output=True,
            )
            if result.returncode != 0:
                subprocess.run(  # noqa: S603
                    [GIT_EXECUTABLE, "-C", str(backup_path), "config", "--local", key, value],
                    check=True,
                    capture_output=True,
                )

        # Configure the remote if GIT_BACKUP_REMOTE is set.
        remote_url: str = get_backup_remote()
        if remote_url:
            # Check if remote "origin" already exists.
            check_remote: subprocess.CompletedProcess[bytes] = subprocess.run(  # noqa: S603
                [GIT_EXECUTABLE, "-C", str(backup_path), "remote", "get-url", "origin"],
                check=False,
                capture_output=True,
            )
            if check_remote.returncode != 0:
                # Remote doesn't exist, add it.
                subprocess.run(  # noqa: S603
                    [GIT_EXECUTABLE, "-C", str(backup_path), "remote", "add", "origin", remote_url],
                    check=True,
                    capture_output=True,
                )
                logger.info("Added remote 'origin' with URL: %s", remote_url)
            else:
                # Remote exists, update it if the URL has changed.
                current_url: str = check_remote.stdout.decode().strip()
                if current_url != remote_url:
                    subprocess.run(  # noqa: S603
                        [GIT_EXECUTABLE, "-C", str(backup_path), "remote", "set-url", "origin", remote_url],
                        check=True,
                        capture_output=True,
                    )
                    logger.info("Updated remote 'origin' URL from %s to %s", current_url, remote_url)
    except Exception:
        logger.exception("Failed to set up git backup repository at %s", backup_path)
        return False
    return True


def export_state(reader: Reader, backup_path: Path) -> None:
    """Serialise the current bot state to ``state.json`` inside *backup_path*.

    Args:
        reader: The :class:`reader.Reader` instance to read state from.
        backup_path: Destination directory for the exported ``state.json``.
    """
    feeds_state: list[dict] = []
    for feed in reader.get_feeds():
        feed_data: dict = {"url": feed.url}
        for tag in _FEED_TAGS:
            try:
                value: TAG_VALUE = reader.get_tag(feed, tag, None)
                if value is not None and value != "":  # noqa: PLC1901
                    feed_data[tag] = value
            except Exception:
                logger.exception("Failed to read tag '%s' for feed '%s' during state export", tag, feed.url)
        feeds_state.append(feed_data)

    try:
        webhooks: list[str | int | float | bool | dict[str, Any] | list[Any] | None] = list(
            reader.get_tag((), "webhooks", []),
        )
    except TagNotFoundError:
        webhooks = []

    # Export global update interval if set
    global_update_interval: dict[str, Any] | None = None
    try:
        global_update_config = reader.get_tag((), ".reader.update", None)
        if isinstance(global_update_config, dict):
            global_update_interval = global_update_config
    except TagNotFoundError:
        pass

    state: dict = {"feeds": feeds_state, "webhooks": webhooks}
    if global_update_interval is not None:
        state["global_update_interval"] = global_update_interval
    state_file: Path = backup_path / "state.json"
    state_file.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def commit_state_change(reader: Reader, message: str) -> None:
    """Export current state and commit it to the backup repository.

    This is a no-op when ``GIT_BACKUP_PATH`` is not configured.  Errors are
    logged but never raised so that a backup failure never interrupts normal
    bot operation.

    Args:
        reader: The :class:`reader.Reader` instance to read state from.
        message: Commit message describing the change (e.g. ``"Add feed example.com/rss.xml"``).
    """
    backup_path: Path | None = get_backup_path()
    if backup_path is None:
        return

    if not setup_backup_repo(backup_path):
        return

    try:
        export_state(reader, backup_path)

        subprocess.run([GIT_EXECUTABLE, "-C", str(backup_path), "add", "-A"], check=True, capture_output=True)  # noqa: S603

        # Only create a commit if there are staged changes.
        diff_result: subprocess.CompletedProcess[bytes] = subprocess.run(  # noqa: S603
            [GIT_EXECUTABLE, "-C", str(backup_path), "diff", "--cached", "--exit-code"],
            check=False,
            capture_output=True,
        )
        if diff_result.returncode == 0:
            logger.debug("No state changes to commit for: %s", message)
            return

        subprocess.run(  # noqa: S603
            [GIT_EXECUTABLE, "-C", str(backup_path), "commit", "-m", message],
            check=True,
            capture_output=True,
        )
        logger.info("Committed state change to backup repo: %s", message)

        # Push to remote if configured.
        if get_backup_remote():
            subprocess.run(  # noqa: S603
                [GIT_EXECUTABLE, "-C", str(backup_path), "push", "origin", "HEAD"],
                check=True,
                capture_output=True,
            )
            logger.info("Pushed state change to remote 'origin': %s", message)
    except Exception:
        logger.exception("Failed to commit state change '%s' to backup repo", message)
