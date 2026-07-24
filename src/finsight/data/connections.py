"""Connection manager: named connections over SQLAlchemy.

Supports SQLite (bundled demo + any local file), Microsoft SQL Server,
and Azure SQL (both via ODBC). Passwords come from the credential vault
at connect time — they are never stored with the connection definition.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ..core import credentials
from ..core.appdb import AppDB, SavedConnection
from ..core.paths import demo_db_path

logger = logging.getLogger(__name__)

DEMO_CONNECTION = "Demo Lending DB"


class ConnectionError_(Exception):
    """Raised when a connection cannot be built or reached."""


@dataclass
class QueryResult:
    """Outcome of one SQL execution."""

    frame: pd.DataFrame
    rows: int
    duration_ms: float
    truncated: bool = False


def _sqlite_url(params: dict[str, Any]) -> str:
    return f"sqlite:///{params['path']}"


def _mssql_url(params: dict[str, Any], password: str | None) -> str:
    driver = params.get("driver", "ODBC Driver 17 for SQL Server")
    server = params["server"]
    database = params["database"]
    if params.get("trusted", False):
        odbc = (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            "Trusted_Connection=yes;TrustServerCertificate=yes"
        )
    else:
        user = params.get("username", "")
        odbc = (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            f"UID={user};PWD={password or ''};TrustServerCertificate=yes"
        )
    return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}"


class ConnectionManager:
    """Builds, caches, tests, and queries named SQLAlchemy engines."""

    def __init__(self, appdb: AppDB) -> None:
        self._appdb = appdb
        self._engines: dict[str, Engine] = {}
        # The demo connection always exists — beginner-friendly first run.
        self._appdb.save_connection(
            SavedConnection(
                name=DEMO_CONNECTION, kind="sqlite", params={"path": str(demo_db_path())}
            )
        )

    def list_connections(self) -> list[SavedConnection]:
        return self._appdb.connections()

    def save(self, conn: SavedConnection, password: str | None = None) -> None:
        """Persist a connection definition; password goes to the vault."""
        self._appdb.save_connection(conn)
        if password:
            credentials.set_secret(f"conn:{conn.name}", password)
        self._engines.pop(conn.name, None)

    def delete(self, name: str) -> None:
        if name == DEMO_CONNECTION:
            raise ConnectionError_("the demo connection cannot be deleted")
        self._appdb.delete_connection(name)
        credentials.delete_secret(f"conn:{name}")
        engine = self._engines.pop(name, None)
        if engine is not None:
            engine.dispose()

    def engine(self, name: str) -> Engine:
        if name in self._engines:
            return self._engines[name]
        definition = next((c for c in self.list_connections() if c.name == name), None)
        if definition is None:
            raise ConnectionError_(f"unknown connection: {name}")

        if definition.kind == "sqlite":
            url = _sqlite_url(definition.params)
        elif definition.kind in ("mssql", "azure"):
            password = credentials.get_secret(f"conn:{name}")
            url = _mssql_url(definition.params, password)
        else:
            raise ConnectionError_(f"unsupported connection kind: {definition.kind}")

        engine = create_engine(url, pool_pre_ping=True, future=True)
        self._engines[name] = engine
        return engine

    def dispose_all(self) -> None:
        """Close every cached engine (required on Windows before deleting
        SQLite files — open handles block deletion there)."""
        for engine in self._engines.values():
            engine.dispose()
        self._engines.clear()

    def test(self, name: str) -> tuple[bool, str]:
        """Cheap connectivity probe; returns (ok, message)."""
        try:
            with self.engine(name).connect() as conn:
                conn.execute(text("SELECT 1"))
            return True, "connection OK"
        except Exception as exc:
            return False, str(exc)

    def run_query(self, name: str, sql: str, max_rows: int = 50_000) -> QueryResult:
        """Execute SQL and return a (possibly truncated) DataFrame.

        ``max_rows`` protects a 16 GB laptop from an accidental
        ``SELECT * FROM ten_million_rows`` — the grid shows a truncation
        banner instead of the app dying.
        """
        statement = sql.strip().rstrip(";")
        if not statement:
            raise ConnectionError_("empty SQL statement")

        start = time.perf_counter()
        engine = self.engine(name)
        lowered = statement.lower()
        is_select = lowered.startswith(("select", "with", "pragma", "explain"))

        with engine.connect() as conn:
            if is_select:
                frame = pd.read_sql_query(text(statement), conn)
                truncated = len(frame) > max_rows
                if truncated:
                    frame = frame.head(max_rows)
                result = QueryResult(
                    frame=frame,
                    rows=int(len(frame)),
                    duration_ms=(time.perf_counter() - start) * 1000,
                    truncated=truncated,
                )
            else:
                outcome = conn.execute(text(statement))
                conn.commit()
                affected = int(outcome.rowcount if outcome.rowcount is not None else 0)
                result = QueryResult(
                    frame=pd.DataFrame({"rows_affected": [affected]}),
                    rows=affected,
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
        logger.info("query on %s: %d row(s) in %.0f ms", name, result.rows, result.duration_ms)
        return result

    def list_tables(self, name: str) -> list[str]:
        """Table + view names for the explorer tree."""
        from sqlalchemy import inspect

        inspector = inspect(self.engine(name))
        return sorted(inspector.get_table_names() + inspector.get_view_names())

    def table_columns(self, name: str, table: str) -> list[dict[str, Any]]:
        from sqlalchemy import inspect

        inspector = inspect(self.engine(name))
        return [{"name": c["name"], "type": str(c["type"])} for c in inspector.get_columns(table)]
