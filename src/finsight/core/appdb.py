"""Application-state store (SQLite).

One small database owns everything the app remembers between sessions:
settings overrides, query history, saved queries, notes, tasks,
favorites, and automation job runs. Thread-safe via a shared lock and
WAL mode; every method is small and directly testable.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import appdb_path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS query_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection TEXT NOT NULL, sql TEXT NOT NULL,
    rows INTEGER NOT NULL, duration_ms REAL NOT NULL, ran_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saved_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL, sql TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'todo',
    due TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL, ref TEXT NOT NULL, label TEXT NOT NULL,
    UNIQUE(kind, ref)
);
CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, params TEXT NOT NULL
);
"""

_VALID_TASK_STATUS = ("todo", "doing", "done")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class SavedConnection:
    """A named database connection (password kept in the credential vault)."""

    name: str
    kind: str  # sqlite | mssql | azure
    params: dict[str, Any]
    id: int | None = None


class AppDB:
    """Single-file application state store."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = str(path if path is not None else appdb_path())
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        logger.debug("app db ready at %s", self._path)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _exec(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock, self._conn:
            return self._conn.execute(sql, params).fetchall()

    # -- key/value settings -------------------------------------------------
    def set_value(self, key: str, value: Any) -> None:
        self._exec(
            "INSERT INTO kv(key, value) VALUES(?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )

    def get_value(self, key: str, default: Any = None) -> Any:
        rows = self._exec("SELECT value FROM kv WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    # -- query history / library --------------------------------------------
    def add_history(self, connection: str, sql: str, rows: int, duration_ms: float) -> None:
        self._exec(
            "INSERT INTO query_history(connection, sql, rows, duration_ms, ran_at)"
            " VALUES(?,?,?,?,?)",
            (connection, sql, rows, duration_ms, _now()),
        )

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._exec("SELECT * FROM query_history ORDER BY id DESC LIMIT ?", (max(1, limit),))
        return [dict(r) for r in rows]

    def save_query(self, name: str, sql: str) -> None:
        self._exec(
            "INSERT INTO saved_queries(name, sql, created_at) VALUES(?,?,?)"
            " ON CONFLICT(name) DO UPDATE SET sql=excluded.sql",
            (name, sql, _now()),
        )

    def saved_queries(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._exec("SELECT * FROM saved_queries ORDER BY name")]

    def delete_saved_query(self, name: str) -> None:
        self._exec("DELETE FROM saved_queries WHERE name=?", (name,))

    # -- notes ----------------------------------------------------------------
    def upsert_note(self, title: str, body: str, note_id: int | None = None) -> int:
        if note_id is None:
            self._exec(
                "INSERT INTO notes(title, body, updated_at) VALUES(?,?,?)",
                (title, body, _now()),
            )
            return int(self._exec("SELECT last_insert_rowid() AS i")[0]["i"])
        self._exec(
            "UPDATE notes SET title=?, body=?, updated_at=? WHERE id=?",
            (title, body, _now(), note_id),
        )
        return note_id

    def notes(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._exec("SELECT * FROM notes ORDER BY updated_at DESC")]

    def delete_note(self, note_id: int) -> None:
        self._exec("DELETE FROM notes WHERE id=?", (note_id,))

    # -- tasks ------------------------------------------------------------------
    def add_task(self, title: str, due: str | None = None) -> int:
        self._exec(
            "INSERT INTO tasks(title, status, due, created_at) VALUES(?,?,?,?)",
            (title, "todo", due, _now()),
        )
        return int(self._exec("SELECT last_insert_rowid() AS i")[0]["i"])

    def set_task_status(self, task_id: int, status: str) -> None:
        if status not in _VALID_TASK_STATUS:
            raise ValueError(f"status must be one of {_VALID_TASK_STATUS}")
        self._exec("UPDATE tasks SET status=? WHERE id=?", (status, task_id))

    def tasks(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._exec("SELECT * FROM tasks ORDER BY id DESC")]

    def delete_task(self, task_id: int) -> None:
        self._exec("DELETE FROM tasks WHERE id=?", (task_id,))

    # -- favorites -----------------------------------------------------------
    def add_favorite(self, kind: str, ref: str, label: str) -> None:
        self._exec(
            "INSERT OR IGNORE INTO favorites(kind, ref, label) VALUES(?,?,?)",
            (kind, ref, label),
        )

    def favorites(self, kind: str | None = None) -> list[dict[str, Any]]:
        if kind is None:
            return [dict(r) for r in self._exec("SELECT * FROM favorites ORDER BY id")]
        return [
            dict(r) for r in self._exec("SELECT * FROM favorites WHERE kind=? ORDER BY id", (kind,))
        ]

    def remove_favorite(self, kind: str, ref: str) -> None:
        self._exec("DELETE FROM favorites WHERE kind=? AND ref=?", (kind, ref))

    # -- automation job runs ---------------------------------------------------
    def job_started(self, job: str) -> int:
        self._exec(
            "INSERT INTO job_runs(job, status, started_at) VALUES(?,?,?)",
            (job, "running", _now()),
        )
        return int(self._exec("SELECT last_insert_rowid() AS i")[0]["i"])

    def job_finished(self, run_id: int, status: str, detail: str = "") -> None:
        self._exec(
            "UPDATE job_runs SET status=?, detail=?, finished_at=? WHERE id=?",
            (status, detail, _now(), run_id),
        )

    def job_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self._exec("SELECT * FROM job_runs ORDER BY id DESC LIMIT ?", (max(1, limit),))
        ]

    # -- saved connections ------------------------------------------------------
    def save_connection(self, conn: SavedConnection) -> None:
        self._exec(
            "INSERT INTO connections(name, kind, params) VALUES(?,?,?)"
            " ON CONFLICT(name) DO UPDATE SET kind=excluded.kind, params=excluded.params",
            (conn.name, conn.kind, json.dumps(conn.params)),
        )

    def connections(self) -> list[SavedConnection]:
        rows = self._exec("SELECT * FROM connections ORDER BY name")
        return [
            SavedConnection(
                id=int(r["id"]), name=r["name"], kind=r["kind"], params=json.loads(r["params"])
            )
            for r in rows
        ]

    def delete_connection(self, name: str) -> None:
        self._exec("DELETE FROM connections WHERE name=?", (name,))
