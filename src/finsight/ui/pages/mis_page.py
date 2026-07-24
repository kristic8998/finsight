"""MIS Reports page: full packs, the business-report catalog, custom
templates, and recent reports — the analyst's daily report desk."""

from __future__ import annotations

import tkinter as tk
import webbrowser

import customtkinter as ctk

from ...core.paths import reports_dir
from ...modules.mis import MisOutput
from ...modules.mis_catalog import CatalogOutput, recent_reports
from ..widgets import Section, run_in_thread


class MisPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context
        self._last_pack: MisOutput | None = None

        ctk.CTkLabel(self, text="MIS Generator", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            self,
            text="Full executive packs, named business MIS reports, and your own "
            "custom templates — one click each.",
            font=ctk.CTkFont(size=12),
            text_color=("gray35", "gray65"),
        ).pack(anchor="w", pady=(0, 8))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # ---- full executive pack ------------------------------------------
        pack = Section(scroll, "Executive pack (KPIs + insights + trend chart)")
        pack.pack(fill="x", pady=4)
        pack_row = ctk.CTkFrame(pack.body, fg_color="transparent")
        pack_row.pack(fill="x")
        self._period = ctk.CTkSegmentedButton(pack_row, values=["daily", "weekly", "monthly"])
        self._period.set("daily")
        self._period.pack(side="left", padx=4, pady=4)
        ctk.CTkButton(
            pack_row, text="▶ Generate pack", height=32, width=150, command=self.generate_pack
        ).pack(side="left", padx=6)
        self._open_html = ctk.CTkButton(
            pack_row,
            text="Open HTML report",
            height=32,
            state="disabled",
            command=self._open_last_html,
        )
        self._open_html.pack(side="left", padx=4)

        # ---- business report catalog ----------------------------------------
        catalog = Section(scroll, "Business MIS catalog")
        catalog.pack(fill="x", pady=4)
        cat_row = ctk.CTkFrame(catalog.body, fg_color="transparent")
        cat_row.pack(fill="x")
        names = self.ctx.mis_catalog.report_names()
        self._report_titles = {title: rid for rid, title in names.items()}
        self._report_menu = ctk.CTkOptionMenu(cat_row, values=list(names.values()), width=240)
        self._report_menu.pack(side="left", padx=4, pady=4)
        ctk.CTkLabel(cat_row, text="Window (days)").pack(side="left", padx=(10, 4))
        self._days = ctk.CTkEntry(cat_row, width=60)
        self._days.insert(0, "30")
        self._days.pack(side="left")
        self._format = ctk.CTkSegmentedButton(cat_row, values=["xlsx", "csv"], width=120)
        self._format.set("xlsx")
        self._format.pack(side="left", padx=10)
        ctk.CTkButton(
            cat_row, text="▶ Generate report", height=32, width=150, command=self.generate_catalog
        ).pack(side="left", padx=6)

        # ---- custom templates -----------------------------------------------
        template = Section(scroll, "Custom templates — build your own MIS once, reuse daily")
        template.pack(fill="x", pady=4)
        boxes = ctk.CTkFrame(template.body, fg_color="transparent")
        boxes.pack(fill="x")
        self._section_vars: dict[str, ctk.BooleanVar] = {}
        sections = self.ctx.mis_catalog.sections
        for index, (section_id, (title, _b)) in enumerate(sections.items()):
            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(boxes, text=title, variable=var, font=ctk.CTkFont(size=11)).grid(
                row=index // 4, column=index % 4, sticky="w", padx=6, pady=2
            )
            self._section_vars[section_id] = var

        template_row = ctk.CTkFrame(template.body, fg_color="transparent")
        template_row.pack(fill="x", pady=(6, 0))
        self._template_name = ctk.CTkEntry(
            template_row, width=200, placeholder_text="Template name"
        )
        self._template_name.pack(side="left", padx=4)
        ctk.CTkButton(
            template_row, text="💾 Save template", height=30, command=self.save_template
        ).pack(side="left", padx=4)
        self._template_menu = ctk.CTkOptionMenu(template_row, values=["(none saved)"], width=200)
        self._template_menu.pack(side="left", padx=(16, 4))
        ctk.CTkButton(
            template_row, text="▶ Generate from template", height=30, command=self.generate_template
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            template_row,
            text="🗑",
            height=30,
            width=34,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self.delete_template,
        ).pack(side="left", padx=2)

        # ---- output + recent -------------------------------------------------
        self._status = ctk.CTkLabel(
            scroll, text="", anchor="w", justify="left", wraplength=1080, font=ctk.CTkFont(size=12)
        )
        self._status.pack(fill="x", pady=6)

        recent = Section(scroll, "Recent reports")
        recent.pack(fill="both", expand=True, pady=4)
        recent_buttons = ctk.CTkFrame(recent.body, fg_color="transparent")
        recent_buttons.pack(fill="x")
        ctk.CTkButton(
            recent_buttons,
            text="Open reports folder",
            height=28,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=lambda: webbrowser.open(reports_dir().as_uri()),
        ).pack(side="right", pady=2)
        self._recent_box = tk.Listbox(
            recent.body,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            height=8,
        )
        self._recent_box.pack(fill="both", expand=True, pady=4)
        self._recent_box.bind("<Double-Button-1>", self._open_recent)

    # ---- helpers -----------------------------------------------------------
    def on_show(self) -> None:
        self._refresh_templates()
        self._refresh_recent()

    def _refresh_templates(self) -> None:
        names = list(self.ctx.mis_catalog.templates()) or ["(none saved)"]
        self._template_menu.configure(values=names)
        self._template_menu.set(names[0])

    def _refresh_recent(self) -> None:
        self._recent_files = recent_reports(limit=12)
        self._recent_box.delete(0, "end")
        for path in self._recent_files:
            self._recent_box.insert("end", f" {path.name}")

    def _open_recent(self, _event: tk.Event) -> None:
        selection = self._recent_box.curselection()
        if selection:
            webbrowser.open(self._recent_files[selection[0]].as_uri())

    def _days_value(self) -> int:
        try:
            return max(1, min(365, int(self._days.get() or "30")))
        except ValueError:
            return 30

    def _failed(self, exc: BaseException) -> None:
        self.app.toast.show(f"Report failed: {exc}", "error")

    # ---- actions ---------------------------------------------------------------
    def generate_pack(self) -> None:
        period = self._period.get()
        self.app.toast.show(f"Generating {period} executive pack…")
        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: self.ctx.mis.generate(period),
            self._pack_done,
            self._failed,
        )

    def _pack_done(self, output: MisOutput) -> None:
        self._last_pack = output
        self._open_html.configure(state="normal")
        self._status.configure(
            text=f"✔ {output.brief.summary_text}\nFiles: {output.excel_path.name}, "
            f"{output.html_path.name}"
        )
        self._refresh_recent()
        self.app.toast.show("Executive pack ready", "ok")

    def _open_last_html(self) -> None:
        if self._last_pack is not None:
            webbrowser.open(self._last_pack.html_path.as_uri())

    def generate_catalog(self) -> None:
        report_id = self._report_titles[self._report_menu.get()]
        days, fmt = self._days_value(), self._format.get()
        self.app.toast.show(f"Generating {self._report_menu.get()}…")
        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: self.ctx.mis_catalog.build(report_id, days=days, fmt=fmt),
            self._catalog_done,
            self._failed,
        )

    def _catalog_done(self, output: CatalogOutput) -> None:
        self._status.configure(text=f"✔ {output.summary}")
        self._refresh_recent()
        self.app.toast.show(f"{output.report} ready", "ok")

    def save_template(self) -> None:
        chosen = [sid for sid, var in self._section_vars.items() if var.get()]
        try:
            self.ctx.mis_catalog.save_template(self._template_name.get(), chosen)
        except Exception as exc:
            self.app.toast.show(str(exc), "error")
            return
        self._refresh_templates()
        self.app.toast.show(f"Template '{self._template_name.get().strip()}' saved", "ok")

    def generate_template(self) -> None:
        name = self._template_menu.get()
        if name == "(none saved)":
            self.app.toast.show("Save a template first", "error")
            return
        days, fmt = self._days_value(), self._format.get()
        self.app.toast.show(f"Generating template '{name}'…")
        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: self.ctx.mis_catalog.build_from_template(name, days=days, fmt=fmt),
            self._catalog_done,
            self._failed,
        )

    def delete_template(self) -> None:
        name = self._template_menu.get()
        if name != "(none saved)":
            self.ctx.mis_catalog.delete_template(name)
            self._refresh_templates()
            self.app.toast.show(f"Template '{name}' deleted", "ok")
