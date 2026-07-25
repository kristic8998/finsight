"""Action & module registry.

Every page and every notable action registers here, which is what powers
global search and the Ctrl+K command palette: one list, filtered live.
Modules can be enabled/disabled; disabled modules disappear from
navigation, search, and the palette together.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid importing the plugin machinery unless it's used
    from .plugins import DiscoveryResult, FinSightPlugin


@dataclass
class Action:
    """Something the user can jump to or execute."""

    id: str
    title: str
    category: str
    run: Callable[[], None]
    keywords: tuple[str, ...] = ()


@dataclass
class Module:
    """A top-level feature area (sidebar entry)."""

    id: str
    title: str
    icon: str  # simple glyph, keeps the UI dependency-free
    order: int = 100
    enabled: bool = True


@dataclass
class Registry:
    """In-memory registry consulted by the shell, palette, and search."""

    modules: dict[str, Module] = field(default_factory=dict)
    actions: dict[str, Action] = field(default_factory=dict)
    plugins: dict[str, FinSightPlugin] = field(default_factory=dict)

    def register_module(self, module: Module) -> None:
        self.modules[module.id] = module

    def register_action(self, action: Action) -> None:
        self.actions[action.id] = action

    def register_plugin(self, plugin: FinSightPlugin) -> None:
        """Store a discovered plugin and expose it as a sidebar module."""
        self.plugins[plugin.id] = plugin
        self.register_module(
            Module(id=plugin.id, title=plugin.title, icon=plugin.icon, order=plugin.order)
        )

    def load_plugins(
        self,
        *,
        builtin_dir: Path | None = None,
        user_dir: Path | None = None,
    ) -> DiscoveryResult:
        """Scan for drop-in plugins and register everything discovered.

        Delegates the file/​import mechanics to :mod:`finsight.core.plugins`
        (imported lazily so the registry stays cheap for callers that never
        use plugins). Returns the :class:`DiscoveryResult` so the shell can
        surface load errors.
        """
        from .plugins import discover_plugins

        result = discover_plugins(builtin_dir=builtin_dir, user_dir=user_dir)
        for plugin in result.plugins:
            self.register_plugin(plugin)
        return result

    def enabled_modules(self) -> list[Module]:
        return sorted(
            (m for m in self.modules.values() if m.enabled), key=lambda m: (m.order, m.title)
        )

    def set_module_enabled(self, module_id: str, enabled: bool) -> None:
        if module_id in self.modules:
            self.modules[module_id].enabled = enabled

    def search(self, text: str, limit: int = 12) -> list[Action]:
        """Rank actions by simple relevance: title prefix > substring > keyword."""
        query = text.strip().lower()
        if not query:
            return sorted(self.actions.values(), key=lambda a: a.title)[:limit]

        scored: list[tuple[int, Action]] = []
        for action in self.actions.values():
            module = self.modules.get(action.category)
            if module is not None and not module.enabled:
                continue
            title = action.title.lower()
            if title.startswith(query):
                score = 0
            elif query in title:
                score = 1
            elif any(query in k for k in action.keywords):
                score = 2
            else:
                continue
            scored.append((score, action))
        scored.sort(key=lambda pair: (pair[0], pair[1].title))
        return [action for _, action in scored[:limit]]
