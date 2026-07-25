"""Data Quality Center page: profile a file or SQL table, flag exceptions."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ...core.paths import reports_dir
from ...modules.data_quality import (
    DataQualityReport,
    export_report,
    profile_frame,
    profile_path,
)
from ..widgets import SEVERITY_COLORS, DataGrid, KpiCard, Section, run_in_thread

_SCORE_COLORS = {"A": "#2E7D32", "B": "#2E7D32", "C": "#EF6C00", "D": "#EF6C00", "F": "#C62828"}


class DqPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context
        self._report: DataQualityReport | None = None
        self._source_label = "—"

        ctk.CTkLabel(
            self, text="Data Quality Center", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            self,
            text="One-click profiling for Excel, CSV, and SQL — duplicates, missing values, "
            "outliers, and business-rule violations, exportable for management.",
            font=ctk.CTkFont(size=12),
            text_color=("gray35", "gray65"),
        ).pack(anchor="w", pady=(0, 8))

        # ---- KPI cards --------------------------------------------------------
        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="x")
        self._cards: dict[str, KpiCard] = {}
        for column, key in enumerate(("Quality score", "Rows", "Columns", "Duplicates", "Alerts")):
            cards.grid_columnconfigure(column, weight=1)
            card = KpiCard(cards, key)
            card.grid(row=0, column=column, padx=4, pady=4, sticky="ew")
            self._cards[key] = card

        # ---- source picker ----------------------------------------------------
        source = Section(self, "Source")
        source.pack(fill="x", pady=(6, 0))
        row = ctk.CTkFrame(source.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="Profile a file…", width=150, command=self._choose_file).pack(
            side="left", padx=4, pady=4
        )
        ctk.CTkLabel(row, text="or SQL table:").pack(side="left", padx=(16, 4))
        self._table = ctk.CTkOptionMenu(row, values=["(connect first)"], width=200)
        self._table.pack(side="left", padx=4)
        ctk.CTkButton(row, text="Profile table", width=130, command=self._profile_table).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            row,
            text="Export exception report…",
            width=200,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self._export,
        ).pack(side="right", padx=4)

        self._summary = ctk.CTkLabel(
            self, text="", anchor="w", font=ctk.CTkFont(size=12, weight="bold")
        )
        self._summary.pack(fill="x", pady=(6, 0))

        # ---- results ----------------------------------------------------------
        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, pady=(6, 0))
        self._grids: dict[str, DataGrid] = {}
        for tab in ("Exceptions", "Column Profiles"):
            tabs.add(tab)
            grid = DataGrid(tabs.tab(tab), page_size=400)
            grid.pack(fill="both", expand=True)
            self._grids[tab] = grid
        self._tabs = tabs

    # ---- lifecycle ------------------------------------------------------------
    def on_show(self) -> None:
        """Refresh the SQL-table dropdown from the active connection."""
        try:
            tables = self.ctx.sql.tables(self.ctx.active_connection)
        except Exception:  # noqa: BLE001 - a bad connection shouldn't break the page
            tables = []
        if tables:
            self._table.configure(values=tables)
            if self._table.get() not in tables:
                self._table.set(tables[0])

    # ---- actions --------------------------------------------------------------
    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose a data file to profile",
            filetypes=[("Data files", "*.csv *.tsv *.txt *.xlsx *.xls"), ("All files", "*.*")],
        )
        if not path:
            return
        chunk = self.ctx.config.data_quality.chunk_size
        alert_pct = self.ctx.config.data_quality.missing_alert_pct
        self._run(
            lambda: profile_path(path, chunk_size=chunk, missing_alert_pct=alert_pct),
            source=Path(path).name,
        )

    def _profile_table(self) -> None:
        table = self._table.get()
        if not table or table.startswith("("):
            self.app.toast.show("Pick a SQL table first", "error")
            return
        alert_pct = self.ctx.config.data_quality.missing_alert_pct
        connection = self.ctx.active_connection

        def work() -> DataQualityReport:
            record = self.ctx.sql.execute(connection, f'SELECT * FROM "{table}"')
            return profile_frame(record.result.frame, missing_alert_pct=alert_pct)

        self._run(work, source=f"{table} ({connection})")

    def _run(self, work, source: str) -> None:  # noqa: ANN001
        self._source_label = source
        self.app.toast.show(f"Profiling {source}…")
        run_in_thread(self, self.ctx.runner.submit, work, self._render, self._failed)

    def _failed(self, exc: BaseException) -> None:
        self.app.toast.show(f"Profiling failed: {exc}", "error")

    def _render(self, report: DataQualityReport) -> None:
        self._report = report
        alerts = sum(1 for i in report.issues if i.severity == "alert")
        warns = sum(1 for i in report.issues if i.severity == "watch")
        self._cards["Quality score"].update_value(
            f"{report.score:.0f}", f"grade {report.grade}", _SCORE_COLORS.get(report.grade)
        )
        self._cards["Rows"].update_value(f"{report.rows:,}", self._source_label)
        self._cards["Columns"].update_value(str(report.columns))
        self._cards["Duplicates"].update_value(
            f"{report.duplicate_rows:,}",
            "row-level" + (" (approx)" if report.duplicate_rows_approx else ""),
            SEVERITY_COLORS["watch"] if report.duplicate_rows else None,
        )
        self._cards["Alerts"].update_value(
            str(alerts),
            f"{warns} warning(s)",
            SEVERITY_COLORS["alert"] if alerts else SEVERITY_COLORS["good"],
        )
        self._summary.configure(text=report.summary())
        self._grids["Exceptions"].show(
            report.issues_frame(), note="worst first" if report.issues else "no issues found"
        )
        self._grids["Column Profiles"].show(report.profiles_frame())
        self._tabs.set("Exceptions")
        self.app.toast.show("Profiling complete", "ok")

    def _export(self) -> None:
        if self._report is None:
            self.app.toast.show("Profile something first", "error")
            return
        default = reports_dir() / f"data_quality_{date.today().isoformat()}.xlsx"
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            initialfile=default.name,
            initialdir=str(default.parent),
            filetypes=[("Excel", "*.xlsx")],
        )
        if not path:
            return
        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: export_report(self._report, path),
            lambda p: self.app.toast.show(f"Exception report saved: {p}", "ok"),
            self._failed,
        )
