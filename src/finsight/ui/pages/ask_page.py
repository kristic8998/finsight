"""Ask FinSight — natural-language query page."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from ...modules.nlq import EXAMPLES, NlqAnswer
from ..widgets import DataGrid, Section, run_in_thread


class AskPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context

        ctk.CTkLabel(self, text="Ask FinSight", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            self,
            text="Plain-English questions → SQL → answer. Offline and transparent: "
            "the generated query is always shown.",
            font=ctk.CTkFont(size=12),
            text_color=("gray35", "gray65"),
        ).pack(anchor="w", pady=(0, 8))

        ask_row = ctk.CTkFrame(self, fg_color="transparent")
        ask_row.pack(fill="x")
        self._question = ctk.CTkEntry(
            ask_row,
            placeholder_text='e.g. "show me branches with highest overdue"',
            height=38,
            font=ctk.CTkFont(size=13),
        )
        self._question.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._question.bind("<Return>", lambda _e: self.ask())
        ctk.CTkButton(ask_row, text="Ask", width=90, height=38, command=self.ask).pack(side="left")

        chips = ctk.CTkFrame(self, fg_color="transparent")
        chips.pack(fill="x", pady=(6, 4))
        for example in EXAMPLES[:6]:
            ctk.CTkButton(
                chips,
                text=example,
                height=24,
                corner_radius=12,
                fg_color="transparent",
                border_width=1,
                text_color=("gray25", "gray80"),
                font=ctk.CTkFont(size=11),
                command=lambda q=example: self._use_example(q),
            ).pack(side="left", padx=3)

        self._narrative = ctk.CTkLabel(
            self, text="", anchor="w", justify="left", wraplength=1100, font=ctk.CTkFont(size=13)
        )
        self._narrative.pack(fill="x", pady=(6, 6))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        result_section = Section(body, "Answer data")
        result_section.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._grid = DataGrid(result_section.body, page_size=200)
        self._grid.pack(fill="both", expand=True)

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=3)
        right.grid_rowconfigure(1, weight=2)
        right.grid_columnconfigure(0, weight=1)

        chart_section = Section(right, "Chart")
        chart_section.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self._figure = Figure(figsize=(4, 2.4), dpi=100)
        self._axes = self._figure.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._figure, master=chart_section.body)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)

        sql_section = Section(right, "Generated SQL / derivation")
        sql_section.grid(row=1, column=0, sticky="nsew")
        self._sql = ctk.CTkTextbox(
            sql_section.body, height=90, font=ctk.CTkFont(family="Consolas", size=11)
        )
        self._sql.pack(fill="both", expand=True)

    def _use_example(self, question: str) -> None:
        self._question.delete(0, "end")
        self._question.insert(0, question)
        self.ask()

    def ask(self) -> None:
        question = self._question.get().strip()
        if not question:
            self.app.toast.show("Type a question first", "error")
            return
        self.app.toast.show("Thinking…")
        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: self.ctx.nlq.ask(question),
            self._render,
            self._failed,
        )

    def _failed(self, exc: BaseException) -> None:
        self.app.toast.show(f"Question failed: {exc}", "error")

    def _render(self, answer: NlqAnswer) -> None:
        self._narrative.configure(text=answer.narrative)
        self._sql.delete("1.0", "end")
        self._sql.insert("1.0", answer.sql or "-- no query (question not recognised)")
        self._grid.show(
            answer.frame
            if not answer.frame.empty
            else pd.DataFrame({"try one of": answer.suggestions or EXAMPLES})
        )

        self._axes.clear()
        frame = answer.frame
        if answer.ok and not frame.empty and answer.chart in ("bar", "line"):
            x = frame.iloc[:, 0].astype(str)
            y = pd.to_numeric(frame.iloc[:, -1], errors="coerce").fillna(0)
            if answer.chart == "bar":
                self._axes.barh(x[::-1][:12], y[::-1][:12], color="#2E7BE6")
            else:
                self._axes.plot(range(len(y)), y, color="#2E7BE6", lw=1.4)
            self._axes.tick_params(labelsize=8)
            self._axes.grid(alpha=0.25)
        self._figure.tight_layout()
        self._canvas.draw_idle()
        self.app.toast.show(
            "Answered" if answer.ok else "Not recognised — see examples",
            "ok" if answer.ok else "error",
        )
