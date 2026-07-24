"""Executive Command Center page: the CEO morning screen."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from ...modules.executive import ExecutiveBrief
from ..widgets import SEVERITY_COLORS, DataGrid, KpiCard, Section, run_in_thread


class ExecutivePage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001 - app shell
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(
            header, text="Executive Command Center", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(header, text="↻ Refresh", width=100, command=self.refresh).pack(side="right")
        self._summary = ctk.CTkLabel(
            self,
            text="Loading today's brief…",
            anchor="w",
            justify="left",
            wraplength=1080,
            font=ctk.CTkFont(size=12),
        )
        self._summary.pack(fill="x", pady=(4, 8))

        cards_row = ctk.CTkFrame(self, fg_color="transparent")
        cards_row.pack(fill="x")
        self._cards: dict[str, KpiCard] = {}
        for key, title in [
            ("health", "Business Health"),
            ("portfolio", "Portfolio Outstanding"),
            ("collected", "Collected (MTD)"),
            ("efficiency", "Collection Efficiency"),
            ("overdue", "Overdue"),
            ("par", "PAR %"),
            ("npa", "NPA"),
            ("growth", "Growth MoM"),
        ]:
            card = KpiCard(cards_row, title)
            card.pack(side="left", expand=True, fill="x", padx=4)
            self._cards[key] = card

        middle = ctk.CTkFrame(self, fg_color="transparent")
        middle.pack(fill="both", expand=True, pady=(10, 0))
        middle.grid_columnconfigure(0, weight=3)
        middle.grid_columnconfigure(1, weight=2)
        middle.grid_rowconfigure(0, weight=1)

        chart_section = Section(middle, "Collections — last 90 days")
        chart_section.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._figure = Figure(figsize=(6, 2.6), dpi=100)
        self._axes = self._figure.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._figure, master=chart_section.body)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)

        insight_section = Section(middle, "Executive insights & recommendations")
        insight_section.grid(row=0, column=1, sticky="nsew")
        self._insights = ctk.CTkScrollableFrame(insight_section.body, fg_color="transparent")
        self._insights.pack(fill="both", expand=True)

        ranking = Section(self, "Branch ranking (score = 60% efficiency + 40% quality)")
        ranking.pack(fill="both", expand=True, pady=(10, 0))
        self._grid = DataGrid(ranking.body, page_size=100)
        self._grid.pack(fill="both", expand=True)

        self._loaded = False

    def on_show(self) -> None:
        if not self._loaded:
            self.refresh()

    def refresh(self) -> None:
        self.app.toast.show("Refreshing executive brief…")

        def work() -> tuple[ExecutiveBrief, object]:
            brief = self.ctx.executive.brief()
            trend = self.ctx.data.daily_collections(days=90)
            return brief, trend

        run_in_thread(self, self.ctx.runner.submit, work, self._render, self._failed)

    def _failed(self, exc: BaseException) -> None:
        self.app.toast.show(f"Refresh failed: {exc}", "error")

    def _render(self, payload) -> None:  # noqa: ANN001
        brief, trend = payload
        self._loaded = True
        kpis, health = brief.kpis, brief.health

        health_color = SEVERITY_COLORS[
            "good" if health.score >= 70 else "watch" if health.score >= 55 else "alert"
        ]
        self._cards["health"].update_value(
            f"{health.score:.0f} / 100", f"Grade {health.grade}", health_color
        )
        self._cards["portfolio"].update_value(
            f"₹{kpis.portfolio_outstanding:,.0f}", f"{kpis.active_loans} active loans"
        )
        self._cards["collected"].update_value(
            f"₹{kpis.collected_mtd:,.0f}", f"of ₹{kpis.due_mtd:,.0f} due"
        )
        self._cards["efficiency"].update_value(
            f"{kpis.efficiency_mtd:.1f}%", f"target ach. {kpis.target_achievement:.0f}%"
        )
        self._cards["overdue"].update_value(f"₹{kpis.overdue_amount:,.0f}", "past-due unpaid")
        self._cards["par"].update_value(
            f"{kpis.par_pct:.1f}%",
            "portfolio at risk",
            (
                SEVERITY_COLORS["alert"]
                if kpis.par_pct > self.ctx.config.executive.par_alert_pct
                else None
            ),
        )
        self._cards["npa"].update_value(f"{kpis.npa_loans}", f"₹{kpis.npa_amount:,.0f} exposure")
        self._cards["growth"].update_value(
            f"{kpis.growth_mom_pct:+.1f}%",
            "disbursement MoM",
            SEVERITY_COLORS["alert"] if kpis.growth_mom_pct < 0 else SEVERITY_COLORS["good"],
        )

        self._summary.configure(text=brief.summary_text)

        self._axes.clear()
        import pandas as pd

        dates = pd.to_datetime(trend["date"])
        self._axes.plot(dates, trend["collected"], color="#2E7BE6", lw=1.4)
        self._axes.fill_between(dates, trend["collected"], color="#2E7BE6", alpha=0.15)
        self._axes.grid(alpha=0.25)
        self._axes.tick_params(labelsize=8)
        self._figure.autofmt_xdate()
        self._figure.tight_layout()
        self._canvas.draw_idle()

        for child in self._insights.winfo_children():
            child.destroy()
        for insight in brief.insights:
            row = ctk.CTkFrame(self._insights, corner_radius=8)
            row.pack(fill="x", pady=3)
            bar = ctk.CTkFrame(
                row, width=5, corner_radius=2, fg_color=SEVERITY_COLORS[insight.severity]
            )
            bar.pack(side="left", fill="y", padx=(6, 8), pady=6)
            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True, pady=4)
            ctk.CTkLabel(
                text, text=insight.title, anchor="w", font=ctk.CTkFont(size=12, weight="bold")
            ).pack(fill="x")
            ctk.CTkLabel(
                text,
                text=f"{insight.detail}\n→ {insight.recommendation}",
                anchor="w",
                justify="left",
                wraplength=360,
                font=ctk.CTkFont(size=11),
                text_color=("gray35", "gray70"),
            ).pack(fill="x")

        self._grid.show(brief.branches)
        self.app.toast.show("Executive brief updated", "ok")
