"""Shared UI building blocks: KPI cards, section frames, data grid, toasts."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

import customtkinter as ctk
import pandas as pd

ACCENT = "#2E7BE6"
GOOD = "#2E7D32"
WATCH = "#EF6C00"
ALERT = "#C62828"

SEVERITY_COLORS = {"good": GOOD, "watch": WATCH, "alert": ALERT}


class KpiCard(ctk.CTkFrame):
    """Rounded metric card: small label, big value, optional sub-line."""

    def __init__(self, master: tk.Misc, title: str, **kwargs: object) -> None:
        super().__init__(master, corner_radius=12, **kwargs)
        self._title = ctk.CTkLabel(
            self, text=title, font=ctk.CTkFont(size=12), text_color=("gray40", "gray70")
        )
        self._title.pack(anchor="w", padx=14, pady=(10, 0))
        self._value = ctk.CTkLabel(self, text="—", font=ctk.CTkFont(size=22, weight="bold"))
        self._value.pack(anchor="w", padx=14)
        self._sub = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), text_color=("gray45", "gray65")
        )
        self._sub.pack(anchor="w", padx=14, pady=(0, 10))

    def update_value(self, value: str, sub: str = "", color: str | None = None) -> None:
        self._value.configure(text=value, text_color=color if color else None)
        self._sub.configure(text=sub)


class HelperCard(ctk.CTkFrame):
    """Always-visible 'How to use' card with numbered steps (MIS Studio UX)."""

    def __init__(self, master: tk.Misc, title: str, steps: Sequence[str], **kwargs: object) -> None:
        super().__init__(master, corner_radius=12, border_width=1, border_color=ACCENT, **kwargs)
        ctk.CTkLabel(
            self,
            text=f"ⓘ  {title}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=ACCENT,
        ).pack(anchor="w", padx=14, pady=(10, 2))
        for number, step in enumerate(steps, start=1):
            ctk.CTkLabel(
                self,
                text=f"{number}.  {step}",
                font=ctk.CTkFont(size=12),
                anchor="w",
                justify="left",
                wraplength=1000,
            ).pack(anchor="w", padx=18, pady=1)
        ctk.CTkLabel(self, text="").pack(pady=(0, 4))  # bottom breathing room


class FriendlyDialog(ctk.CTkToplevel):
    """A friendly modal popup for user-facing problems — never a crash."""

    def __init__(self, parent: tk.Misc, title: str, message: str, kind: str = "error") -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        icon = {"error": "⚠", "info": "ℹ", "ok": "✔"}.get(kind, "ℹ")
        color = {"error": ALERT, "info": ACCENT, "ok": GOOD}.get(kind, ACCENT)
        ctk.CTkLabel(
            self,
            text=f"{icon}  {title}",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=color,
        ).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            self, text=message, font=ctk.CTkFont(size=12), wraplength=420, justify="left"
        ).pack(anchor="w", padx=20)
        ctk.CTkButton(self, text="OK, got it", width=110, command=self.destroy).pack(pady=(14, 16))
        self.update_idletasks()
        root = parent.winfo_toplevel()
        x = root.winfo_x() + (root.winfo_width() - self.winfo_width()) // 2
        y = root.winfo_y() + (root.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()


def show_friendly_error(parent: tk.Misc, message: str, title: str = "That didn't work") -> None:
    FriendlyDialog(parent, title, message, kind="error")


class Section(ctk.CTkFrame):
    """Titled rounded container."""

    def __init__(self, master: tk.Misc, title: str, **kwargs: object) -> None:
        super().__init__(master, corner_radius=12, **kwargs)
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=14, pady=(10, 4)
        )
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=10, pady=(0, 10))


class DataGrid(ctk.CTkFrame):
    """DataFrame viewer on ttk.Treeview with theme-aware styling.

    Shows up to ``page_size`` rows with a count banner — a deliberate
    guard for 16 GB laptops; exports always use the full frame.
    """

    def __init__(self, master: tk.Misc, page_size: int = 500, **kwargs: object) -> None:
        super().__init__(master, corner_radius=8, **kwargs)
        self._page_size = page_size
        self._frame: pd.DataFrame = pd.DataFrame()

        self._banner = ctk.CTkLabel(
            self, text="", anchor="w", font=ctk.CTkFont(size=11), text_color=("gray40", "gray70")
        )
        self._banner.pack(fill="x", padx=8, pady=(6, 0))

        container = tk.Frame(self, highlightthickness=0, bd=0)
        container.pack(fill="both", expand=True, padx=6, pady=6)
        self._tree = ttk.Treeview(container, show="headings", height=12)
        vsb = ttk.Scrollbar(container, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(container, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

    @property
    def frame(self) -> pd.DataFrame:
        return self._frame

    def selected_index(self) -> int | None:
        """Positional index (within the shown frame) of the selected row, if any."""
        selection = self._tree.selection()
        iids = getattr(self, "_iids", [])
        if not selection or selection[0] not in iids:
            return None
        return iids.index(selection[0])

    def show(self, frame: pd.DataFrame, note: str = "") -> None:
        self._frame = frame
        self._tree.delete(*self._tree.get_children())
        self._iids: list[str] = []
        columns = [str(c) for c in frame.columns]
        self._tree.configure(columns=columns)
        for column in columns:
            self._tree.heading(column, text=column)
            self._tree.column(column, width=max(90, min(240, 11 * len(column))), anchor="w")
        shown = frame.head(self._page_size)
        for _, row in shown.iterrows():
            iid = self._tree.insert("", "end", values=[_fmt(v) for v in row.tolist()])
            self._iids.append(iid)
        extra = f" (showing first {self._page_size:,})" if len(frame) > self._page_size else ""
        banner = f"{len(frame):,} row(s) × {len(columns)} column(s){extra}"
        if note:
            banner = f"{banner} — {note}"
        self._banner.configure(text=banner)


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}"
    return "" if value is None else str(value)


class Toast:
    """Transient status message in the shell's status bar."""

    def __init__(self, label: ctk.CTkLabel) -> None:
        self._label = label
        self._token = 0

    def show(self, message: str, kind: str = "info", ms: int = 5000) -> None:
        color = {"info": ("gray25", "gray80"), "ok": GOOD, "error": ALERT}.get(kind, ALERT)
        self._label.configure(text=message, text_color=color)
        self._token += 1
        token = self._token

        def clear() -> None:
            if self._token == token:
                self._label.configure(text="")

        self._label.after(ms, clear)


def style_treeview(dark: bool) -> None:
    """Make ttk.Treeview match the CTk theme (ttk has its own styling)."""
    style = ttk.Style()
    style.theme_use("clam")
    bg, fg, field = ("#23272e", "#e8e8e8", "#2b3038") if dark else ("#ffffff", "#1c2733", "#f4f6f9")
    style.configure(
        "Treeview", background=bg, foreground=fg, fieldbackground=bg, rowheight=26, borderwidth=0
    )
    style.configure(
        "Treeview.Heading",
        background=field,
        foreground=fg,
        borderwidth=0,
        font=("Segoe UI", 9, "bold"),
    )
    style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])


def run_in_thread(
    widget: tk.Misc,
    runner: Callable[[Callable[..., object], object], object],
    func: Callable[[], object],
    on_done: Callable[[object], None],
    on_error: Callable[[BaseException], None],
) -> None:
    """Submit work to the TaskRunner, marshalling callbacks onto the Tk thread."""
    runner(  # type: ignore[operator]
        func,
        on_done=lambda result: widget.after(0, lambda: on_done(result)),
        on_error=lambda exc: widget.after(0, lambda: on_error(exc)),
    )
