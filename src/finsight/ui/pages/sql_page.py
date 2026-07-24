"""SQL Studio page: editor, results, history, library, schema browser."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from ...modules.sql_studio import SQL_KEYWORDS, ExecutionRecord
from ..widgets import DataGrid, run_in_thread


class SqlPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context
        self._last: ExecutionRecord | None = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text="SQL Studio", font=ctk.CTkFont(size=20, weight="bold")).pack(
            side="left"
        )
        self._conn = ctk.CTkOptionMenu(top, values=self._connection_names(), width=220)
        self._conn.pack(side="right")
        ctk.CTkLabel(top, text="Connection:", font=ctk.CTkFont(size=12)).pack(side="right", padx=6)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(8, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=4)
        body.grid_rowconfigure(0, weight=1)

        # -- left: schema browser + library --------------------------------
        left = ctk.CTkTabview(body, width=250)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.add("Tables")
        left.add("Library")
        self._tables_box = tk.Listbox(
            left.tab("Tables"),
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
        )
        self._tables_box.pack(fill="both", expand=True, padx=4, pady=4)
        self._tables_box.bind("<Double-Button-1>", self._insert_table)
        ctk.CTkButton(
            left.tab("Tables"), text="↻ Load tables", height=26, command=self.load_tables
        ).pack(fill="x", padx=4, pady=(0, 4))

        self._library_box = tk.Listbox(
            left.tab("Library"),
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
        )
        self._library_box.pack(fill="both", expand=True, padx=4, pady=4)
        self._library_box.bind("<Double-Button-1>", self._insert_saved)
        ctk.CTkButton(
            left.tab("Library"), text="💾 Save current as…", height=26, command=self.save_current
        ).pack(fill="x", padx=4, pady=(0, 4))

        # -- right: editor over results ---------------------------------------
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        editor_frame = ctk.CTkFrame(right, corner_radius=8)
        editor_frame.grid(row=0, column=0, sticky="ew")
        self._editor = tk.Text(
            editor_frame,
            height=8,
            font=("Consolas", 11),
            background="#1e2228",
            foreground="#e6e6e6",
            insertbackground="#e6e6e6",
            borderwidth=0,
            wrap="none",
            undo=True,
        )
        self._editor.pack(fill="x", padx=8, pady=8)
        self._editor.tag_configure("kw", foreground="#61afef")
        self._editor.bind("<KeyRelease>", self._highlight)
        self._editor.bind("<Control-Return>", lambda _e: (self.run(), "break")[1])
        self._editor.insert("1.0", "SELECT name, city, region FROM branches ORDER BY name")
        self._highlight()

        buttons = ctk.CTkFrame(right, fg_color="transparent")
        buttons.grid(row=0, column=0, sticky="se", padx=10, pady=10)
        self._timer = ctk.CTkLabel(
            buttons, text="", font=ctk.CTkFont(size=11), text_color=("gray40", "gray65")
        )
        self._timer.pack(side="left", padx=8)
        ctk.CTkButton(
            buttons,
            text="Export…",
            width=80,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self.export,
        ).pack(side="left", padx=4)
        ctk.CTkButton(buttons, text="▶ Run (Ctrl+Enter)", width=140, command=self.run).pack(
            side="left"
        )

        self._grid = DataGrid(right, page_size=500)
        self._grid.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    # ---- helpers ----------------------------------------------------------
    def _connection_names(self) -> list[str]:
        return [c.name for c in self.ctx.connections.list_connections()]

    def on_show(self) -> None:
        self._conn.configure(values=self._connection_names())
        self._refresh_library()

    def _highlight(self, _event: tk.Event | None = None) -> None:
        self._editor.tag_remove("kw", "1.0", "end")
        text = self._editor.get("1.0", "end-1c")
        lower = text.lower()
        for keyword in SQL_KEYWORDS:
            start = 0
            while True:
                index = lower.find(keyword, start)
                if index < 0:
                    break
                before_ok = index == 0 or not lower[index - 1].isalnum()
                after = index + len(keyword)
                after_ok = after >= len(lower) or not lower[after].isalnum()
                if before_ok and after_ok:
                    self._editor.tag_add("kw", f"1.0+{index}c", f"1.0+{after}c")
                start = after

    def load_tables(self) -> None:
        connection = self._conn.get()

        def work() -> list[str]:
            return self.ctx.sql.tables(connection)

        def done(tables: list[str]) -> None:
            self._tables_box.delete(0, "end")
            for table in tables:
                self._tables_box.insert("end", f" {table}")

        run_in_thread(self, self.ctx.runner.submit, work, done, self._failed)

    def _insert_table(self, _event: tk.Event) -> None:
        selection = self._tables_box.curselection()
        if selection:
            table = self._tables_box.get(selection[0]).strip()
            self._editor.insert("insert", table)
            self._highlight()

    def _refresh_library(self) -> None:
        self._library = self.ctx.sql.library()
        self._library_box.delete(0, "end")
        for name in self._library:
            self._library_box.insert("end", f" {name}")

    def _insert_saved(self, _event: tk.Event) -> None:
        selection = self._library_box.curselection()
        if selection:
            name = self._library_box.get(selection[0]).strip()
            self._editor.delete("1.0", "end")
            self._editor.insert("1.0", self._library[name])
            self._highlight()

    def save_current(self) -> None:
        dialog = ctk.CTkInputDialog(text="Save query as:", title="Save to library")
        name = dialog.get_input()
        if name:
            self.ctx.sql.save_query(name, self._editor.get("1.0", "end-1c"))
            self._refresh_library()
            self.app.toast.show(f"Saved '{name}' to library", "ok")

    # ---- run / export ------------------------------------------------------
    def run(self) -> None:
        sql = self._editor.get("1.0", "end-1c").strip()
        connection = self._conn.get()
        if not sql:
            self.app.toast.show("Nothing to run", "error")
            return
        self._timer.configure(text="running…")

        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: self.ctx.sql.execute(connection, sql),
            self._render,
            self._failed,
        )

    def _failed(self, exc: BaseException) -> None:
        self._timer.configure(text="")
        self.app.toast.show(f"SQL error: {exc}", "error")

    def _render(self, record: ExecutionRecord) -> None:
        self._last = record
        note = "TRUNCATED — refine your query" if record.result.truncated else ""
        self._grid.show(record.result.frame, note=note)
        self._timer.configure(
            text=f"{record.result.rows:,} row(s) in " f"{record.result.duration_ms:,.0f} ms"
        )
        self.app.toast.show("Query finished", "ok")

    def export(self) -> None:
        if self._last is None:
            self.app.toast.show("Run a query first", "error")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
            initialfile="query_result.xlsx",
        )
        if not path:
            return
        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: self.ctx.sql.export(self._last, path),
            lambda p: self.app.toast.show(f"Exported: {p}", "ok"),
            self._failed,
        )
