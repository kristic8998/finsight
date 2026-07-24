"""Excel Intelligence page: merge, split, clean, profile, compare, to-SQL."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ...modules import excel_tools as xt
from ..widgets import DataGrid, Section, run_in_thread


class ExcelPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context

        ctk.CTkLabel(
            self, text="Excel Intelligence", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            self,
            text="One-click operations on .xlsx / .xls / .csv files.",
            font=ctk.CTkFont(size=12),
            text_color=("gray35", "gray65"),
        ).pack(anchor="w", pady=(0, 8))

        toolbar = Section(self, "Operations")
        toolbar.pack(fill="x")
        row = ctk.CTkFrame(toolbar.body, fg_color="transparent")
        row.pack(fill="x")
        for label, handler in [
            ("Merge files…", self.merge),
            ("Split by column…", self.split),
            ("One-click clean…", self.clean),
            ("Profile / quality…", self.profile),
            ("Compare two files…", self.compare),
            ("Excel → SQL…", self.to_sql),
        ]:
            ctk.CTkButton(row, text=label, height=32, command=handler).pack(
                side="left", padx=4, pady=4
            )

        self._status = ctk.CTkLabel(
            self, text="", anchor="w", justify="left", wraplength=1100, font=ctk.CTkFont(size=12)
        )
        self._status.pack(fill="x", pady=6)

        result = Section(self, "Result preview")
        result.pack(fill="both", expand=True)
        self._grid = DataGrid(result.body, page_size=500)
        self._grid.pack(fill="both", expand=True)

    # ---- helpers -------------------------------------------------------------
    def _pick(self, title: str, multiple: bool = False):
        types = [("Spreadsheets", "*.xlsx *.xls *.csv"), ("All files", "*.*")]
        if multiple:
            return filedialog.askopenfilenames(title=title, filetypes=types)
        return filedialog.askopenfilename(title=title, filetypes=types)

    def _save_as(self, initial: str) -> str:
        return filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")], initialfile=initial
        )

    def _done(self, message: str) -> None:
        self._status.configure(text=message)
        self.app.toast.show("Done", "ok")

    def _failed(self, exc: BaseException) -> None:
        self.app.toast.show(f"Failed: {exc}", "error")
        self._status.configure(text=f"⚠ {exc}")

    def _ask_column(self, columns: list[str], prompt: str) -> str | None:
        dialog = ctk.CTkInputDialog(
            text=f"{prompt}\nAvailable: {', '.join(columns[:15])}", title="Choose column"
        )
        value = dialog.get_input()
        if value is None:
            return None
        value = value.strip()
        return value if value in columns else None

    # ---- operations --------------------------------------------------------------
    def merge(self) -> None:
        paths = self._pick("Choose files to merge (same layout)", multiple=True)
        if not paths:
            return
        target = self._save_as("merged.xlsx")
        if not target:
            return

        def work():
            frame = xt.merge_files(list(paths))
            xt.sql_to_excel(frame, target)
            return frame

        run_in_thread(
            self,
            self.ctx.runner.submit,
            work,
            lambda f: (self._grid.show(f), self._done(f"Merged {len(paths)} file(s) → {target}")),
            self._failed,
        )

    def split(self) -> None:
        path = self._pick("Choose the file to split")
        if not path:
            return
        frame = xt.read_table(path)
        column = self._ask_column(list(frame.columns.astype(str)), "Split by which column?")
        if not column:
            return
        out_dir = filedialog.askdirectory(title="Output folder for the split files")
        if not out_dir:
            return
        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: xt.split_file(path, column, out_dir),
            lambda files: self._done(f"Split into {len(files)} file(s) in {out_dir}"),
            self._failed,
        )

    def clean(self) -> None:
        path = self._pick("Choose the file to clean")
        if not path:
            return
        target = self._save_as(f"{Path(path).stem}_clean.xlsx")
        if not target:
            return

        def work():
            report = xt.clean(xt.read_table(path))
            xt.sql_to_excel(report.frame, target)
            return report

        run_in_thread(
            self,
            self.ctx.runner.submit,
            work,
            lambda r: (
                self._grid.show(r.frame),
                self._done("Cleaned → " + target + "\n• " + "\n• ".join(r.actions)),
            ),
            self._failed,
        )

    def profile(self) -> None:
        path = self._pick("Choose the file to profile")
        if not path:
            return
        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: xt.profile(xt.read_table(path)),
            lambda f: (self._grid.show(f), self._done(f"Profile of {Path(path).name}")),
            self._failed,
        )

    def compare(self) -> None:
        left = self._pick("Choose the FIRST file")
        if not left:
            return
        right = self._pick("Choose the SECOND file")
        if not right:
            return
        left_frame = xt.read_table(left)
        key = self._ask_column(list(left_frame.columns.astype(str)), "Compare on which key column?")
        if not key:
            return

        def work():
            return xt.compare_files(left_frame, xt.read_table(right), key)

        def done(result) -> None:  # noqa: ANN001
            if result.identical:
                self._done("Files are identical on shared columns ✔")
                self._grid.show(result.changed)
                return
            self._grid.show(
                result.changed
                if not result.changed.empty
                else result.only_left if not result.only_left.empty else result.only_right
            )
            self._done(
                f"Differences — changed cells: {len(result.changed)}, "
                f"rows only in first: {len(result.only_left)}, "
                f"rows only in second: {len(result.only_right)} (preview shows changes)"
            )

        run_in_thread(self, self.ctx.runner.submit, work, done, self._failed)

    def to_sql(self) -> None:
        path = self._pick("Choose the file to load into SQL")
        if not path:
            return
        dialog = ctk.CTkInputDialog(text="Target table name:", title="Excel → SQL")
        table = dialog.get_input()
        if not table:
            return
        connection = self.ctx.active_connection

        def work() -> int:
            engine = self.ctx.connections.engine(connection)
            return xt.excel_to_sql(path, engine, table.strip())

        run_in_thread(
            self,
            self.ctx.runner.submit,
            work,
            lambda n: self._done(f"Loaded {n:,} rows into table '{table}' on {connection}"),
            self._failed,
        )
