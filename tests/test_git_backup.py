from __future__ import annotations

import contextlib
import json
import shutil
import subprocess  # noqa: S404
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from discord_rss_bot.git_backup import commit_state_change
from discord_rss_bot.git_backup import export_state
from discord_rss_bot.git_backup import get_backup_path
from discord_rss_bot.git_backup import get_backup_remote
from discord_rss_bot.git_backup import setup_backup_repo
from discord_rss_bot.main import app

if TYPE_CHECKING:
    from pathlib import Path


SKIP_IF_NO_GIT: pytest.MarkDecorator = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git executable not found",
)


def test_get_backup_path_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_backup_path returns None when GIT_BACKUP_PATH is not set."""
    monkeypatch.delenv("GIT_BACKUP_PATH", raising=False)
    assert get_backup_path() is None


def test_get_backup_path_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """get_backup_path returns a Path when GIT_BACKUP_PATH is set."""
    monkeypatch.setenv("GIT_BACKUP_PATH", str(tmp_path))
    result: Path | None = get_backup_path()
    assert result == tmp_path


def test_get_backup_path_strips_whitespace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """get_backup_path strips surrounding whitespace from the env var value."""
    monkeypatch.setenv("GIT_BACKUP_PATH", f"  {tmp_path}  ")
    result: Path | None = get_backup_path()
    assert result == tmp_path


def test_get_backup_remote_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_backup_remote returns empty string when GIT_BACKUP_REMOTE is not set."""
    monkeypatch.delenv("GIT_BACKUP_REMOTE", raising=False)
    assert not get_backup_remote()


def test_get_backup_remote_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_backup_remote returns the configured remote URL."""
    monkeypatch.setenv("GIT_BACKUP_REMOTE", "git@github.com:user/repo.git")
    assert get_backup_remote() == "git@github.com:user/repo.git"


@SKIP_IF_NO_GIT
def test_setup_backup_repo_creates_git_repo(tmp_path: Path) -> None:
    """setup_backup_repo initialises a git repo in a fresh directory."""
    backup_path: Path = tmp_path / "backup"
    result: bool = setup_backup_repo(backup_path)
    assert result is True
    assert (backup_path / ".git").exists()


@SKIP_IF_NO_GIT
def test_setup_backup_repo_idempotent(tmp_path: Path) -> None:
    """setup_backup_repo does not fail when called on an existing repo."""
    backup_path: Path = tmp_path / "backup"
    assert setup_backup_repo(backup_path) is True
    assert setup_backup_repo(backup_path) is True


def test_setup_backup_repo_adds_origin_remote(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """setup_backup_repo adds remote 'origin' when GIT_BACKUP_REMOTE is set."""
    backup_path: Path = tmp_path / "backup"
    monkeypatch.setenv("GIT_BACKUP_REMOTE", "git@github.com:user/private.git")

    with patch("discord_rss_bot.git_backup.subprocess.run") as mock_run:
        # git config --local queries fail initially so setup writes defaults.
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git init
            MagicMock(returncode=1),  # config user.email read
            MagicMock(returncode=0),  # config user.email write
            MagicMock(returncode=1),  # config user.name read
            MagicMock(returncode=0),  # config user.name write
            MagicMock(returncode=1),  # remote get-url origin (missing)
            MagicMock(returncode=0),  # remote add origin <url>
        ]

        assert setup_backup_repo(backup_path) is True

    called_commands: list[list[str]] = [call.args[0] for call in mock_run.call_args_list]
    assert ["remote", "add", "origin", "git@github.com:user/private.git"] in [
        cmd[-4:] for cmd in called_commands if len(cmd) >= 4
    ]


def test_setup_backup_repo_updates_origin_remote(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """setup_backup_repo updates existing origin when URL differs."""
    backup_path: Path = tmp_path / "backup"
    monkeypatch.setenv("GIT_BACKUP_REMOTE", "git@github.com:user/new-private.git")

    with patch("discord_rss_bot.git_backup.subprocess.run") as mock_run:
        # Existing repo path: no git init call.
        (backup_path / ".git").mkdir(parents=True)

        mock_run.side_effect = [
            MagicMock(returncode=0),  # config user.email read
            MagicMock(returncode=0),  # config user.name read
            MagicMock(returncode=0, stdout=b"git@github.com:user/old-private.git\n"),  # remote get-url origin
            MagicMock(returncode=0),  # remote set-url origin <new>
        ]

        assert setup_backup_repo(backup_path) is True

    called_commands: list[list[str]] = [call.args[0] for call in mock_run.call_args_list]
    assert ["remote", "set-url", "origin", "git@github.com:user/new-private.git"] in [
        cmd[-4:] for cmd in called_commands if len(cmd) >= 4
    ]


def test_export_state_creates_state_json(tmp_path: Path) -> None:
    """export_state writes a valid state.json to the backup directory."""
    mock_reader = MagicMock()

    # Feeds
    feed1 = MagicMock()
    feed1.url = "https://example.com/feed.rss"
    mock_reader.get_feeds.return_value = [feed1]

    # Tag values: webhook present, everything else absent (returns None)
    def get_tag_side_effect(
        feed_or_key: tuple | str,
        tag: str | None = None,
        default: str | None = None,
    ) -> list[Any] | str | None:
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

    data: dict[str, Any] = json.loads(state_file.read_text(encoding="utf-8"))
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

    def get_tag_side_effect(
        feed_or_key: tuple | str,
        tag: str | None = None,
        default: str | None = None,
    ) -> list[Any] | str | None:
        if feed_or_key == ():
            return []

        # Return empty string for all tags
        return default  # default is None

    mock_reader.get_tag.side_effect = get_tag_side_effect

    backup_path: Path = tmp_path / "backup"
    backup_path.mkdir()
    export_state(mock_reader, backup_path)

    data: dict[str, Any] = json.loads((backup_path / "state.json").read_text())

    # Only "url" key should be present (no empty-value tags)
    assert list(data["feeds"][0].keys()) == ["url"]


def test_commit_state_change_noop_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """commit_state_change does nothing when GIT_BACKUP_PATH is not set."""
    monkeypatch.delenv("GIT_BACKUP_PATH", raising=False)
    mock_reader = MagicMock()

    # Should not raise and should not call reader methods for export
    commit_state_change(mock_reader, "Add feed example.com/rss")
    mock_reader.get_feeds.assert_not_called()


@SKIP_IF_NO_GIT
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
    git_executable: str | None = shutil.which("git")

    assert git_executable is not None, "git executable not found"
    result: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603
        [git_executable, "-C", str(backup_path), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Add feed https://example.com/rss" in result.stdout


@SKIP_IF_NO_GIT
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

    git_executable: str | None = shutil.which("git")
    assert git_executable is not None, "git executable not found"
    result: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603
        [git_executable, "-C", str(backup_path), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=False,
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

    called_commands: list[list[str]] = [call.args[0] for call in mock_run.call_args_list]
    push_calls: list[list[str]] = [cmd for cmd in called_commands if "push" in cmd]
    assert push_calls, "git push should have been called when GIT_BACKUP_REMOTE is set"
    assert any(cmd[-3:] == ["push", "origin", "HEAD"] for cmd in called_commands), (
        "git push should target configured remote name 'origin'"
    )


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

    called_commands: list[list[str]] = [call.args[0] for call in mock_run.call_args_list]
    push_calls: list[list[str]] = [cmd for cmd in called_commands if "push" in cmd]
    assert not push_calls, "git push should NOT be called when GIT_BACKUP_REMOTE is not set"


client: TestClient = TestClient(app)
test_webhook_name: str = "Test Backup Webhook"
test_webhook_url: str = "https://discord.com/api/webhooks/999999999/testbackupwebhook"
test_feed_url: str = "https://lovinator.space/rss_test.xml"


def setup_test_feed() -> None:
    """Set up a test webhook and feed for endpoint tests."""
    # Clean up existing test data
    with contextlib.suppress(Exception):
        client.post(url="/remove", data={"feed_url": test_feed_url})

    with contextlib.suppress(Exception):
        client.post(url="/delete_webhook", data={"webhook_url": test_webhook_url})

    # Create webhook and feed
    client.post(
        url="/add_webhook",
        data={"webhook_name": test_webhook_name, "webhook_url": test_webhook_url},
    )
    client.post(url="/add", data={"feed_url": test_feed_url, "webhook_dropdown": test_webhook_name})


def test_post_embed_triggers_backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Posting to /embed should trigger a git backup with appropriate message."""
    # Set up git backup
    backup_path: Path = tmp_path / "backup"
    monkeypatch.setenv("GIT_BACKUP_PATH", str(backup_path))
    monkeypatch.delenv("GIT_BACKUP_REMOTE", raising=False)

    setup_test_feed()

    with patch("discord_rss_bot.main.commit_state_change") as mock_commit:
        response = client.post(
            url="/embed",
            data={
                "feed_url": test_feed_url,
                "title": "Custom Title",
                "description": "Custom Description",
                "color": "#FF5733",
            },
        )
        assert response.status_code == 200, f"Failed to post embed: {response.text}"
        mock_commit.assert_called_once()

        # Verify the commit message contains the feed URL
        call_args = mock_commit.call_args
        assert call_args is not None
        commit_message: str = call_args[0][1]
        assert "Update embed settings" in commit_message
        assert test_feed_url in commit_message


def test_post_use_embed_triggers_backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Posting to /use_embed should trigger a git backup."""
    backup_path: Path = tmp_path / "backup"
    monkeypatch.setenv("GIT_BACKUP_PATH", str(backup_path))
    monkeypatch.delenv("GIT_BACKUP_REMOTE", raising=False)

    setup_test_feed()

    with patch("discord_rss_bot.main.commit_state_change") as mock_commit:
        response = client.post(url="/use_embed", data={"feed_url": test_feed_url})
        assert response.status_code == 200, f"Failed to enable embed: {response.text}"
        mock_commit.assert_called_once()

        # Verify the commit message
        call_args = mock_commit.call_args
        assert call_args is not None
        commit_message: str = call_args[0][1]
        assert "Enable embed mode" in commit_message
        assert test_feed_url in commit_message


def test_post_use_text_triggers_backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Posting to /use_text should trigger a git backup."""
    backup_path: Path = tmp_path / "backup"
    monkeypatch.setenv("GIT_BACKUP_PATH", str(backup_path))
    monkeypatch.delenv("GIT_BACKUP_REMOTE", raising=False)

    setup_test_feed()

    with patch("discord_rss_bot.main.commit_state_change") as mock_commit:
        response = client.post(url="/use_text", data={"feed_url": test_feed_url})
        assert response.status_code == 200, f"Failed to disable embed: {response.text}"
        mock_commit.assert_called_once()

        # Verify the commit message
        call_args = mock_commit.call_args
        assert call_args is not None
        commit_message: str = call_args[0][1]
        assert "Disable embed mode" in commit_message
        assert test_feed_url in commit_message


def test_post_custom_message_triggers_backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Posting to /custom should trigger a git backup."""
    backup_path: Path = tmp_path / "backup"
    monkeypatch.setenv("GIT_BACKUP_PATH", str(backup_path))
    monkeypatch.delenv("GIT_BACKUP_REMOTE", raising=False)

    setup_test_feed()

    with patch("discord_rss_bot.main.commit_state_change") as mock_commit:
        response = client.post(
            url="/custom",
            data={
                "feed_url": test_feed_url,
                "custom_message": "Check out this entry: {entry.title}",
            },
        )
        assert response.status_code == 200, f"Failed to set custom message: {response.text}"
        mock_commit.assert_called_once()

        # Verify the commit message
        call_args = mock_commit.call_args
        assert call_args is not None
        commit_message: str = call_args[0][1]
        assert "Update custom message" in commit_message
        assert test_feed_url in commit_message


@SKIP_IF_NO_GIT
def test_embed_backup_end_to_end(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """End-to-end test: customizing embed creates a real commit in the backup repo."""
    git_executable: str | None = shutil.which("git")
    assert git_executable is not None, "git executable not found"

    backup_path: Path = tmp_path / "backup"
    monkeypatch.setenv("GIT_BACKUP_PATH", str(backup_path))
    monkeypatch.delenv("GIT_BACKUP_REMOTE", raising=False)

    setup_test_feed()

    # Post embed customization
    response = client.post(
        url="/embed",
        data={
            "feed_url": test_feed_url,
            "title": "{entry.title}",
            "description": "{entry.summary}",
            "color": "#0099FF",
            "image_url": "{entry.image}",
        },
    )
    assert response.status_code == 200, f"Failed to customize embed: {response.text}"

    # Verify a commit was created
    result: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603
        [git_executable, "-C", str(backup_path), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Failed to read git log: {result.stderr}"
    assert "Update embed settings" in result.stdout, f"Commit not found in log: {result.stdout}"

    # Verify state.json contains embed data
    state_file: Path = backup_path / "state.json"
    assert state_file.exists(), "state.json should exist in backup repo"
    state_data: dict[str, Any] = json.loads(state_file.read_text(encoding="utf-8"))

    # Find our test feed in the state
    test_feed_data = next((feed for feed in state_data["feeds"] if feed["url"] == test_feed_url), None)
    assert test_feed_data is not None, f"Test feed not found in state.json: {state_data}"

    # The embed settings are stored as a nested dict under custom_embed tag
    # This verifies the embed customization was persisted
    assert "webhook" in test_feed_data, "Feed should have webhook set"
