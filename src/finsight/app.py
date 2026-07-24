"""FinSight application shell.

Sidebar navigation + page host + status bar + command palette. Pages
are lazily constructed CTk frames registered in the module registry, so
enabling/disabling modules, global search, and Ctrl+K all share one
source of truth. All heavy work runs on the TaskRunner; the Tk thread
only ever draws.
"""

from __future__ import annotations

import logging

import customtkinter as ctk

from . import APP_NAME, __version__
from .core.backup import create_backup
from .core.config import AppConfig, load_config, save_config
from .core.logging_setup import setup_logging
from .core.registry import Action, Module
from .data.demo_data import generate_demo_db
from .modules.automation import Schedule
from .ui.context import AppContext, build_context
from .ui.palette import CommandPalette
from .ui.widgets import Toast, style_treeview

logger = logging.getLogger(__name__)

_PAGES: list[tuple[str, str, str, int]] = [
    # (module id, title, glyph, order)
    ("executive", "Executive", "◆", 10),
    ("ask", "Ask FinSight", "✦", 20),
    ("sql", "SQL Studio", "▤", 30),
    ("excel", "Excel Tools", "▦", 40),
    ("recon", "Reconciliation", "⇄", 50),
    ("mis", "MIS Reports", "▣", 60),
    ("analytics", "Analytics", "∿", 70),
    ("automation", "Automation", "⚙", 80),
    ("productivity", "Productivity", "☰", 90),
    ("settings", "Settings", "✎", 100),
]


class FinSightApp(ctk.CTk):
    """Main window."""

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        config = context.config

        ctk.set_appearance_mode(config.ui.theme)
        ctk.set_default_color_theme("blue")
        style_treeview(dark=config.ui.theme != "light")

        self.title(f"{APP_NAME} — Lending Analytics Suite")
        self.geometry("1360x820")
        self.minsize(1080, 680)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._pages: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._current: str | None = None

        self._build_sidebar()
        self._host = ctk.CTkFrame(self, fg_color="transparent")
        self._host.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=12)

        status = ctk.CTkFrame(self, height=30, corner_radius=0)
        status.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._status_label = ctk.CTkLabel(status, text="", anchor="w", font=ctk.CTkFont(size=11))
        self._status_label.pack(side="left", padx=12)
        ctk.CTkLabel(
            status,
            text=f"v{__version__} • Ctrl+K commands • Ctrl+D theme",
            font=ctk.CTkFont(size=11),
            text_color=("gray45", "gray60"),
        ).pack(side="right", padx=12)
        self.toast = Toast(self._status_label)

        self._register_modules()
        self.bind("<Control-k>", lambda _e: self.open_palette())
        self.bind("<Control-K>", lambda _e: self.open_palette())
        self.bind("<Control-d>", lambda _e: self.toggle_theme())
        for index, (module_id, *_rest) in enumerate(_PAGES[:9], start=1):
            self.bind(f"<Control-Key-{index % 10}>", lambda _e, m=module_id: self.show_page(m))

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_page(
            config.ui.start_page
            if config.ui.start_page in dict((p[0], p) for p in _PAGES)
            else "executive"
        )

    # ---- construction -----------------------------------------------------
    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        sidebar.grid_propagate(False)

        ctk.CTkLabel(sidebar, text="FinSight", font=ctk.CTkFont(size=21, weight="bold")).pack(
            anchor="w", padx=18, pady=(18, 0)
        )
        ctk.CTkLabel(
            sidebar,
            text="Lending Intelligence",
            font=ctk.CTkFont(size=11),
            text_color=("gray45", "gray60"),
        ).pack(anchor="w", padx=18, pady=(0, 14))

        search = ctk.CTkEntry(sidebar, placeholder_text="Search (Ctrl+K)")
        search.pack(fill="x", padx=12, pady=(0, 10))
        search.bind("<FocusIn>", lambda _e: self.open_palette())

        self._nav_holder = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self._nav_holder.pack(fill="both", expand=True, padx=6)

        for module_id, title, glyph, _order in _PAGES:
            button = ctk.CTkButton(
                self._nav_holder,
                text=f"  {glyph}  {title}",
                anchor="w",
                fg_color="transparent",
                hover_color=("gray85", "gray25"),
                text_color=("gray15", "gray90"),
                height=34,
                corner_radius=8,
                command=lambda m=module_id: self.show_page(m),
            )
            button.pack(fill="x", pady=1)
            self._nav_buttons[module_id] = button

        theme = ctk.CTkButton(
            sidebar,
            text="◐  Toggle theme",
            height=30,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self.toggle_theme,
        )
        theme.pack(fill="x", padx=12, pady=12)

    def _register_modules(self) -> None:
        registry = self.context.registry
        for module_id, title, glyph, order in _PAGES:
            registry.register_module(Module(id=module_id, title=title, icon=glyph, order=order))
            registry.register_action(
                Action(
                    id=f"open:{module_id}",
                    title=f"Open {title}",
                    category=module_id,
                    run=lambda m=module_id: self.show_page(m),
                    keywords=(module_id, title.lower()),
                )
            )
        registry.register_action(
            Action(
                id="app:theme",
                title="Toggle dark/light theme",
                category="settings",
                run=self.toggle_theme,
                keywords=("dark", "light", "mode", "theme"),
            )
        )
        registry.register_action(
            Action(
                id="app:backup",
                title="Back up FinSight data now",
                category="settings",
                run=self._backup_now,
                keywords=("backup", "save", "archive"),
            )
        )
        registry.register_action(
            Action(
                id="mis:daily",
                title="Generate daily MIS pack",
                category="mis",
                run=lambda: self.show_page("mis"),
                keywords=("report", "ceo", "daily"),
            )
        )

    # ---- page management ----------------------------------------------------
    def _make_page(self, module_id: str) -> ctk.CTkFrame:
        from .ui.pages import PAGE_FACTORIES

        factory = PAGE_FACTORIES[module_id]
        return factory(self._host, self)

    def show_page(self, module_id: str) -> None:
        if module_id not in {p[0] for p in _PAGES}:
            return
        if module_id not in self._pages:
            self._pages[module_id] = self._make_page(module_id)
        for shown_id, page in self._pages.items():
            if shown_id != module_id:
                page.pack_forget()
        page = self._pages[module_id]
        page.pack(fill="both", expand=True)
        self._current = module_id
        for nav_id, button in self._nav_buttons.items():
            button.configure(
                fg_color=("gray80", "gray28") if nav_id == module_id else "transparent"
            )
        refresh = getattr(page, "on_show", None)
        if callable(refresh):
            refresh()

    # ---- global actions --------------------------------------------------------
    def open_palette(self) -> None:
        CommandPalette(self, self.context.registry)

    def toggle_theme(self) -> None:
        current = ctk.get_appearance_mode().lower()
        new_mode = "light" if current == "dark" else "dark"
        ctk.set_appearance_mode(new_mode)
        style_treeview(dark=new_mode == "dark")
        self.context.config.ui.theme = new_mode
        save_config(self.context.config)

    def _backup_now(self) -> None:
        self.context.runner.submit(
            create_backup,
            on_done=lambda p: self.after(
                0, lambda: self.toast.show(f"Backup created: {p.name}", "ok")
            ),
            on_error=lambda e: self.after(
                0, lambda: self.toast.show(f"Backup failed: {e}", "error")
            ),
        )

    def _on_close(self) -> None:
        try:
            self.context.automation.stop()
            self.context.runner.shutdown()
            self.context.connections.dispose_all()
            create_backup()
        except Exception as exc:  # closing must never hang the window
            logger.warning("shutdown housekeeping failed: %s", exc)
        self.destroy()


def _register_default_jobs(context: AppContext) -> None:
    """Built-in automation jobs (documented in the Automation page)."""

    def job_daily_mis() -> str:
        output = context.mis.generate("daily")
        return f"daily MIS → {output.excel_path.name}"

    def job_backup() -> str:
        return f"backup → {create_backup().name}"

    context.automation.register_job("Generate daily MIS pack", job_daily_mis)
    context.automation.register_job("Back up FinSight data", job_backup)


def create_app(config: AppConfig | None = None) -> FinSightApp:
    """Composition root: config → demo data → services → window."""
    app_config = config if config is not None else load_config()
    setup_logging()
    generate_demo_db(app_config.demo)
    context = build_context(app_config)
    _register_default_jobs(context)
    if app_config.automation.enabled:
        context.automation.add_schedule(Schedule(job="Back up FinSight data", daily_at="19:00"))
        context.automation.start()
    return FinSightApp(context)


def main() -> int:
    app = create_app()
    app.mainloop()
    return 0
