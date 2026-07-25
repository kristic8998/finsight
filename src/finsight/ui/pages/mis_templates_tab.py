"""One-Click Lending Templates tab — three giant buttons (MIS Studio)."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
import pandas as pd

from ...core.paths import reports_dir
from ...modules import excel_tools as xt
from ...modules.mis_samples import sample_lending_dataset
from ...modules.mis_templates import (
    TEMPLATES,
    TemplateError,
    TemplateResult,
    export_template,
    run_template,
)
from ..widgets import DataGrid, HelperCard, KpiCard, Section, run_in_thread, show_friendly_error


class TemplatesTab(ctk.CTkFrame):
    """Pick a template → drop the raw file → get a CEO-ready workbook."""

    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._result: TemplateResult | None = None

        HelperCard(
            self,
            "How to use — 3 steps",
            (
                "Click one of the three big template buttons below.",
                "Pick the raw export from your LMS (CSV/Excel) — no special format needed; "
                "columns are detected by name. Or click a template's “Sample” to demo it.",
                "Read the headline KPIs, preview any sheet, then click “Export CEO-ready "
                "Excel” — formatted, multi-sheet, ready to forward.",
            ),
        ).pack(fill="x", pady=(0, 8))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x")
        for column, spec in enumerate(TEMPLATES.values()):
            buttons.grid_columnconfigure(column, weight=1)
            card = ctk.CTkFrame(buttons, corner_radius=14, border_width=1)
            card.grid(row=0, column=column, padx=5, pady=2, sticky="nsew")
            ctk.CTkLabel(
                card, text=f"{spec.icon}  {spec.title}", font=ctk.CTkFont(size=16, weight="bold")
            ).pack(anchor="w", padx=14, pady=(12, 0))
            ctk.CTkLabel(
                card,
                text=spec.tagline,
                font=ctk.CTkFont(size=12),
                text_color=("gray35", "gray65"),
                wraplength=300,
                justify="left",
            ).pack(anchor="w", padx=14, pady=(2, 0))
            ctk.CTkLabel(
                card,
                text=f"Needs: {spec.needs}",
                font=ctk.CTkFont(size=10),
                text_color=("gray45", "gray60"),
                wraplength=300,
                justify="left",
            ).pack(anchor="w", padx=14, pady=(2, 6))
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=(0, 12))
            ctk.CTkButton(
                row,
                text="▶ Run with my file…",
                height=40,
                font=ctk.CTkFont(size=13, weight="bold"),
                command=lambda k=spec.key: self._run_with_file(k),
            ).pack(side="left", fill="x", expand=True, padx=(0, 4))
            ctk.CTkButton(
                row,
                text="Sample",
                width=76,
                height=40,
                fg_color="transparent",
                border_width=1,
                text_color=("gray15", "gray90"),
                command=lambda k=spec.key: self._run(k, sample_lending_dataset(), "sample data"),
            ).pack(side="left")

        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="x", pady=(8, 0))
        self._kpis: list[KpiCard] = []
        for column in range(4):
            cards.grid_columnconfigure(column, weight=1)
            card = KpiCard(cards, "—")
            card.grid(row=0, column=column, padx=4, pady=4, sticky="ew")
            self._kpis.append(card)

        result_section = Section(self, "Report preview")
        result_section.pack(fill="both", expand=True, pady=(6, 0))
        controls = ctk.CTkFrame(result_section.body, fg_color="transparent")
        controls.pack(fill="x")
        ctk.CTkLabel(controls, text="Sheet").pack(side="left", padx=(0, 6))
        self._sheet_menu = ctk.CTkOptionMenu(
            controls, values=["(run a template first)"], width=220, command=self._show_sheet
        )
        self._sheet_menu.pack(side="left")
        ctk.CTkButton(
            controls,
            text="Export CEO-ready Excel…",
            width=190,
            height=32,
            command=self._export,
        ).pack(side="right")
        self._notes = ctk.CTkLabel(
            controls, text="", font=ctk.CTkFont(size=11), text_color=("gray45", "gray60")
        )
        self._notes.pack(side="left", padx=12)
        self._grid = DataGrid(result_section.body, page_size=300)
        self._grid.pack(fill="both", expand=True, pady=(6, 0))

    # ---- running ------------------------------------------------------------
    def _run_with_file(self, key: str) -> None:
        path = filedialog.askopenfilename(
            title=f"Choose the raw file for: {TEMPLATES[key].title}",
            filetypes=[("Data files", "*.csv *.tsv *.xlsx *.xls"), ("All files", "*.*")],
        )
        if not path:
            return
        self.app.toast.show(f"Running {TEMPLATES[key].title}…")

        def work() -> TemplateResult:
            return run_template(key, xt.read_table(path))

        run_in_thread(
            self,
            self.app.context.runner.submit,
            work,
            lambda result: self._render(result, Path(path).name),
            self._failed,
        )

    def _run(self, key: str, frame: pd.DataFrame, label: str) -> None:
        self.app.toast.show(f"Running {TEMPLATES[key].title}…")
        run_in_thread(
            self,
            self.app.context.runner.submit,
            lambda: run_template(key, frame),
            lambda result: self._render(result, label),
            self._failed,
        )

    def _failed(self, exc: BaseException) -> None:
        if isinstance(exc, TemplateError):
            show_friendly_error(self, str(exc), title="This file doesn't fit the template")
        else:
            show_friendly_error(self, f"Something went wrong: {exc}")

    def _render(self, result: TemplateResult, source_label: str) -> None:
        self._result = result
        for index, card in enumerate(self._kpis):
            if index < len(result.kpis):
                label, value = result.kpis[index]
                card.update_value(value, label)
            else:
                card.update_value("—", "")
        self._notes.configure(
            text=("Note: " + "; ".join(result.notes)) if result.notes else f"source: {source_label}"
        )
        sheet_names = list(result.sheets)
        self._sheet_menu.configure(values=sheet_names)
        self._sheet_menu.set(sheet_names[0])
        self._show_sheet(sheet_names[0])
        self.app.toast.show(result.summary_text(), "ok")

    def _show_sheet(self, name: str) -> None:
        if self._result and name in self._result.sheets:
            self._grid.show(self._result.sheets[name], note=self._result.title)

    def _export(self) -> None:
        if self._result is None:
            show_friendly_error(self, "Run a template first — then export.")
            return
        default = reports_dir() / f"{self._result.key}_{date.today().isoformat()}.xlsx"
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            initialfile=default.name,
            initialdir=str(default.parent),
            filetypes=[("Excel", "*.xlsx")],
        )
        if not path:
            return
        result = self._result
        run_in_thread(
            self,
            self.app.context.runner.submit,
            lambda: export_template(result, path),
            lambda p: self.app.toast.show(f"CEO-ready report saved: {p}", "ok"),
            self._failed,
        )
