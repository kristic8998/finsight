"""MIS Studio page: One-Click Templates · Visual Builder · Auto-Reporter.

The v1.5 'Layman-Friendly MIS Engine' — three tabs, each fully
click-driven with a permanent How-to-Use card, friendly error popups,
and every heavy pandas operation on a background thread.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from .auto_reporter_tab import AutoReporterTab
from .mis_builder_tab import BuilderTab
from .mis_templates_tab import TemplatesTab


class MisStudioPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text="MIS Studio", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            self,
            text="Zero-code MIS: run a one-click lending template, build any pivot "
            "visually, or put a report on a schedule — no formulas, no training.",
            font=ctk.CTkFont(size=12),
            text_color=("gray35", "gray65"),
        ).pack(anchor="w", pady=(0, 6))

        self._tabs = ctk.CTkTabview(self, command=self._tab_changed)
        self._tabs.pack(fill="both", expand=True)
        for tab_name in ("One-Click Templates", "Visual Builder", "Auto-Reporter"):
            self._tabs.add(tab_name)

        self._templates = TemplatesTab(self._tabs.tab("One-Click Templates"), app)
        self._templates.pack(fill="both", expand=True)
        self._builder = BuilderTab(self._tabs.tab("Visual Builder"), app)
        self._builder.pack(fill="both", expand=True)
        self._reporter = AutoReporterTab(self._tabs.tab("Auto-Reporter"), app)
        self._reporter.pack(fill="both", expand=True)

    def _tab_changed(self) -> None:
        if self._tabs.get() == "Auto-Reporter":
            self._reporter.on_show()

    def on_show(self) -> None:
        """Called by the shell when the page becomes visible."""
        if self._tabs.get() == "Auto-Reporter":
            self._reporter.on_show()
