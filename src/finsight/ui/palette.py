"""Command palette (Ctrl+K): VS Code-style fuzzy action launcher."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ..core.registry import Registry


class CommandPalette(ctk.CTkToplevel):
    """Modal search-and-run overlay driven by the action registry."""

    def __init__(self, master: tk.Misc, registry: Registry) -> None:
        super().__init__(master)
        self._registry = registry
        self._actions: list = []

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        width = 560
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + 90
        self.geometry(f"{width}x340+{max(x, 0)}+{max(y, 0)}")

        frame = ctk.CTkFrame(self, corner_radius=12, border_width=1)
        frame.pack(fill="both", expand=True)

        self._entry = ctk.CTkEntry(
            frame,
            placeholder_text="Type a command or page name…  (Esc to close)",
            height=38,
            font=ctk.CTkFont(size=14),
        )
        self._entry.pack(fill="x", padx=10, pady=(10, 6))
        self._entry.bind("<KeyRelease>", self._refresh)
        self._entry.bind("<Return>", self._run_selected)
        self._entry.bind("<Escape>", lambda _e: self.destroy())
        self._entry.bind("<Down>", self._move(1))
        self._entry.bind("<Up>", self._move(-1))

        self._listbox = tk.Listbox(
            frame,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 11),
            height=10,
        )
        self._listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._listbox.bind("<Double-Button-1>", self._run_selected)
        self._listbox.bind("<Return>", self._run_selected)
        self._listbox.bind("<Escape>", lambda _e: self.destroy())

        self.bind("<FocusOut>", self._maybe_close)
        self._refresh()
        self._entry.focus_set()

    def _maybe_close(self, _event: tk.Event) -> None:
        # Close only when focus leaves the palette entirely.
        self.after(120, lambda: None if self.focus_get() else self.destroy())

    def _refresh(self, _event: tk.Event | None = None) -> None:
        query = self._entry.get()
        self._actions = self._registry.search(query, limit=14)
        self._listbox.delete(0, "end")
        for action in self._actions:
            module = self._registry.modules.get(action.category)
            prefix = module.title if module else action.category
            self._listbox.insert("end", f"  {prefix}  ›  {action.title}")
        if self._actions:
            self._listbox.selection_set(0)

    def _move(self, delta: int):
        def handler(_event: tk.Event) -> str:
            if not self._actions:
                return "break"
            current = self._listbox.curselection()
            index = (current[0] if current else 0) + delta
            index = max(0, min(len(self._actions) - 1, index))
            self._listbox.selection_clear(0, "end")
            self._listbox.selection_set(index)
            self._listbox.see(index)
            return "break"

        return handler

    def _run_selected(self, _event: tk.Event | None = None) -> None:
        selection = self._listbox.curselection()
        if not selection or not self._actions:
            return
        action = self._actions[selection[0]]
        self.destroy()
        action.run()
