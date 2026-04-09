from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests

from discord_rss_bot.healthcheck import healthcheck


def test_healthcheck_success() -> None:
    """Test that healthcheck exits with 0 when the website is up."""
    mock_response = MagicMock()
    mock_response.ok = True

    with (
        patch("discord_rss_bot.healthcheck.requests.get", return_value=mock_response),
        pytest.raises(SystemExit) as exc_info,
    ):
        healthcheck()

    assert exc_info.value.code == 0


def test_healthcheck_not_ok() -> None:
    """Test that healthcheck exits with 1 when the response is not ok."""
    mock_response = MagicMock()
    mock_response.ok = False

    with (
        patch("discord_rss_bot.healthcheck.requests.get", return_value=mock_response),
        pytest.raises(SystemExit) as exc_info,
    ):
        healthcheck()

    assert exc_info.value.code == 1


def test_healthcheck_request_exception(capsys: pytest.CaptureFixture) -> None:
    """Test that healthcheck exits with 1 on a request exception."""
    with (
        patch(
            "discord_rss_bot.healthcheck.requests.get",
            side_effect=requests.exceptions.ConnectionError("Connection refused"),
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        healthcheck()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Healthcheck failed" in captured.err


def test_healthcheck_timeout(capsys: pytest.CaptureFixture) -> None:
    """Test that healthcheck exits with 1 on a timeout."""
    with (
        patch(
            "discord_rss_bot.healthcheck.requests.get",
            side_effect=requests.exceptions.Timeout("Request timed out"),
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        healthcheck()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Healthcheck failed" in captured.err
