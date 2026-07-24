"""Productivity service: notes, tasks, and favorites over the app DB.

Thin by design — AppDB owns storage; this layer adds validation and the
small amount of shaping the UI needs (kanban grouping, favorite jump
targets), keeping pages dumb and testable logic here.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.appdb import AppDB

TASK_COLUMNS = ("todo", "doing", "done")


@dataclass
class Board:
    todo: list[dict]
    doing: list[dict]
    done: list[dict]


class ProductivityService:
    def __init__(self, appdb: AppDB) -> None:
        self._db = appdb

    # ---- notes ----------------------------------------------------------
    def save_note(self, title: str, body: str, note_id: int | None = None) -> int:
        if not title.strip():
            raise ValueError("note title is required")
        return self._db.upsert_note(title.strip(), body, note_id)

    def notes(self) -> list[dict]:
        return self._db.notes()

    def delete_note(self, note_id: int) -> None:
        self._db.delete_note(note_id)

    # ---- tasks ------------------------------------------------------------
    def add_task(self, title: str, due: str | None = None) -> int:
        if not title.strip():
            raise ValueError("task title is required")
        return self._db.add_task(title.strip(), due)

    def move_task(self, task_id: int, status: str) -> None:
        self._db.set_task_status(task_id, status)

    def delete_task(self, task_id: int) -> None:
        self._db.delete_task(task_id)

    def board(self) -> Board:
        tasks = self._db.tasks()
        return Board(
            todo=[t for t in tasks if t["status"] == "todo"],
            doing=[t for t in tasks if t["status"] == "doing"],
            done=[t for t in tasks if t["status"] == "done"],
        )

    # ---- favorites ------------------------------------------------------------
    def pin(self, kind: str, ref: str, label: str) -> None:
        self._db.add_favorite(kind, ref, label)

    def unpin(self, kind: str, ref: str) -> None:
        self._db.remove_favorite(kind, ref)

    def pinned(self, kind: str | None = None) -> list[dict]:
        return self._db.favorites(kind)
