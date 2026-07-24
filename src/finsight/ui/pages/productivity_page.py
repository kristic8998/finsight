"""Productivity page: notes, kanban tasks, pinned favorites."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ..widgets import Section


class ProductivityPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context
        self._current_note: int | None = None

        ctk.CTkLabel(self, text="Productivity", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w", pady=(0, 8)
        )

        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True)
        tabs.add("Tasks")
        tabs.add("Notes")

        # ---- tasks: 3-column kanban ------------------------------------
        board_frame = tabs.tab("Tasks")
        entry_row = ctk.CTkFrame(board_frame, fg_color="transparent")
        entry_row.pack(fill="x", pady=(4, 6))
        self._new_task = ctk.CTkEntry(entry_row, placeholder_text="New task…")
        self._new_task.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._new_task.bind("<Return>", lambda _e: self.add_task())
        ctk.CTkButton(entry_row, text="＋ Add", width=80, command=self.add_task).pack(side="left")

        columns = ctk.CTkFrame(board_frame, fg_color="transparent")
        columns.pack(fill="both", expand=True)
        columns.grid_columnconfigure((0, 1, 2), weight=1)
        columns.grid_rowconfigure(0, weight=1)
        self._columns: dict[str, ctk.CTkScrollableFrame] = {}
        for index, (status, title) in enumerate(
            [("todo", "📋 To do"), ("doing", "⚙ In progress"), ("done", "✔ Done")]
        ):
            section = Section(columns, title)
            section.grid(row=0, column=index, sticky="nsew", padx=4)
            holder = ctk.CTkScrollableFrame(section.body, fg_color="transparent")
            holder.pack(fill="both", expand=True)
            self._columns[status] = holder

        # ---- notes ------------------------------------------------------
        notes_frame = tabs.tab("Notes")
        notes_frame.grid_columnconfigure(1, weight=1)
        notes_frame.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(notes_frame, width=240)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 8), pady=4)
        self._notes_list = tk.Listbox(
            left,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            width=30,
        )
        self._notes_list.pack(fill="both", expand=True, padx=6, pady=6)
        self._notes_list.bind("<<ListboxSelect>>", self._open_note)
        note_buttons = ctk.CTkFrame(left, fg_color="transparent")
        note_buttons.pack(fill="x", padx=6, pady=(0, 6))
        ctk.CTkButton(note_buttons, text="＋ New", width=70, command=self.new_note).pack(
            side="left", padx=2
        )
        ctk.CTkButton(
            note_buttons,
            text="🗑 Delete",
            width=80,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self.delete_note,
        ).pack(side="left", padx=2)

        editor = ctk.CTkFrame(notes_frame)
        editor.grid(row=0, column=1, sticky="nsew", pady=4)
        self._note_title = ctk.CTkEntry(
            editor, placeholder_text="Title", font=ctk.CTkFont(size=14, weight="bold")
        )
        self._note_title.pack(fill="x", padx=8, pady=(8, 4))
        self._note_body = ctk.CTkTextbox(editor, wrap="word", font=ctk.CTkFont(size=12))
        self._note_body.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        ctk.CTkButton(editor, text="💾 Save note (Ctrl+S)", command=self.save_note).pack(
            anchor="e", padx=8, pady=(0, 8)
        )
        self.bind_all("<Control-s>", lambda _e: self.save_note(), add="+")

    def on_show(self) -> None:
        self._refresh_board()
        self._refresh_notes()

    # ---- tasks -------------------------------------------------------------
    def add_task(self) -> None:
        title = self._new_task.get().strip()
        if not title:
            return
        self.ctx.productivity.add_task(title)
        self._new_task.delete(0, "end")
        self._refresh_board()

    def _refresh_board(self) -> None:
        board = self.ctx.productivity.board()
        moves = {"todo": ("doing", "Start ▸"), "doing": ("done", "Finish ✔"), "done": (None, None)}
        for status, holder in self._columns.items():
            for child in holder.winfo_children():
                child.destroy()
            for task in getattr(board, status):
                card = ctk.CTkFrame(holder, corner_radius=8)
                card.pack(fill="x", pady=3)
                ctk.CTkLabel(
                    card, text=task["title"], anchor="w", wraplength=220, font=ctk.CTkFont(size=12)
                ).pack(fill="x", padx=8, pady=(6, 2))
                buttons = ctk.CTkFrame(card, fg_color="transparent")
                buttons.pack(fill="x", padx=6, pady=(0, 6))
                next_status, label = moves[status]
                if next_status:
                    ctk.CTkButton(
                        buttons,
                        text=label,
                        height=22,
                        width=76,
                        font=ctk.CTkFont(size=11),
                        command=lambda t=task["id"], s=next_status: self._move(t, s),
                    ).pack(side="left", padx=2)
                ctk.CTkButton(
                    buttons,
                    text="🗑",
                    height=22,
                    width=30,
                    fg_color="transparent",
                    border_width=1,
                    text_color=("gray15", "gray90"),
                    command=lambda t=task["id"]: self._delete_task(t),
                ).pack(side="right", padx=2)

    def _move(self, task_id: int, status: str) -> None:
        self.ctx.productivity.move_task(task_id, status)
        self._refresh_board()

    def _delete_task(self, task_id: int) -> None:
        self.ctx.productivity.delete_task(task_id)
        self._refresh_board()

    # ---- notes -----------------------------------------------------------------
    def _refresh_notes(self) -> None:
        self._notes = self.ctx.productivity.notes()
        self._notes_list.delete(0, "end")
        for note in self._notes:
            self._notes_list.insert("end", f" {note['title']}")

    def _open_note(self, _event: tk.Event) -> None:
        selection = self._notes_list.curselection()
        if not selection:
            return
        note = self._notes[selection[0]]
        self._current_note = note["id"]
        self._note_title.delete(0, "end")
        self._note_title.insert(0, note["title"])
        self._note_body.delete("1.0", "end")
        self._note_body.insert("1.0", note["body"])

    def new_note(self) -> None:
        self._current_note = None
        self._note_title.delete(0, "end")
        self._note_body.delete("1.0", "end")
        self._note_title.focus_set()

    def save_note(self) -> None:
        title = self._note_title.get().strip()
        if not title:
            return
        body = self._note_body.get("1.0", "end-1c")
        self._current_note = self.ctx.productivity.save_note(title, body, self._current_note)
        self._refresh_notes()
        self.app.toast.show("Note saved", "ok")

    def delete_note(self) -> None:
        if self._current_note is not None:
            self.ctx.productivity.delete_note(self._current_note)
            self.new_note()
            self._refresh_notes()
