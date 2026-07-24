"""Automation Center page: jobs, schedules, folder watches, run log."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
import pandas as pd

from ...modules.automation import Schedule, Watch
from ..widgets import DataGrid, Section, run_in_thread


class AutomationPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(
            header, text="Automation Center", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left")
        self._engine_switch = ctk.CTkSwitch(
            header, text="Scheduler running", command=self._toggle_engine
        )
        self._engine_switch.pack(side="right")
        if self.ctx.config.automation.enabled:
            self._engine_switch.select()

        columns = ctk.CTkFrame(self, fg_color="transparent")
        columns.pack(fill="x", pady=(8, 0))
        columns.grid_columnconfigure((0, 1, 2), weight=1)

        jobs = Section(columns, "Jobs — run now")
        jobs.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._job_menu = ctk.CTkOptionMenu(
            jobs.body, values=self.ctx.automation.job_names() or ["-"]
        )
        self._job_menu.pack(fill="x", pady=4)
        ctk.CTkButton(jobs.body, text="▶ Run selected job now", command=self.run_now).pack(
            fill="x", pady=4
        )

        schedule = Section(columns, "Add schedule")
        schedule.grid(row=0, column=1, sticky="nsew", padx=6)
        self._sched_job = ctk.CTkOptionMenu(
            schedule.body, values=self.ctx.automation.job_names() or ["-"]
        )
        self._sched_job.pack(fill="x", pady=3)
        row = ctk.CTkFrame(schedule.body, fg_color="transparent")
        row.pack(fill="x")
        self._mode = ctk.CTkSegmentedButton(row, values=["daily at", "every (min)"])
        self._mode.set("daily at")
        self._mode.pack(side="left", padx=(0, 6))
        self._when = ctk.CTkEntry(row, width=90, placeholder_text="07:30")
        self._when.pack(side="left")
        ctk.CTkButton(schedule.body, text="＋ Add schedule", command=self.add_schedule).pack(
            fill="x", pady=4
        )

        watch = Section(columns, "Watch a folder")
        watch.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        self._watch_job = ctk.CTkOptionMenu(
            watch.body, values=self.ctx.automation.job_names() or ["-"]
        )
        self._watch_job.pack(fill="x", pady=3)
        self._pattern = ctk.CTkEntry(watch.body, placeholder_text="pattern e.g. *.xlsx")
        self._pattern.pack(fill="x", pady=3)
        ctk.CTkButton(watch.body, text="＋ Choose folder & watch", command=self.add_watch).pack(
            fill="x", pady=4
        )

        active = Section(self, "Active schedules & watches")
        active.pack(fill="x", pady=(8, 0))
        self._active_label = ctk.CTkLabel(
            active.body, text="none yet", anchor="w", justify="left", font=ctk.CTkFont(size=12)
        )
        self._active_label.pack(fill="x")

        log = Section(self, "Run log (latest first)")
        log.pack(fill="both", expand=True, pady=(8, 0))
        self._log_grid = DataGrid(log.body, page_size=200)
        self._log_grid.pack(fill="both", expand=True)
        ctk.CTkButton(
            log.body, text="↻ Refresh log", height=26, width=110, command=self.refresh
        ).pack(anchor="e", pady=(4, 0))

    def on_show(self) -> None:
        names = self.ctx.automation.job_names() or ["-"]
        for menu in (self._job_menu, self._sched_job, self._watch_job):
            menu.configure(values=names)
        self.refresh()

    def _toggle_engine(self) -> None:
        if self._engine_switch.get():
            self.ctx.automation.start()
            self.app.toast.show("Scheduler started", "ok")
        else:
            self.ctx.automation.stop()
            self.app.toast.show("Scheduler stopped", "ok")

    def run_now(self) -> None:
        job = self._job_menu.get()
        self.app.toast.show(f"Running '{job}'…")
        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: self.ctx.automation.run_job(job),
            lambda detail: (self.refresh(), self.app.toast.show(f"✔ {detail}", "ok")),
            lambda exc: (self.refresh(), self.app.toast.show(f"Job failed: {exc}", "error")),
        )

    def add_schedule(self) -> None:
        job = self._sched_job.get()
        when = self._when.get().strip()
        try:
            if self._mode.get() == "daily at":
                if ":" not in when:
                    raise ValueError("time must look like 07:30")
                self.ctx.automation.add_schedule(Schedule(job=job, daily_at=when))
            else:
                self.ctx.automation.add_schedule(Schedule(job=job, every_minutes=max(1, int(when))))
        except (ValueError, TypeError) as exc:
            self.app.toast.show(f"Cannot add schedule: {exc}", "error")
            return
        self._refresh_active()
        self.app.toast.show("Schedule added — switch the scheduler on to arm it", "ok")

    def add_watch(self) -> None:
        folder = filedialog.askdirectory(title="Folder to watch")
        if not folder:
            return
        pattern = self._pattern.get().strip() or "*.*"
        try:
            self.ctx.automation.add_watch(
                Watch(folder=folder, pattern=pattern, job=self._watch_job.get())
            )
        except ValueError as exc:
            self.app.toast.show(str(exc), "error")
            return
        self._refresh_active()
        self.app.toast.show(f"Watching {folder} for {pattern}", "ok")

    def _refresh_active(self) -> None:
        lines = []
        for schedule in self.ctx.automation.schedules():
            when = (
                f"daily at {schedule.daily_at}"
                if schedule.daily_at
                else f"every {schedule.every_minutes} min"
            )
            lines.append(f"⏰ {schedule.job} — {when}")
        for watch in self.ctx.automation.watches():
            lines.append(f"👁 {watch.job} — on new '{watch.pattern}' in {watch.folder}")
        self._active_label.configure(text="\n".join(lines) if lines else "none yet")

    def refresh(self) -> None:
        self._refresh_active()
        runs = self.ctx.appdb.job_runs(limit=100)
        frame = (
            pd.DataFrame(runs)
            if runs
            else pd.DataFrame({"job": [], "status": [], "detail": [], "started_at": []})
        )
        self._log_grid.show(frame)
