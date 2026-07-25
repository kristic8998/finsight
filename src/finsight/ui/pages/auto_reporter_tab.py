"""Visual Auto-Reporter tab — scheduling that looks like an alarm clock."""

from __future__ import annotations

import contextlib
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
import pandas as pd

from ...modules.auto_reporter import FREQUENCIES, WEEKDAYS, AutoReporter, ReportJob
from ...modules.mis_builder import list_reports
from ...modules.mis_templates import TEMPLATES
from ..widgets import DataGrid, HelperCard, Section, run_in_thread, show_friendly_error

_TEMPLATE_PREFIX = "Template: "
_BUILDER_PREFIX = "My report: "


class AutoReporterTab(ctk.CTkFrame):
    """Pick a report → pick a frequency & time → Activate Automation."""

    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._source_path = ""
        self._jobs: list[ReportJob] = []

        # One shared reporter per app, surviving tab rebuilds and stopped on close.
        reporter = app.context.extras.get("auto_reporter")
        if reporter is None:
            reporter = AutoReporter(on_event=self._event_from_thread)
            app.context.extras["auto_reporter"] = reporter
        else:
            reporter._on_event = self._event_from_thread  # rebind log to the live tab
        self.reporter: AutoReporter = reporter
        self.reporter.start()

        HelperCard(
            self,
            "How to use — like setting an alarm",
            (
                "Pick which report to automate — a one-click template or any recipe you "
                "saved in the Visual Builder — and the raw file it should read.",
                "Choose the frequency (Daily / Weekly / Monthly) and the time.",
                "Click “⏰ Activate Automation”. The report lands in your reports folder "
                "on schedule — while FinSight is open (it's a desktop app, not a server).",
            ),
        ).pack(fill="x", pady=(0, 8))

        form = Section(self, "New automation")
        form.pack(fill="x")
        row1 = ctk.CTkFrame(form.body, fg_color="transparent")
        row1.pack(fill="x")
        ctk.CTkLabel(row1, text="Report").pack(side="left", padx=(0, 6))
        self._report_menu = ctk.CTkOptionMenu(
            row1, values=self._report_options(), width=300, command=self._report_chosen
        )
        self._report_menu.pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            row1, text="Source file…", width=110, height=30, command=self._pick_source
        ).pack(side="left")
        self._source_label = ctk.CTkLabel(
            row1, text="no file chosen", text_color=("gray35", "gray65")
        )
        self._source_label.pack(side="left", padx=10)

        row2 = ctk.CTkFrame(form.body, fg_color="transparent")
        row2.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(row2, text="Every").pack(side="left", padx=(0, 6))
        self._frequency = ctk.CTkOptionMenu(
            row2, values=list(FREQUENCIES), width=110, command=lambda _v: self._update_hint()
        )
        self._frequency.pack(side="left", padx=(0, 10))
        self._weekday = ctk.CTkOptionMenu(
            row2, values=list(WEEKDAYS), width=120, command=lambda _v: self._update_hint()
        )
        self._weekday.pack(side="left", padx=(0, 10))
        self._monthday = ctk.CTkOptionMenu(
            row2,
            values=[str(d) for d in range(1, 29)],
            width=70,
            command=lambda _v: self._update_hint(),
        )
        self._monthday.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(row2, text="at").pack(side="left", padx=(0, 6))
        self._hour = ctk.CTkOptionMenu(
            row2,
            values=[f"{h:02d}" for h in range(24)],
            width=70,
            command=lambda _v: self._update_hint(),
        )
        self._hour.set("09")
        self._hour.pack(side="left", padx=(0, 4))
        self._minute = ctk.CTkOptionMenu(
            row2,
            values=["00", "15", "30", "45"],
            width=70,
            command=lambda _v: self._update_hint(),
        )
        self._minute.pack(side="left", padx=(0, 14))
        ctk.CTkButton(
            row2,
            text="⏰ Activate Automation",
            width=190,
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._activate,
        ).pack(side="left")
        self._hint = ctk.CTkLabel(
            form.body, text="", font=ctk.CTkFont(size=11), text_color=("gray45", "gray60")
        )
        self._hint.pack(anchor="w", pady=(4, 0))
        self._update_hint()

        jobs_section = Section(self, "Your automations (select a row to manage)")
        jobs_section.pack(fill="both", expand=True, pady=(8, 0))
        manage = ctk.CTkFrame(jobs_section.body, fg_color="transparent")
        manage.pack(fill="x")
        for text, handler in (
            ("▶ Run now", self._run_now),
            ("⏯ Enable / disable", self._toggle),
            ("🗑 Delete", self._delete),
            ("↻ Refresh list", self._refresh_jobs),
        ):
            ctk.CTkButton(
                manage,
                text=text,
                width=130,
                height=28,
                fg_color="transparent",
                border_width=1,
                text_color=("gray15", "gray90"),
                command=handler,
            ).pack(side="left", padx=3)
        self._grid = DataGrid(jobs_section.body, page_size=100)
        self._grid.pack(fill="both", expand=True, pady=(4, 0))

        log_section = Section(self, "Activity log")
        log_section.pack(fill="x", pady=(8, 0))
        self._log = ctk.CTkTextbox(log_section.body, height=96, wrap="none")
        self._log.pack(fill="both", expand=True)
        self._log.configure(state="disabled")

        self._refresh_jobs()

    # ---- form helpers ---------------------------------------------------------
    def _report_options(self) -> list[str]:
        options = [f"{_TEMPLATE_PREFIX}{spec.title}" for spec in TEMPLATES.values()]
        options += [f"{_BUILDER_PREFIX}{report.name}" for report in list_reports()]
        return options

    def on_show(self) -> None:
        """Refresh saved-recipe list whenever the tab becomes visible."""
        current = self._report_menu.get()
        options = self._report_options()
        self._report_menu.configure(values=options)
        if current not in options and options:
            self._report_menu.set(options[0])
        self._refresh_jobs()

    def _report_chosen(self, choice: str) -> None:
        if choice.startswith(_BUILDER_PREFIX):
            saved = next(
                (r for r in list_reports() if r.name == choice[len(_BUILDER_PREFIX) :]), None
            )
            if saved is not None and saved.source_path:
                self._source_path = saved.source_path
                self._source_label.configure(text=Path(saved.source_path).name)

    def _pick_source(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose the raw data file this automation should read",
            filetypes=[("Data files", "*.csv *.tsv *.xlsx *.xls"), ("All files", "*.*")],
        )
        if path:
            self._source_path = path
            self._source_label.configure(text=Path(path).name)

    def _update_hint(self) -> None:
        frequency = self._frequency.get()
        at = f"{self._hour.get()}:{self._minute.get()}"
        if frequency == "Weekly":
            text = f"Will run every {self._weekday.get()} at {at}."
        elif frequency == "Monthly":
            text = f"Will run on day {self._monthday.get()} of every month at {at}."
        else:
            text = f"Will run every day at {at}."
        self._hint.configure(text=text + " Reports save automatically to your reports folder.")

    # ---- activation -------------------------------------------------------------
    def _activate(self) -> None:
        choice = self._report_menu.get()
        if choice.startswith(_TEMPLATE_PREFIX):
            title = choice[len(_TEMPLATE_PREFIX) :]
            key = next((k for k, s in TEMPLATES.items() if s.title == title), "")
            kind, name = f"template:{key}", title
        elif choice.startswith(_BUILDER_PREFIX):
            name = choice[len(_BUILDER_PREFIX) :]
            kind = f"builder:{name}"
        else:
            show_friendly_error(self, "Pick a report to automate first.")
            return
        if not self._source_path:
            show_friendly_error(
                self,
                "Choose the source file this automation should read each time "
                "(the raw export your team refreshes).",
                title="One thing missing",
            )
            return
        job = ReportJob(
            name=name,
            kind=kind,
            source_path=self._source_path,
            frequency=self._frequency.get(),
            at=f"{self._hour.get()}:{self._minute.get()}",
            weekday=WEEKDAYS.index(self._weekday.get()),
            monthday=int(self._monthday.get()),
        )
        self.reporter.add_job(job)
        self._refresh_jobs()
        self.app.toast.show(f"Automation activated — {job.schedule_text()}", "ok")

    # ---- job management -----------------------------------------------------------
    def _refresh_jobs(self) -> None:
        self._jobs = self.reporter.jobs()
        frame = pd.DataFrame(
            [
                {
                    "name": job.name,
                    "schedule": job.schedule_text(),
                    "next run": job.next_run.replace("T", " "),
                    "last run": (job.last_run or "—").replace("T", " "),
                    "status": "on" if job.enabled else "paused",
                    "source": Path(job.source_path).name,
                }
                for job in self._jobs
            ],
            columns=["name", "schedule", "next run", "last run", "status", "source"],
        )
        self._grid.show(frame, note="automations run while FinSight is open")

    def _selected_job(self) -> ReportJob | None:
        index = self._grid.selected_index()
        if index is None or index >= len(self._jobs):
            show_friendly_error(
                self, "Select an automation in the list first.", title="No row selected"
            )
            return None
        return self._jobs[index]

    def _run_now(self) -> None:
        job = self._selected_job()
        if job is None:
            return
        self.app.toast.show(f"Running {job.name} now…")
        run_in_thread(
            self,
            self.app.context.runner.submit,
            lambda: self.reporter.run_job_now(job.job_id),
            lambda p: (self._refresh_jobs(), self.app.toast.show(f"Saved: {p}", "ok")),
            lambda exc: show_friendly_error(self, f"The report failed: {exc}"),
        )

    def _toggle(self) -> None:
        job = self._selected_job()
        if job is None:
            return
        self.reporter.set_enabled(job.job_id, not job.enabled)
        self._refresh_jobs()

    def _delete(self) -> None:
        job = self._selected_job()
        if job is None:
            return
        self.reporter.remove_job(job.job_id)
        self._refresh_jobs()
        self.app.toast.show(f"Deleted automation '{job.name}'", "ok")

    # ---- log ------------------------------------------------------------------------
    def _event_from_thread(self, line: str) -> None:
        # The tab may be destroyed while the reporter thread lives on; ignore that.
        with contextlib.suppress(Exception):
            self.after(0, self._append_log, line)

    def _append_log(self, line: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", line + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")
        self._refresh_jobs()
