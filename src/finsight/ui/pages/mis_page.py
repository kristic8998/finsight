"""MIS Reports page: one click → Excel + HTML executive packs."""

from __future__ import annotations

import tkinter as tk
import webbrowser

import customtkinter as ctk

from ...core.paths import reports_dir
from ...modules.mis import MisOutput
from ..widgets import Section, run_in_thread


class MisPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context
        self._last: MisOutput | None = None

        ctk.CTkLabel(self, text="MIS Generator", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            self,
            text="One click builds the full pack: styled Excel workbook + "
            "board-ready HTML (print → PDF from any browser).",
            font=ctk.CTkFont(size=12),
            text_color=("gray35", "gray65"),
        ).pack(anchor="w", pady=(0, 8))

        controls = Section(self, "Generate")
        controls.pack(fill="x")
        row = ctk.CTkFrame(controls.body, fg_color="transparent")
        row.pack(fill="x")
        self._period = ctk.CTkSegmentedButton(row, values=["daily", "weekly", "monthly"])
        self._period.set("daily")
        self._period.pack(side="left", padx=4, pady=4)
        ctk.CTkButton(
            row, text="▶ Generate MIS pack", height=34, width=180, command=self.generate
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            row,
            text="Open reports folder",
            height=34,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self._open_folder,
        ).pack(side="left", padx=4)
        self._open_html = ctk.CTkButton(
            row, text="Open HTML report", height=34, state="disabled", command=self._open_last
        )
        self._open_html.pack(side="left", padx=4)

        preview = Section(self, "Preview — executive summary & insights")
        preview.pack(fill="both", expand=True, pady=(8, 0))
        self._preview = ctk.CTkTextbox(preview.body, font=ctk.CTkFont(size=13), wrap="word")
        self._preview.pack(fill="both", expand=True)
        self._preview.insert("1.0", "Generate a pack to see the summary here.")
        self._preview.configure(state="disabled")

    def generate(self) -> None:
        period = self._period.get()
        self.app.toast.show(f"Generating {period} MIS…")

        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: self.ctx.mis.generate(period),
            self._render,
            self._failed,
        )

    def _failed(self, exc: BaseException) -> None:
        self.app.toast.show(f"MIS failed: {exc}", "error")

    def _render(self, output: MisOutput) -> None:
        self._last = output
        brief = output.brief
        lines = [
            f"EXECUTIVE SUMMARY — {brief.as_of}",
            "=" * 60,
            brief.summary_text,
            "",
            "INSIGHTS & RECOMMENDATIONS",
            "=" * 60,
        ]
        for insight in brief.insights:
            lines += [
                f"[{insight.severity.upper()}] {insight.title}",
                f"    {insight.detail}",
                f"    → {insight.recommendation}",
                "",
            ]
        lines += ["FILES", "=" * 60, f"Excel : {output.excel_path}", f"HTML  : {output.html_path}"]
        self._preview.configure(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.insert("1.0", "\n".join(lines))
        self._preview.configure(state="disabled")
        self._open_html.configure(state="normal")
        self.app.toast.show(f"MIS pack ready: {output.excel_path.name}", "ok")

    def _open_last(self) -> None:
        if self._last is not None:
            webbrowser.open(self._last.html_path.as_uri())

    def _open_folder(self) -> None:
        webbrowser.open(reports_dir().as_uri())
