from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from discord_rss_bot.git_backup import (
    commit_state_change,
    export_state,
    get_backup_path,
    get_backup_remote,
    setup_backup_repo,
)


def test_get_backup_path_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_backup_path returns None when GIT_BACKUP_PATH is not set."""
    monkeypatch.delenv("GIT_BACKUP_PATH", raising=False)
    assert get_backup_path() is None


def test_get_backup_path_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """get_backup_path returns a Path when GIT_BACKUP_PATH is set."""
    monkeypatch.setenv("GIT_BACKUP_PATH", str(tmp_path))
    result = get_backup_path()
    assert result == tmp_path


def test_get_backup_path_strips_whitespace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """get_backup_path strips surrounding whitespace from the env var value."""
    monkeypatch.setenv("GIT_BACKUP_PATH", f"  {tmp_path}  ")
    result = get_backup_path()
    assert result == tmp_path


def test_get_backup_remote_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_backup_remote returns empty string when GIT_BACKUP_REMOTE is not set."""
    monkeypatch.delenv("GIT_BACKUP_REMOTE", raising=False)
    assert get_backup_remote() == ""


def test_get_backup_remote_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_backup_remote returns the configured remote URL."""
    monkeypatch.setenv("GIT_BACKUP_REMOTE", "git@github.com:user/repo.git")
    assert get_backup_remote() == "git@github.com:user/repo.git"


def test_setup_backup_repo_creates_git_repo(tmp_path: Path) -> None:
    """setup_backup_repo initialises a git repo in a fresh directory."""
    backup_path: Path = tmp_path / "backup"
    result = setup_backup_repo(backup_path)
    assert result is True
    assert (backup_path / ".git").exists()


def test_setup_backup_repo_idempotent(tmp_path: Path) -> None:
    """setup_backup_repo does not fail when called on an existing repo."""
    backup_path: Path = tmp_path / "backup"
    assert setup_backup_repo(backup_path) is True
    assert setup_backup_repo(backup_path) is True


def test_export_state_creates_state_json(tmp_path: Path) -> None:
    """export_state writes a valid state.json to the backup directory."""
    mock_reader = MagicMock()

    # Feeds
    feed1 = MagicMock()
    feed1.url = "https://example.com/feed.rss"
    mock_reader.get_feeds.return_value = [feed1]

    # Tag values: webhook present, everything else absent (returns None)
    def get_tag_side_effect(feed_or_key, tag=None, default=None):  # noqa: ARG001
        if feed_or_key == () and tag is None:
            # Called for global webhooks list
            return []
        if tag == "webhook":
            return "https://discord.com/api/webhooks/123/abc"
        return default

    mock_reader.get_tag.side_effect = get_tag_side_effect

    backup_path: Path = tmp_path / "backup"
    backup_path.mkdir()
    export_state(mock_reader, backup_path)

    state_file: Path = backup_path / "state.json"
    assert state_file.exists(), "state.json should be created by export_state"

    data = json.loads(state_file.read_text())
    assert "feeds" in data
    assert "webhooks" in data
    assert data["feeds"][0]["url"] == "https://example.com/feed.rss"
    assert data["feeds"][0]["webhook"] == "https://discord.com/api/webhooks/123/abc"


def test_export_state_omits_empty_tags(tmp_path: Path) -> None:
    """export_state does not include tags with empty-string or None values."""
    mock_reader = MagicMock()
    feed1 = MagicMock()
    feed1.url = "https://example.com/feed.rss"
    mock_reader.get_feeds.return_value = [feed1]

    def get_tag_side_effect(feed_or_key, tag=None, default=None):  # noqa: ARG001
        if feed_or_key == ():
            return []
        # Return empty string for all tags
        return default  # default is None

    mock_reader.get_tag.side_effect = get_tag_side_effect

    backup_path: Path = tmp_path / "backup"
    backup_path.mkdir()
    export_state(mock_reader, backup_path)

    data = json.loads((backup_path / "state.json").read_text())
    # Only "url" key should be present (no empty-value tags)
    assert list(data["feeds"][0].keys()) == ["url"]


def test_commit_state_change_noop_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """commit_state_change does nothing when GIT_BACKUP_PATH is not set."""
    monkeypatch.delenv("GIT_BACKUP_PATH", raising=False)
    mock_reader = MagicMock()
    # Should not raise and should not call reader methods for export
    commit_state_change(mock_reader, "Add feed example.com/rss")
    mock_reader.get_feeds.assert_not_called()


def test_commit_state_change_commits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """commit_state_change creates a commit in the backup repo."""
    backup_path: Path = tmp_path / "backup"
    monkeypatch.setenv("GIT_BACKUP_PATH", str(backup_path))
    monkeypatch.delenv("GIT_BACKUP_REMOTE", raising=False)

    mock_reader = MagicMock()
    mock_reader.get_feeds.return_value = []
    mock_reader.get_tag.return_value = []

    commit_state_change(mock_reader, "Add feed https://example.com/rss")

    # Verify a commit was created in the backup repo
    result = subprocess.run(
        ["git", "-C", str(backup_path), "log", "--oneline"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Add feed https://example.com/rss" in result.stdout


def test_commit_state_change_no_double_commit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """commit_state_change does not create a commit when state has not changed."""
    backup_path: Path = tmp_path / "backup"
    monkeypatch.setenv("GIT_BACKUP_PATH", str(backup_path))
    monkeypatch.delenv("GIT_BACKUP_REMOTE", raising=False)

    mock_reader = MagicMock()
    mock_reader.get_feeds.return_value = []
    mock_reader.get_tag.return_value = []

    commit_state_change(mock_reader, "First commit")
    commit_state_change(mock_reader, "Should not appear")

    result = subprocess.run(
        ["git", "-C", str(backup_path), "log", "--oneline"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "First commit" in result.stdout
    assert "Should not appear" not in result.stdout


def test_commit_state_change_push_when_remote_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """commit_state_change calls git push when GIT_BACKUP_REMOTE is configured."""
    backup_path: Path = tmp_path / "backup"
    monkeypatch.setenv("GIT_BACKUP_PATH", str(backup_path))
    monkeypatch.setenv("GIT_BACKUP_REMOTE", "git@github.com:user/private.git")

    mock_reader = MagicMock()
    mock_reader.get_feeds.return_value = []
    mock_reader.get_tag.return_value = []

    with patch("discord_rss_bot.git_backup.subprocess.run") as mock_run:
        # Make all subprocess calls succeed
        mock_run.return_value = MagicMock(returncode=1)  # returncode=1 means staged changes exist
        commit_state_change(mock_reader, "Add feed https://example.com/rss")

    called_commands = [call.args[0] for call in mock_run.call_args_list]
    push_calls = [cmd for cmd in called_commands if "push" in cmd]
    assert push_calls, "git push should have been called when GIT_BACKUP_REMOTE is set"


def test_commit_state_change_no_push_when_remote_unset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """commit_state_change does not call git push when GIT_BACKUP_REMOTE is not set."""
    backup_path: Path = tmp_path / "backup"
    monkeypatch.setenv("GIT_BACKUP_PATH", str(backup_path))
    monkeypatch.delenv("GIT_BACKUP_REMOTE", raising=False)

    mock_reader = MagicMock()
    mock_reader.get_feeds.return_value = []
    mock_reader.get_tag.return_value = []

    with patch("discord_rss_bot.git_backup.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        commit_state_change(mock_reader, "Add feed https://example.com/rss")

    called_commands = [call.args[0] for call in mock_run.call_args_list]
    push_calls = [cmd for cmd in called_commands if "push" in cmd]
    assert not push_calls, "git push should NOT be called when GIT_BACKUP_REMOTE is not set"
