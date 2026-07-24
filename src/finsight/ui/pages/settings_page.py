"""Settings page: appearance, thresholds, connections, email, backup."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ... import __version__
from ...core import credentials
from ...core.appdb import SavedConnection
from ...core.backup import create_backup, list_backups
from ...core.config import save_config
from ..widgets import Section, run_in_thread


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context
        config = self.ctx.config

        ctk.CTkLabel(self, text="Settings", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w", pady=(0, 8)
        )

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # ---- appearance ----------------------------------------------------
        appearance = Section(scroll, "Appearance")
        appearance.pack(fill="x", pady=4)
        row = ctk.CTkFrame(appearance.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Theme").pack(side="left", padx=(0, 8))
        self._theme = ctk.CTkSegmentedButton(row, values=["dark", "light"], command=self._set_theme)
        self._theme.set(config.ui.theme if config.ui.theme in ("dark", "light") else "dark")
        self._theme.pack(side="left")
        ctk.CTkLabel(row, text="Start page").pack(side="left", padx=(24, 8))
        self._start = ctk.CTkOptionMenu(
            row,
            values=["executive", "ask", "sql", "excel", "recon", "mis"],
            command=self._set_start,
        )
        self._start.set(config.ui.start_page)
        self._start.pack(side="left")

        # ---- branding -----------------------------------------------------
        branding = Section(scroll, "Branding (stamped on every report pack)")
        branding.pack(fill="x", pady=4)
        brand_row = ctk.CTkFrame(branding.body, fg_color="transparent")
        brand_row.pack(fill="x")
        ctk.CTkLabel(brand_row, text="Company name").pack(side="left", padx=(0, 8))
        self._company = ctk.CTkEntry(brand_row, width=320)
        if config.branding.company_name:
            self._company.insert(0, config.branding.company_name)
        self._company.pack(side="left")
        ctk.CTkButton(brand_row, text="💾 Save", width=80, command=self._save_branding).pack(
            side="left", padx=8
        )

        # ---- alert thresholds ------------------------------------------------
        thresholds = Section(scroll, "Executive alert thresholds")
        thresholds.pack(fill="x", pady=4)
        grid = ctk.CTkFrame(thresholds.body, fg_color="transparent")
        grid.pack(fill="x")
        self._par = self._threshold_field(
            grid, 0, "PAR alert above (%)", config.executive.par_alert_pct
        )
        self._eff = self._threshold_field(
            grid, 1, "Efficiency alert below (%)", config.executive.efficiency_alert_pct
        )
        self._conc = self._threshold_field(
            grid, 2, "Concentration alert above (%)", config.executive.concentration_alert_pct
        )
        ctk.CTkButton(
            thresholds.body, text="💾 Save thresholds", command=self._save_thresholds
        ).pack(anchor="e", pady=4)

        # ---- connections -------------------------------------------------------
        connections = Section(scroll, "Database connections (Azure SQL / MS SQL / SQLite)")
        connections.pack(fill="x", pady=4)
        self._conn_list = ctk.CTkLabel(
            connections.body, text="", anchor="w", justify="left", font=ctk.CTkFont(size=12)
        )
        self._conn_list.pack(fill="x")
        form = ctk.CTkFrame(connections.body, fg_color="transparent")
        form.pack(fill="x", pady=4)
        self._c_name = self._form_entry(form, 0, "Name")
        self._c_server = self._form_entry(form, 1, "Server (host or host,port)")
        self._c_db = self._form_entry(form, 2, "Database")
        self._c_user = self._form_entry(form, 3, "Username (blank = Windows auth)")
        self._c_pass = self._form_entry(form, 4, "Password", show="•")
        buttons = ctk.CTkFrame(connections.body, fg_color="transparent")
        buttons.pack(fill="x")
        ctk.CTkButton(buttons, text="＋ Save connection", command=self._save_connection).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            buttons,
            text="Test active connection",
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self._test_connection,
        ).pack(side="left", padx=4)
        self._active_menu = ctk.CTkOptionMenu(
            buttons, values=self._names(), command=self._switch_active
        )
        self._active_menu.set(self.ctx.active_connection)
        self._active_menu.pack(side="right", padx=4)
        ctk.CTkLabel(buttons, text="Active data source:").pack(side="right")

        # ---- email -----------------------------------------------------------------
        email = Section(scroll, "Email (for automated report delivery)")
        email.pack(fill="x", pady=4)
        email_grid = ctk.CTkFrame(email.body, fg_color="transparent")
        email_grid.pack(fill="x")
        self._smtp_host = self._form_entry(
            email_grid, 0, "SMTP host", value=self.ctx.config.email.smtp_host
        )
        self._smtp_port = self._form_entry(
            email_grid, 1, "Port", value=str(self.ctx.config.email.smtp_port)
        )
        self._smtp_sender = self._form_entry(
            email_grid, 2, "Sender address", value=self.ctx.config.email.sender
        )
        self._smtp_pass = self._form_entry(email_grid, 3, "Password (stored in vault)", show="•")
        ctk.CTkButton(email.body, text="💾 Save email settings", command=self._save_email).pack(
            anchor="e", pady=4
        )
        ctk.CTkLabel(
            email.body,
            text=f"Secret storage backend: {credentials.backend_name()}",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w")

        # ---- backup ------------------------------------------------------------------
        backup = Section(scroll, "Backup & data")
        backup.pack(fill="x", pady=4)
        backup_row = ctk.CTkFrame(backup.body, fg_color="transparent")
        backup_row.pack(fill="x")
        ctk.CTkButton(backup_row, text="⛃ Back up now", command=self._backup).pack(
            side="left", padx=4
        )
        self._backup_label = ctk.CTkLabel(
            backup_row, text=f"{len(list_backups())} backup(s) on disk", font=ctk.CTkFont(size=12)
        )
        self._backup_label.pack(side="left", padx=8)
        ctk.CTkLabel(
            backup.body,
            text="A backup also runs automatically every time you close FinSight.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w")

        ctk.CTkLabel(
            scroll,
            text=f"FinSight v{__version__}",
            font=ctk.CTkFont(size=11),
            text_color=("gray45", "gray60"),
        ).pack(anchor="w", pady=8)
        self._refresh_connections()

    # ---- small form helpers ---------------------------------------------------
    @staticmethod
    def _form_entry(
        master: tk.Misc, row: int, label: str, value: str = "", show: str | None = None
    ) -> ctk.CTkEntry:
        ctk.CTkLabel(master, text=label).grid(row=row, column=0, sticky="e", padx=6, pady=2)
        entry = ctk.CTkEntry(master, width=320, show=show)
        if value:
            entry.insert(0, value)
        entry.grid(row=row, column=1, sticky="w", padx=6, pady=2)
        return entry

    @staticmethod
    def _threshold_field(master: tk.Misc, row: int, label: str, value: float) -> ctk.CTkEntry:
        ctk.CTkLabel(master, text=label).grid(row=row, column=0, sticky="e", padx=6, pady=2)
        entry = ctk.CTkEntry(master, width=100)
        entry.insert(0, str(value))
        entry.grid(row=row, column=1, sticky="w", padx=6, pady=2)
        return entry

    def _names(self) -> list[str]:
        return [c.name for c in self.ctx.connections.list_connections()]

    # ---- handlers -----------------------------------------------------------------
    def _set_theme(self, value: str) -> None:
        if value != ctk.get_appearance_mode().lower():
            self.app.toggle_theme()

    def _set_start(self, value: str) -> None:
        self.ctx.config.ui.start_page = value
        save_config(self.ctx.config)
        self.app.toast.show(f"Start page set to {value}", "ok")

    def _save_branding(self) -> None:
        self.ctx.config.branding.company_name = self._company.get().strip()
        save_config(self.ctx.config)
        # Rebuild report generators so the new name applies immediately.
        self.ctx.use_connection(self.ctx.active_connection)
        self.app.toast.show("Branding saved — new reports will carry it", "ok")

    def _save_thresholds(self) -> None:
        try:
            self.ctx.config.executive.par_alert_pct = float(self._par.get())
            self.ctx.config.executive.efficiency_alert_pct = float(self._eff.get())
            self.ctx.config.executive.concentration_alert_pct = float(self._conc.get())
        except ValueError:
            self.app.toast.show("Thresholds must be numbers", "error")
            return
        save_config(self.ctx.config)
        self.app.toast.show("Thresholds saved", "ok")

    def _refresh_connections(self) -> None:
        lines = [f"• {c.name}  ({c.kind})" for c in self.ctx.connections.list_connections()]
        self._conn_list.configure(text="\n".join(lines))
        self._active_menu.configure(values=self._names())

    def _save_connection(self) -> None:
        name = self._c_name.get().strip()
        server = self._c_server.get().strip()
        database = self._c_db.get().strip()
        if not name or not server or not database:
            self.app.toast.show("Name, server, and database are required", "error")
            return
        user = self._c_user.get().strip()
        params = {"server": server, "database": database, "username": user, "trusted": not user}
        self.ctx.connections.save(
            SavedConnection(name=name, kind="mssql", params=params),
            password=self._c_pass.get() or None,
        )
        self._refresh_connections()
        self.app.toast.show(f"Connection '{name}' saved — password kept in vault", "ok")

    def _test_connection(self) -> None:
        name = self._active_menu.get()
        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: self.ctx.connections.test(name),
            lambda ok_msg: self.app.toast.show(
                f"{name}: {ok_msg[1]}", "ok" if ok_msg[0] else "error"
            ),
            lambda exc: self.app.toast.show(str(exc), "error"),
        )

    def _switch_active(self, name: str) -> None:
        self.ctx.use_connection(name)
        self.app.toast.show(f"All modules now use '{name}'", "ok")

    def _save_email(self) -> None:
        self.ctx.config.email.smtp_host = self._smtp_host.get().strip()
        try:
            self.ctx.config.email.smtp_port = int(self._smtp_port.get() or "587")
        except ValueError:
            self.app.toast.show("Port must be a number", "error")
            return
        self.ctx.config.email.sender = self._smtp_sender.get().strip()
        if self._smtp_pass.get():
            credentials.set_secret("smtp_password", self._smtp_pass.get())
        save_config(self.ctx.config)
        self.app.toast.show("Email settings saved", "ok")

    def _backup(self) -> None:
        run_in_thread(
            self,
            self.ctx.runner.submit,
            create_backup,
            lambda p: (
                self._backup_label.configure(text=f"{len(list_backups())} backup(s) on disk"),
                self.app.toast.show(f"Backup created: {p.name}", "ok"),
            ),
            lambda exc: self.app.toast.show(f"Backup failed: {exc}", "error"),
        )
