"""Drop-in plugin support.

A *plugin* is a single ``.py`` file that defines a subclass of
:class:`FinSightPlugin`. At startup the registry scans two folders and
mounts whatever it finds into the sidebar — no edits to the core:

* the built-in package ``finsight/plugins/`` (ships with the app);
* a user folder ``%LOCALAPPDATA%/FinSight/plugins/`` (drop files here,
  no reinstall).

Discovery is deliberately defensive: a plugin that raises on import
(missing dependency, syntax error, bad metadata) is logged and skipped,
never crashing the app. The core stays UI-free — a plugin's
``create_page`` returns a CustomTkinter frame, but that method is only
ever *called* by the UI layer, so this module imports no UI code.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import pkgutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BUILTIN_PACKAGE = "finsight.plugins"


class FinSightPlugin(ABC):
    """Base class for a drop-in FinSight feature.

    Subclass it, set the four metadata attributes, and implement
    :meth:`create_page`. Example::

        import customtkinter as ctk
        from finsight.core.plugins import FinSightPlugin

        class HelloPlugin(FinSightPlugin):
            id = "hello"
            title = "Hello"
            icon = "☺"
            order = 500

            def create_page(self, parent, app):
                frame = ctk.CTkFrame(parent, fg_color="transparent")
                ctk.CTkLabel(frame, text="Hello from a plugin!").pack()
                return frame
    """

    #: Unique, identifier-safe id (also the sidebar route). Required.
    id: str = ""
    #: Human-readable sidebar label. Required.
    title: str = ""
    #: Single glyph shown in the sidebar (keeps the UI dependency-free).
    icon: str = "◈"
    #: Sort order; built-ins use 10–100, so plugins default after them.
    order: int = 500

    @abstractmethod
    def create_page(self, parent: Any, app: Any) -> Any:
        """Build and return the plugin's page as a CustomTkinter frame.

        Called lazily the first time the user opens the plugin. ``app`` is
        the running :class:`FinSightApp` (use ``app.context`` for services,
        ``app.toast`` for status, ``app.context.runner`` for threads).
        """
        raise NotImplementedError

    def validate(self) -> None:
        """Raise ``ValueError`` if the metadata is unusable."""
        if not isinstance(self.id, str) or not self.id.isidentifier():
            raise ValueError(f"plugin id must be a valid identifier, got {self.id!r}")
        if not self.title:
            raise ValueError(f"plugin {self.id!r} needs a non-empty title")
        if not isinstance(self.icon, str) or len(self.icon) == 0:
            raise ValueError(f"plugin {self.id!r} needs an icon glyph")


@dataclass
class DiscoveryResult:
    """Outcome of a plugin scan: what loaded, and what failed and why."""

    plugins: list[FinSightPlugin] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (source, message)


def builtin_plugins_dir() -> Path:
    """Filesystem folder backing the built-in ``finsight.plugins`` package."""
    return Path(__file__).resolve().parent.parent / "plugins"


def _plugin_classes(module: Any) -> list[type[FinSightPlugin]]:
    """Concrete FinSightPlugin subclasses *defined in* ``module``."""
    found: list[type[FinSightPlugin]] = []
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if (
            issubclass(obj, FinSightPlugin)
            and obj is not FinSightPlugin
            and obj.__module__ == module.__name__
            and not inspect.isabstract(obj)
        ):
            found.append(obj)
    return found


def _instantiate(cls: type[FinSightPlugin], source: str, result: DiscoveryResult) -> None:
    try:
        plugin = cls()
        plugin.validate()
    except Exception as exc:  # a broken plugin must not sink the others
        logger.warning("skipping plugin %s from %s: %s", cls.__name__, source, exc)
        result.errors.append((source, f"{cls.__name__}: {exc}"))
        return
    if any(p.id == plugin.id for p in result.plugins):
        logger.warning("duplicate plugin id %r from %s — keeping the first", plugin.id, source)
        result.errors.append((source, f"duplicate id {plugin.id!r} ignored"))
        return
    result.plugins.append(plugin)
    logger.info("loaded plugin %r (%s) from %s", plugin.id, plugin.title, source)


def _load_package_module(stem: str, result: DiscoveryResult) -> None:
    name = f"{BUILTIN_PACKAGE}.{stem}"
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        logger.warning("failed to import built-in plugin %s: %s", name, exc)
        result.errors.append((name, str(exc)))
        return
    for cls in _plugin_classes(module):
        _instantiate(cls, name, result)


def _load_file_module(path: Path, result: DiscoveryResult) -> None:
    mod_name = f"finsight_user_plugin_{path.stem}"
    try:
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not create import spec for {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        logger.warning("failed to import user plugin %s: %s", path, exc)
        result.errors.append((str(path), str(exc)))
        return
    for cls in _plugin_classes(module):
        _instantiate(cls, str(path), result)


def _iter_plugin_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.glob("*.py") if p.name != "__init__.py" and not p.name.startswith("_")
    )


def _iter_builtin_module_names() -> list[str]:
    """Submodule names of the built-in package (works when frozen too).

    Uses package import + ``pkgutil`` rather than a filesystem glob so the
    built-ins are found inside a PyInstaller bundle, where the source
    ``.py`` files are not present on disk.
    """
    try:
        package = importlib.import_module(BUILTIN_PACKAGE)
    except Exception as exc:  # pragma: no cover - only if the package is unimportable
        logger.warning("cannot import %s: %s", BUILTIN_PACKAGE, exc)
        return []
    names: list[str] = []
    for info in pkgutil.iter_modules(getattr(package, "__path__", [])):
        if not info.name.startswith("_"):
            names.append(info.name)
    return sorted(names)


def discover_plugins(
    *,
    builtin_dir: Path | None = None,
    user_dir: Path | None = None,
) -> DiscoveryResult:
    """Scan the built-in package and an optional user folder for plugins.

    ``builtin_dir`` defaults to the shipped ``finsight/plugins`` package
    (imported by dotted name so it works when installed as a wheel).
    ``user_dir`` files are imported straight from disk. Everything is
    best-effort: failures are collected in :attr:`DiscoveryResult.errors`.
    """
    result = DiscoveryResult()

    if builtin_dir is None:
        # Production: enumerate the importable package (frozen-safe).
        for name in _iter_builtin_module_names():
            _load_package_module(name, result)
    else:
        # Explicit dir (tests): scan the filesystem so an empty temp dir
        # yields nothing and the real CTk example is never imported.
        for path in _iter_plugin_files(builtin_dir):
            _load_package_module(path.stem, result)

    if user_dir is not None:
        for path in _iter_plugin_files(user_dir):
            _load_file_module(path, result)

    result.plugins.sort(key=lambda p: (p.order, p.title))
    return result
