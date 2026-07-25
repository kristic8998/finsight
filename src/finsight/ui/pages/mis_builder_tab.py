"""Visual MIS Builder tab — the zero-code pivot wizard (MIS Studio)."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from ...core.paths import reports_dir
from ...modules import excel_tools as xt
from ...modules.mis_builder import (
    AGGREGATES,
    NO_SPLIT,
    BuilderConfig,
    PivotResult,
    SavedReport,
    build_pivot,
    export_pivot,
    save_report,
)
from ...modules.mis_samples import sample_lending_dataset
from ..widgets import ACCENT, DataGrid, HelperCard, Section, run_in_thread, show_friendly_error


class BuilderTab(ctk.CTkFrame):
    """Step 1 upload → Step 2 choose metrics → Step 3 generate/export/save."""

    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._data: pd.DataFrame | None = None
        self._source_path: str = ""
        self._result: PivotResult | None = None

        HelperCard(
            self,
            "How to use — 3 steps",
            (
                "Step 1: upload any raw CSV/Excel export — the dropdowns fill themselves "
                "with your file's own column names.",
                "Step 2: pick what to Group by, which Metric to aggregate, and how "
                "(Sum / Average / Count…). 'Split by' adds an optional second dimension.",
                "Step 3: click Generate — pivot table + chart appear instantly. Export a "
                "formatted Excel, or save the recipe for the Auto-Reporter.",
            ),
        ).pack(fill="x", pady=(0, 8))

        step1 = Section(self, "Step 1 — Upload your raw data")
        step1.pack(fill="x")
        row1 = ctk.CTkFrame(step1.body, fg_color="transparent")
        row1.pack(fill="x")
        ctk.CTkButton(row1, text="Upload file…", width=140, height=32, command=self._upload).pack(
            side="left", padx=(0, 6)
        )
        ctk.CTkButton(
            row1,
            text="Try with sample data",
            width=160,
            height=32,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self._load_sample,
        ).pack(side="left")
        self._file_label = ctk.CTkLabel(
            row1, text="No file loaded yet.", text_color=("gray35", "gray65")
        )
        self._file_label.pack(side="left", padx=12)

        step2 = Section(self, "Step 2 — Choose your metrics")
        step2.pack(fill="x", pady=(6, 0))
        row2 = ctk.CTkFrame(step2.body, fg_color="transparent")
        row2.pack(fill="x")
        placeholder = ["(upload a file first)"]
        ctk.CTkLabel(row2, text="Group by").pack(side="left", padx=(0, 4))
        self._group = ctk.CTkOptionMenu(row2, values=placeholder, width=160)
        self._group.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row2, text="Metric").pack(side="left", padx=(0, 4))
        self._value = ctk.CTkOptionMenu(row2, values=placeholder, width=160)
        self._value.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row2, text="Aggregate").pack(side="left", padx=(0, 4))
        self._agg = ctk.CTkOptionMenu(row2, values=list(AGGREGATES), width=120)
        self._agg.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row2, text="Split by").pack(side="left", padx=(0, 4))
        self._split = ctk.CTkOptionMenu(row2, values=[NO_SPLIT], width=150)
        self._split.pack(side="left")

        step3 = Section(self, "Step 3 — Generate")
        step3.pack(fill="x", pady=(6, 0))
        row3 = ctk.CTkFrame(step3.body, fg_color="transparent")
        row3.pack(fill="x")
        self._generate_btn = ctk.CTkButton(
            row3, text="⚡ Generate Report", width=170, height=34, command=self._generate
        )
        self._generate_btn.pack(side="left")
        ctk.CTkButton(
            row3,
            text="Export formatted Excel…",
            width=190,
            height=34,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self._export,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            row3,
            text="💾 Save for Auto-Reporter…",
            width=200,
            height=34,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self._save_recipe,
        ).pack(side="left")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(8, 0))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)
        self._grid = DataGrid(body, page_size=300)
        self._grid.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        chart_section = Section(body, "Chart")
        chart_section.grid(row=0, column=1, sticky="nsew")
        self._figure = Figure(figsize=(4.6, 3.2), dpi=100)
        self._axes = self._figure.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._figure, master=chart_section.body)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)

    # ---- data loading ---------------------------------------------------------
    def _upload(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose your raw data file",
            filetypes=[("Data files", "*.csv *.tsv *.xlsx *.xls"), ("All files", "*.*")],
        )
        if not path:
            return
        self.app.toast.show("Reading file…")
        run_in_thread(
            self,
            self.app.context.runner.submit,
            lambda: xt.read_table(path),
            lambda df: self._loaded(df, path),
            self._read_failed,
        )

    def _load_sample(self) -> None:
        self._loaded(sample_lending_dataset(), "")
        self._file_label.configure(text="Loaded: sample data (500 demo loans)")

    def _loaded(self, df: pd.DataFrame, path: str) -> None:
        if df is None or df.empty:
            show_friendly_error(self, "That file has no rows — please check the export.")
            return
        self._data = df
        self._source_path = path
        self._result = None
        if path:
            self._file_label.configure(text=f"Loaded: {Path(path).name} ({len(df):,} rows)")
        columns = [str(c) for c in df.columns]
        numeric_first = sorted(
            columns, key=lambda c: (0 if pd.api.types.is_numeric_dtype(df[c]) else 1, c)
        )
        self._group.configure(values=columns)
        self._group.set(columns[0])
        self._value.configure(values=numeric_first)
        self._value.set(numeric_first[0])
        self._split.configure(values=[NO_SPLIT, *columns])
        self._split.set(NO_SPLIT)
        self.app.toast.show(
            f"Loaded {len(df):,} rows × {len(columns)} columns — pick your metrics (Step 2)", "ok"
        )

    def _read_failed(self, exc: BaseException) -> None:
        show_friendly_error(
            self,
            f"FinSight couldn't read that file: {exc}\n\n"
            "Please upload a CSV or Excel export (xlsx/xls/csv/tsv).",
        )

    # ---- generation -------------------------------------------------------------
    def _config(self) -> BuilderConfig:
        split = self._split.get()
        return BuilderConfig(
            group_by=self._group.get(),
            value=self._value.get(),
            aggregate=self._agg.get(),
            split_by=None if split == NO_SPLIT else split,
        )

    def _generate(self) -> None:
        if self._data is None:
            show_friendly_error(self, "Upload a file first (Step 1) — or use the sample data.")
            return
        self._generate_btn.configure(state="disabled", text="Working…")
        data, config = self._data, self._config()
        run_in_thread(
            self,
            self.app.context.runner.submit,
            lambda: build_pivot(data, config),
            self._render,
            self._failed,
        )

    def _render(self, result: PivotResult) -> None:
        self._generate_btn.configure(state="normal", text="⚡ Generate Report")
        self._result = result
        self._grid.show(result.frame, note=result.title)
        self._draw_chart(result)
        self.app.toast.show(f"Generated: {result.title}", "ok")

    def _draw_chart(self, result: PivotResult) -> None:
        self._axes.clear()
        frame = result.frame[result.frame[result.config.group_by].astype(str) != "TOTAL"]
        top = frame.head(15)
        value_col = [c for c in top.columns if c != result.config.group_by][0]
        self._axes.barh(
            top[result.config.group_by].astype(str)[::-1],
            pd.to_numeric(top[value_col], errors="coerce").fillna(0)[::-1],
            color=ACCENT,
        )
        self._axes.set_title(result.title, fontsize=9)
        self._axes.tick_params(labelsize=7)
        self._axes.grid(alpha=0.25, axis="x")
        self._figure.tight_layout()
        self._canvas.draw_idle()

    def _failed(self, exc: BaseException) -> None:
        self._generate_btn.configure(state="normal", text="⚡ Generate Report")
        show_friendly_error(self, str(exc))

    # ---- export & save ---------------------------------------------------------
    def _export(self) -> None:
        if self._result is None:
            show_friendly_error(self, "Generate a report first (Step 3).")
            return
        default = reports_dir() / f"mis_builder_{date.today().isoformat()}.xlsx"
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            initialfile=default.name,
            initialdir=str(default.parent),
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not path:
            return
        result = self._result
        run_in_thread(
            self,
            self.app.context.runner.submit,
            lambda: export_pivot(result, path),
            lambda p: self.app.toast.show(f"Report saved: {p}", "ok"),
            self._failed,
        )

    def _save_recipe(self) -> None:
        if self._result is None:
            show_friendly_error(self, "Generate a report first — then save it as a recipe.")
            return
        if not self._source_path:
            show_friendly_error(
                self,
                "Sample data can't be scheduled. Upload a real file (Step 1), generate, "
                "and save again — the Auto-Reporter will re-read that file on schedule.",
                title="Almost there",
            )
            return
        dialog = ctk.CTkInputDialog(
            text="Name this report (the Auto-Reporter will list it):", title="Save report recipe"
        )
        name = (dialog.get_input() or "").strip()
        if not name:
            return
        save_report(
            SavedReport(name=name, source_path=self._source_path, config=self._result.config)
        )
        self.app.toast.show(f"Saved '{name}' — find it in the Auto-Reporter tab", "ok")
