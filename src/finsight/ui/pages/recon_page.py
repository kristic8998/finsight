"""Reconciliation page: two files in, matched/mismatch/missing out."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ...core.paths import reports_dir
from ...modules import excel_tools as xt
from ...modules.recon import ReconResult, export_recon_report, reconcile
from ..widgets import DataGrid, Section, run_in_thread


class ReconPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context
        self._left_path: str | None = None
        self._right_path: str | None = None
        self._result: ReconResult | None = None

        ctk.CTkLabel(
            self, text="Reconciliation Engine", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            self,
            text="Ledger vs gateway, bank vs collections, settlement vs books — "
            "pick two files, choose key & amount, click Reconcile.",
            font=ctk.CTkFont(size=12),
            text_color=("gray35", "gray65"),
        ).pack(anchor="w", pady=(0, 8))

        setup = Section(self, "Setup")
        setup.pack(fill="x")
        grid = ctk.CTkFrame(setup.body, fg_color="transparent")
        grid.pack(fill="x")
        for column in range(6):
            grid.grid_columnconfigure(column, weight=1 if column in (1, 4) else 0)

        self._left_label = ctk.CTkLabel(
            grid, text="no file", anchor="w", text_color=("gray35", "gray65")
        )
        self._right_label = ctk.CTkLabel(
            grid, text="no file", anchor="w", text_color=("gray35", "gray65")
        )
        ctk.CTkButton(
            grid, text="Ledger / left file…", width=150, command=lambda: self._choose("left")
        ).grid(row=0, column=0, padx=4, pady=4)
        self._left_label.grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkButton(
            grid, text="Statement / right file…", width=150, command=lambda: self._choose("right")
        ).grid(row=0, column=3, padx=4, pady=4)
        self._right_label.grid(row=0, column=4, sticky="ew", padx=4)

        self._key = ctk.CTkOptionMenu(grid, values=["(load files first)"], width=180)
        self._amount = ctk.CTkOptionMenu(grid, values=["(load files first)"], width=180)
        self._tolerance = ctk.CTkEntry(grid, width=90)
        self._tolerance.insert(0, str(self.ctx.config.recon.amount_tolerance))
        ctk.CTkLabel(grid, text="Key column").grid(row=1, column=0, sticky="e", padx=4)
        self._key.grid(row=1, column=1, sticky="w", padx=4, pady=4)
        ctk.CTkLabel(grid, text="Amount column").grid(row=1, column=3, sticky="e", padx=4)
        self._amount.grid(row=1, column=4, sticky="w", padx=4, pady=4)
        ctk.CTkLabel(grid, text="Tolerance ±").grid(row=2, column=0, sticky="e", padx=4)
        self._tolerance.grid(row=2, column=1, sticky="w", padx=4)

        actions = ctk.CTkFrame(setup.body, fg_color="transparent")
        actions.pack(fill="x", pady=(4, 0))
        ctk.CTkButton(actions, text="⇄ Reconcile", width=140, height=34, command=self.run).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            actions,
            text="Export difference report…",
            width=200,
            height=34,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self.export,
        ).pack(side="left", padx=4)
        self._summary = ctk.CTkLabel(
            actions, text="", anchor="w", font=ctk.CTkFont(size=12, weight="bold")
        )
        self._summary.pack(side="left", padx=12)
        self._narrative = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            justify="left",
            wraplength=1150,
            font=ctk.CTkFont(size=11),
            text_color=("gray30", "gray70"),
        )
        self._narrative.pack(fill="x", pady=(4, 0))

        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, pady=(8, 0))
        self._grids: dict[str, DataGrid] = {}
        for tab in ("Mismatches", "Only Left", "Only Right", "Matched", "Duplicates"):
            self._tabs.add(tab)
            grid_widget = DataGrid(self._tabs.tab(tab), page_size=300)
            grid_widget.pack(fill="both", expand=True)
            self._grids[tab] = grid_widget

    def _choose(self, side: str) -> None:
        path = filedialog.askopenfilename(
            title=f"Choose the {side} file",
            filetypes=[("Spreadsheets", "*.xlsx *.xls *.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        if side == "left":
            self._left_path = path
            self._left_label.configure(text=Path(path).name)
        else:
            self._right_path = path
            self._right_label.configure(text=Path(path).name)
        if self._left_path:
            columns = list(xt.read_table(self._left_path).columns.astype(str))
            self._key.configure(values=columns)
            self._amount.configure(values=columns)
            lowered = [c.lower() for c in columns]
            for i, name in enumerate(lowered):
                if any(k in name for k in ("utr", "ref", "txn", "id")):
                    self._key.set(columns[i])
                    break
            for i, name in enumerate(lowered):
                if "amount" in name or "amt" in name:
                    self._amount.set(columns[i])
                    break

    def run(self) -> None:
        if not self._left_path or not self._right_path:
            self.app.toast.show("Pick both files first", "error")
            return
        key, amount = self._key.get(), self._amount.get()
        try:
            tolerance = float(self._tolerance.get() or "0")
        except ValueError:
            self.app.toast.show("Tolerance must be a number", "error")
            return
        self.app.toast.show("Reconciling…")

        def work() -> ReconResult:
            return reconcile(
                xt.read_table(self._left_path),
                xt.read_table(self._right_path),
                key=key,
                amount=amount,
                tolerance=tolerance,
                left_name=Path(self._left_path).stem,
                right_name=Path(self._right_path).stem,
            )

        run_in_thread(self, self.ctx.runner.submit, work, self._render, self._failed)

    def _failed(self, exc: BaseException) -> None:
        self.app.toast.show(f"Reconciliation failed: {exc}", "error")

    def _render(self, result: ReconResult) -> None:
        self._result = result
        from ...modules.investigate import investigate

        inv = investigate(result)
        self._summary.configure(text=result.summary)
        self._status_narrative(inv.narrative)
        self._grids["Mismatches"].show(result.amount_mismatch)
        self._grids["Only Left"].show(result.only_left)
        self._grids["Only Right"].show(result.only_right)
        self._grids["Matched"].show(result.matched)
        import pandas as pd

        duplicates = (
            pd.concat(
                [
                    result.dup_left.assign(side=result.left_name),
                    result.dup_right.assign(side=result.right_name),
                ],
                ignore_index=True,
            )
            if (len(result.dup_left) or len(result.dup_right))
            else pd.DataFrame()
        )
        self._grids["Duplicates"].show(duplicates)
        self._tabs.set("Mismatches")
        self.app.toast.show("Reconciliation complete", "ok")

    def _status_narrative(self, text: str) -> None:
        """Show the root-cause narrative under the summary line."""
        self._narrative.configure(text=text)

    def export(self) -> None:
        if self._result is None:
            self.app.toast.show("Run a reconciliation first", "error")
            return
        default = reports_dir() / f"recon_{date.today().isoformat()}.xlsx"
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
            lambda: export_recon_report(self._result, path),
            lambda p: self.app.toast.show(f"Report saved: {p}", "ok"),
            self._failed,
        )
