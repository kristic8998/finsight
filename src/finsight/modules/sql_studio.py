"""SQL Studio service: execution with history, library, and export.

The UI page is a thin shell over this: run queries (threaded by the
caller), record history, manage the saved-query library, browse schema,
and export results. Basic keyword sets are exposed for the editor's
syntax highlighter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..core.appdb import AppDB
from ..data.connections import ConnectionManager, QueryResult
from .excel_tools import sql_to_excel

logger = logging.getLogger(__name__)

SQL_KEYWORDS = (
    "select from where group by order having join left right inner outer on as and or not "
    "in like between is null insert into values update set delete create table view index "
    "drop alter distinct union all limit offset case when then else end with exists count "
    "sum avg min max cast coalesce substr date datetime"
).split()

STARTER_QUERIES: dict[str, str] = {
    "Portfolio by branch": (
        "SELECT b.name AS branch, COUNT(*) AS loans, ROUND(SUM(l.principal),0) AS principal\n"
        "FROM loans l JOIN branches b ON b.id = l.branch_id\n"
        "WHERE l.status != 'closed'\nGROUP BY b.name ORDER BY principal DESC"
    ),
    "Overdue installments": (
        "SELECT l.id AS loan, b.name AS branch, p.due_date,\n"
        "       ROUND(p.amount_due - p.amount_paid, 2) AS unpaid\n"
        "FROM payments p JOIN loans l ON l.id = p.loan_id\n"
        "JOIN branches b ON b.id = l.branch_id\n"
        "WHERE p.due_date < date('now') AND p.amount_paid < p.amount_due\n"
        "ORDER BY unpaid DESC LIMIT 100"
    ),
    "Collections this month": (
        "SELECT substr(p.paid_date,1,10) AS day, ROUND(SUM(p.amount_paid),0) AS collected\n"
        "FROM payments p\nWHERE substr(p.paid_date,1,7) = strftime('%Y-%m','now')\n"
        "GROUP BY day ORDER BY day"
    ),
    "NPA loans": (
        "SELECT l.id, b.name AS branch, l.customer_name, l.product, l.principal\n"
        "FROM loans l JOIN branches b ON b.id = l.branch_id\n"
        "WHERE l.status = 'npa' ORDER BY l.principal DESC"
    ),
}


@dataclass
class ExecutionRecord:
    sql: str
    connection: str
    result: QueryResult


class SqlStudioService:
    """Query execution + history + library + schema browsing."""

    def __init__(self, connections: ConnectionManager, appdb: AppDB) -> None:
        self._cm = connections
        self._appdb = appdb

    def execute(self, connection: str, sql: str, max_rows: int = 50_000) -> ExecutionRecord:
        result = self._cm.run_query(connection, sql, max_rows=max_rows)
        self._appdb.add_history(connection, sql.strip(), result.rows, result.duration_ms)
        return ExecutionRecord(sql=sql, connection=connection, result=result)

    def history(self, limit: int = 50) -> list[dict]:
        return self._appdb.history(limit)

    def library(self) -> dict[str, str]:
        saved = {row["name"]: row["sql"] for row in self._appdb.saved_queries()}
        # Starter queries appear until shadowed by a user save of the same name.
        return {**STARTER_QUERIES, **saved}

    def save_query(self, name: str, sql: str) -> None:
        if not name.strip() or not sql.strip():
            raise ValueError("both a name and SQL are required")
        self._appdb.save_query(name.strip(), sql.strip())

    def delete_query(self, name: str) -> None:
        self._appdb.delete_saved_query(name)

    def tables(self, connection: str) -> list[str]:
        return self._cm.list_tables(connection)

    def columns(self, connection: str, table: str) -> list[dict]:
        return self._cm.table_columns(connection, table)

    def export(self, record: ExecutionRecord, path: Path | str) -> Path:
        target = Path(path)
        if target.suffix.lower() == ".csv":
            target.parent.mkdir(parents=True, exist_ok=True)
            record.result.frame.to_csv(target, index=False)
            return target
        return sql_to_excel(record.result.frame, target)
