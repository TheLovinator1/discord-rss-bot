"""Plugin discovery — import ``.py`` files from ``EXTENSIONS_DIR``.

All ``FeedExtension`` subclasses found in those files are collected into
a global registry (``dict[str, type[FeedExtension]]``).
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import types

from discord_rss_bot.extensions.base import FeedExtension

logger: logging.Logger = logging.getLogger(__name__)

#: Environment variable that points to the extensions directory.
ENV_EXTENSIONS_DIR: str = "EXTENSIONS_DIR"

#: Fallback if the env var is not set.
DEFAULT_EXTENSIONS_DIR: str = "extensions"

_registry: dict[str, type[FeedExtension]] = {}
_discovered: bool = False


def _get_extensions_dir() -> Path:
    """Return the path to the extensions directory.

    Respects the ``EXTENSIONS_DIR`` environment variable.  Falls back to
    ``extensions/`` relative to the current working directory.
    """
    raw: str = os.getenv(ENV_EXTENSIONS_DIR, "").strip()
    if raw:
        return Path(raw).resolve()
    return Path.cwd() / DEFAULT_EXTENSIONS_DIR


def _try_import_module(module_name: str, filepath: Path) -> types.ModuleType | None:
    """Create a module spec and execute it, returning the module or ``None``.

    Args:
        module_name: The name to give the imported module.
        filepath: Absolute path to a ``.py`` file.

    Returns:
        The imported module, or ``None`` if the spec could not be created.
    """
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        logger.warning("Could not create module spec for %s", filepath)
        return None

    module = importlib.util.module_from_spec(spec)
    # Make the parent package importable so relative imports in plugins work.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _import_module_from_path(filepath: Path) -> types.ModuleType | None:
    """Import a single ``.py`` file as a module and return the module object.

    Args:
        filepath: Absolute path to a ``.py`` file.

    Returns:
        The imported module, or ``None`` on failure.
    """
    module_name: str = f"_ext_plugin_{filepath.stem}"

    # Avoid re-importing if already loaded.
    if module_name in sys.modules:
        return sys.modules[module_name]

    try:
        return _try_import_module(module_name, filepath)
    except Exception:
        logger.exception("Failed to import extension plugin from %s", filepath)
        return None


def _collect_extensions_from_module(module: types.ModuleType) -> list[type[FeedExtension]]:
    """Return ``FeedExtension`` subclasses defined in *module*.

    Only concrete (non-ABC) subclasses with a non-empty ``name`` are
    returned.

    Args:
        module: An imported module object.

    Returns:
        List of extension classes found in the module.
    """
    extensions: list[type[FeedExtension]] = []
    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        if (
            isinstance(obj, type)
            and issubclass(obj, FeedExtension)
            and obj is not FeedExtension
            and not getattr(obj, "__abstractmethods__", None)
        ):
            name: str = getattr(obj, "name", "") or attr_name
            extensions.append(obj)
            logger.debug("Discovered extension %r (class %s)", name, attr_name)
    return extensions


def _scan_directory(ext_dir: Path) -> None:
    """Scan a single directory and register any ``FeedExtension`` subclasses found."""
    if not ext_dir.is_dir():
        return

    py_files: list[Path] = sorted(p for p in ext_dir.iterdir() if p.suffix == ".py" and p.stem != "__init__")
    for filepath in py_files:
        module = _import_module_from_path(filepath)
        if module is None:
            continue
        classes = _collect_extensions_from_module(module)
        for cls in classes:
            cls_name: str = cls.name or cls.__name__
            if cls_name in _registry:
                logger.warning("Duplicate extension name %r — overwriting with %s", cls_name, filepath)
            _registry[cls_name] = cls


def discover_plugins(*, force: bool = False) -> dict[str, type[FeedExtension]]:
    """Scan built-in and external extension directories and register.

    All ``FeedExtension`` subclasses found in those directories are
    collected into a global registry.

    Order of discovery:
    1. Built-in extensions shipped with the bot (``discord_rss_bot/extensions/``)
    2. External user-provided plugins from ``EXTENSIONS_DIR``

    External plugins can override built-in ones by using the same ``name``.
    This is called automatically on first import.  Call with
    ``force=True`` to re-scan (useful in tests).

    Args:
        force: If ``True``, re-scan even if already discovered.

    Returns:
        The global registry ``{name: class}``.
    """
    global _discovered  # ruff:ignore[global-statement]
    if _discovered and not force:
        return _registry

    # 1. Scan the built-in package directory first.
    built_in_dir: Path = Path(__file__).resolve().parent
    logger.debug("Scanning built-in extensions directory: %s", built_in_dir)
    _scan_directory(built_in_dir)

    # 2. Scan the external user-provided extensions directory.
    ext_dir: Path = _get_extensions_dir()
    if ext_dir != built_in_dir:
        logger.info("Scanning external extensions directory: %s", ext_dir)
        _scan_directory(ext_dir)
    else:
        logger.debug("External extensions directory is the same as built-in — skipping duplicate scan")

    _discovered = True
    logger.info("Discovered %d extension plugin(s): %s", len(_registry), list(_registry.keys()))
    return _registry


def get_registry() -> dict[str, type[FeedExtension]]:
    """Return the current extension registry, discovering plugins if needed.

    Returns:
        The global registry ``{name: class}``.
    """
    if not _discovered:
        return discover_plugins()
    return _registry


def registry_clear() -> None:
    """Clear the registry (useful for testing)."""
    global _discovered, _registry  # ruff:ignore[global-statement]
    _registry = {}
    _discovered = False
