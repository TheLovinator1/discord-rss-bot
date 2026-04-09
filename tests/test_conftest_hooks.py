from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import tests.conftest as hooks

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_pytest_addoption_registers_real_git_backup_flag() -> None:
    """The hook should register the opt-in flag for real git-backup tests."""
    parser: MagicMock = MagicMock()

    hooks.pytest_addoption(parser)

    parser.addoption.assert_called_once_with(
        "--run-real-git-backup-tests",
        action="store_true",
        default=False,
        help="Run tests that push git backup state to a real repository.",
    )


def test_pytest_sessionstart_initializes_worker_data_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The hook should set worker-scoped state and silence bs4 locator warnings."""
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
    monkeypatch.setattr(hooks.tempfile, "gettempdir", lambda: str(tmp_path))

    filterwarnings_mock: MagicMock = MagicMock()
    monkeypatch.setattr(hooks.warnings, "filterwarnings", filterwarnings_mock)

    hooks.pytest_sessionstart(session=MagicMock())

    expected_dir: Path = tmp_path / "discord-rss-bot-tests" / "gw3"
    assert expected_dir.exists(), f"Expected worker dir to exist: {expected_dir}"
    assert os.environ.get("DISCORD_RSS_BOT_DATA_DIR") == str(expected_dir)
    filterwarnings_mock.assert_any_call("ignore", category=hooks.MarkupResemblesLocatorWarning)


def test_pytest_sessionstart_refreshes_preloaded_settings_and_main_modules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Preloaded modules should be re-pointed to worker-local storage and refreshed."""
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw9")
    monkeypatch.setattr(hooks.tempfile, "gettempdir", lambda: str(tmp_path))

    get_reader: MagicMock = MagicMock()
    get_reader.cache_clear = MagicMock()  # type: ignore[attr-defined]
    close: MagicMock = MagicMock()

    settings_module = SimpleNamespace(data_dir="stale", get_reader=get_reader)
    main_module = SimpleNamespace(reader=SimpleNamespace(close=close))

    monkeypatch.setitem(sys.modules, "discord_rss_bot.settings", settings_module)
    monkeypatch.setitem(sys.modules, "discord_rss_bot.main", main_module)

    hooks.pytest_sessionstart(session=MagicMock())

    expected_dir: Path = tmp_path / "discord-rss-bot-tests" / "gw9"
    assert settings_module.data_dir == str(expected_dir)
    get_reader.cache_clear.assert_called_once()  # type: ignore[attr-defined]
    close.assert_called_once()
    get_reader.assert_called_once()


def test_pytest_sessionstart_suppresses_reader_close_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reader close failures should not prevent rebuilding the main reader."""
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw11")
    monkeypatch.setattr(hooks.tempfile, "gettempdir", lambda: str(tmp_path))

    get_reader: MagicMock = MagicMock()
    settings_module = SimpleNamespace(data_dir="stale", get_reader=get_reader)

    failing_reader = SimpleNamespace(close=MagicMock(side_effect=RuntimeError("close failed")))
    main_module = SimpleNamespace(reader=failing_reader)

    monkeypatch.setitem(sys.modules, "discord_rss_bot.settings", settings_module)
    monkeypatch.setitem(sys.modules, "discord_rss_bot.main", main_module)

    hooks.pytest_sessionstart(session=MagicMock())

    get_reader.assert_called_once()


def test_pytest_collection_modifyitems_noops_when_real_git_backup_tests_enabled() -> None:
    """When the flag is enabled, collection hook should return immediately."""
    config: MagicMock = MagicMock()
    config.getoption.return_value = True

    items: list[MagicMock] = [MagicMock()]
    hooks.pytest_collection_modifyitems(config=config, items=items)

    config.getoption.assert_called_once_with("--run-real-git-backup-tests")
