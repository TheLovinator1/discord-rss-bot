import os

from discord_rss_bot.main import app
from discord_rss_bot.settings import Settings
from typer.testing import CliRunner

runner = CliRunner()


def test_stats():
    result = runner.invoke(app, "stats")
    assert result.exit_code == 0
    assert "Average number of entries per day:" in result.stdout


def test_check():
    result = runner.invoke(app, "check")
    assert result.exit_code == 0


def test_backup():
    # Where we store backups
    backup_dir = os.path.join(Settings.app_dir, "backup")

    # Check how many files in the backup directory
    files_before = len(os.listdir(backup_dir))

    # Run the backup command
    result = runner.invoke(app, "backup")

    # Check how many files in the backup directory after the backup
    files_after = len(os.listdir(backup_dir))

    # Check if the exit code is 0 and if we got one file more
    assert result.exit_code == 0
    assert files_after == files_before + 1


def test_add():
    result = runner.invoke(app, "add https://www.reddit.com/r/Games/new/.rss")

    # Check if the exit code is 0 and if the output contains the word "added" or "already"
    assert result.exit_code == 0
    assert "added" or "already" in result.stdout


def test_delete():
    # https://typer.tiangolo.com/tutorial/testing/#testing-input
    result = runner.invoke(app, "delete", input="1\nY\n")

    # Check if the exit code is 0 and if the output contains the word "deleted"
    assert result.exit_code == 0
    assert "deleted" in result.stdout
