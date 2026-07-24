"""Analytics page: forecast, anomalies, segmentation, risk scores."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from ..widgets import DataGrid, Section, run_in_thread


class AnalyticsPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context

        ctk.CTkLabel(self, text="AI Analytics", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            self,
            text="Transparent, auditable models — every result explains its method.",
            font=ctk.CTkFont(size=12),
            text_color=("gray35", "gray65"),
        ).pack(anchor="w", pady=(0, 8))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x")
        for label, handler in [
            ("📈 30-day collections forecast", self.forecast),
            ("⚠ Collection anomalies", self.anomalies),
            ("👥 Customer segments", self.segments),
            ("🎯 Loan risk scores", self.risk),
        ]:
            ctk.CTkButton(buttons, text=label, height=34, command=handler).pack(side="left", padx=4)

        self._explanation = ctk.CTkLabel(
            self, text="", anchor="w", justify="left", wraplength=1100, font=ctk.CTkFont(size=12)
        )
        self._explanation.pack(fill="x", pady=6)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        chart_section = Section(body, "Chart")
        chart_section.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._figure = Figure(figsize=(5, 3), dpi=100)
        self._axes = self._figure.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._figure, master=chart_section.body)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)

        data_section = Section(body, "Data")
        data_section.grid(row=0, column=1, sticky="nsew")
        self._grid = DataGrid(data_section.body, page_size=300)
        self._grid.pack(fill="both", expand=True)

    def _busy(self, what: str) -> None:
        self.app.toast.show(f"Running {what}…")

    def _failed(self, exc: BaseException) -> None:
        self.app.toast.show(f"Analytics failed: {exc}", "error")

    def _draw_clear(self) -> None:
        self._axes.clear()
        self._axes.grid(alpha=0.25)
        self._axes.tick_params(labelsize=8)

    # ---- runs -----------------------------------------------------------
    def forecast(self) -> None:
        self._busy("forecast")

        def done(result) -> None:  # noqa: ANN001
            self._draw_clear()
            history_dates = pd.to_datetime(result.history["date"])
            forecast_dates = pd.to_datetime(result.forecast["date"])
            self._axes.plot(
                history_dates, result.history["collected"], color="#2E7BE6", lw=1.2, label="actual"
            )
            self._axes.plot(
                forecast_dates,
                result.forecast["predicted"],
                color="#EF6C00",
                lw=1.6,
                ls="--",
                label="forecast",
            )
            self._axes.legend(fontsize=8)
            self._figure.autofmt_xdate()
            self._figure.tight_layout()
            self._canvas.draw_idle()
            self._grid.show(result.forecast)
            self._explanation.configure(text=result.explanation)
            self.app.toast.show("Forecast ready", "ok")

        run_in_thread(
            self,
            self.ctx.runner.submit,
            self.ctx.analytics.collections_forecast,
            done,
            self._failed,
        )

    def anomalies(self) -> None:
        self._busy("anomaly detection")

        def done(result) -> None:  # noqa: ANN001
            self._draw_clear()
            frame = result.frame
            if not frame.empty:
                self._axes.bar(
                    pd.to_datetime(frame["date"]).dt.strftime("%d %b"),
                    frame["collected"],
                    color="#C62828",
                )
            self._figure.tight_layout()
            self._canvas.draw_idle()
            self._grid.show(frame)
            self._explanation.configure(text=result.explanation)
            self.app.toast.show(f"{len(frame)} anomalous day(s) flagged", "ok")

        run_in_thread(
            self,
            self.ctx.runner.submit,
            self.ctx.analytics.collection_anomalies,
            done,
            self._failed,
        )

    def segments(self) -> None:
        self._busy("segmentation")

        def done(result) -> None:  # noqa: ANN001
            self._draw_clear()
            profile = result.profile
            self._axes.barh(profile["label"], profile["loans"], color="#2E7BE6")
            self._figure.tight_layout()
            self._canvas.draw_idle()
            self._grid.show(profile)
            self._explanation.configure(text=result.explanation)
            self.app.toast.show("Segments built", "ok")

        run_in_thread(
            self, self.ctx.runner.submit, self.ctx.analytics.customer_segments, done, self._failed
        )

    def risk(self) -> None:
        self._busy("risk scoring")

        def done(result) -> None:  # noqa: ANN001
            self._draw_clear()
            top = result.frame.head(15)
            self._axes.barh(
                top["loan_id"].astype(str)[::-1], top["risk_score"][::-1], color="#EF6C00"
            )
            self._axes.set_xlabel("risk score", fontsize=8)
            self._figure.tight_layout()
            self._canvas.draw_idle()
            self._grid.show(result.frame)
            self._explanation.configure(
                text=result.explanation + "  Top factors: " + ", ".join(result.top_factors)
            )
            self.app.toast.show("Risk scores computed", "ok")

        run_in_thread(
            self, self.ctx.runner.submit, self.ctx.analytics.loan_risk_scores, done, self._failed
        )
